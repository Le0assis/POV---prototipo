"""Senha do editor do mapa.

No ambiente fica só ``EDITOR_PASSWORD_HASH`` (argon2id). A senha em claro
não é aceita. Sem o hash, a escrita responde 503. Header ausente ou
diferente: 401. Hash malformado: 503.

O limite (8 a cada 5 minutos) e o incremento acontecem no mesmo lock.
No máximo quatro ``verify`` ao mesmo tempo; o que não pega vaga responde
429, sem entrar na fila do argon2. A senha é conferida antes de qualquer
conexão MySQL.

``CF-Connecting-IP`` e ``X-Forwarded-For`` só valem se o par do socket
estiver em ``TRUSTED_PROXIES`` (lista explícita; ``*`` não entra). O
uvicorn deve usar ``--forwarded-allow-ips`` com essa mesma lista, nunca
``*``.
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
_MAX_TRACKED_CLIENTS = 4096
VERIFY_SLOTS = 4
_failures: dict[str, list[float]] = {}
_guard = threading.Lock()
_verify_slots = threading.BoundedSemaphore(VERIFY_SLOTS)

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


def trusted_proxy_peers() -> set[str]:
    """Pares de socket que podem informar o cliente. ``*`` não é aceito."""
    raw = os.environ.get("TRUSTED_PROXIES", "")
    peers = set()
    for item in raw.split(","):
        peer = item.strip()
        if peer and peer != "*":
            peers.add(peer)
    return peers


def _forwarded_client(request: Request) -> str:
    cloudflare = request.headers.get("cf-connecting-ip", "").strip()
    if cloudflare:
        return cloudflare.split(",")[0].strip()
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return ""


def client_key(request: Request) -> str:
    peer = request.client.host if request.client is not None and request.client.host else ""
    if peer and peer in trusted_proxy_peers():
        forwarded = _forwarded_client(request)
        if forwarded and forwarded != "*":
            return forwarded
    return peer or "unknown"


def _clock(now: float | None) -> float:
    return time.monotonic() if now is None else now


def _prune_locked(current: float) -> None:
    expired = []
    for ip, stamps in _failures.items():
        fresh = [stamp for stamp in stamps if current - stamp < _WINDOW_S]
        if fresh:
            _failures[ip] = fresh
        else:
            expired.append(ip)
    for ip in expired:
        del _failures[ip]
    _cap_locked()


def _cap_locked() -> None:
    overflow = len(_failures) - _MAX_TRACKED_CLIENTS
    if overflow <= 0:
        return
    oldest = sorted(_failures, key=lambda ip: _failures[ip][0])
    for ip in oldest[:overflow]:
        del _failures[ip]


def too_many_attempts(ip: str, now: float | None = None) -> bool:
    current = _clock(now)
    with _guard:
        _prune_locked(current)
        recent = _failures.get(ip, [])
        return len(recent) >= _MAX_ATTEMPTS


def note_failure(ip: str, now: float | None = None) -> None:
    current = _clock(now)
    with _guard:
        _prune_locked(current)
        recent = _failures.get(ip, [])
        recent.append(current)
        _failures[ip] = recent
        _cap_locked()


def _reserve_attempt(ip: str, now: float | None = None) -> float | None:
    """Conta a tentativa no mesmo lock da consulta. None se o limite já fechou."""
    current = _clock(now)
    with _guard:
        _prune_locked(current)
        recent = list(_failures.get(ip, []))
        if len(recent) >= _MAX_ATTEMPTS:
            return None
        recent.append(current)
        _failures[ip] = recent
        _cap_locked()
        return current


def _drop_attempt(ip: str, stamp: float) -> None:
    with _guard:
        recent = [item for item in _failures.get(ip, []) if item != stamp]
        if recent:
            _failures[ip] = recent
        else:
            _failures.pop(ip, None)


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
    """Confere a senha antes de qualquer sessão MySQL da rota."""
    ip = client_key(request)
    stamp = _reserve_attempt(ip)
    if stamp is None:
        raise HTTPException(status_code=429, detail=LOCKED_DETAIL)
    if not _verify_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail=LOCKED_DETAIL)
    try:
        try:
            check_editor_password(x_editor_password)
        except HTTPException as exc:
            if exc.status_code != 401:
                _drop_attempt(ip, stamp)
            raise
        clear_failures(ip)
    finally:
        _verify_slots.release()
