"""Senha do editor: 503 sem env, 401 sem/errada, escrita protegida no app."""

from __future__ import annotations

import ast
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException

from argon2 import PasswordHasher

import api.editor_auth as editor_auth
from api.editor_auth import (
    BAD_HASH_DETAIL,
    BUSY_DETAIL,
    LOCKED_DETAIL,
    MISSING_HASH_DETAIL,
    VERIFY_SLOTS,
    _MAX_TRACKED_CLIENTS,
    _failures,
    check_editor_password,
    client_key,
    make_password_hash,
    note_failure,
    require_editor_password,
    set_attempt_limit,
    too_many_attempts,
)

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
    "check_editor_auth",
    "download_sensor_log_csv",
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
    "health",
    "localize_user",
    "get_current_location",
}


def _use_hash(monkeypatch, password: str = "segredo-do-editor") -> None:
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", make_password_hash(password))
    monkeypatch.delenv("EDITOR_PASSWORD", raising=False)


def test_missing_env_is_503(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    with pytest.raises(HTTPException) as exc:
        check_editor_password("qualquer")
    assert exc.value.status_code == 503
    assert exc.value.detail == MISSING_HASH_DETAIL


def test_empty_env_is_503(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", "")
    with pytest.raises(HTTPException) as exc:
        check_editor_password("qualquer")
    assert exc.value.status_code == 503


def test_plaintext_env_is_not_accepted(monkeypatch):
    monkeypatch.delenv("EDITOR_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("EDITOR_PASSWORD", "segredo-do-editor")
    with pytest.raises(HTTPException) as exc:
        check_editor_password("segredo-do-editor")
    assert exc.value.status_code == 503


def test_invalid_hash_is_503(monkeypatch):
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", "nao-e-hash")
    with pytest.raises(HTTPException) as exc:
        check_editor_password("segredo-do-editor")
    assert exc.value.status_code == 503
    assert exc.value.detail == BAD_HASH_DETAIL


def test_missing_or_wrong_header_is_401(monkeypatch):
    _use_hash(monkeypatch)
    for provided in (None, "", "outra"):
        with pytest.raises(HTTPException) as exc:
            check_editor_password(provided)
        assert exc.value.status_code == 401


def test_correct_password_passes(monkeypatch):
    _use_hash(monkeypatch)
    check_editor_password("segredo-do-editor")


def test_hash_is_argon2id_and_auth_does_not_load_dotenv():
    encoded = make_password_hash("segredo-do-editor")
    assert encoded.startswith("$argon2id$")
    PasswordHasher().verify(encoded, "segredo-do-editor")
    source = (BACKEND_ROOT / "api" / "editor_auth.py").read_text(encoding="utf-8")
    assert "PasswordHasher" in source
    assert "Type.ID" in source
    assert "verify" in source
    assert "load_dotenv" not in source
    assert "import dotenv" not in source
    script = (BACKEND_ROOT / "scripts" / "hash_password.py").read_text(encoding="utf-8")
    assert "getpass.getpass" in script
    assert "sys.argv" in script


class _Client:
    def __init__(self, host: str, headers: dict | None = None) -> None:
        self.client = type("Peer", (), {"host": host})()
        self.headers = headers or {}


def test_attempt_limit_locks_only_that_client():
    set_attempt_limit(2)
    note_failure("203.0.113.8", now=0)
    note_failure("203.0.113.8", now=1)
    assert too_many_attempts("203.0.113.8", now=2) is True
    assert too_many_attempts("203.0.113.9", now=2) is False
    assert too_many_attempts("203.0.113.8", now=400) is False


def test_require_editor_password_returns_429(monkeypatch):
    _use_hash(monkeypatch)
    set_attempt_limit(2)
    request = _Client("198.51.100.4")
    for _ in range(2):
        with pytest.raises(HTTPException) as exc:
            require_editor_password(request, x_editor_password="errada")
        assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as locked:
        require_editor_password(request, x_editor_password="errada")
    assert locked.value.status_code == 429
    assert locked.value.detail == LOCKED_DETAIL


def test_untrusted_peer_ignores_forwarded_headers(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    loopback = _Client("127.0.0.1", {
        "cf-connecting-ip": "203.0.113.50",
        "x-forwarded-for": "198.51.100.9",
    })
    assert client_key(loopback) == "127.0.0.1"
    public = _Client("203.0.113.7", {"cf-connecting-ip": "198.51.100.9"})
    assert client_key(public) == "203.0.113.7"


def test_trusted_proxy_list_is_explicit(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
    request = _Client("127.0.0.1", {"cf-connecting-ip": "203.0.113.50"})
    assert client_key(request) == "203.0.113.50"
    monkeypatch.setenv("TRUSTED_PROXIES", "*")
    assert client_key(request) == "127.0.0.1"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "--no-proxy-headers" in readme
    assert "forwarded-allow-ips=127.0.0.1" not in readme
    assert "forwarded-allow-ips=*" not in readme
    assert "forwarded-allow-ips *" not in readme


def test_forwarded_for_uses_rightmost_untrusted(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1, 10.0.0.8")
    chained = _Client("127.0.0.1", {
        "x-forwarded-for": "203.0.113.9, 198.51.100.20, 10.0.0.8",
    })
    assert client_key(chained) == "198.51.100.20"
    spoofed_left = _Client("127.0.0.1", {
        "x-forwarded-for": "203.0.113.9, 198.51.100.20",
    })
    assert client_key(spoofed_left) == "198.51.100.20"


def test_rotating_forwarded_headers_do_not_bypass_429(monkeypatch):
    _use_hash(monkeypatch)
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    set_attempt_limit(2)
    for index in range(2):
        request = _Client("198.51.100.8", {
            "cf-connecting-ip": f"203.0.113.{index}",
            "x-forwarded-for": f"198.51.100.{index}",
        })
        with pytest.raises(HTTPException) as exc:
            require_editor_password(request, x_editor_password="errada")
        assert exc.value.status_code == 401
    rotated = _Client("198.51.100.8", {
        "cf-connecting-ip": "203.0.113.99",
        "x-forwarded-for": "198.51.100.99",
    })
    with pytest.raises(HTTPException) as locked:
        require_editor_password(rotated, x_editor_password="errada")
    assert locked.value.status_code == 429


def test_cached_password_skips_argon2(monkeypatch):
    _use_hash(monkeypatch)
    request = _Client("203.0.113.70")
    require_editor_password(request, x_editor_password="segredo-do-editor")

    def boom(_encoded, _password):
        raise AssertionError("senha já conferida não repete o argon2")

    class _Hasher:
        def verify(self, encoded, password):
            boom(encoded, password)

    monkeypatch.setattr("api.editor_auth._hasher", _Hasher())
    require_editor_password(request, x_editor_password="segredo-do-editor")


def test_forty_parallel_bad_attempts_do_not_count_slot_miss(monkeypatch):
    _use_hash(monkeypatch)
    set_attempt_limit(8)
    monkeypatch.setattr("api.editor_auth.SLOT_WAIT_S", 0.25)
    gate = threading.Event()
    inside = threading.Semaphore(0)

    def verify(_encoded, _password):
        inside.release()
        assert gate.wait(timeout=3)
        raise VerifyMismatchError()

    class _SlowHasher:
        def verify(self, _encoded, _password):
            verify(_encoded, _password)

    monkeypatch.setattr("api.editor_auth._hasher", _SlowHasher())
    request = _Client("203.0.113.40")

    def once() -> HTTPException | None:
        try:
            require_editor_password(request, x_editor_password="errada")
        except HTTPException as exc:
            return exc
        return None

    with ThreadPoolExecutor(max_workers=40) as pool:
        pending = [pool.submit(once) for _ in range(40)]
        for _ in range(VERIFY_SLOTS):
            assert inside.acquire(timeout=3)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if sum(item.done() for item in pending) >= 40 - VERIFY_SLOTS:
                break
            time.sleep(0.01)
        gate.set()
        outcomes = [item.result(timeout=5) for item in pending]
    codes = [200 if item is None else item.status_code for item in outcomes]
    assert codes.count(200) == 0
    assert codes.count(401) == VERIFY_SLOTS
    assert codes.count(429) == 0
    assert codes.count(503) == 40 - VERIFY_SLOTS
    for item in outcomes:
        if item is not None and item.status_code == 503:
            assert item.detail == BUSY_DETAIL
            assert item.headers is not None
            assert item.headers["Retry-After"] == str(max(1, int(round(editor_auth.SLOT_WAIT_S))))
    assert too_many_attempts("203.0.113.40") is False


def test_failure_log_is_bounded():
    now = 1_000_000.0
    for index in range(_MAX_TRACKED_CLIENTS + 25):
        note_failure(f"client-{index}", now=now)
    assert len(_failures) <= _MAX_TRACKED_CLIENTS


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
    assert any(line.strip() == "EDITOR_PASSWORD_HASH=" for line in example.splitlines())
    assert "$argon2" not in example
    assert "EDITOR_PASSWORD=" not in example
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in {line.strip() for line in ignored}
