"""Sessões do matcher: id válido, TTL, teto e isolamento."""

from __future__ import annotations

import threading

import pytest

from api.walk_session import InvalidSessionId, WalkSessions, parse_session_id

pytestmark = pytest.mark.unit


class _Map:
    def __init__(self) -> None:
        self.nodes: dict[str, str] = {}


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_session_id_accepts_a_device_token_and_rejects_the_rest():
    assert parse_session_id("device-0001") == "device-0001"
    assert parse_session_id("a" * 8) == "a" * 8
    assert parse_session_id("A" * 64) == "A" * 64
    for raw in (None, "", "curto", "a" * 65, "tem espaco", "barra/reta", "acento-ção", "  device-0001"):
        with pytest.raises(InvalidSessionId):
            parse_session_id(raw)


def test_expired_session_starts_over_and_the_cap_drops_the_oldest():
    clock = _Clock()
    store = WalkSessions(_Map(), ttl_s=10, max_sessions=2, clock=clock)
    clock.now = 1
    with store.hold("aaaaaaaa") as state:
        state.visited_path.append("marca-a")
    clock.now = 2
    with store.hold("bbbbbbbb") as state:
        state.visited_path.append("marca-b")
    clock.now = 12
    with store.hold("aaaaaaaa") as state:
        assert state.visited_path == ["Recepcao"]
    clock.now = 13
    with store.hold("cccccccc") as state:
        state.visited_path.append("marca-c")
    with store.hold("bbbbbbbb") as state:
        assert state.visited_path == ["Recepcao"]
    with store.hold("cccccccc") as state:
        assert state.visited_path[-1] == "marca-c"
    assert len(store) == 2


def test_two_sessions_keep_their_own_matcher_under_threads():
    store = WalkSessions(_Map(), ttl_s=60, max_sessions=8)
    start = threading.Barrier(2)

    def walk(session_id: str) -> None:
        start.wait()
        for _ in range(40):
            with store.hold(session_id) as state:
                state.matcher.accumulated_distance += 0.25
                state.visited_path.append(session_id)

    left = threading.Thread(target=walk, args=("sessao-aaaa",))
    right = threading.Thread(target=walk, args=("sessao-bbbb",))
    left.start()
    right.start()
    left.join()
    right.join()

    with store.hold("sessao-aaaa") as first:
        distance_a = first.matcher.accumulated_distance
        path_a = list(first.visited_path)
        matcher_a = first.matcher
    with store.hold("sessao-bbbb") as second:
        distance_b = second.matcher.accumulated_distance
        path_b = list(second.visited_path)
        matcher_b = second.matcher
    assert matcher_a is not matcher_b
    assert distance_a == pytest.approx(10.0)
    assert distance_b == pytest.approx(10.0)
    assert path_a == ["Recepcao", *["sessao-aaaa"] * 40]
    assert path_b == ["Recepcao", *["sessao-bbbb"] * 40]
