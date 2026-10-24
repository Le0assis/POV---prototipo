"""O seed acha o checkpoint pelo nome exato. O resolve por slug não muda."""

from __future__ import annotations

from pathlib import Path

import pytest

from others.seed_map import SQL_NAME, seed

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class _SeedDB:
    """Sem CAST, a collation junta Recepcao e recepcao."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple]] = []

    def execute_search(self, sql, params=None):
        params = params or ()
        self.calls.append((sql, params))
        if "slug IS NOT NULL" in sql:
            return [{"slug": row["slug"]} for row in self.rows if row.get("slug")]
        if "CAST(name AS BINARY)" in sql:
            return [
                {"slug": row["slug"]}
                for row in self.rows
                if row["name"] == params[0]
            ]
        if "WHERE name = %s" in sql:
            return [
                {"slug": row["slug"]}
                for row in self.rows
                if row["name"].casefold() == str(params[0]).casefold()
            ]
        raise AssertionError(sql)

    def execute_query(self, sql, params=None):
        params = params or ()
        self.calls.append((sql, params))
        if sql.startswith("INSERT INTO checkpoints"):
            name, _building_id, slug = params
            for row in self.rows:
                if row["name"].casefold() == name.casefold():
                    return True
            self.rows.append({"name": name, "slug": slug})
        return True


def _inserted(db: _SeedDB) -> list[str]:
    return [
        params[0]
        for sql, params in db.calls
        if sql.startswith("INSERT INTO checkpoints")
    ]


def _edge_calls(db: _SeedDB) -> list[tuple]:
    return [params for sql, params in db.calls if sql.startswith("INSERT INTO edges")]


def test_seed_name_lookup_is_binary():
    assert "CAST(name AS BINARY) = CAST(%s AS BINARY)" in SQL_NAME
    assert "WHERE name = %s" not in SQL_NAME
    text = (BACKEND_ROOT / "others" / "seed_map.py").read_text(encoding="utf-8")
    assert "WHERE name = %s" not in text

    exact = _SeedDB([{"name": "Recepcao", "slug": "recepcao"}])
    seed(exact)
    assert "Recepcao" not in _inserted(exact)
    assert _edge_calls(exact)
    assert _edge_calls(exact)[0][0] == "Recepcao"


def test_case_conflict_stops_before_the_edge():
    different_case = _SeedDB([{"name": "recepcao", "slug": "recepcao"}])
    with pytest.raises(RuntimeError) as exc:
        seed(different_case)
    message = str(exc.value)
    assert "Conflito de maiúsculas" in message
    assert "Recepcao" in message
    assert "aresta" in message
    assert "Recepcao" in _inserted(different_case)
    assert _edge_calls(different_case) == []
    assert different_case.rows == [{"name": "recepcao", "slug": "recepcao"}]


def test_resolve_by_slug_stays_on_the_column_collation():
    text = (BACKEND_ROOT / "map" / "MapDatabaseManager.py").read_text(encoding="utf-8")
    assert "WHERE c.building_id = %s AND c.slug = %s" in text
    assert "CAST(c.slug AS BINARY)" not in text
    assert "CAST(slug AS BINARY)" not in text
