"""Senha do editor do mapa.

No ambiente fica só ``EDITOR_PASSWORD_HASH`` (argon2id). A senha em claro
não é aceita. Sem o hash, a escrita responde 503. Header ausente ou
diferente: 401. Hash malformado: 503.

O limite (8 a cada 5 minutos) e o incremento acontecem no mesmo lock, e
só depois de um argon2 que recusou a senha. No máximo quatro ``verify``
ao mesmo tempo. Quem não pega vaga em cerca de 2s responde 503 com
``Retry-After`` e essa espera não conta como falha. Uma senha que acabou
de conferir fica em cache por cerca de 60s (HMAC comparado em tempo
constante); as outras requisições certas não repetem o argon2. A senha
é conferida antes de qualquer conexão MySQL.

``CF-Connecting-IP`` e ``X-Forwarded-For`` só valem se o par do socket
estiver em ``TRUSTED_PROXIES`` (lista explícita; ``*`` não entra). No
``X-Forwarded-For`` o cliente é o endereço mais à direita que não está
nessa lista. O uvicorn sobe com ``--no-proxy-headers``: o padrão dele
trata ``127.0.0.1`` como proxy e reescreve o par a partir do header.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
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
SLOT_WAIT_S = 2.0
VERIFIED_TTL_S = 60.0
_failures: dict[str, list[float]] = {}
_guard = threading.Lock()
_verify_slots = threading.BoundedSemaphore(VERIFY_SLOTS)
_cache_key = secrets.token_bytes(32)
_verified_digest: bytes | None = None
_verified_until = 0.0
_verified_for: str | None = None

MISSING_HASH_DETAIL = "EDITOR_PASSWORD_HASH não está definida no ambiente do servidor."
BAD_HASH_DETAIL = "EDITOR_PASSWORD_HASH não é um hash argon2id válido."
UNAUTHORIZED_DETAIL = "Senha do editor ausente ou inválida."
LOCKED_DETAIL = "Muitas tentativas. Espere alguns minutos e tente de novo."
BUSY_DETAIL = "Muitas conferências ao mesmo tempo. Tente de novo em instantes."


def make_password_hash(password: str) -> str:
    """Hash argon2id da senha. O script de linha de comando usa esta função."""
    return _hasher.hash(password)


def reset_attempts() -> None:
    global _verified_digest, _verified_until, _verified_for
    with _guard:
        _failures.clear()
        _verified_digest = None
        _verified_until = 0.0
        _verified_for = None


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


def _rightmost_untrusted(header: str, trusted: set[str]) -> str:
    """O endereço mais à direita que o proxy não assina.

    A esquerda do ``X-Forwarded-For`` pode ser forjada. Andando da
    direita para a esquerda, o primeiro que não está em ``trusted`` é
    o cliente. Se todos forem de confiança, sobra o da esquerda.
    """
    parts = []
    for item in header.split(","):
        part = item.strip()
        if part and part != "*":
            parts.append(part)
    for part in reversed(parts):
        if part not in trusted:
            return part
    return parts[0] if parts else ""


def _forwarded_client(request: Request) -> str:
    trusted = trusted_proxy_peers()
    cloudflare = request.headers.get("cf-connecting-ip", "").strip()
    if cloudflare:
        return _rightmost_untrusted(cloudflare, trusted)
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return _rightmost_untrusted(forwarded, trusted)
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


def clear_failures(ip: str) -> None:
    with _guard:
        _failures.pop(ip, None)


def _password_fingerprint(password: str) -> bytes:
    return hmac.new(_cache_key, password.encode("utf-8"), hashlib.sha256).digest()


def _cached_password_ok(provided: str) -> bool:
    if not provided:
        return False
    expected = os_hash()
    if not expected:
        return False
    candidate = _password_fingerprint(provided)
    with _guard:
        if (
            _verified_digest is None
            or _verified_for != expected
            or time.monotonic() >= _verified_until
        ):
            return False
        return hmac.compare_digest(_verified_digest, candidate)


def _remember_verified(provided: str) -> None:
    if not provided:
        return
    expected = os_hash()
    if not expected:
        return
    digest = _password_fingerprint(provided)
    global _verified_digest, _verified_until, _verified_for
    with _guard:
        _verified_digest = digest
        _verified_until = time.monotonic() + VERIFIED_TTL_S
        _verified_for = expected


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


def _slot_busy() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=BUSY_DETAIL,
        headers={"Retry-After": str(max(1, int(round(SLOT_WAIT_S))))},
    )


def require_editor_password(
    request: Request,
    x_editor_password: str | None = Header(default=None),
) -> None:
    """Confere a senha antes de qualquer sessão MySQL da rota.

    Senha errada é a única coisa que entra no 429. Sem vaga de argon2 a
    reserva não fica: espera até ``SLOT_WAIT_S`` e, se o cache não
    cobrir, responde 503.
    """
    ip = client_key(request)
    given = x_editor_password if isinstance(x_editor_password, str) else ""
    if too_many_attempts(ip):
        raise HTTPException(status_code=429, detail=LOCKED_DETAIL)
    if _cached_password_ok(given):
        clear_failures(ip)
        return
    deadline = time.monotonic() + SLOT_WAIT_S
    while True:
        if _cached_password_ok(given):
            clear_failures(ip)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _slot_busy()
        if not _verify_slots.acquire(timeout=min(0.05, remaining)):
            continue
        try:
            if _cached_password_ok(given):
                clear_failures(ip)
                return
            try:
                check_editor_password(x_editor_password)
            except HTTPException as exc:
                if exc.status_code == 401:
                    note_failure(ip)
                raise
            clear_failures(ip)
            _remember_verified(given)
            return
        finally:
            _verify_slots.release()
