"""GET /api/auth/check: 204 com a senha, 401 sem ela, 503 sem a env."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.editor_auth import MISSING_HASH_DETAIL, make_password_hash

pytestmark = pytest.mark.integration

PASSWORD = "segredo-do-editor"
PASSWORD_HASH = make_password_hash(PASSWORD)
OK = {"X-Editor-Password": PASSWORD}
WRONG = {"X-Editor-Password": "outra"}


def test_valid_password_is_204_with_empty_body(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    response = TestClient(app).get("/api/auth/check", headers=OK)
    assert response.status_code == 204
    assert response.content == b""


def test_missing_or_wrong_password_is_401(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", PASSWORD_HASH)
    client = TestClient(app)
    missing = client.get("/api/auth/check")
    wrong = client.get("/api/auth/check", headers=WRONG)
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"] == "Senha do editor ausente ou inválida."
    assert wrong.json()["detail"] == "Senha do editor ausente ou inválida."


def test_unset_editor_password_is_503(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    response = TestClient(app).get("/api/auth/check", headers=OK)
    assert response.status_code == 503
    assert response.json()["detail"] == MISSING_HASH_DETAIL
