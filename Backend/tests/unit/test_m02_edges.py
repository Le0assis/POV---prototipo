"""Dedupe, upsert em memória e migração 002. Sem MySQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from map.edge_rules import median, resolve_recorded_edge, split_duplicate_edges
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

    module.apply(db)
    creates = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    deletes = [sql for sql, _params in db.statements if sql.startswith("DELETE FROM edges")]
    assert len(creates) == 1
    assert len(deletes) == 1
    assert [row["id"] for row in db.edges] == [3, 4]
