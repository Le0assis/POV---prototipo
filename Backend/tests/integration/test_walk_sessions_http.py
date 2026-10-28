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


def _open(client: TestClient, session_id: str, headers: dict | None = None):
    sent = {"X-Pov-Session": session_id}
    if headers:
        sent.update(headers)
    return client.get("/api/current_location", headers=sent)


def test_ninth_session_from_one_ip_is_429_and_the_other_ip_stays(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    first = TestClient(app, client=("203.0.113.10", 50000))
    for index in range(8):
        opened = _open(first, f"device-a-{index:02d}")
        assert opened.status_code == 200, opened.text
    blocked = _open(first, "device-a-09")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]
    assert int(blocked.headers["retry-after"]) >= 1
    spoofed = _open(first, "device-a-10", {
        "X-Forwarded-For": "198.51.100.20",
        "CF-Connecting-IP": "198.51.100.21",
    })
    assert spoofed.status_code == 429
    other = TestClient(app, client=("203.0.113.11", 50000))
    assert _open(other, "device-b-01").status_code == 200
    assert _open(first, "device-a-00").status_code == 200
    assert len(app_module.walk_sessions) == 9


def test_trusted_proxy_counts_the_forwarded_client(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "203.0.113.10")
    proxy = TestClient(app, client=("203.0.113.10", 50000))
    forwarded = {"X-Forwarded-For": "198.51.100.20"}
    for index in range(8):
        opened = _open(proxy, f"device-p-{index:02d}", forwarded)
        assert opened.status_code == 200, opened.text
    assert _open(proxy, "device-p-09", forwarded).status_code == 429
    spoofed_left = _open(proxy, "device-p-10", {
        "X-Forwarded-For": "203.0.113.99, 198.51.100.20",
    })
    assert spoofed_left.status_code == 429
    neighbor = _open(proxy, "device-q-01", {
        "X-Forwarded-For": "203.0.113.9, 198.51.100.30",
    })
    assert neighbor.status_code == 200
    assert len(app_module.walk_sessions) == 9


def test_another_ip_does_not_inherit_the_walk(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    session = "device-dono-01"
    owner = TestClient(app, client=("203.0.113.40", 50000))
    stranger = TestClient(app, client=("203.0.113.41", 50000))
    reset = owner.post(
        "/api/reset",
        params={"start_node": NODE_A},
        headers=_headers(session, editor=True),
    )
    assert reset.status_code == 200, reset.text
    assert _step(owner, session, 0.4)["accumulated_distance_m"] == pytest.approx(0.4)

    stolen = stranger.get(
        "/api/current_location",
        headers={
            "X-Pov-Session": session,
            "X-Forwarded-For": "203.0.113.40",
            "CF-Connecting-IP": "203.0.113.40",
        },
    )
    assert stolen.status_code == 200, stolen.text
    body = stolen.json()
    assert body["accumulated_distance_m"] == pytest.approx(0.0)
    assert body["visited_path"] == [body["current_node"]]

    again = _where(owner, session)
    assert again["current_node"] == NODE_A
    assert again["visited_path"] == [NODE_A]
    assert again["accumulated_distance_m"] == pytest.approx(0.4)
    assert len(app_module.walk_sessions) == 2


def test_trusted_proxy_binds_the_session_to_the_forwarded_client(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "203.0.113.10")
    proxy = TestClient(app, client=("203.0.113.10", 50000))
    session = "device-proxy-01"
    owner_headers = {
        "X-Pov-Session": session,
        "X-Editor-Password": PASSWORD,
        "X-Forwarded-For": "198.51.100.20",
    }
    reset = proxy.post("/api/reset", params={"start_node": NODE_A}, headers=owner_headers)
    assert reset.status_code == 200, reset.text
    stepped = proxy.post(
        "/api/localize",
        json={"step_length_m": 0.4, "yaw_rad": 0.0},
        headers={"X-Pov-Session": session, "X-Forwarded-For": "198.51.100.20"},
    )
    assert stepped.status_code == 200, stepped.text
    assert stepped.json()["accumulated_distance_m"] == pytest.approx(0.4)

    stranger = proxy.get(
        "/api/current_location",
        headers={"X-Pov-Session": session, "X-Forwarded-For": "198.51.100.30"},
    )
    assert stranger.status_code == 200, stranger.text
    assert stranger.json()["accumulated_distance_m"] == pytest.approx(0.0)

    owner = proxy.get(
        "/api/current_location",
        headers={"X-Pov-Session": session, "X-Forwarded-For": "198.51.100.20"},
    )
    assert owner.status_code == 200, owner.text
    assert owner.json()["current_node"] == NODE_A
    assert owner.json()["visited_path"] == [NODE_A]
    assert owner.json()["accumulated_distance_m"] == pytest.approx(0.4)


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


def test_cloudflared_on_loopback_gives_each_visitor_their_own_limit(monkeypatch):
    """Atrás do cloudflared o par é 127.0.0.1: com TRUSTED_PROXIES o 9º visitante entra."""
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1,::1")
    tunnel = TestClient(app, client=("127.0.0.1", 50000))
    for index in range(12):
        opened = _open(tunnel, f"device-t-{index:02d}", {"CF-Connecting-IP": f"198.51.100.{index + 1}"})
        assert opened.status_code == 200, opened.text
    assert len(app_module.walk_sessions) == 12
