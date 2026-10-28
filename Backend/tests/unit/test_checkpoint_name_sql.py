"""A chave do checkpoint ignora caixa e espaço. O UPDATE grava o rótulo já salvo."""

from __future__ import annotations

from pathlib import Path

import pytest

from map.MapDatabaseManager import MapDatabaseManager

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _binary(sql: str) -> bool:
    return "CAST(" in sql and "AS BINARY" in sql


def _same(sql: str, stored: str, wanted: str) -> bool:
    if _binary(sql):
        return stored == wanted
    return stored.casefold() == wanted.casefold()


class CollationStore:
    """Sem CAST, a collation junta Sala e sala. Com CAST, só o texto exato."""

    def __init__(self) -> None:
        self.checkpoint = {
            "id": 1,
            "name": "Sala",
            "slug": "sala",
            "building_id": 1,
            "pos_x_px": 1.0,
            "pos_y_px": 2.0,
            "category_id": None,
        }
        self.edge = {
            "id": 10,
            "source_node": "Sala",
            "target_node": "Quarto",
            "distance_m": 3.0,
            "heading_rad": 0.1,
            "origin": "manual",
            "dup_rank": 0,
        }

    def execute_update(self, sql, params=None):
        _x, _y, name = params
        if not _same(sql, self.checkpoint["name"], name):
            return 0
        self.checkpoint["pos_x_px"] = _x
        self.checkpoint["pos_y_px"] = _y
        return 1

    def execute_query(self, sql, params=None):
        if sql.startswith("UPDATE checkpoints SET category_id"):
            category_id, name = params
            if not _same(sql, self.checkpoint["name"], name):
                return False
            self.checkpoint["category_id"] = category_id
            return True
        raise AssertionError(sql)

    def execute_search(self, sql, params=None):
        params = params or ()
        if "FROM checkpoints c" in sql and "CAST(" not in sql:
            return [{
                **self.checkpoint,
                "category_code": None,
                "category_label": None,
            }]
        if "CAST(c.name AS BINARY)" in sql:
            if _same(sql, self.checkpoint["name"], params[0]):
                return [dict(self.checkpoint)]
            return []
        if "CAST(name AS BINARY)" in sql and sql.startswith("SELECT name"):
            if _same(sql, self.checkpoint["name"], params[0]):
                return [{"name": self.checkpoint["name"]}]
            return []
        if "FROM edges" in sql and "CAST(source_node AS BINARY)" in sql:
            if _same(sql, self.edge["source_node"], params[0]) and _same(
                sql, self.edge["target_node"], params[1]
            ):
                return [dict(self.edge)]
            return []
        if "FROM checkpoint_categories" in sql:
            return []
        raise AssertionError(sql)


def test_checkpoint_lookup_folds_case_and_space_and_keeps_the_label():
    text = (BACKEND_ROOT / "map" / "MapDatabaseManager.py").read_text(encoding="utf-8")
    assert "WHERE name = %s" not in text
    assert "WHERE c.name = %s" not in text
    assert "WHERE source_node = %s" not in text
    assert "name IN (%s, %s)" not in text
    assert "checkpoint_name_key" in text

    store = CollationStore()
    manager = MapDatabaseManager(store)
    assert manager.get_checkpoint_by_name("Sála") is None
    assert manager.update_checkpoint_position("Sála", 3.0, 3.0) is False
    assert store.checkpoint["pos_x_px"] == 1.0

    found = manager.get_checkpoint_by_name(" sala ")
    assert found["name"] == "Sala"
    assert manager.update_checkpoint_position("SALA", 9.0, 8.0) is True
    assert store.checkpoint["name"] == "Sala"
    assert store.checkpoint["pos_x_px"] == 9.0
    assert store.checkpoint["pos_y_px"] == 8.0
    cleared = manager.update_checkpoint_category("sala", None)
    assert cleared["name"] == "Sala"
    assert manager._edge_row("sala", "Quarto") is None
    assert manager._edge_row(found["name"], "Quarto")["id"] == 10
