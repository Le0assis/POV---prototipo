"""1205/1213 sobem DatabaseBusy depois de uma tentativa. Ausência continua 404."""

from __future__ import annotations

from pathlib import Path

import pytest
from mysql.connector import Error

from datasets.ManagerDatabase import ConexaoBD, DatabaseBusy, DatabaseQueryError
from map.MapDatabaseManager import MapDatabaseManager
from tests.unit.test_m02_walk_transaction import _EdgeTx

pytestmark = pytest.mark.unit


class _Cursor:
    def __init__(self, steps) -> None:
        self.steps = list(steps)
        self.rowcount = 0
        self.lastrowid = 7
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        self._step()

    def executemany(self, sql, seq):
        self.calls += 1
        self._step()

    def _step(self):
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        self.rowcount = int(step)

    def fetchall(self):
        return [{"name": "Sala"}]


class _Conn:
    def __init__(self) -> None:
        self.in_transaction = False
        self.rollbacks = 0

    def commit(self):
        return None

    def rollback(self):
        self.rollbacks += 1
        self.in_transaction = False

    def start_transaction(self):
        self.in_transaction = True


def _db(steps) -> tuple[ConexaoBD, _Cursor]:
    database = ConexaoBD("127.0.0.1", "pov", "pov", "x")
    database.connection = _Conn()
    database.cursor = _Cursor(steps)
    return database, database.cursor


def _lock(errno: int = 1205) -> Error:
    return Error(msg="lock", errno=errno)


@pytest.mark.parametrize("errno", [1205, 1213])
def test_execute_update_retries_a_lock_once_then_raises(errno):
    database, cursor = _db([_lock(errno), _lock(errno)])
    with pytest.raises(DatabaseBusy):
        database.execute_update("UPDATE checkpoints SET pos_x_px = %s WHERE name = %s", (1, "Sala"))
    assert cursor.calls == 2
    assert database.connection.rollbacks == 2


def test_execute_update_lock_then_success_returns_the_rowcount():
    database, cursor = _db([_lock(), 1])
    assert database.execute_update("UPDATE t SET a = %s", (1,)) == 1
    assert cursor.calls == 2


def test_execute_update_zero_rows_is_not_an_error():
    database, _cursor = _db([0])
    assert database.execute_update("UPDATE t SET a = %s WHERE id = %s", (1, 9)) == 0


def test_statement_inside_a_transaction_does_not_retry_the_lock():
    database, cursor = _db([_lock(), 1])
    database._explicit = True
    with pytest.raises(DatabaseBusy):
        database.execute_within("UPDATE edges SET distance_m = %s", (1,))
    assert cursor.calls == 1


@pytest.mark.parametrize("method", ["execute_search", "execute_query", "execute_insert", "execute_many"])
def test_autocommit_helpers_raise_after_one_lock_retry(method):
    database, cursor = _db([_lock(), _lock()])
    call = getattr(database, method)
    with pytest.raises(DatabaseBusy):
        if method == "execute_many":
            call("INSERT INTO t VALUES (%s)", [(1,)])
        else:
            call("SELECT 1")
    assert cursor.calls == 2


def test_begin_and_commit_raise_lock_without_a_second_try():
    database, _cursor = _db([])

    def locked_start():
        raise _lock()

    database.connection.start_transaction = locked_start
    with pytest.raises(DatabaseBusy):
        database.begin_transaction()
    assert database._explicit is False

    def locked_commit():
        raise _lock()

    database.connection.commit = locked_commit
    database._explicit = True
    with pytest.raises(DatabaseBusy):
        database.commit_transaction()
    assert database._explicit is False


def test_non_lock_update_returns_none():
    database, cursor = _db([Error(msg="bad sql", errno=1064)])
    assert database.execute_update("UPDATE t SET a = 1") is None
    assert cursor.calls == 1


def _denied(secret: str) -> Error:
    return Error(msg=f"denied for {secret}", errno=1064)


@pytest.mark.parametrize(
    "method",
    [
        "execute_search",
        "execute_query",
        "execute_update",
        "execute_insert",
        "execute_many",
        "execute_within",
        "insert_within",
        "executemany_within",
    ],
)
def test_sql_errors_do_not_print_the_password(method, capsys):
    secret = "segredo-que-nao-sai"
    database, _cursor = _db([_denied(secret)])
    database.password = secret
    call = getattr(database, method)
    if method in ("execute_many", "executemany_within"):
        result = call("INSERT INTO t VALUES (%s)", [(1,)])
    else:
        result = call("SELECT 1")
    assert result is None or result is False
    printed = capsys.readouterr().out
    assert secret not in printed
    assert "***" in printed
    assert "Traceback" not in printed


def test_transaction_errors_do_not_print_the_password(capsys):
    secret = "segredo-que-nao-sai"
    database, _cursor = _db([])
    database.password = secret

    def fail():
        raise _denied(secret)

    database.connection.start_transaction = fail
    assert database.begin_transaction() is False
    database.connection.commit = fail
    assert database.commit_transaction() is False
    database.connection.rollback = fail
    assert database.rollback_transaction() is False
    printed = capsys.readouterr().out
    assert secret not in printed
    assert printed.count("***") == 3
    assert "Erro ao abrir transação:" in printed
    assert "Erro ao confirmar transação:" in printed
    assert "Erro ao reverter transação:" in printed
    assert "Traceback" not in printed


def test_every_mysql_error_print_uses_redact():
    source = (Path(__file__).resolve().parents[2] / "datasets" / "ManagerDatabase.py").read_text(
        encoding="utf-8"
    )
    checked = 0
    for line in source.splitlines():
        if "print(" not in line or "exc" not in line:
            continue
        assert "_redact(exc)" in line, line
        checked += 1
    assert checked == 12


def test_save_edge_retries_database_busy_once():
    class _Once(_EdgeTx):
        def __init__(self) -> None:
            super().__init__()
            self.hits = 0

        def execute_within(self, sql, params=None):
            self.hits += 1
            if self.hits == 1:
                raise DatabaseBusy()
            return super().execute_within(sql, params)

    database = _Once()
    assert MapDatabaseManager(database).save_edge("Sala", "Quarto", 4.0, 0.2) is True
    assert database.ops.count("begin") == 2
    assert database.ops.count("rollback") == 1
    assert database.ops.count("commit") == 1


def test_save_edge_raises_when_the_lock_survives_the_retry():
    class _Busy(_EdgeTx):
        def begin_transaction(self):
            raise DatabaseBusy()

    with pytest.raises(DatabaseBusy):
        MapDatabaseManager(_Busy()).save_edge("Sala", "Quarto", 4.0, 0.2)


class _Rows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def execute_search(self, sql, params=None):
        return self.rows

    def execute_update(self, sql, params=None):
        return self.rows


def test_failed_reads_are_not_a_missing_row():
    manager = MapDatabaseManager(_Rows(None))
    with pytest.raises(DatabaseQueryError):
        manager.get_route_by_id(1)
    with pytest.raises(DatabaseQueryError):
        manager.get_connection(1)
    with pytest.raises(DatabaseQueryError):
        manager.get_sensor_log_csv(1)
    with pytest.raises(DatabaseQueryError):
        manager.get_all_routes()
    with pytest.raises(DatabaseQueryError):
        manager.delete_route(1)


def test_delete_and_position_zero_rows_stay_absent():
    manager = MapDatabaseManager(_Rows(0))
    assert manager.delete_route(4) is False
    assert manager.update_checkpoint_position("Ninguem", 1, 2) is False
