"""Slug do checkpoint: acento, colisão e rename. Sem MySQL."""

from __future__ import annotations

import pytest

from mysql.connector import IntegrityError

from map.MapDatabaseManager import (
    CheckpointConflictError,
    CheckpointLookupError,
    MapDatabaseManager,
    UnknownCategoryError,
)
from map.checkpoint_slug import allocate_slug, slugify

pytestmark = pytest.mark.unit


class _Store:
    def __init__(self) -> None:
        self.checkpoints: list[dict] = []
        self.categories = [
            {"id": 1, "code": "atendimento", "label": "Atendimento", "sort_order": 1},
            {"id": 4, "code": "saidas", "label": "Saídas", "sort_order": 4},
            {"id": 2, "code": "banheiros", "label": "Banheiros", "sort_order": 2},
            {"id": 3, "code": "alimentacao", "label": "Alimentação", "sort_order": 3},
        ]
        self.statements: list[tuple] = []
        self._next_id = 1

    def execute_search(self, sql, params=None):
        params = params or ()
        self.statements.append((sql, params))
        if "FROM checkpoint_categories" in sql and "WHERE code = %s" in sql:
            return [dict(row) for row in self.categories if row["code"] == params[0]]
        if "FROM checkpoint_categories" in sql:
            rows = sorted(self.categories, key=lambda row: (row["sort_order"], row["code"]))
            return [dict(row) for row in rows]
        if "SELECT slug FROM checkpoints WHERE building_id" in sql:
            building_id = params[0]
            return [
                {"slug": row["slug"]}
                for row in self.checkpoints
                if row["building_id"] == building_id and row["slug"]
            ]
        if "SELECT slug FROM checkpoints WHERE" in sql and "CAST(name AS BINARY)" in sql:
            return [{"slug": row["slug"]} for row in self.checkpoints if row["name"] == params[0]]
        if "SELECT name FROM checkpoints WHERE" in sql and "CAST(name AS BINARY)" in sql:
            return [{"name": row["name"]} for row in self.checkpoints if row["name"] == params[0]]
        if "WHERE c.building_id = %s AND c.slug = %s" in sql:
            building_id, slug = params
            return [
                self._joined(row)
                for row in self.checkpoints
                if row["building_id"] == building_id and row["slug"] == slug
            ]
        if "CAST(c.name AS BINARY)" in sql:
            return [self._joined(row) for row in self.checkpoints if row["name"] == params[0]]
        if "FROM checkpoints c" in sql:
            return [self._joined(row) for row in self.checkpoints]
        raise AssertionError(sql)

    def execute_query(self, sql, params=None):
        params = params or ()
        self.statements.append((sql, params))
        if sql.startswith("INSERT INTO checkpoints"):
            name, building_id, slug, category_id = params
            if any(row["name"] == name for row in self.checkpoints):
                return False
            self.checkpoints.append({
                "id": self._next_id,
                "name": name,
                "building_id": building_id,
                "slug": slug,
                "category_id": category_id,
                "pos_x_px": None,
                "pos_y_px": None,
            })
            self._next_id += 1
            return True
        if sql.startswith("UPDATE checkpoints SET name"):
            new_name, old_name = params
            for row in self.checkpoints:
                if row["name"] == old_name:
                    row["name"] = new_name
                    return True
            return False
        if sql.startswith("UPDATE checkpoints SET category_id"):
            category_id, name = params
            for row in self.checkpoints:
                if row["name"] == name:
                    row["category_id"] = category_id
                    return True
            return False
        raise AssertionError(sql)

    def _joined(self, row: dict) -> dict:
        category = next(
            (item for item in self.categories if item["id"] == row.get("category_id")),
            None,
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "building_id": row["building_id"],
            "pos_x_px": row.get("pos_x_px"),
            "pos_y_px": row.get("pos_y_px"),
            "category_code": None if category is None else category["code"],
            "category_label": None if category is None else category["label"],
        }


def test_slugify_strips_accents_and_collapses_hyphens():
    assert slugify("Recepção") == "recepcao"
    assert slugify("AÇÃO") == "acao"
    assert slugify("São João") == "sao-joao"
    assert slugify("ÁÉÍÓÚÃÕÂÊÔÇ") == "aeiouaoaeoc"
    assert slugify("  Corredor   Central ") == "corredor-central"
    assert slugify("Sala/TI") == "sala-ti"
    assert slugify("!!!") == "checkpoint"
    assert slugify("a" * 80) == "a" * 64
    assert len(slugify("a" * 80)) == 64


def test_collision_appends_2_then_3_inside_64_chars():
    taken: set[str] = set()
    first = allocate_slug("Recepção", taken)
    taken.add(first)
    second = allocate_slug("Recepcao", taken)
    taken.add(second)
    third = allocate_slug("Recepção!!", taken)
    assert first == "recepcao"
    assert second == "recepcao-2"
    assert third == "recepcao-3"

    long_taken = {"a" * 64}
    suffixed = allocate_slug("a" * 90, long_taken)
    assert suffixed == ("a" * 62) + "-2"
    assert len(suffixed) == 64

    other_building = allocate_slug("Recepção", set())
    assert other_building == "recepcao"


def test_save_assigns_slug_once_and_rename_keeps_it():
    store = _Store()
    manager = MapDatabaseManager(store)
    created = manager.save_checkpoint("Recepção")
    assert created["slug"] == "recepcao"
    assert created["building_id"] == 1
    assert created["category"] is None

    collided = manager.save_checkpoint("Recepcao", "atendimento")
    assert collided["slug"] == "recepcao-2"
    assert collided["category"] == {"code": "atendimento", "label": "Atendimento"}

    assert manager.update_checkpoint_name("Recepção", "Hall de Entrada") is True
    renamed = manager.get_checkpoint_by_name("Hall de Entrada")
    assert renamed["slug"] == "recepcao"
    assert renamed["name"] == "Hall de Entrada"
    updates = [sql for sql, _params in store.statements if sql.startswith("UPDATE checkpoints SET name")]
    assert updates
    assert all("slug" not in sql.lower() for sql in updates)

    fresh = manager.save_checkpoint("Recepção")
    assert fresh["slug"] == "recepcao-3"


def test_invalid_category_is_rejected_before_insert():
    store = _Store()
    manager = MapDatabaseManager(store)
    with pytest.raises(UnknownCategoryError) as exc:
        manager.save_checkpoint("Sala", "inexistente")
    assert exc.value.code == "inexistente"
    assert store.checkpoints == []


def test_null_category_clears_and_categories_come_sorted():
    store = _Store()
    manager = MapDatabaseManager(store)
    manager.save_checkpoint("Sala", "saidas")
    cleared = manager.update_checkpoint_category("Sala", None)
    assert cleared["category"] is None
    assert cleared["slug"] == "sala"
    listed = manager.list_categories()
    assert [row["code"] for row in listed] == [
        "atendimento",
        "banheiros",
        "alimentacao",
        "saidas",
    ]


class _SlugRace(_Store):
    """O slug escolhido só aparece depois que o INSERT perde a corrida."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.inserts = 0
        self._hide_slugs = True

    def execute_search(self, sql, params=None):
        if "SELECT slug FROM checkpoints WHERE building_id" in sql and self._hide_slugs:
            self.statements.append((sql, params or ()))
            return []
        return super().execute_search(sql, params)

    def execute_query(self, sql, params=None):
        if sql.startswith("INSERT INTO checkpoints"):
            self.inserts += 1
            if self.inserts <= self.failures:
                self.statements.append((sql, params or ()))
                self._hide_slugs = False
                slug = params[2]
                if not any(row["slug"] == slug for row in self.checkpoints):
                    self.checkpoints.append({
                        "id": self._next_id,
                        "name": f"concorrente-{self.inserts}",
                        "building_id": params[1],
                        "slug": slug,
                        "category_id": None,
                        "pos_x_px": None,
                        "pos_y_px": None,
                    })
                    self._next_id += 1
                raise IntegrityError(
                    "Duplicate entry for key 'uq_checkpoints_building_slug'"
                )
        return super().execute_query(sql, params)


def test_slug_collision_retries_once_with_the_next_suffix():
    store = _SlugRace(failures=1)
    created = MapDatabaseManager(store).save_checkpoint("Sala")
    assert store.inserts == 2
    assert created["slug"] == "sala-2"
    assert created["name"] == "Sala"


def test_second_slug_collision_is_a_conflict():
    store = _SlugRace(failures=2)
    with pytest.raises(CheckpointConflictError) as exc:
        MapDatabaseManager(store).save_checkpoint("Sala")
    assert exc.value.slug == "sala-2"
    assert store.inserts == 2
    assert not any(row["name"] == "Sala" for row in store.checkpoints)


def test_failed_position_query_is_not_an_empty_map(capsys):
    class _Broken:
        def execute_search(self, sql, params=None):
            return None

    with pytest.raises(CheckpointLookupError):
        MapDatabaseManager(_Broken()).get_checkpoint_positions()
    assert "migração 003" in capsys.readouterr().out

    class _Empty:
        def execute_search(self, sql, params=None):
            return []

    assert MapDatabaseManager(_Empty()).get_checkpoint_positions() == {}


def test_resolve_finds_slug_in_the_building():
    store = _Store()
    manager = MapDatabaseManager(store)
    manager.save_checkpoint("Recepção", "banheiros")
    found = manager.resolve_checkpoint(1, "recepcao")
    assert found["name"] == "Recepção"
    assert found["slug"] == "recepcao"
    assert found["building_id"] == 1
    assert found["category"]["code"] == "banheiros"
    assert manager.resolve_checkpoint(1, "nao-existe") is None
    assert manager.resolve_checkpoint(2, "recepcao") is None
