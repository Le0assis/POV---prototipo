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
