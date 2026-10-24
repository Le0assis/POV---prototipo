"""O seed confere a caixa antes de gravar e desfaz a transação se errar."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from others.seed_map import SQL_NAME, SeedConflict, cli, seed

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _ci(name: str) -> str:
    """A unique utf8mb4_unicode_ci ignora caixa e acento. O casefold, não."""
    decomposed = unicodedata.normalize("NFD", name)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return without_marks.casefold()


class _SeedDB:
    """INSERT de checkpoint esbarra na unique; a transação devolve o snapshot."""

    def __init__(self, rows: list[dict], *, fail_edges: bool = False, fail_commit: bool = False) -> None:
        self.rows = [dict(row) for row in rows]
        self.calls: list[tuple[str, tuple]] = []
        self.log: list[str] = []
        self.fail_edges = fail_edges
        self.fail_commit = fail_commit
        self._snapshot: list[dict] | None = None
        self._open = False

    def execute_search(self, sql, params=None):
        params = tuple(params or ())
        self.calls.append((sql, params))
        self.log.append("search")
        if "CAST(name AS BINARY)" in sql:
            return [
                {"slug": row["slug"]}
                for row in self.rows
                if row["name"] == params[0]
            ]
        if sql.startswith("SELECT name, slug FROM checkpoints"):
            return [{"name": row["name"], "slug": row["slug"]} for row in self.rows]
        if sql.startswith("SELECT name FROM checkpoints"):
            return [{"name": row["name"]} for row in self.rows]
        raise AssertionError(sql)

    def begin_transaction(self):
        assert not self._open
        self._snapshot = [dict(row) for row in self.rows]
        self._open = True
        self.log.append("begin")
        return True

    def commit_transaction(self):
        assert self._open
        if self.fail_commit:
            self.log.append("commit-fail")
            return False
        self._open = False
        self._snapshot = None
        self.log.append("commit")
        return True

    def rollback_transaction(self):
        assert self._snapshot is not None
        self.rows = [dict(row) for row in self._snapshot]
        self._open = False
        self.log.append("rollback")
        return True

    def execute_within(self, sql, params=None):
        params = tuple(params or ())
        self.calls.append((sql, params))
        assert self._open
        if sql.startswith("INSERT INTO checkpoints"):
            self.log.append("checkpoint")
            name, _building_id, slug = params
            for row in self.rows:
                if _ci(row["name"]) == _ci(name):
                    return True
            self.rows.append({"name": name, "slug": slug})
            return True
        if sql.startswith("INSERT INTO edges"):
            self.log.append("edge")
            if self.fail_edges:
                return False
            return True
        raise AssertionError(sql)


def _inserted(db: _SeedDB) -> list[str]:
    return [
        params[0]
        for sql, params in db.calls
        if sql.startswith("INSERT INTO checkpoints")
    ]


def _edge_calls(db: _SeedDB) -> list[tuple]:
    return [params for sql, params in db.calls if sql.startswith("INSERT INTO edges")]


def _tx(db: _SeedDB) -> list[str]:
    return [item for item in db.log if item in {"begin", "commit", "rollback", "commit-fail"}]


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
    assert _tx(exact) == ["begin", "commit"]
    assert exact.rows[0] == {"name": "Recepcao", "slug": "recepcao"}


def test_case_conflict_stops_before_any_insert():
    original = [{"name": "recepcao", "slug": "recepcao"}]
    different_case = _SeedDB(original)
    with pytest.raises(SeedConflict) as exc:
        seed(different_case)
    message = str(exc.value)
    assert message == (
        "Conflito de maiúsculas: 'Recepcao' já está como 'recepcao'. "
        "Nada foi gravado e nenhuma aresta foi criada."
    )
    assert _inserted(different_case) == []
    assert _edge_calls(different_case) == []
    assert _tx(different_case) == []
    assert different_case.rows == original


def test_every_case_conflict_is_reported_before_the_transaction():
    original = [
        {"name": "recepcao", "slug": "recepcao"},
        {"name": "sala 101", "slug": "sala-101"},
    ]
    db = _SeedDB(original)
    with pytest.raises(SeedConflict) as exc:
        seed(db)
    assert str(exc.value) == (
        "Conflito de maiúsculas: 'Recepcao' já está como 'recepcao'; "
        "'Sala 101' já está como 'sala 101'. "
        "Nada foi gravado e nenhuma aresta foi criada."
    )
    assert _inserted(db) == []
    assert "begin" not in db.log
    assert db.rows == original


def test_accent_collision_rolls_the_transaction_back():
    original = [{"name": "Corredor Á", "slug": "corredor-a"}]
    db = _SeedDB(original)
    with pytest.raises(SeedConflict) as exc:
        seed(db)
    message = str(exc.value)
    assert "Corredor A" in message
    assert "Nada foi gravado" in message
    assert "aresta" in message
    assert "Recepcao" in _inserted(db)
    assert _edge_calls(db) == []
    assert _tx(db) == ["begin", "rollback"]
    assert db.rows == original


def test_edge_failure_rolls_inserted_checkpoints_back():
    original = [{"name": "Recepcao", "slug": "recepcao"}]
    db = _SeedDB(original, fail_edges=True)
    with pytest.raises(RuntimeError, match="Não gravou a aresta") as exc:
        seed(db)
    assert not isinstance(exc.value, SeedConflict)
    assert "checkpoint" in db.log
    assert _tx(db) == ["begin", "rollback"]
    assert db.rows == original


def test_failed_commit_rolls_back():
    original = [{"name": "Recepcao", "slug": "recepcao"}]
    db = _SeedDB(original, fail_commit=True)
    with pytest.raises(RuntimeError, match="Não confirmou o seed"):
        seed(db)
    assert _tx(db) == ["begin", "commit-fail", "rollback"]
    assert db.rows == original


def test_cli_conflict_exits_with_only_the_message(capsys):
    original = [{"name": "recepcao", "slug": "recepcao"}]
    db = _SeedDB(original)
    assert cli(db) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        "Conflito de maiúsculas: 'Recepcao' já está como 'recepcao'. "
        "Nada foi gravado e nenhuma aresta foi criada.\n"
    )
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert db.rows == original
    text = (BACKEND_ROOT / "others" / "seed_map.py").read_text(encoding="utf-8")
    assert "raise SystemExit(code)" in text


def test_cli_lets_other_errors_propagate(capsys):
    db = _SeedDB([{"name": "Recepcao", "slug": "recepcao"}], fail_edges=True)
    with pytest.raises(RuntimeError, match="Não gravou a aresta"):
        cli(db)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert db.rows == [{"name": "Recepcao", "slug": "recepcao"}]


def test_cli_success_returns_zero(capsys):
    db = _SeedDB([{"name": "Recepcao", "slug": "recepcao"}])
    assert cli(db) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Mapa de exemplo garantido" in captured.out
    assert _tx(db) == ["begin", "commit"]


def test_resolve_by_slug_stays_on_the_column_collation():
    text = (BACKEND_ROOT / "map" / "MapDatabaseManager.py").read_text(encoding="utf-8")
    assert "WHERE c.building_id = %s AND c.slug = %s" in text
    assert "CAST(c.slug AS BINARY)" not in text
    assert "CAST(slug AS BINARY)" not in text
