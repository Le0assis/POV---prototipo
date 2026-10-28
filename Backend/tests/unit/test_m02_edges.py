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


def test_edge_matches_checkpoint_ignoring_case_and_space():
    """``quarto``, `` quarto `` e ``QUARTO`` são o mesmo nó. O rótulo fica o primeiro."""
    topo = TopologicalMap()
    topo.add_checkpoint("Sala")
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint(" sala ")
    topo.add_checkpoint("QUARTO")
    assert list(topo.nodes) == ["Sala", "Quarto"]
    assert topo.canonical_name("Sala") == "Sala"
    assert topo.canonical_name("  sala ") == "Sala"
    assert topo.canonical_name("QUARTO") == "Quarto"
    topo.load_directed_edges([
        {"id": 1, "source_node": "Sala", "target_node": "Quarto", "distance_m": 3.0, "heading_rad": 0.1},
        {"id": 2, "source_node": "sala", "target_node": "quarto", "distance_m": 9.0, "heading_rad": 0.4},
    ])
    assert [(edge.source, edge.target, edge.distance_m) for edge in topo.edges] == [
        ("Sala", "Quarto", 9.0),
    ]
    assert topo.get_outgoing_edges("sala")[0].target == "Quarto"
    from map.router import TopologicalRouter
    router = TopologicalRouter(topo)
    assert router.calculate_route("Sala", "Quarto") == ["Sala", "Quarto"]
    assert router.calculate_route(" sala ", "QUARTO") == ["Sala", "Quarto"]


def test_accents_stay_distinct_from_case():
    topo = TopologicalMap()
    topo.add_checkpoint("Recepção")
    topo.add_checkpoint("Recepcao")
    assert set(topo.nodes) == {"Recepção", "Recepcao"}
    topo.upsert_directed_edge("Recepcao", "Recepção", 1.0, 0.0)
    topo.upsert_directed_edge("recepcao", "Recepção", 2.0, 0.0)
    assert [(edge.source, edge.target, edge.distance_m) for edge in topo.edges] == [
        ("Recepcao", "Recepção", 2.0),
    ]
    assert topo.canonical_name("recepção") == "Recepção"
    assert topo.canonical_name("recepcao") == "Recepcao"
    assert topo.canonical_name("Recepção") != topo.canonical_name("Recepcao")


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
        self.ranked_unique = False
        self.checkpoint_names = {"Quarto", "Sala"}
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
        if sql == module.SQL_EXTRAS:
            return [
                {
                    "id": row["id"],
                    "source_node": row["source_node"],
                    "target_node": row["target_node"],
                    "dup_rank": int(row.get("dup_rank") or 0),
                }
                for row in sorted(self.edges, key=lambda item: int(item["id"]))
                if int(row.get("dup_rank") or 0) > 0
            ]
        if sql == module.SQL_ENGINE:
            if "sensors_log" not in self.tables:
                return []
            return [{"engine": "InnoDB"}]
        if sql == module.SQL_UNIQUE_HAS_RANK:
            return [{"ok": 1}] if self.ranked_unique else []
        if sql == module.SQL_DUP_GROUPS:
            grouped: dict[tuple, list] = {}
            for row in self.edges:
                key = (str(row["source_node"]).casefold(), str(row["target_node"]).casefold())
                grouped.setdefault(key, []).append(row)
            found = []
            for group in grouped.values():
                if len(group) < 2:
                    continue
                group_id = min(int(item["id"]) for item in group)
                for item in group:
                    exact = (
                        item["source_node"] in self.checkpoint_names
                        and item["target_node"] in self.checkpoint_names
                    )
                    found.append({
                        "id": item["id"],
                        "source_node": item["source_node"],
                        "target_node": item["target_node"],
                        "dup_rank": int(item.get("dup_rank") or 0),
                        "group_id": group_id,
                        "exact_name": 1 if exact else 0,
                    })
            found.sort(key=lambda item: (item["group_id"], item["id"]))
            return found
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
        if sql == module.SQL_SET_RANK:
            rank, edge_id = params
            for row in self.edges:
                if row["id"] == edge_id:
                    row["dup_rank"] = rank
            return True
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
            if "dup_rank" in sql:
                self.columns.add(("edges", "dup_rank"))
                for row in self.edges:
                    row.setdefault("dup_rank", 0)
        if sql == module.SQL_UNIQUE_RANKED:
            self.unique = True
            self.ranked_unique = True
        elif "uq_edges_direction" in sql:
            self.unique = True
            self.ranked_unique = False
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


def test_migration_backs_up_then_keeps_duplicates_and_is_idempotent():
    module = _migration()
    db = _MigrationDB()
    preserved = module.apply(db)
    assert [row["id"] for row in preserved] == [1, 2]
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
    assert db.backup is not None and [row["id"] for row in db.backup] == [1, 2, 3, 4]
    by_id = {row["id"]: int(row.get("dup_rank") or 0) for row in db.edges}
    assert by_id == {1: 1, 2: 1, 3: 0, 4: 0}
    creates = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    deletes = [sql for sql, _params in db.statements if sql.startswith("DELETE FROM")]
    assert len(creates) == 1 and deletes == []
    assert module.SQL_UNIQUE_RANKED in [sql for sql, _params in db.statements]
    walk_sql = next(sql for sql, _params in db.statements if "CREATE TABLE IF NOT EXISTS walk_traces" in sql)
    assert "varchar(100)" in walk_sql
    assert "sensors_log_id) REFERENCES sensors_log(id) ON DELETE CASCADE" in walk_sql

    classify = [sql for sql, _params in db.statements if sql == module.SQL_CLASSIFY_RECORDED]
    assert classify == [module.SQL_CLASSIFY_RECORDED]
    assert "is_valid" not in module.SQL_CLASSIFY_RECORDED
    assert "s.source = e.source_node AND s.target = e.target_node" in module.SQL_CLASSIFY_RECORDED
    assert any(sql == module.SQL_BACKFILL_SAMPLES for sql, _params in db.statements)
    assert ("edges", "samples_count") in db.columns

    again = module.apply(db)
    assert [row["id"] for row in again] == [1, 2]
    creates = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    ranks = [sql for sql, _params in db.statements if sql == module.SQL_SET_RANK]
    classify = [sql for sql, _params in db.statements if sql == module.SQL_CLASSIFY_RECORDED]
    assert len(creates) == 1
    assert len(ranks) == 2
    assert classify == [module.SQL_CLASSIFY_RECORDED]
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]


def test_migration_aborts_when_backup_fails_and_does_not_dedupe():
    module = _migration()
    db = _MigrationDB()
    db.fail_exact.add(module.SQL_BACKUP)
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql == module.SQL_SET_RANK for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
    assert "edges_backup_m02" not in db.tables


def test_migration_aborts_when_backup_is_not_confirmed():
    module = _migration()
    db = _MigrationDB()
    db.hide_backup = True
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql == module.SQL_SET_RANK for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]


def test_migration_aborts_when_column_add_fails_before_dedupe():
    module = _migration()
    db = _MigrationDB()
    db.fail_parts = ("origin ENUM",)
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert not any(sql == module.SQL_SET_RANK for sql, _params in db.statements)
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
    assert "edges_backup_m02" in db.tables


def test_canonical_edge_matches_checkpoint_name_not_the_larger_id():
    module = _migration()
    assert "CAST(src.name AS BINARY) = CAST(e.source_node AS BINARY)" in module.SQL_DUP_GROUPS
    assert "CAST(tgt.name AS BINARY) = CAST(e.target_node AS BINARY)" in module.SQL_DUP_GROUPS
    assert "EXISTS" not in module.SQL_DUP_GROUPS
    db = _MigrationDB()
    db.edges = [
        {"id": 1, "source_node": "Quarto", "target_node": "Sala", "distance_m": 3.0, "heading_rad": 0.0},
        {"id": 2, "source_node": "Quarto", "target_node": "sala", "distance_m": 9.0, "heading_rad": 0.2},
    ]
    db.checkpoint_names = {"Quarto", "Sala"}
    preserved = module.apply(db)
    by_id = {row["id"]: int(row["dup_rank"]) for row in db.edges}
    assert by_id == {1: 0, 2: 1}
    assert [row["id"] for row in preserved] == [2]
    assert [row["id"] for row in db.edges] == [1, 2]
    assert not any(sql.startswith("DELETE FROM") for sql, _params in db.statements)


def test_rerank_is_idempotent_when_the_old_canonical_was_the_lowercase_copy():
    module = _migration()
    db = _MigrationDB()
    db.tables.add("edges_backup_m02")
    db.columns.add(("edges", "dup_rank"))
    db.unique = True
    db.ranked_unique = True
    db.edges = [
        {
            "id": 1,
            "source_node": "Quarto",
            "target_node": "Sala",
            "distance_m": 3.0,
            "heading_rad": 0.0,
            "dup_rank": 1,
        },
        {
            "id": 2,
            "source_node": "Quarto",
            "target_node": "sala",
            "distance_m": 9.0,
            "heading_rad": 0.2,
            "dup_rank": 0,
        },
    ]
    module.apply(db)
    by_id = {row["id"]: int(row["dup_rank"]) for row in db.edges}
    assert by_id == {1: 0, 2: 1}
    parked = [params for sql, params in db.statements if sql == module.SQL_SET_RANK and params[0] < 0]
    assert {params[1] for params in parked} == {1, 2}
    again = module.apply(db)
    assert [row["id"] for row in again] == [2]
    assert {row["id"]: int(row["dup_rank"]) for row in db.edges} == {1: 0, 2: 1}
    assert len([sql for sql, _params in db.statements if sql == module.SQL_SET_RANK]) == 4


def test_without_an_exact_name_the_highest_id_stays_and_a_warning_is_printed(capsys):
    module = _migration()
    db = _MigrationDB()
    db.edges = [
        {"id": 4, "source_node": "Quarto", "target_node": "sala", "distance_m": 1.0, "heading_rad": 0.0},
        {"id": 5, "source_node": "quarto", "target_node": "Sala", "distance_m": 2.0, "heading_rad": 0.0},
    ]
    db.checkpoint_names = {"Quarto", "Sala"}
    module.apply(db)
    by_id = {row["id"]: int(row["dup_rank"]) for row in db.edges}
    assert by_id[5] == 0
    assert by_id[4] != 0
    assert "aviso" in capsys.readouterr().out
    assert [row["id"] for row in db.edges] == [4, 5]


def test_existing_backup_is_enough_to_rank_duplicates():
    module = _migration()
    db = _MigrationDB()
    db.tables.add("edges_backup_m02")
    preserved = module.apply(db)
    assert [row["id"] for row in preserved] == [1, 2]
    assert [row["id"] for row in db.edges] == [1, 2, 3, 4]
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
