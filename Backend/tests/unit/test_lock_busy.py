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


def test_short_password_stays_in_the_message_and_a_url_credential_does_not(capsys):
    database, _cursor = _db([Error(msg="denied for ab near OR", errno=1064)])
    database.password = "ab"
    assert database.execute_update("UPDATE t SET a = 1") is None
    plain = capsys.readouterr().out
    assert "denied for ab near OR" in plain
    assert "***" not in plain

    database, _cursor = _db([Error(msg="mysql://pov:ab@127.0.0.1/POV", errno=1064)])
    database.password = "ab"
    assert database.execute_search("SELECT 1") is None
    masked = capsys.readouterr().out
    assert "pov:ab@" not in masked
    assert "mysql://***@127.0.0.1/POV" in masked

    database, _cursor = _db([
        Error(msg="senha1 em mysql://pov:senha1@db.internal/POV", errno=1064),
    ])
    database.password = "senha1"
    assert database.execute_search("SELECT 1") is None
    long = capsys.readouterr().out
    assert "senha1" not in long
    assert "mysql://***@db.internal/POV" in long


def test_url_userinfo_runs_to_the_last_at_before_the_host():
    database = ConexaoBD("127.0.0.1", "POV", "pov", "ab")
    with_at = database._redact(RuntimeError("mysql://pov:p@ss@db"))
    assert with_at == "mysql://***@db"
    assert "p@ss" not in with_at
    slash = database._redact(RuntimeError("mysql+pymysql://pov:p/ss@db"))
    assert slash == "mysql+pymysql://***@db"
    assert "p/ss" not in slash
    kept = database._redact(RuntimeError("mysql://u:p@db/x;a@b.com"))
    assert kept == "mysql://***@db/x;a@b.com"
    stopped = database._redact(RuntimeError("mysql://u:p@db;a@b.com"))
    assert stopped == "mysql://***@db;a@b.com"
    plain = database._redact(RuntimeError("http://x/a:b@c"))
    assert plain == "http://x/a:b@c"
    both = database._redact(RuntimeError(
        "antes mysql://pov:p@ss@db/POV depois"
    ))
    assert both == "antes mysql://***@db/POV depois"
    for char in ("/", ";", " ", "(", ",", "'", "?", "#", "<"):
        raw = f"mysql://pov:p{char}ss@db"
        masked = database._redact(RuntimeError(raw))
        assert masked == "mysql://***@db", char
        assert f"p{char}ss" not in masked


def test_redact_removes_a_password_that_crosses_the_cut(monkeypatch):
    env_secret = "EnvPass99word"
    conn_secret = "ConnPass88word"
    monkeypatch.setenv("DB_PASSWORD", env_secret)
    database = ConexaoBD("127.0.0.1", "POV", "pov", conn_secret)
    both = database._redact(RuntimeError(f"{env_secret} e {conn_secret}"))
    assert both == "*** e ***"
    database.password = "segredo"
    monkeypatch.setenv("DB_PASSWORD", "segredo-extra")
    assert database._redact(RuntimeError("segredo-extra")) == "***"
    cases = (
        (env_secret, "ab"),
        (conn_secret, conn_secret),
        ("Zz9secretPIECE", "Zz9secretPIECE"),
    )
    monkeypatch.setenv("DB_PASSWORD", env_secret)
    for secret, password in cases:
        holder = ConexaoBD("127.0.0.1", "POV", "pov", password)
        for head in range(0, len(secret) + 1):
            text = "q" * (4096 - head) + secret
            out = holder._redact(RuntimeError(text))
            assert secret not in out
            assert len(out) <= 4096
            if head:
                assert secret[:head] not in out, (secret, head, out[-20:])


def test_redact_of_a_long_message_stays_under_50ms():
    import time

    database = ConexaoBD("127.0.0.1", "POV", "pov", "senha-longa-demais")
    payload = "a" * 50000
    started = time.perf_counter()
    redacted = database._redact(RuntimeError(payload + "mysql://" + "b" * 1000 + "://"))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.05
    assert len(redacted) == 4096
    assert "senha-longa-demais" not in redacted


def test_map_rollback_prints_use_redact():
    source = (Path(__file__).resolve().parents[2] / "map" / "MapDatabaseManager.py").read_text(
        encoding="utf-8"
    )
    checked = 0
    for line in source.splitlines():
        if "print(" not in line or "{exc}" in line:
            continue
        if "exc" not in line:
            continue
        assert "_redact(exc)" in line, line
        checked += 1
    assert checked == 2


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


def test_redact_scan_is_linear_and_still_masks_before_the_cut(monkeypatch):
    """Muitos ``esquema://`` sem @ não podem custar O(n²): antes eram ~40s."""
    import time

    monkeypatch.delenv("DB_PASSWORD", raising=False)
    database = ConexaoBD("127.0.0.1", "POV", "pov", "ab")
    hostile = "a://" * 50_000
    started = time.perf_counter()
    assert database._redact(RuntimeError(hostile)) == hostile[:4096]
    dotted = "a." * 50_000 + "b"
    assert database._redact(RuntimeError(dotted)) == dotted[:4096]
    assert time.perf_counter() - started < 2.0
    # A credencial depois de muito ruído e cruzando o corte ainda some inteira.
    secret_tail = "S3gr3d0Long" * 600
    raw = "x" * 4000 + " mysql://pov:" + secret_tail + "@db/POV"
    masked = database._redact(RuntimeError(raw))
    assert "S3gr3d0" not in masked
    assert ("x" * 4000 + " mysql://***@db/POV")[:4096] == masked
