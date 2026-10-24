"""Matcher e caminho visitado por sessão. Não há estado global de usuário.

O TTL conta a partir do último uso. Acima de 8 sessões no mesmo IP, ou
do teto global, a sessão nova é recusada: a mais antiga de outro cliente
não sai para abrir vaga.
"""

from __future__ import annotations

import math
import re
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from map.topological_matcher import TopologicalMatcher

SESSION_HEADER = "X-Pov-Session"
SESSION_TTL_S = 30 * 60
SESSION_MAX = 256
SESSION_MAX_PER_IP = 8
INVALID_SESSION_DETAIL = (
    "Envie o header X-Pov-Session: um id de 8 a 64 caracteres "
    "(letras, números, _ e -)."
)
SESSION_LIMIT_DETAIL = (
    "Muitas sessões neste endereço. Reuse o X-Pov-Session ou espere a inatividade."
)
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class InvalidSessionId(ValueError):
    """O header falta ou não passa na validação. O valor não é ecoado."""


class SessionLimit(Exception):
    """Este IP, ou a tabela inteira, já está no teto. Ninguém é expulso."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(SESSION_LIMIT_DETAIL)
        self.retry_after = max(1, int(retry_after))


def parse_session_id(raw: str | None) -> str:
    """Aceita só um id opaco curto. Espaço, barra e vazio não entram."""
    if raw is None or _SESSION_ID.fullmatch(raw) is None:
        raise InvalidSessionId(INVALID_SESSION_DETAIL)
    return raw


class _Walk:
    def __init__(self, matcher: TopologicalMatcher, start: str, touched: float, client_ip: str) -> None:
        self.matcher = matcher
        self.visited_path = [start]
        self.touched = touched
        self.client_ip = client_ip


class WalkSessions:
    """Dicionário com teto e TTL. O lock cobre a tabela e o passo da sessão."""

    def __init__(
        self,
        topo_map,
        *,
        default_start: str = "Recepcao",
        ttl_s: float = SESSION_TTL_S,
        max_sessions: int = SESSION_MAX,
        max_per_ip: int = SESSION_MAX_PER_IP,
        clock=time.monotonic,
    ) -> None:
        self._map = topo_map
        self._default_start = default_start
        self._ttl_s = float(ttl_s)
        self._max_sessions = int(max_sessions)
        self._max_per_ip = int(max_per_ip)
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[tuple[str, str], _Walk] = {}

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _start_for_new(self, preferred: str | None, *, explicit: bool) -> str:
        nodes = getattr(self._map, "nodes", None) or {}
        if explicit and preferred and preferred in nodes:
            return preferred
        if not explicit and self._default_start in nodes:
            return self._default_start
        if nodes:
            return next(iter(nodes))
        return self._default_start

    def _purge(self, now: float) -> None:
        """Sai quem não foi usado dentro do TTL. Uso renova ``touched``."""
        expired = [
            key for key, item in self._items.items()
            if now - item.touched > self._ttl_s
        ]
        for key in expired:
            del self._items[key]

    def _retry_after(self, keys: list[str], now: float) -> int:
        if not keys:
            return 1
        oldest = min(self._items[key].touched for key in keys)
        remaining = self._ttl_s - (now - oldest)
        return max(1, math.ceil(remaining))

    def _ensure_room(self, client_ip: str, now: float) -> None:
        """Recusa a sessão nova. Não apaga a de outro IP para abrir vaga."""
        owned = [key for key, item in self._items.items() if item.client_ip == client_ip]
        if len(owned) >= self._max_per_ip:
            raise SessionLimit(self._retry_after(owned, now))
        if len(self._items) >= self._max_sessions:
            raise SessionLimit(self._retry_after(list(self._items), now))

    @contextmanager
    def hold(
        self,
        session_id: str,
        *,
        reset: bool = False,
        start_node: str | None = None,
        client_ip: str | None = None,
    ) -> Iterator[_Walk]:
        """Devolve a caminhada desta sessão. Outra sessão é outro objeto.

        ``client_ip`` é o mesmo valor de ``editor_auth.client_key``, o IP
        confiável. A sessão fica presa a esse IP. Outro endereço não acha
        a linha, não renova o TTL e não vê o caminho.
        """
        owner = (client_ip or "").strip() or "unknown"
        now = self._clock()
        with self._lock:
            self._purge(now)
            key = (session_id, owner)
            current = self._items.get(key)
            if reset or current is None:
                if not reset or current is None:
                    self._ensure_room(owner, now)
                if current is not None:
                    del self._items[key]
                start = self._start_for_new(start_node, explicit=reset)
                current = _Walk(
                    TopologicalMatcher(self._map, starting_node=start),
                    start,
                    now,
                    owner,
                )
                self._items[key] = current
            else:
                current.touched = now
            yield current
