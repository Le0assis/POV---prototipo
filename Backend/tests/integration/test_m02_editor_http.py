"""Senha do editor nas rotas reais: 401, 503 e 200/201, sem MySQL.

O front (PR #3) depende deste contrato: path é array, include_path
default true, reset e routes pedem senha, map-config sem px_per_m é 422.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import app
from api.editor_auth import make_password_hash, set_attempt_limit
from map.MapDatabaseManager import MapDatabaseManager
from tests.unit.test_m02_connections import _MemDB
from tests.unit.test_m02_walk_transaction import _TxDB

pytestmark = pytest.mark.integration

PASSWORD = "segredo-do-editor"
PASSWORD_HASH = make_password_hash(PASSWORD)
OK = {"X-Editor-Password": PASSWORD}
WRONG = {"X-Editor-Password": "outra"}


def _samples(count: int = 20) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append({
            "timestamp": index / 50.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        })
    return rows


def _calls():
    return [
        ("post", "/api/checkpoints", {"name": "Novo"}),
        ("post", "/api/edges", {"source": "A", "target": "B", "distance_m": 1.0, "heading_rad": 0.0}),
        ("post", "/api/edges/process-raw", {"source": "A", "target": "B", "samples": _samples()}),
        ("patch", "/api/checkpoints/Sala/position", {"pos_x_px": 1.0, "pos_y_px": 2.0}),
        ("put", "/api/map-config", {"plan_image": "assets/planta.png", "px_per_m": 10.0, "rotation_rad": 0.0}),
        ("delete", "/api/routes/1", None),
        ("post", "/api/routes", {"start_node": "A", "end_node": "B", "name": "Rota"}),
        ("post", "/api/reset", None),
    ]


def _succeed(monkeypatch):
    app_module.topo_map.add_checkpoint("A")
    app_module.topo_map.add_checkpoint("B")
    app_module.topo_map.upsert_directed_edge("A", "B", 1.0, 0.0)
    monkeypatch.setattr(app_module.map_db_manager, "save_checkpoint", lambda name: True)
    monkeypatch.setattr(app_module.map_db_manager, "save_edge", lambda *args, **kwargs: True)
    monkeypatch.setattr(app_module.map_db_manager, "delete_route", lambda route_id: True)
    monkeypatch.setattr(app_module.map_db_manager, "update_checkpoint_position", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        app_module.map_db_manager,
        "save_map_config",
        lambda *args, **kwargs: {"plan_image": "assets/planta.png", "px_per_m": 10.0, "rotation_rad": 0.0},
    )
    monkeypatch.setattr(
        app_module.map_db_manager,
        "get_map_config",
        lambda: {"plan_image": None, "px_per_m": None, "rotation_rad": 0.0},
    )
    monkeypatch.setattr(app_module.map_db_manager, "get_checkpoint_positions", lambda: {})
    monkeypatch.setattr(app_module.map_db_manager, "list_connections", lambda include_path=True: [])
    monkeypatch.setattr(app_module.map_db_manager, "save_route", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        app_module.map_db_manager,
        "get_all_routes",
        lambda: [{
            "id": 1,
            "name": "Rota",
            "start_node": "A",
            "end_node": "B",
            "total_distance_m": 1.0,
            "total_steps_estimated": 1,
            "created_at": "2026-01-01",
        }],
    )
    monkeypatch.setattr(
        app_module.edge_processor,
        "process_samples",
        lambda source, target, samples: {"status": "success", "valid": True, "source": source, "target": target},
    )


def _send(client: TestClient, method: str, path: str, body, headers=None):
    request = getattr(client, method)
    if body is None:
        return request(path, headers=headers)
    return request(path, json=body, headers=headers)


def test_protected_writes_reject_missing_and_wrong_password(monkeypatch):
    set_attempt_limit(50)
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    client = TestClient(app)
    for method, path, body in _calls():
        missing = _send(client, method, path, body)
        wrong = _send(client, method, path, body, WRONG)
        assert missing.status_code == 401, path
        assert wrong.status_code == 401, path
        assert missing.json()["detail"] == "Senha do editor ausente ou inválida."


def test_protected_writes_fail_closed_without_env(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    client = TestClient(app)
    for method, path, body in _calls():
        response = _send(client, method, path, body, OK)
        assert response.status_code == 503, path


def test_protected_writes_accept_the_password(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    _succeed(monkeypatch)
    client = TestClient(app)
    expected = {
        "/api/checkpoints": 201,
        "/api/edges": 201,
        "/api/edges/process-raw": 201,
        "/api/checkpoints/Sala/position": 200,
        "/api/map-config": 200,
        "/api/routes/1": 200,
        "/api/routes": 201,
        "/api/reset": 200,
    }
    for method, path, body in _calls():
        response = _send(client, method, path, body, OK)
        assert response.status_code == expected[path], (path, response.text)


def test_each_http_request_uses_its_own_connection(monkeypatch):
    from datasets.ManagerDatabase import ConexaoBD

    previous = app_module.db.connection
    opened: list = []

    class _Live:
        def is_connected(self):
            return True

    def connect(self, announce=True):
        self.connection = _Live()
        self.cursor = None
        opened.append(self)

    def disconnect(self, announce=True):
        opened.append("closed")
        self.connection = None

    app_module.db.connection = _Live()
    monkeypatch.setattr(ConexaoBD, "connect", connect)
    monkeypatch.setattr(ConexaoBD, "disconnect", disconnect)
    seen = {}

    def get_map_config():
        with app_module.map_db_manager._session():
            seen["db"] = app_module.map_db_manager.db
        return {"plan_image": None, "px_per_m": None, "rotation_rad": 0.0}

    monkeypatch.setattr(app_module.map_db_manager, "get_map_config", get_map_config)
    try:
        response = TestClient(app).get("/api/map-config")
        assert response.status_code == 200
        assert seen["db"] is not app_module.db
        assert seen["db"] in opened
        assert "closed" in opened
    finally:
        app_module.db.connection = previous


def test_public_gets_do_not_need_the_header(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    seen = {}

    def list_connections(include_path=True):
        seen["include_path"] = include_path
        return []

    monkeypatch.setattr(app_module.map_db_manager, "list_connections", list_connections)
    monkeypatch.setattr(app_module.map_db_manager, "get_checkpoint_positions", lambda: {"A": (1.0, 2.0)})
    monkeypatch.setattr(
        app_module.map_db_manager,
        "get_map_config",
        lambda: {"plan_image": None, "px_per_m": None, "rotation_rad": 0.0},
    )
    client = TestClient(app)
    for path in ("/api/map", "/api/connections", "/api/map-config", "/api/pdr/config"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert seen["include_path"] is True
    hidden = client.get("/api/connections?include_path=false")
    assert hidden.status_code == 200
    assert seen["include_path"] is False
    config = client.get("/api/pdr/config").json()
    assert config["version"] == "m02-1"
    assert config["min_samples"] == 20
    map_config = client.get("/api/map-config").json()
    assert map_config["status"] == "success"
    assert set(map_config["map_config"]) == {"plan_image", "px_per_m", "rotation_rad"}


def test_map_config_and_position_reject_invalid_bodies(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    client = TestClient(app)
    missing = client.put("/api/map-config", json={"plan_image": "assets/planta.png"}, headers=OK)
    zero = client.put("/api/map-config", json={"px_per_m": 0}, headers=OK)
    negative = client.put("/api/map-config", json={"px_per_m": -2}, headers=OK)
    assert missing.status_code == 422
    assert zero.status_code == 422
    assert negative.status_code == 422
    assert missing.status_code != 400
    assert zero.status_code != 400
    assert negative.status_code != 400
    assert client.patch("/api/checkpoints/Sala/position", json={"pos_x_px": 1}, headers=OK).status_code == 422
    assert client.patch(
        "/api/checkpoints/Sala/position",
        json={"pos_x_px": "no", "pos_y_px": 1},
        headers=OK,
    ).status_code == 422


class _ProcessRawDB:
    """Log em memória e a gravação real de trajetória, sem MySQL."""

    def __init__(self) -> None:
        self.tx = _TxDB()
        self.manager = MapDatabaseManager(self.tx)

    def save_sensor_log(self, source, target, csv_data):
        assert csv_data
        return 3

    def update_sensor_log(self, log_id, steps, distance, is_valid, message):
        return True

    def record_walk(self, **kwargs):
        return self.manager.record_walk(**kwargs)


def test_process_raw_returns_500_when_the_walk_is_not_saved(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    app_module.topo_map.add_checkpoint("Quarto")
    app_module.topo_map.add_checkpoint("Sala")

    class _FailingWalk:
        def save_sensor_log(self, source, target, csv_data):
            return 3

        def update_sensor_log(self, log_id, steps, distance, is_valid, message):
            return True

        def record_walk(self, **kwargs):
            return None

    monkeypatch.setattr(app_module.edge_processor, "db_manager", _FailingWalk())
    client = TestClient(app)
    response = client.post(
        "/api/edges/process-raw",
        headers=OK,
        json={"source": "Quarto", "target": "Sala", "samples": _samples(80)},
    )
    assert response.status_code == 500
    assert response.status_code != 201
    assert response.json() == {"detail": "Erro interno ao salvar."}
    assert "trace_id" not in response.json()


def test_process_raw_path_is_an_array_with_origin(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    app_module.topo_map.add_checkpoint("Quarto")
    app_module.topo_map.add_checkpoint("Sala")
    monkeypatch.setattr(app_module.edge_processor, "db_manager", _ProcessRawDB())
    client = TestClient(app)
    response = client.post(
        "/api/edges/process-raw",
        headers=OK,
        json={"source": "Quarto", "target": "Sala", "samples": _samples(80)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["path"], list)
    assert not isinstance(body["path"], dict)
    assert "points" not in body
    assert body["path"][0] == {"x": 0.0, "y": 0.0, "t": 0.0}
    assert set(body["path"][0]) == {"x", "y", "t"}
    assert "trace_id" in body
    assert body["trace_id"] == 1


def test_connections_include_path_defaults_to_true_and_path_is_array(monkeypatch):
    monkeypatch.setattr(app_module, "map_db_manager", MapDatabaseManager(_MemDB()))
    client = TestClient(app)
    default = client.get("/api/connections")
    explicit = client.get("/api/connections?include_path=true")
    hidden = client.get("/api/connections?include_path=false")
    assert default.status_code == 200
    assert explicit.status_code == 200
    assert hidden.status_code == 200
    assert default.json() == explicit.json()
    connection = default.json()["connections"][0]
    assert isinstance(connection["path"], list)
    assert connection["path"][0] == {"x": 0.0, "y": 0.0, "t": None}
    assert "points" not in connection
    assert "path" not in hidden.json()["connections"][0]


def test_wrong_password_does_not_open_mysql(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("a senha errada não abre MySQL")

    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    monkeypatch.setattr("datasets.ManagerDatabase.ConexaoBD.connect", fail)
    response = TestClient(app).post("/api/checkpoints", json={"name": "Novo"})
    assert response.status_code == 401


def test_sixty_parallel_correct_saves_all_succeed(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    monkeypatch.setattr(app_module.map_db_manager, "save_checkpoint", lambda *_args, **_kwargs: True)

    def once(index: int) -> int:
        return TestClient(app).post(
            "/api/checkpoints",
            headers=OK,
            json={"name": f"Paralelo{index}"},
        ).status_code

    with ThreadPoolExecutor(max_workers=60) as pool:
        codes = list(pool.map(once, range(60)))
    assert codes == [201] * 60


def test_lock_conflict_after_retry_is_503(monkeypatch):
    from datasets.ManagerDatabase import DatabaseBusy

    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    app_module.topo_map.add_checkpoint("A")
    app_module.topo_map.add_checkpoint("B")

    def busy(*_args, **_kwargs):
        raise DatabaseBusy()

    monkeypatch.setattr(app_module.map_db_manager, "save_edge", busy)
    response = TestClient(app).post(
        "/api/edges",
        headers=OK,
        json={"source": "A", "target": "B", "distance_m": 1.0, "heading_rad": 0.0},
    )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_post_reset_requires_editor_password(monkeypatch):
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    client = TestClient(app)
    missing = client.post("/api/reset")
    wrong = client.post("/api/reset", headers=WRONG)
    assert missing.status_code == 401
    assert wrong.status_code == 401
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    closed = client.post("/api/reset", headers=OK)
    assert closed.status_code == 503


def _lock_error(errno: int = 1205):
    from mysql.connector import Error

    return Error(msg="lock wait", errno=errno)


class _PositionCursor:
    def __init__(self, steps) -> None:
        self.steps = list(steps)
        self.rowcount = 0
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        self.rowcount = int(step)


class _PositionConnection:
    def commit(self):
        return None

    def rollback(self):
        return None


def _patch_position(monkeypatch, steps):
    from datasets.ManagerDatabase import ConexaoBD

    database = ConexaoBD("127.0.0.1", "pov", "pov", "x")
    database.connection = _PositionConnection()
    database.cursor = _PositionCursor(steps)
    monkeypatch.setattr(app_module.map_db_manager, "_per_request", False)
    monkeypatch.setattr(app_module.map_db_manager, "_database", database)
    return database.cursor


def _patch_position_request(monkeypatch, steps):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    cursor = _patch_position(monkeypatch, steps)
    response = TestClient(app).patch(
        "/api/checkpoints/Sala/position",
        headers=OK,
        json={"pos_x_px": 12.0, "pos_y_px": 40.0},
    )
    return cursor, response


def test_position_patch_held_lock_is_503_with_retry_after(monkeypatch):
    cursor, response = _patch_position_request(monkeypatch, [_lock_error(), _lock_error()])
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["detail"] != "Checkpoint não encontrado."
    assert cursor.calls == 2


def test_position_patch_missing_checkpoint_is_404(monkeypatch):
    cursor, response = _patch_position_request(monkeypatch, [0])
    assert response.status_code == 404
    assert response.json()["detail"] == "Checkpoint não encontrado."
    assert response.headers.get("retry-after") is None
    assert cursor.calls == 1


def test_position_patch_sql_error_is_500_not_404(monkeypatch, caplog):
    with caplog.at_level("ERROR"):
        cursor, response = _patch_position_request(monkeypatch, [_lock_error(1064)])
    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno."}
    assert "Checkpoint não encontrado." not in response.text
    assert "Falha ao gravar a posição do checkpoint." in caplog.text
    assert cursor.calls == 1


def test_post_routes_requires_editor_password(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    body = {"start_node": "A", "end_node": "B", "name": "Rota"}
    client = TestClient(app)
    missing = client.post("/api/routes", json=body)
    wrong = client.post("/api/routes", json=body, headers=WRONG)
    assert missing.status_code == 401
    assert wrong.status_code == 401
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    closed = client.post("/api/routes", json=body, headers=OK)
    assert closed.status_code == 503
