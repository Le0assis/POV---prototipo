"""Migração 004: índices do salvamento, sem duplicar o que o InnoDB já criou."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _migration():
    path = BACKEND_ROOT / "datasets" / "migrations" / "004_save_indexes.py"
    spec = importlib.util.spec_from_file_location("migration_004_save_indexes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MigrationDB:
    def __init__(self) -> None:
        self.tables = {"edges", "walk_traces", "saved_routes", "checkpoints"}
        self.named: set[tuple[str, str]] = set()
        self.leftmost: set[tuple[str, str]] = {("edges", "target_node")}
        self.statements: list[str] = []

    def execute_search(self, sql, params=None):
        module = _migration()
        params = params or ()
        if sql == module.SQL_TABLE_EXISTS:
            return [{"ok": 1}] if params[0] in self.tables else []
        if sql == module.SQL_INDEX_NAME:
            return [{"ok": 1}] if (params[0], params[1]) in self.named else []
        if sql == module.SQL_LEFTMOST:
            return [{"ok": 1}] if (params[0], params[1]) in self.leftmost else []
        raise AssertionError(sql)

    def execute_query(self, sql, params=None):
        self.statements.append(sql)
        if sql.startswith("ALTER TABLE"):
            parts = sql.split()
            table = parts[2]
            index_name = parts[5]
            self.named.add((table, index_name))
            first = sql.split("(", 1)[1].split(",", 1)[0].strip(" )")
            self.leftmost.add((table, first))
        return True


def test_migration_adds_aggregate_indexes_and_skips_existing_fk_index():
    module = _migration()
    db = _MigrationDB()
    module.apply(db)
    alters = [sql for sql in db.statements if sql.startswith("ALTER TABLE")]
    assert not any("idx_edges_target_node" in sql for sql in alters)
    assert any("idx_trace_median" in sql and "is_valid, total_distance_m" in sql for sql in alters)
    assert any("idx_trace_latest" in sql and "started_at, id" in sql for sql in alters)
    assert any("idx_edges_active_trace" in sql for sql in alters)
    assert any("idx_walk_traces_sensors_log" in sql for sql in alters)
    assert any("idx_saved_routes_start_node" in sql for sql in alters)

    again = list(db.statements)
    module.apply(db)
    assert db.statements == again


def test_saved_routes_can_be_missing():
    module = _migration()
    db = _MigrationDB()
    db.tables.discard("saved_routes")
    module.apply(db)
    assert not any("saved_routes" in sql for sql in db.statements)


def test_create_tables_runs_migration_004():
    text = (BACKEND_ROOT / "datasets" / "create_tables.py").read_text(encoding="utf-8")
    assert "aplicar_migracao_004" in text
    assert "004_save_indexes.py" in text
