"""Senha do editor do mapa.

No ambiente fica só ``EDITOR_PASSWORD_HASH`` (argon2id). A senha em claro
não é aceita. Sem o hash, a escrita responde 503. Header ausente ou
diferente: 401. Hash malformado: 503.

O limite (8 a cada 5 minutos) reserva a tentativa no mesmo lock antes
do argon2: entram as que estão em curso e as que já falharam. No
limite a resposta é 429, sem conferir. Senha certa ou 503 devolve a
reserva; senha errada fica contada. No máximo quatro ``verify`` ao
mesmo tempo. Quem não pega vaga em cerca de 2s responde 503 com
``Retry-After``. Uma senha que acabou de conferir fica em cache por
cerca de 60s, na chave do HMAC dela: só a mesma senha confere, em
tempo constante, e senha ausente ou vazia nunca passa pelo cache. A
senha é conferida antes de qualquer conexão MySQL.

``CF-Connecting-IP`` e ``X-Forwarded-For`` só valem se o par do socket
estiver em ``TRUSTED_PROXIES`` (lista explícita de IPs ou CIDRs; ``*`` e ``/0`` não entram). No
``X-Forwarded-For`` o cliente é o endereço mais à direita que não está
nessa lista. O uvicorn sobe com ``--no-proxy-headers``: o padrão dele
trata ``127.0.0.1`` como proxy e reescreve o par a partir do header.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
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
# token -> HMAC da senha em curso (None se o header veio vazio).
_pending: dict[str, dict[int, bytes | None]] = {}
_pending_seq = 0
_guard = threading.Lock()
_waiters = threading.Condition(_guard)
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
        _pending.clear()
        _verified_digest = None
        _verified_until = 0.0
        _verified_for = None
        _waiters.notify_all()


def set_attempt_limit(limit: int) -> None:
    global _MAX_ATTEMPTS
    _MAX_ATTEMPTS = int(limit)


def _parse_ip(value: str):
    """Endereço válido ou None. ``::ffff:1.2.3.4`` vira ``1.2.3.4``."""
    try:
        address = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped or address


def trusted_proxy_networks() -> list:
    """Redes de ``TRUSTED_PROXIES``: IP solto ou CIDR, separados por vírgula.

    ``*``, ``0.0.0.0/0``, ``::/0`` e item inválido são ignorados: confiar em
    todo mundo deixaria qualquer um forjar o IP pelo header.
    """
    networks = []
    for item in os.environ.get("TRUSTED_PROXIES", "").split(","):
        entry = item.strip()
        if not entry or entry == "*":
            continue
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if network.prefixlen == 0:
            continue
        networks.append(network)
    return networks


def trusted_proxy_peers() -> set[str]:
    """Texto normalizado dos itens aceitos (compatibilidade e diagnóstico)."""
    return {str(network) for network in trusted_proxy_networks()}


def _is_trusted(value: str, networks: list) -> bool:
    address = _parse_ip(value)
    if address is None:
        return False
    return any(address.version == network.version and address in network for network in networks)


def _rightmost_untrusted(header: str, networks: list) -> str:
    """O endereço mais à direita que não é proxy de confiança.

    A esquerda do ``X-Forwarded-For`` pode ser forjada. Andando da
    direita para a esquerda, o primeiro que não está em ``networks`` é
    o cliente. Item que não é IP encerra a busca sem cliente. Se todos
    forem de confiança, sobra o da esquerda.
    """
    parts = [item.strip() for item in header.split(",") if item.strip()]
    for part in reversed(parts):
        if _is_trusted(part, networks):
            continue
        address = _parse_ip(part)
        return str(address) if address is not None else ""
    if parts:
        address = _parse_ip(parts[0])
        return str(address) if address is not None else ""
    return ""


def _forwarded_client(request: Request, networks: list) -> str:
    cloudflare = request.headers.get("cf-connecting-ip", "").strip()
    if cloudflare:
        return _rightmost_untrusted(cloudflare, networks)
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return _rightmost_untrusted(forwarded, networks)
    return ""


def client_key(request: Request) -> str:
    """IP do cliente para limites (senha do editor, sessões por IP).

    Os headers só contam quando o par do socket está em ``TRUSTED_PROXIES``.
    Atrás do cloudflared o par é ``127.0.0.1`` (ou ``::1``): sem essa
    variável todo mundo divide o mesmo IP e a 9ª sessão é recusada.
    """
    peer = request.client.host if request.client is not None and request.client.host else ""
    if peer:
        networks = trusted_proxy_networks()
        if networks and _is_trusted(peer, networks):
            forwarded = _forwarded_client(request, networks)
            if forwarded:
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


def _cache_hit_locked(provided: str) -> bool:
    """True só se ``provided`` é a senha que o argon2 acabou de aceitar.

    Header ausente ou vazio não entra. A chave é o HMAC dessa senha, não
    um flag de "já passou alguém".
    """
    if not provided:
        return False
    expected = os_hash()
    if (
        not expected
        or _verified_digest is None
        or _verified_for != expected
        or time.monotonic() >= _verified_until
    ):
        return False
    candidate = _password_fingerprint(provided)
    return hmac.compare_digest(_verified_digest, candidate)


def _cached_password_ok(provided: str) -> bool:
    with _guard:
        return _cache_hit_locked(provided)


def _remember_verified_locked(provided: str) -> None:
    global _verified_digest, _verified_until, _verified_for
    if not provided:
        return
    expected = os_hash()
    if not expected:
        return
    _verified_digest = _password_fingerprint(provided)
    _verified_until = time.monotonic() + VERIFIED_TTL_S
    _verified_for = expected


def _used_locked(ip: str) -> int:
    return len(_failures.get(ip, [])) + len(_pending.get(ip, {}))


def _reserve_attempt(ip: str, fingerprint: bytes | None) -> int | None:
    """Ocupa uma vaga (em curso + falhas). None se o limite já fechou."""
    global _pending_seq
    with _guard:
        _prune_locked(time.monotonic())
        pending = _pending.get(ip, {})
        if _used_locked(ip) >= _MAX_ATTEMPTS:
            return None
        _pending_seq += 1
        token = _pending_seq
        pending = dict(pending)
        pending[token] = fingerprint
        _pending[ip] = pending
        return token


def _drop_pending_locked(ip: str, token: int) -> None:
    pending = _pending.get(ip)
    if not pending or token not in pending:
        return
    pending = dict(pending)
    pending.pop(token, None)
    if pending:
        _pending[ip] = pending
    else:
        _pending.pop(ip, None)


def _release_reservation(ip: str, token: int) -> None:
    with _guard:
        _drop_pending_locked(ip, token)
        _waiters.notify_all()


def _commit_failure(ip: str, token: int) -> None:
    with _guard:
        _drop_pending_locked(ip, token)
        current = time.monotonic()
        _prune_locked(current)
        recent = list(_failures.get(ip, []))
        recent.append(current)
        _failures[ip] = recent
        _cap_locked()
        _waiters.notify_all()


def _inflight_locked(ip: str, fingerprint: bytes) -> bool:
    return any(item == fingerprint for item in _pending.get(ip, {}).values())


def _wait_for_same_password(ip: str, provided: str, deadline: float) -> bool:
    """Espera a mesma senha terminar de conferir. Não chama o argon2."""
    fingerprint = _password_fingerprint(provided)
    with _guard:
        while True:
            if _cache_hit_locked(provided):
                _failures.pop(ip, None)
                return True
            if not _inflight_locked(ip, fingerprint):
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _waiters.wait(timeout=remaining)


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

    A vaga (em curso + falhas) é reservada antes do argon2. Senha errada
    converte a reserva em falha. Senha certa, ou 503 por falta de vaga
    de argon2, devolve a reserva. O cache só aceita a mesma senha.
    """
    ip = client_key(request)
    given = x_editor_password if isinstance(x_editor_password, str) else ""
    if given and _cached_password_ok(given):
        clear_failures(ip)
        return
    fingerprint = _password_fingerprint(given) if given else None
    token = _reserve_attempt(ip, fingerprint)
    if token is None:
        if given and _wait_for_same_password(ip, given, time.monotonic() + SLOT_WAIT_S):
            return
        raise HTTPException(status_code=429, detail=LOCKED_DETAIL)
    try:
        deadline = time.monotonic() + SLOT_WAIT_S
        while True:
            if given and _cached_password_ok(given):
                _release_reservation(ip, token)
                clear_failures(ip)
                token = None
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _release_reservation(ip, token)
                token = None
                raise _slot_busy()
            if not _verify_slots.acquire(timeout=min(0.05, remaining)):
                continue
            try:
                if given and _cached_password_ok(given):
                    _release_reservation(ip, token)
                    clear_failures(ip)
                    token = None
                    return
                try:
                    check_editor_password(x_editor_password)
                except HTTPException as exc:
                    if exc.status_code == 401:
                        _commit_failure(ip, token)
                    else:
                        _release_reservation(ip, token)
                    token = None
                    raise
                with _guard:
                    _remember_verified_locked(given)
                    _drop_pending_locked(ip, token)
                    _failures.pop(ip, None)
                    _waiters.notify_all()
                token = None
                return
            finally:
                _verify_slots.release()
    finally:
        if token is not None:
            _release_reservation(ip, token)
