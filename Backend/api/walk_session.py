"""Matcher e caminho visitado por sessão. Não há estado global de usuário."""

from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from map.topological_matcher import TopologicalMatcher

SESSION_HEADER = "X-Pov-Session"
SESSION_TTL_S = 30 * 60
SESSION_MAX = 256
INVALID_SESSION_DETAIL = (
    "Envie o header X-Pov-Session: um id de 8 a 64 caracteres "
    "(letras, números, _ e -)."
)
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class InvalidSessionId(ValueError):
    """O header falta ou não passa na validação. O valor não é ecoado."""


def parse_session_id(raw: str | None) -> str:
    """Aceita só um id opaco curto. Espaço, barra e vazio não entram."""
    if raw is None or _SESSION_ID.fullmatch(raw) is None:
        raise InvalidSessionId(INVALID_SESSION_DETAIL)
    return raw


class _Walk:
    def __init__(self, matcher: TopologicalMatcher, start: str, touched: float) -> None:
        self.matcher = matcher
        self.visited_path = [start]
        self.touched = touched


class WalkSessions:
    """Dicionário com teto e TTL. O lock cobre a tabela e o passo da sessão."""

    def __init__(
        self,
        topo_map,
        *,
        default_start: str = "Recepcao",
        ttl_s: float = SESSION_TTL_S,
        max_sessions: int = SESSION_MAX,
        clock=time.monotonic,
    ) -> None:
        self._map = topo_map
        self._default_start = default_start
        self._ttl_s = float(ttl_s)
        self._max_sessions = int(max_sessions)
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, _Walk] = {}

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
        expired = [
            key for key, item in self._items.items()
            if now - item.touched > self._ttl_s
        ]
        for key in expired:
            del self._items[key]

    def _room_for_newcomer(self) -> None:
        overflow = len(self._items) - self._max_sessions + 1
        if overflow <= 0:
            return
        oldest = sorted(self._items, key=lambda key: self._items[key].touched)
        for key in oldest[:overflow]:
            del self._items[key]

    @contextmanager
    def hold(
        self,
        session_id: str,
        *,
        reset: bool = False,
        start_node: str | None = None,
    ) -> Iterator[_Walk]:
        """Devolve a caminhada desta sessão. Outra sessão é outro objeto."""
        now = self._clock()
        with self._lock:
            self._purge(now)
            current = self._items.get(session_id)
            if reset or current is None:
                if current is not None:
                    del self._items[session_id]
                self._room_for_newcomer()
                start = self._start_for_new(start_node, explicit=reset)
                current = _Walk(
                    TopologicalMatcher(self._map, starting_node=start),
                    start,
                    now,
                )
                self._items[session_id] = current
            else:
                current.touched = now
            yield current
