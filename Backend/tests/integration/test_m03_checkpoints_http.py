"""Resolve, categoria e slug imutável no HTTP. Sem MySQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import app
from map.MapDatabaseManager import UnknownCategoryError

pytestmark = pytest.mark.integration

PASSWORD = "segredo-do-editor"
OK = {"X-Editor-Password": PASSWORD}


def test_resolve_200_404_and_422(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)

    def resolve(building_id, slug):
        if building_id == 1 and slug == "recepcao":
            return {
                "name": "Recepção",
                "slug": "recepcao",
                "building_id": 1,
                "category": {"code": "atendimento", "label": "Atendimento"},
                "pos_x_px": None,
                "pos_y_px": None,
            }
        return None

    monkeypatch.setattr(app_module.map_db_manager, "resolve_checkpoint", resolve)
    client = TestClient(app)

    found = client.get("/api/checkpoints/resolve", params={"b": 1, "cp": "recepcao"})
    assert found.status_code == 200
    body = found.json()["checkpoint"]
    assert body["slug"] == "recepcao"
    assert body["building_id"] == 1
    assert body["category"] == {"code": "atendimento", "label": "Atendimento"}

    missing = client.get("/api/checkpoints/resolve", params={"b": 9, "cp": "recepcao"})
    assert missing.status_code == 404

    no_building = client.get("/api/checkpoints/resolve", params={"cp": "recepcao"})
    no_slug = client.get("/api/checkpoints/resolve", params={"b": 1})
    blank_slug = client.get("/api/checkpoints/resolve", params={"b": 1, "cp": "  "})
    bad_building = client.get("/api/checkpoints/resolve", params={"b": "bloco", "cp": "recepcao"})
    assert no_building.status_code == 422
    assert no_slug.status_code == 422
    assert blank_slug.status_code == 422
    assert bad_building.status_code == 422


def test_patch_slug_is_422_and_does_not_write(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", PASSWORD)

    def refuse(*_args, **_kwargs):
        raise AssertionError("PATCH com slug não pode gravar")

    monkeypatch.setattr(app_module.map_db_manager, "update_checkpoint_category", refuse)
    client = TestClient(app)
    for payload in (
        {"slug": "outra"},
        {"slug": "outra", "category_code": "atendimento"},
    ):
        response = client.patch("/api/checkpoints/Sala", json=payload, headers=OK)
        assert response.status_code == 422, payload


def test_category_patch_requires_password_rejects_unknown_and_null_clears(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", PASSWORD)
    client = TestClient(app)

    missing = client.patch("/api/checkpoints/Sala", json={"category_code": "atendimento"})
    wrong = client.patch(
        "/api/checkpoints/Sala",
        json={"category_code": "atendimento"},
        headers={"X-Editor-Password": "outra"},
    )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"] == "Senha do editor ausente ou inválida."

    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)
    closed = client.patch(
        "/api/checkpoints/Sala",
        json={"category_code": None},
        headers=OK,
    )
    assert closed.status_code == 503

    monkeypatch.setenv("EDITOR_PASSWORD", PASSWORD)

    def update(name, category_code):
        if category_code == "inexistente":
            raise UnknownCategoryError(category_code)
        return {
            "name": name,
            "slug": "sala",
            "building_id": 1,
            "category": None if category_code is None else {
                "code": category_code,
                "label": "Atendimento",
            },
            "pos_x_px": None,
            "pos_y_px": None,
        }

    monkeypatch.setattr(app_module.map_db_manager, "update_checkpoint_category", update)
    invalid = client.patch(
        "/api/checkpoints/Sala",
        json={"category_code": "inexistente"},
        headers=OK,
    )
    assert invalid.status_code == 422
    assert "inexistente" in invalid.json()["detail"]

    cleared = client.patch(
        "/api/checkpoints/Sala",
        json={"category_code": None},
        headers=OK,
    )
    assert cleared.status_code == 200
    checkpoint = cleared.json()["checkpoint"]
    assert checkpoint["category"] is None
    assert checkpoint["slug"] == "sala"
    assert checkpoint["building_id"] == 1


def test_map_and_categories_expose_slug_building_and_category(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)
    app_module.topo_map.add_checkpoint("M03 Recepção")
    monkeypatch.setattr(
        app_module.map_db_manager,
        "get_checkpoint_positions",
        lambda: {
            "M03 Recepção": {
                "pos_x_px": 3.0,
                "pos_y_px": 4.0,
                "slug": "m03-recepcao",
                "building_id": 1,
                "category": {"code": "saidas", "label": "Saídas"},
            }
        },
    )
    monkeypatch.setattr(
        app_module.map_db_manager,
        "list_categories",
        lambda: [
            {"code": "atendimento", "label": "Atendimento", "sort_order": 1},
            {"code": "banheiros", "label": "Banheiros", "sort_order": 2},
        ],
    )
    client = TestClient(app)
    listed = client.get("/api/categories")
    assert listed.status_code == 200
    assert [row["code"] for row in listed.json()["categories"]] == ["atendimento", "banheiros"]

    layout = client.get("/api/map")
    assert layout.status_code == 200
    node = next(item for item in layout.json()["nodes"] if item["id"] == "M03 Recepção")
    assert node["slug"] == "m03-recepcao"
    assert node["building_id"] == 1
    assert node["category"] == {"code": "saidas", "label": "Saídas"}
    assert node["pos_x_px"] == 3.0
    assert node["pos_y_px"] == 4.0


def test_create_checkpoint_accepts_optional_category_code(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", PASSWORD)
    seen = {}

    def save(name, category_code=None):
        seen["call"] = (name, category_code)
        if category_code == "inexistente":
            raise UnknownCategoryError(category_code)
        return True

    monkeypatch.setattr(app_module.map_db_manager, "save_checkpoint", save)
    client = TestClient(app)
    created = client.post(
        "/api/checkpoints",
        json={"name": "Sala", "category_code": "banheiros"},
        headers=OK,
    )
    assert created.status_code == 201
    assert seen["call"] == ("Sala", "banheiros")

    invalid = client.post(
        "/api/checkpoints",
        json={"name": "Sala 2", "category_code": "inexistente"},
        headers=OK,
    )
    assert invalid.status_code == 422
