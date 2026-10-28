"""Sessões do matcher: id válido, TTL, teto e isolamento."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import api.app as app_module
from api.walk_session import InvalidSessionId, SessionLimit, WalkSessions, parse_session_id

pytestmark = pytest.mark.unit


class _Map:
    def __init__(self) -> None:
        self.nodes: dict[str, str] = {}


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_app_does_not_keep_a_process_wide_matcher():
    text = (Path(__file__).resolve().parents[2] / "api" / "app.py").read_text(encoding="utf-8")
    assert "global matcher" not in text
    assert "visited_path = [" not in text
    assert not hasattr(app_module, "matcher")
    assert not hasattr(app_module, "visited_path")
    assert app_module.walk_sessions is not None


def test_session_id_accepts_a_device_token_and_rejects_the_rest():
    assert parse_session_id("device-0001") == "device-0001"
    assert parse_session_id("a" * 8) == "a" * 8
    assert parse_session_id("A" * 64) == "A" * 64
    for raw in (None, "", "curto", "a" * 65, "tem espaco", "barra/reta", "acento-ção", "  device-0001"):
        with pytest.raises(InvalidSessionId):
            parse_session_id(raw)


def test_inactivity_expires_the_session_and_a_touch_renews_it():
    clock = _Clock()
    store = WalkSessions(_Map(), ttl_s=10, clock=clock)
    clock.now = 1
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        state.visited_path.append("marca-a")
    clock.now = 9
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path[-1] == "marca-a"
    clock.now = 19
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path[-1] == "marca-a"
    clock.now = 30
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path == []


def test_a_full_table_refuses_the_newcomer_and_keeps_the_others():
    clock = _Clock()
    store = WalkSessions(_Map(), ttl_s=10, max_sessions=2, max_per_ip=8, clock=clock)
    clock.now = 1
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        state.visited_path.append("marca-a")
    clock.now = 2
    with store.hold("bbbbbbbb", client_ip="203.0.113.2") as state:
        state.visited_path.append("marca-b")
    clock.now = 3
    with pytest.raises(SessionLimit) as exc:
        with store.hold("cccccccc", client_ip="198.51.100.3"):
            pass
    assert exc.value.retry_after >= 1
    with store.hold("bbbbbbbb", client_ip="203.0.113.2") as state:
        assert state.visited_path[-1] == "marca-b"
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path[-1] == "marca-a"
    assert len(store) == 2


def test_one_address_stops_at_eight_and_does_not_evict_another():
    clock = _Clock()
    store = WalkSessions(_Map(), ttl_s=100, max_per_ip=2, clock=clock)
    clock.now = 5
    with store.hold("aaaaaaa1", client_ip="203.0.113.1") as state:
        state.visited_path.append("fica")
    with store.hold("aaaaaaa2", client_ip="203.0.113.1"):
        pass
    with pytest.raises(SessionLimit) as exc:
        with store.hold("aaaaaaa3", client_ip="203.0.113.1"):
            pass
    assert exc.value.retry_after == 100
    with store.hold("bbbbbbb1", client_ip="203.0.113.2") as state:
        state.visited_path.append("outro")
    with store.hold("bbbbbbb2", client_ip="203.0.113.2"):
        pass
    with store.hold("aaaaaaa1", client_ip="203.0.113.1", reset=True) as state:
        assert state.visited_path == []
    with pytest.raises(SessionLimit):
        with store.hold("aaaaaaa1", client_ip="203.0.113.2", reset=True):
            pass
    with store.hold("bbbbbbb1", client_ip="203.0.113.2") as state:
        assert state.visited_path[-1] == "outro"
    with store.hold("aaaaaaa1", client_ip="203.0.113.1") as state:
        assert state.visited_path == []
    assert len(store) == 4


def test_another_ip_does_not_see_the_path_or_renew_the_owner():
    clock = _Clock()
    store = WalkSessions(_Map(), ttl_s=10, clock=clock)
    clock.now = 0
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        state.visited_path.append("marca-a")
    clock.now = 9
    with store.hold("aaaaaaaa", client_ip="203.0.113.2") as state:
        assert state.visited_path == []
        state.visited_path.append("intruso")
    assert len(store) == 2
    clock.now = 11
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path == []
    with store.hold("aaaaaaaa", client_ip="203.0.113.2") as state:
        assert state.visited_path[-1] == "intruso"


def test_reset_from_another_ip_does_not_replace_the_owner():
    store = WalkSessions(_Map(), ttl_s=100)
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        state.visited_path.append("fica")
    with store.hold("aaaaaaaa", client_ip="203.0.113.2", reset=True) as state:
        assert state.visited_path == []
    with store.hold("aaaaaaaa", client_ip="203.0.113.1") as state:
        assert state.visited_path[-1] == "fica"
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
    assert path_a == ["sessao-aaaa"] * 40
    assert path_b == ["sessao-bbbb"] * 40
