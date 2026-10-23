"""Conexão por requisição e transação que não herda um SELECT anterior."""

from __future__ import annotations

import pytest

from datasets.ManagerDatabase import ConexaoBD, request_connection
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


def test_per_request_manager_uses_the_request_connection():
    boot = object()
    local = object()
    manager = MapDatabaseManager(boot, per_request=True)
    assert manager.db is boot
    token = request_connection.set(local)
    try:
        assert manager.db is local
    finally:
        request_connection.reset(token)
    assert manager.db is boot
    isolated = MapDatabaseManager(boot)
    token = request_connection.set(local)
    try:
        assert isolated.db is boot
    finally:
        request_connection.reset(token)


def test_record_walk_keeps_the_lock_until_commit():
    database = _TxDB()
    manager = MapDatabaseManager(database)
    seen: list[bool] = []
    original = database.commit_transaction

    def commit_transaction():
        seen.append(manager._lock_for("Quarto", "Sala").locked())
        return original()

    database.commit_transaction = commit_transaction
    saved = manager.record_walk(
        "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
        _built(), is_valid=True,
    )
    assert saved is not None
    assert seen == [True]
    assert manager._lock_for("Quarto", "Sala").locked() is False
