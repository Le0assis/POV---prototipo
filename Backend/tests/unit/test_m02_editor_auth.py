"""Senha do editor: 503 sem env, 401 sem/errada, escrita protegida no app."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.editor_auth import check_editor_password

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

PROTECTED = {
    "process_raw_edge",
    "create_checkpoint",
    "create_edge",
    "delete_route",
    "update_checkpoint_position",
    "put_map_config",
    "create_route",
    "reset_session",
    "update_checkpoint_category",
}
PUBLIC = {
    "get_map_layout",
    "list_categories",
    "resolve_checkpoint",
    "get_connections",
    "get_connection_by_id",
    "get_map_config",
    "get_pdr_config",
    "get_all_routes",
    "download_sensor_log_csv",
    "localize_user",
}


def test_missing_env_is_503(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)
    with pytest.raises(HTTPException) as exc:
        check_editor_password("qualquer")
    assert exc.value.status_code == 503


def test_empty_env_is_503(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", "")
    with pytest.raises(HTTPException) as exc:
        check_editor_password("qualquer")
    assert exc.value.status_code == 503


def test_missing_or_wrong_header_is_401(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", "segredo-do-editor")
    for provided in (None, "", "outra"):
        with pytest.raises(HTTPException) as exc:
            check_editor_password(provided)
        assert exc.value.status_code == 401


def test_correct_password_passes(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD", "segredo-do-editor")
    check_editor_password("segredo-do-editor")


def test_comparison_is_constant_time_and_does_not_load_dotenv():
    source = (BACKEND_ROOT / "api" / "editor_auth.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in source
    assert "hashlib.sha256" in source
    assert "load_dotenv" not in source
    assert "import dotenv" not in source


def _guarded_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for default in list(node.args.defaults) + list(node.args.kw_defaults or []):
            if default is None:
                continue
            for child in ast.walk(default):
                if isinstance(child, ast.Name) and child.id == "require_editor_password":
                    guarded.add(node.name)
    return guarded


def test_write_routes_require_password_and_reads_stay_open():
    guarded = _guarded_functions(BACKEND_ROOT / "api" / "app.py")
    assert PROTECTED <= guarded
    assert PUBLIC.isdisjoint(guarded)


def test_env_example_has_no_secret_and_gitignore_covers_dotenv():
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert any(line.strip() == "EDITOR_PASSWORD=" for line in example.splitlines())
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in {line.strip() for line in ignored}
