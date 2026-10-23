"""A travada ao salvar vinha da sessão MySQL, não de índice faltando.

Três causas que se somam:

1. O middleware HTTP chamava ``mysql.connector.connect()`` e
   ``is_connected()`` (um PING) no event loop, em todo pedido, inclusive
   CSS e JS. O conector C trata timeout nulo como 0, ou seja, sem prazo.
   Um handshake que não termina segura o loop e o POST fica na fila.
2. PING ou ``START TRANSACTION`` com resultado ainda não lido não recebe
   resposta: o servidor espera o cliente ler o SELECT anterior. ``disconnect``
   pingava antes de fechar o cursor, então a limpeza também não voltava.
3. Um ``threading.Lock`` único cobria a transação inteira de qualquer
   corredor. Um salvamento preso segurava todos os outros.

A sessão de boot não fica aberta no processo. Autocommit desligado deixava
o SELECT do mapa numa transação até o shutdown.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest

from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager
from tests.unit.test_m02_walk_transaction import _TxDB, _built

pytestmark = pytest.mark.unit


def test_connect_gives_up_when_the_handshake_never_arrives():
    """Servidor TCP que aceita e cala. Sem prazo isso não retorna."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    held: list[socket.socket] = []

    def accept_and_hold() -> None:
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        held.append(conn)
        time.sleep(2)

    thread = threading.Thread(target=accept_and_hold, daemon=True)
    thread.start()
    database = ConexaoBD("127.0.0.1", "POV", "root", "", port=port)
    started = time.perf_counter()
    try:
        database.connect(announce=False, timeout=0.4)
        elapsed = time.perf_counter() - started
    finally:
        listener.close()
        for conn in held:
            conn.close()
        thread.join(timeout=2)
    assert database.connection is None
    assert elapsed < 2.0


def test_begin_transaction_reads_pending_rows_before_start():
    class _Cursor:
        def __init__(self, connection) -> None:
            self.connection = connection

        def fetchall(self):
            self.connection.unread_result = False
            self.connection.events.append("drain")
            return []

    class _Conn:
        def __init__(self) -> None:
            self.unread_result = True
            self.in_transaction = False
            self.events: list[str] = []

        def start_transaction(self) -> None:
            if self.unread_result:
                raise AssertionError("START TRANSACTION com resultado pendente não volta")
            self.events.append("start")
            self.in_transaction = True

        def rollback(self) -> None:
            self.events.append("rollback")
            self.in_transaction = False

    database = ConexaoBD("localhost", "POV", "root", "")
    database.connection = _Conn()
    database.cursor = _Cursor(database.connection)
    assert database.begin_transaction() is True
    assert database.connection.events == ["drain", "start"]


def test_disconnect_does_not_ping_while_rows_are_unread():
    class _Cursor:
        def __init__(self, connection) -> None:
            self.connection = connection
            self.closed = False

        def close(self) -> None:
            self.closed = True
            self.connection.unread_result = False

    class _Conn:
        def __init__(self) -> None:
            self.unread_result = True
            self.in_transaction = True
            self.events: list[str] = []

        def is_connected(self) -> bool:
            raise AssertionError("PING com resultado pendente trava o protocolo")

        def rollback(self) -> None:
            if self.unread_result:
                raise AssertionError("ROLLBACK ainda tem linhas por ler")
            self.events.append("rollback")
            self.in_transaction = False

        def shutdown(self) -> None:
            self.events.append("shutdown")

        def close(self) -> None:
            self.events.append("close")

    database = ConexaoBD("localhost", "POV", "root", "")
    connection = _Conn()
    cursor = _Cursor(connection)
    database.connection = connection
    database.cursor = cursor
    database.disconnect(announce=False)
    assert cursor.closed is True
    assert database.cursor is None
    assert database.connection is None
    assert connection.events == ["rollback", "shutdown", "close"]


def test_disconnect_order_is_cursor_then_rollback_then_socket():
    events: list[str] = []

    class _Cursor:
        def close(self) -> None:
            events.append("cursor")

    class _Conn:
        unread_result = False
        in_transaction = True

        def rollback(self) -> None:
            events.append("rollback")
            self.in_transaction = False

        def shutdown(self) -> None:
            events.append("shutdown")

        def close(self) -> None:
            events.append("close")

        def is_connected(self) -> bool:
            events.append("ping")
            return True

    database = ConexaoBD("localhost", "POV", "root", "")
    database.connection = _Conn()
    database.cursor = _Cursor()
    database.disconnect(announce=False)
    assert events == ["cursor", "rollback", "shutdown", "close"]
    assert "ping" not in events


def test_other_corridor_is_not_stuck_behind_one_walk():
    first_db = _TxDB()
    other_db = _TxDB()
    first = MapDatabaseManager(first_db)
    other = MapDatabaseManager(other_db)
    started = threading.Event()
    release = threading.Event()
    original = first_db.commit_transaction

    def commit_transaction():
        started.set()
        assert release.wait(timeout=2)
        return original()

    first_db.commit_transaction = commit_transaction
    holder: list = []

    def save_first() -> None:
        holder.append(first.record_walk(
            "Quarto", "Sala", 4, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
            _built(), is_valid=True,
        ))

    worker = threading.Thread(target=save_first)
    worker.start()
    assert started.wait(timeout=2)
    finished: list = []

    def save_other() -> None:
        finished.append(other.record_walk(
            "Cozinha", "Varanda", 5, "2026-10-20 16:05:11.020", "2026-10-20 16:05:12.020",
            _built(), is_valid=True,
        ))

    second = threading.Thread(target=save_other)
    second.start()
    second.join(1.0)
    assert not second.is_alive()
    assert finished and finished[0] is not None
    assert first._lock_for("Quarto", "Sala").locked() is True
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert holder and holder[0] is not None


def test_blocking_connect_does_not_freeze_the_other_requests(monkeypatch):
    import api.app as app_module
    from api.app import app

    def slow_connect(self, announce=True, timeout=None):
        time.sleep(0.8)
        self.connection = None
        self.cursor = None

    monkeypatch.setattr(ConexaoBD, "connect", slow_connect)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            db_call = asyncio.create_task(client.get("/api/map-config"))
            await asyncio.sleep(0.05)
            started = time.perf_counter()
            free = await client.get("/api/pdr/config")
            elapsed = time.perf_counter() - started
            await db_call
            return free, elapsed

    # O import do app já rodou a subida. O monkeypatch pega o connect da rota.
    assert app_module.map_db_manager is not None
    free, elapsed = asyncio.run(scenario())
    assert free.status_code == 200
    assert elapsed < 0.4
