"""CORS, saúde e rotas de laboratório no app já importado."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import app
from api.editor_auth import make_password_hash

pytestmark = pytest.mark.integration

PASSWORD = "segredo-do-editor"
PASSWORD_HASH = make_password_hash(PASSWORD)
OK = {"X-Editor-Password": PASSWORD}


def _clear_cors(monkeypatch, env: str) -> None:
    monkeypatch.setenv("POV_ENV", env)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


def test_health_does_not_open_mysql(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("o ping não abre MySQL")

    monkeypatch.setattr(app_module, "checkout_connection", fail)
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_cors_allows_only_the_pages(monkeypatch):
    _clear_cors(monkeypatch, "production")
    client = TestClient(app)
    page = client.get("/api/health", headers={"Origin": "https://pov-unimar.com"})
    www = client.get("/api/health", headers={"Origin": "https://www.pov-unimar.com"})
    local = client.get("/api/health", headers={"Origin": "http://localhost"})
    assert page.headers["access-control-allow-origin"] == "https://pov-unimar.com"
    assert www.headers["access-control-allow-origin"] == "https://www.pov-unimar.com"
    assert "access-control-allow-origin" not in local.headers
    assert "access-control-allow-credentials" not in page.headers


def test_production_preflight_allows_the_editor_header(monkeypatch):
    _clear_cors(monkeypatch, "production")
    response = TestClient(app).options(
        "/api/health",
        headers={
            "Origin": "https://www.pov-unimar.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Editor-Password",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://www.pov-unimar.com"
    assert "x-editor-password" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_development_cors_keeps_localhost(monkeypatch):
    _clear_cors(monkeypatch, "development")
    client = TestClient(app)
    local = client.get("/api/health", headers={"Origin": "http://127.0.0.1:8000"})
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert local.headers["access-control-allow-origin"] == "http://127.0.0.1:8000"
    assert "access-control-allow-origin" not in other.headers


def test_location_routes_are_404_unless_the_flag_is_on(monkeypatch):
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "0")
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    client = TestClient(app)
    body = {"step_length_m": 0.7, "yaw_rad": 0.0}
    hidden = [
        client.get("/api/current_location"),
        client.post("/api/localize", json=body),
        client.post("/api/reset", headers={"X-Editor-Password": "x"}),
    ]
    assert [item.status_code for item in hidden] == [404, 404, 404]
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "1")
    visible = client.get("/api/current_location")
    assert visible.status_code == 200
    assert "current_node" in visible.json()


def test_sensor_log_csv_requires_the_editor_password(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    monkeypatch.setattr(
        app_module.map_db_manager,
        "get_sensor_log_csv",
        lambda log_id: "a,b\n1,2\n",
    )
    client = TestClient(app)
    missing = client.get("/api/sensors_log/1/csv")
    assert missing.status_code == 401
    saved = client.get("/api/sensors_log/1/csv", headers=OK)
    assert saved.status_code == 200
    assert saved.headers["content-type"].startswith("text/csv")
    assert "a,b" in saved.text


def test_database_from_settings_reads_the_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_NAME", "pov_test")
    monkeypatch.setenv("DB_USER", "pov")
    monkeypatch.setenv("DB_PASSWORD", "local-only")
    conn = app_module.database_from_settings()
    assert conn.host == "db.internal"
    assert conn.port == 3307
    assert conn.database == "pov_test"
    assert conn.user == "pov"
    assert conn.password == "local-only"
    assert conn.connection is None
