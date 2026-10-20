"""Dedupe, upsert em memória e migração 002. Sem MySQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from map.edge_rules import group_edge_pairs, median, resolve_recorded_edge, split_duplicate_edges
from map.topological_map import TopologicalMap

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def _migration():
    path = BACKEND_ROOT / "datasets" / "migrations" / "002_walk_traces.py"
    spec = importlib.util.spec_from_file_location("migration_002_walk_traces", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUARTO_SALA = [
    {"id": 1, "source_node": "Quarto", "target_node": "Sala", "distance_m": 3.0, "heading_rad": 0.0},
    {"id": 2, "source_node": "Sala", "target_node": "Quarto", "distance_m": 3.0, "heading_rad": 3.1416},
    {"id": 3, "source_node": "Quarto", "target_node": "Sala", "distance_m": 2.61527, "heading_rad": 0.2},
    {"id": 4, "source_node": "Sala", "target_node": "Quarto", "distance_m": 2.61527, "heading_rad": 0.3},
]


def test_quarto_sala_keeps_latest_id_per_direction():
    kept, removed = split_duplicate_edges(QUARTO_SALA)
    assert [row["id"] for row in removed] == [1, 2]
    assert sorted(row["id"] for row in kept) == [3, 4]
    assert removed[0]["distance_m"] == 3.0
    sala = next(row for row in kept if row["source_node"] == "Quarto")
    assert sala["distance_m"] == 2.61527


def test_split_is_idempotent_when_already_unique():
    kept, removed = split_duplicate_edges(QUARTO_SALA)
    again_kept, again_removed = split_duplicate_edges(kept)
    assert again_removed == []
    assert {row["id"] for row in again_kept} == {row["id"] for row in kept}


def test_manual_distance_wins_over_trace_median():
    resolved = resolve_recorded_edge(
        {"origin": "manual", "distance_m": 3.0, "heading_rad": 1.0},
        [
            {"id": 1, "total_distance_m": 2.0, "net_heading_rad": 0.0, "started_at": 1, "is_valid": True},
            {"id": 2, "total_distance_m": 4.0, "net_heading_rad": 0.4, "started_at": 2, "is_valid": True},
        ],
    )
    assert resolved["distance_m"] == 3.0
    assert resolved["heading_rad"] == 1.0
    assert resolved["origin"] == "manual"
    assert resolved["active_trace_id"] == 2


def test_recorded_distance_is_median_and_active_is_latest():
    resolved = resolve_recorded_edge(
        None,
        [
            {"id": 5, "total_distance_m": 9.0, "net_heading_rad": 0.0, "started_at": 1, "is_valid": True},
            {"id": 4, "total_distance_m": 1.0, "net_heading_rad": 0.0, "started_at": 3, "is_valid": True},
            {"id": 9, "total_distance_m": 100.0, "net_heading_rad": 0.0, "started_at": 2, "is_valid": False},
        ],
    )
    assert resolved["origin"] == "recorded"
    assert resolved["distance_m"] == median([9.0, 1.0])
    assert resolved["active_trace_id"] == 4


def test_load_does_not_mirror_duplicate_rows():
    topo = TopologicalMap()
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint("Sala")
    topo.load_directed_edges(QUARTO_SALA)
    assert len(topo.edges) == 2
    forward = [edge for edge in topo.edges if edge.source == "Quarto" and edge.target == "Sala"]
    backward = [edge for edge in topo.edges if edge.source == "Sala" and edge.target == "Quarto"]
    assert len(forward) == 1 and forward[0].distance_m == 2.61527
    assert len(backward) == 1 and backward[0].distance_m == 2.61527


def test_connect_checkpoints_upserts_instead_of_appending():
    topo = TopologicalMap()
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint("Sala")
    topo.connect_checkpoints("Quarto", "Sala", distance=3.0, angle_deg=0)
    topo.connect_checkpoints("Quarto", "Sala", distance=2.5, angle_deg=10)
    assert len(topo.edges) == 2
    forward = next(edge for edge in topo.edges if edge.source == "Quarto")
    assert forward.distance_m == 2.5


def test_loader_source_does_not_call_connect_checkpoints():
    text = (BACKEND_ROOT / "map" / "MapDatabaseManager.py").read_text(encoding="utf-8")
    assert "load_directed_edges" in text
    assert "connect_checkpoints" not in text
    assert "ON DUPLICATE KEY UPDATE" in text
    assert "IF(origin = 'manual'" in text


def test_checkpoints_name_ddl_is_varchar_100():
    text = (BACKEND_ROOT / "datasets" / "create_tables.py").read_text(encoding="utf-8")
    assert "name VARCHAR(100) NOT NULL UNIQUE" in text
    assert "samples_count INT NOT NULL DEFAULT 0" in text
    module = _migration()
    fragment = module.node_column_sql({
        "COLUMN_TYPE": "varchar(100)",
        "CHARACTER_SET_NAME": "utf8mb4",
        "COLLATION_NAME": "utf8mb4_general_ci",
    })
    assert fragment.startswith("varchar(100)")
    with pytest.raises(RuntimeError):
        module.node_column_sql({
            "COLUMN_TYPE": "int",
            "CHARACTER_SET_NAME": "utf8mb4",
            "COLLATION_NAME": "utf8mb4_general_ci",
        })


class _MigrationDB:
    def __init__(self) -> None:
        self.edges = [dict(row) for row in QUARTO_SALA]
        self.tables = {"edges", "checkpoints", "sensors_log", "saved_routes"}
        self.columns: set[tuple[str, str]] = {("checkpoints", "name")}
        self.backup: list[dict] | None = None
        self.statements: list[tuple[str, object]] = []
        self.unique = False
        self.fk = False
        self.map_row = False
        self.fail_exact: set[str] = set()
        self.fail_parts: tuple[str, ...] = ()
        self.hide_backup = False

    def execute_search(self, sql, params=None):
        module = _migration()
        if sql == module.SQL_TABLE_EXISTS:
            return [{"ok": 1}] if params[0] in self.tables else []
        if sql == module.SQL_COLUMN_EXISTS:
            return [{"ok": 1}] if (params[0], params[1]) in self.columns else []
        if sql == module.SQL_COLUMN_META:
            return [{
                "COLUMN_TYPE": "varchar(100)",
                "CHARACTER_SET_NAME": "utf8mb4",
                "COLLATION_NAME": "utf8mb4_general_ci",
            }]
        if sql == module.SQL_UNIQUE_EXISTS:
            return [{"ok": 1}] if self.unique else []
        if sql == module.SQL_FK_EXISTS:
            return [{"ok": 1}] if self.fk else []
        if sql == module.SQL_SELECT_EDGES:
            return [dict(row) for row in self.edges]
        if sql == module.SQL_MAP_EXISTS_ROW:
            return [{"id": 1}] if self.map_row else []
        return []

    def execute_query(self, sql, params=None):
        self.statements.append((sql, params))
        module = _migration()
        if sql in self.fail_exact or any(part in sql for part in self.fail_parts):
            return False
        if sql == module.SQL_BACKUP and self.hide_backup:
            return True
        if sql == module.SQL_BACKUP:
            self.backup = [dict(row) for row in self.edges]
            self.tables.add("edges_backup_m02")
        if sql.startswith("DELETE FROM edges"):
            dropped = set(params)
            self.edges = [row for row in self.edges if row["id"] not in dropped]
        if "ADD COLUMN" in sql:
            if "pos_x_px" in sql:
                self.columns.add(("checkpoints", "pos_x_px"))
            if "pos_y_px" in sql:
                self.columns.add(("checkpoints", "pos_y_px"))
            if "origin ENUM" in sql:
                self.columns.add(("edges", "origin"))
            if "updated_at" in sql:
                self.columns.add(("edges", "updated_at"))
            if "active_trace_id" in sql:
                self.columns.add(("edges", "active_trace_id"))
            if "samples_count" in sql:
                self.columns.add(("edges", "samples_count"))
        if "uq_edges_direction" in sql:
            self.unique = True
        if "walk_traces" in sql and "CREATE TABLE" in sql:
            self.tables.add("walk_traces")
        if "walk_steps" in sql and "CREATE TABLE" in sql:
            self.tables.add("walk_steps")
        if "fk_edges_active_trace" in sql:
            self.fk = True
        if "CREATE TABLE" in sql and "map_config" in sql:
            self.tables.add("map_config")
        if sql == module.SQL_MAP_INSERT:
            self.map_row = True
        return True


def test_migration_backs_up_then_dedupes_and_is_idempotent():
    module = _migration()
    db = _MigrationDB()
    removed = module.apply(db)
    assert [row["id"] for row in removed] == [1, 2]
    assert db.backup is not None and [row["id"] for row in db.backup] == [1, 2, 3, 4]
    assert [row["id"] for row in db.edges] == [3, 4]
    creates = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    deletes = [sql for sql, _params in db.statements if sql.startswith("DELETE FROM edges")]
    assert len(creates) == 1 and len(deletes) == 1
    walk_sql = next(sql for sql, _params in db.statements if "CREATE TABLE IF NOT EXISTS walk_traces" in sql)
    assert "varchar(100)" in walk_sql
    assert "sensors_log_id) REFERENCES sensors_log(id) ON DELETE CASCADE" in walk_sql

    classify = [sql for sql, _params in db.statements if sql == module.SQL_CLASSIFY_RECORDED]
    assert classify == [module.SQL_CLASSIFY_RECORDED]
    assert "is_valid" not in module.SQL_CLASSIFY_RECORDED
    assert "s.source = e.source_node AND s.target = e.target_node" in module.SQL_CLASSIFY_RECORDED
    assert any(sql == module.SQL_BACKFILL_SAMPLES for sql, _params in db.statements)
    assert ("edges", "samples_count") in db.columns

    module.apply(db)
    creates = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    deletes = [sql for sql, _params in db.statements if sql.startswith("DELETE FROM edges")]
    classify = [sql for sql, _params in db.statements if sql == module.SQL_CLASSIFY_RECORDED]
    assert len(creates) == 1
    assert len(deletes) == 1
    assert classify == [module.SQL_CLASSIFY_RECORDED]
    assert [row["id"] for row in db.edges] == [3, 4]


def test_migration_aborts_when_backup_fails_and_does_not_dedupe():
    module = _migration()
    db = _MigrationDB()
    db.fail_exact.add(module.SQL_BACKUP)
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql.startswith("DELETE FROM edges") for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
    assert "edges_backup_m02" not in db.tables


def test_migration_aborts_when_backup_is_not_confirmed():
    module = _migration()
    db = _MigrationDB()
    db.hide_backup = True
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql.startswith("DELETE FROM edges") for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]


def test_migration_aborts_when_column_add_fails_before_dedupe():
    module = _migration()
    db = _MigrationDB()
    db.fail_parts = ("origin ENUM",)
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql.startswith("DELETE FROM edges") for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
    assert "edges_backup_m02" in db.tables


def test_existing_backup_is_enough_to_dedupe():
    module = _migration()
    db = _MigrationDB()
    db.tables.add("edges_backup_m02")
    removed = module.apply(db)
    assert [row["id"] for row in removed] == [1, 2]
    assert module.SQL_BACKUP not in [sql for sql, _params in db.statements]


def test_connections_group_keeps_smaller_id_and_reverse():
    rows = [
        {"id": 42, "source_node": "Quarto", "target_node": "Sala"},
        {"id": 43, "source_node": "Sala", "target_node": "Quarto"},
        {"id": 7, "source_node": "Recepcao", "target_node": "Corredor"},
        {"id": 8, "source_node": "Corredor", "target_node": "Recepcao"},
    ]
    grouped = group_edge_pairs(rows)
    assert [(primary["id"], None if reverse is None else reverse["id"]) for primary, reverse in grouped] == [
        (7, 8),
        (42, 43),
    ]
    collapsed = group_edge_pairs(QUARTO_SALA)
    assert len(collapsed) == 1
    assert collapsed[0][0]["id"] == 1
    assert collapsed[0][1]["id"] == 2


def test_connections_group_prefers_the_direction_with_active_trace():
    rows = [
        {"id": 10, "source_node": "Quarto", "target_node": "Sala", "active_trace_id": None},
        {"id": 11, "source_node": "Sala", "target_node": "Quarto", "active_trace_id": 99},
    ]
    primary, reverse = group_edge_pairs(rows)[0]
    assert primary["id"] == 11
    assert reverse["id"] == 10

    both = [
        {"id": 10, "source_node": "Quarto", "target_node": "Sala", "active_trace_id": 1},
        {"id": 11, "source_node": "Sala", "target_node": "Quarto", "active_trace_id": 2},
    ]
    primary, reverse = group_edge_pairs(both)[0]
    assert primary["id"] == 10
    assert reverse["id"] == 11
