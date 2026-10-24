"""Conexão por requisição e transação que não herda um SELECT anterior."""

from __future__ import annotations

import threading
import time

import pytest

import datasets.ManagerDatabase as db
from datasets.ManagerDatabase import ConexaoBD, DatabaseUnavailable, request_connection
from map.MapDatabaseManager import MapDatabaseManager
from tests.unit.test_m02_walk_transaction import _TxDB, _built

pytestmark = pytest.mark.unit


def test_begin_transaction_rolls_back_an_implicit_transaction_first():
    class _Conn:
        def __init__(self) -> None:
            self.in_transaction = True
            self.events: list[str] = []

        def rollback(self) -> None:
            self.events.append("rollback")
            self.in_transaction = False

        def start_transaction(self) -> None:
            if self.in_transaction:
                raise AssertionError("start_transaction com transação já aberta")
            self.events.append("start")
            self.in_transaction = True

    database = ConexaoBD("localhost", "POV", "root", "")
    database.connection = _Conn()
    assert database.begin_transaction() is True
    assert database.connection.events == ["rollback", "start"]


def test_per_request_manager_does_not_fall_back_to_boot():
    boot = object()
    local = object()
    manager = MapDatabaseManager(boot, per_request=True)
    with pytest.raises(DatabaseUnavailable):
        manager.db
    token = request_connection.set(local)
    try:
        assert manager.db is local
    finally:
        request_connection.reset(token)
    with pytest.raises(DatabaseUnavailable):
        manager.db
    isolated = MapDatabaseManager(boot)
    token = request_connection.set(local)
    try:
        assert isolated.db is boot
    finally:
        request_connection.reset(token)


def test_record_walk_keeps_the_pair_lock_until_commit():
    database = _TxDB()
    manager = MapDatabaseManager(database)
    seen: list[bool] = []
    other_free: list[bool] = []
    original = database.commit_transaction

    def commit_transaction():
        pair = manager._lock_for("Quarto", "Sala")
        other = manager._lock_for("Copa", "Hall")
        seen.append(pair.locked())
        acquired = other.acquire(blocking=False)
        other_free.append(acquired)
        if acquired:
            other.release()
        return original()

    database.commit_transaction = commit_transaction
    saved = manager.record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(), is_valid=True,
    )
    assert saved is not None
    assert seen == [True]
    assert other_free == [True]
    assert manager._lock_for("Quarto", "Sala").locked() is False


class _IdleConn:
    def __init__(self) -> None:
        self.connection = object()
        self.cursor = object()
        self.host = "127.0.0.1"
        self.database = "POV"
        self.user = "root"
        self.password = ""
        self.port = 3306


def _zero_pool() -> None:
    with db._pool_lock:
        db._idle.clear()
        db._open = 0


def test_pool_waits_for_a_free_connection_before_503(monkeypatch):
    monkeypatch.setattr(db, "POOL_MAX_TOTAL", 1)
    monkeypatch.setattr(db, "POOL_WAIT_S", 1.0)
    _zero_pool()
    db._open = 1
    entered = threading.Event()
    real_wait = db._pool_ready.wait

    def wait_and_signal(timeout=None):
        entered.set()
        return real_wait(timeout)

    monkeypatch.setattr(db._pool_ready, "wait", wait_and_signal)
    result: dict = {}
    started = time.monotonic()

    def waiter() -> None:
        try:
            result["conn"] = db.checkout_connection(_IdleConn())
        except db.DatabaseBusy as exc:
            result["err"] = exc

    thread = threading.Thread(target=waiter)
    thread.start()
    try:
        assert entered.wait(timeout=2)
        time.sleep(0.2)
        assert thread.is_alive()
        ready = _IdleConn()
        with db._pool_lock:
            db._idle.append(ready)
            db._pool_ready.notify()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert result.get("conn") is ready
        assert "err" not in result
        assert time.monotonic() - started >= 0.2
    finally:
        with db._pool_lock:
            db._idle.append(_IdleConn())
            db._pool_ready.notify_all()
        thread.join(timeout=2)
        _zero_pool()


def test_connect_error_does_not_print_the_password(monkeypatch, capsys):
    secret = "segredo-que-nao-sai"

    def boom(*_args, **_kwargs):
        from mysql.connector import Error

        raise Error(msg=f"Access denied for {secret}")

    monkeypatch.setattr(db.mysql.connector, "connect", boom)
    database = ConexaoBD("127.0.0.1", "POV", "pov", secret)
    database.connect(announce=True)
    printed = capsys.readouterr().out
    assert secret not in printed
    assert "***" in printed
    assert database.connection is None


def test_ensure_live_pings_then_reconnects_once(monkeypatch):
    secret = "segredo-que-nao-sai"
    database = ConexaoBD("127.0.0.1", "POV", "pov", secret)
    pings: list[bool] = []

    class _Conn:
        unread_result = False
        in_transaction = False

        def ping(self, reconnect=False, attempts=1, delay=0):
            pings.append(bool(reconnect))
            from mysql.connector import Error

            raise Error(msg=f"lost {secret}")

        def close(self):
            return None

        def rollback(self):
            return None

    class _Cursor:
        unread_result = False

        def close(self):
            return None

    database.connection = _Conn()
    database.cursor = _Cursor()

    def connect(self, announce=True, timeout=None):
        self.connection = object()
        self.cursor = object()

    monkeypatch.setattr(ConexaoBD, "connect", connect)
    assert database.ensure_live() is True
    assert pings == [False]
    assert database.connection is not None
    assert database.cursor is not None


def test_checkout_drops_a_dead_session_and_opens_another(monkeypatch):
    _zero_pool()
    secret = "segredo-que-nao-sai"
    dead = ConexaoBD("127.0.0.1", "POV", "pov", secret)
    dead.connection = object()
    dead.cursor = object()
    dead.ensure_live = lambda: False
    closed: list[str] = []
    dead.disconnect = lambda announce=True: closed.append("dead")

    def connect(self, announce=True, timeout=None):
        self.connection = object()
        self.cursor = object()

    monkeypatch.setattr(ConexaoBD, "connect", connect)
    with db._pool_lock:
        db._idle.append(dead)
        db._open = 1
    try:
        got = db.checkout_connection(ConexaoBD("127.0.0.1", "POV", "pov", secret))
        assert got is not dead
        assert got.connection is not None
        assert closed == ["dead"]
        assert db._open == 1
    finally:
        _zero_pool()


def test_pool_busy_only_after_the_wait(monkeypatch):
    monkeypatch.setattr(db, "POOL_MAX_TOTAL", 1)
    monkeypatch.setattr(db, "POOL_WAIT_S", 0.4)
    _zero_pool()
    db._open = 1
    started = time.monotonic()
    try:
        with pytest.raises(db.DatabaseBusy):
            db.checkout_connection(_IdleConn())
        elapsed = time.monotonic() - started
        assert elapsed >= 0.35
        assert elapsed < 1.5
    finally:
        _zero_pool()
