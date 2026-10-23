"""Senha do editor do mapa.

No ambiente fica só ``EDITOR_PASSWORD_HASH`` (argon2id). A senha em claro
não é aceita. Sem o hash, a escrita responde 503. Header ausente ou
diferente: 401. Hash malformado: 503. Tentativas erradas são limitadas
por cliente (8 a cada 5 minutos); no túnel, o par é 127.0.0.1 e o IP real
vem de ``CF-Connecting-IP``.
"""

from __future__ import annotations

import os
import threading
import time

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Header, HTTPException, Request

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)

_WINDOW_S = 300.0
_MAX_ATTEMPTS = 8
_failures: dict[str, list[float]] = {}
_guard = threading.Lock()

MISSING_HASH_DETAIL = "EDITOR_PASSWORD_HASH não está definida no ambiente do servidor."
BAD_HASH_DETAIL = "EDITOR_PASSWORD_HASH não é um hash argon2id válido."
UNAUTHORIZED_DETAIL = "Senha do editor ausente ou inválida."
LOCKED_DETAIL = "Muitas tentativas. Espere alguns minutos e tente de novo."


def make_password_hash(password: str) -> str:
    """Hash argon2id da senha. O script de linha de comando usa esta função."""
    return _hasher.hash(password)


def reset_attempts() -> None:
    with _guard:
        _failures.clear()


def set_attempt_limit(limit: int) -> None:
    global _MAX_ATTEMPTS
    _MAX_ATTEMPTS = int(limit)


def client_key(request: Request) -> str:
    peer = request.client.host if request.client is not None and request.client.host else ""
    if peer in {"127.0.0.1", "::1", "localhost"}:
        forwarded = request.headers.get("cf-connecting-ip", "").strip()
        if forwarded:
            return forwarded
    return peer or "unknown"


def too_many_attempts(ip: str, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    with _guard:
        recent = [stamp for stamp in _failures.get(ip, []) if current - stamp < _WINDOW_S]
        _failures[ip] = recent
        return len(recent) >= _MAX_ATTEMPTS


def note_failure(ip: str, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    with _guard:
        recent = [stamp for stamp in _failures.get(ip, []) if current - stamp < _WINDOW_S]
        recent.append(current)
        _failures[ip] = recent


def clear_failures(ip: str) -> None:
    with _guard:
        _failures.pop(ip, None)


def check_editor_password(provided: str | None) -> None:
    expected = os_hash()
    if expected is None or expected == "":
        raise HTTPException(status_code=503, detail=MISSING_HASH_DETAIL)
    given = provided if isinstance(provided, str) else ""
    try:
        _hasher.verify(expected, given)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL) from None
    except (InvalidHashError, VerificationError):
        raise HTTPException(status_code=503, detail=BAD_HASH_DETAIL) from None
    if _hasher.check_needs_rehash(expected):
        # O hash antigo ainda confere. Não regravamos o .env daqui.
        return


def os_hash() -> str | None:
    return os.environ.get("EDITOR_PASSWORD_HASH")


def require_editor_password(
    request: Request,
    x_editor_password: str | None = Header(default=None),
) -> None:
    ip = client_key(request)
    if too_many_attempts(ip):
        raise HTTPException(status_code=429, detail=LOCKED_DETAIL)
    try:
        check_editor_password(x_editor_password)
    except HTTPException as exc:
        if exc.status_code == 401:
            note_failure(ip)
        raise
    clear_failures(ip)
