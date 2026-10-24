"""Dois aparelhos intercalados não compartilham o matcher."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import app
from api.editor_auth import make_password_hash

pytestmark = pytest.mark.integration

PASSWORD = "segredo-do-editor"
SESSION_A = "device-aaaa-01"
SESSION_B = "device-bbbb-02"
NODE_A = "SessaoA"
NODE_B = "SessaoB"


@pytest.fixture(autouse=True)
def _routes_and_clean_sessions(monkeypatch):
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", make_password_hash(PASSWORD))
    app_module.walk_sessions.clear()
    app_module.topo_map.add_checkpoint(NODE_A)
    app_module.topo_map.add_checkpoint(NODE_B)
    app_module.topo_map.upsert_directed_edge(NODE_A, NODE_B, 1.0, 0.0)
    yield
    app_module.walk_sessions.clear()


def _headers(session_id: str, *, editor: bool = False) -> dict[str, str]:
    headers = {"X-Pov-Session": session_id}
    if editor:
        headers["X-Editor-Password"] = PASSWORD
    return headers


def _step(client: TestClient, session_id: str, length: float) -> dict:
    response = client.post(
        "/api/localize",
        json={"step_length_m": length, "yaw_rad": 0.0},
        headers=_headers(session_id),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _where(client: TestClient, session_id: str) -> dict:
    response = client.get("/api/current_location", headers=_headers(session_id))
    assert response.status_code == 200, response.text
    return response.json()


def test_interleaved_sessions_do_not_share_the_walk():
    client = TestClient(app)
    for session_id in (SESSION_A, SESSION_B):
        reset = client.post(
            "/api/reset",
            params={"start_node": NODE_A},
            headers=_headers(session_id, editor=True),
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["start_node"] == NODE_A

    _step(client, SESSION_A, 0.6)
    _step(client, SESSION_B, 0.2)
    moved = _step(client, SESSION_A, 0.6)
    stayed = _where(client, SESSION_B)
    arrived = _where(client, SESSION_A)

    assert moved["current_node"] == NODE_B
    assert arrived["current_node"] == NODE_B
    assert arrived["visited_path"] == [NODE_A, NODE_B]
    assert arrived["accumulated_distance_m"] == pytest.approx(0.0)
    assert stayed["current_node"] == NODE_A
    assert stayed["visited_path"] == [NODE_A]
    assert stayed["accumulated_distance_m"] == pytest.approx(0.2)

    again = client.post(
        "/api/reset",
        params={"start_node": NODE_A},
        headers=_headers(SESSION_A, editor=True),
    )
    assert again.status_code == 200
    assert _where(client, SESSION_A)["visited_path"] == [NODE_A]
    assert _where(client, SESSION_A)["accumulated_distance_m"] == pytest.approx(0.0)
    assert _where(client, SESSION_B)["accumulated_distance_m"] == pytest.approx(0.2)
    assert _where(client, SESSION_B)["current_node"] == NODE_A


def test_concurrent_sessions_do_not_add_each_others_steps():
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def walk(session_id: str, length: float) -> None:
        client = TestClient(app)
        try:
            reset = client.post(
                "/api/reset",
                params={"start_node": NODE_A},
                headers=_headers(session_id, editor=True),
            )
            assert reset.status_code == 200, reset.text
            start.wait()
            for _ in range(10):
                body = _step(client, session_id, length)
                assert body["current_node"] == NODE_A
        except BaseException as exc:
            errors.append(exc)

    # 0.05 * 10 = 0.5, abaixo da aresta de 1 m: os dois continuam no nó de partida.
    left = threading.Thread(target=walk, args=(SESSION_A, 0.05))
    right = threading.Thread(target=walk, args=(SESSION_B, 0.03))
    left.start()
    right.start()
    left.join()
    right.join()
    assert errors == []

    client = TestClient(app)
    first = _where(client, SESSION_A)
    second = _where(client, SESSION_B)
    assert first["current_node"] == NODE_A
    assert second["current_node"] == NODE_A
    assert first["accumulated_distance_m"] == pytest.approx(0.5)
    assert second["accumulated_distance_m"] == pytest.approx(0.3)
    assert first["visited_path"] == [NODE_A]
    assert second["visited_path"] == [NODE_A]


def test_missing_or_invalid_session_is_400_and_stores_nothing():
    client = TestClient(app)
    missing = client.post("/api/localize", json={"step_length_m": 0.4, "yaw_rad": 0.0})
    invalid = client.post(
        "/api/localize",
        json={"step_length_m": 0.4, "yaw_rad": 0.0},
        headers={"X-Pov-Session": "../etc/passwd"},
    )
    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert "X-Pov-Session" in missing.json()["detail"]
    assert "passwd" not in invalid.text
    assert len(app_module.walk_sessions) == 0
