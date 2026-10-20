"""Integração da trajetória e contrato de leitura. Sem MySQL."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pdr.trajectory import (
    displacement_m,
    integrate_walk,
    path_points,
    points_for_api,
    straight_path,
    trace_payload,
)

pytestmark = pytest.mark.unit


def test_integrate_uses_right_and_up_axes():
    t0 = 1_700_000_000.0
    events = [
        SimpleNamespace(timestamp=t0 + 0.5, heading_rad=0.0, step_length_m=2.0),
        SimpleNamespace(timestamp=t0 + 1.1, heading_rad=math.pi / 2, step_length_m=2.0),
    ]
    built = integrate_walk(events, t0)
    assert built["polyline"][0] == [0.0, 0.0]
    assert built["steps"][0]["x_m"] == pytest.approx(2.0)
    assert built["steps"][0]["y_m"] == pytest.approx(0.0)
    assert built["steps"][1]["x_m"] == pytest.approx(2.0)
    assert built["steps"][1]["y_m"] == pytest.approx(2.0)
    assert built["steps"][0]["t_ms"] == 500
    assert built["steps"][1]["t_ms"] == 1100
    assert built["total_distance_m"] == pytest.approx(4.0)
    assert built["net_heading_rad"] == pytest.approx(math.pi / 4)


def test_path_is_xy_t_array_including_origin():
    started = 1_700_000_000.0
    steps = [
        {"step_index": 0, "t_ms": 500, "heading_rad": 0.0, "step_length_m": 2.0, "x_m": 2.0, "y_m": 0.0},
        {"step_index": 1, "t_ms": 1100, "heading_rad": math.pi / 2, "step_length_m": 2.0, "x_m": 2.0, "y_m": 2.0},
    ]
    path = path_points(started, steps)
    assert len(path) == len(steps) + 1
    assert path[0] == {"x": 0.0, "y": 0.0, "t": started}
    assert set(path[1]) == {"x", "y", "t"}
    assert path[1]["t"] == pytest.approx(started + 0.5)
    assert path[2]["x"] == pytest.approx(2.0)
    assert path[2]["y"] == pytest.approx(2.0)
    assert path[2]["t"] == pytest.approx(started + 1.1)
    assert displacement_m(steps) == pytest.approx(math.hypot(2.0, 2.0))
    straight = straight_path(4.5, 0.0)
    assert straight == [
        {"x": 0.0, "y": 0.0, "t": None},
        {"x": pytest.approx(4.5), "y": pytest.approx(0.0), "t": None},
    ]


def test_api_points_expose_epoch_t_and_read_time_cadence():
    started = 1_700_000_000.0
    steps = [
        {"step_index": 0, "t_ms": 500, "heading_rad": 0.0, "step_length_m": 2.0, "x_m": 2.0, "y_m": 0.0},
        {"step_index": 1, "t_ms": 1100, "heading_rad": math.pi / 2, "step_length_m": 2.0, "x_m": 2.0, "y_m": 2.0},
    ]
    points = points_for_api(started, steps)
    assert points[0]["t"] == pytest.approx(started + 0.5)
    assert points[0]["t_rel"] == pytest.approx(0.5)
    assert points[0]["cadence"] == 0.0
    assert points[0]["displacement"] == pytest.approx(2.0)
    assert points[1]["t"] == pytest.approx(started + 1.1)
    assert points[1]["t_rel"] == pytest.approx(1.1)
    assert points[1]["cadence"] == pytest.approx(100.0)
    assert points[1]["displacement"] == pytest.approx(4.0)
    assert points[1]["heading"] == pytest.approx(math.pi / 2)
    assert points[1]["step_length"] == pytest.approx(2.0)
    assert set(points[0]) == {"x", "y", "t", "t_rel", "heading", "step_length", "cadence", "displacement"}


def test_trace_payload_matches_read_contract():
    payload = trace_payload(
        {
            "id": 8,
            "source_node": "Quarto",
            "target_node": "Sala",
            "edge_id": 3,
            "created_at": None,
            "started_at": 1_700_000_000.0,
            "is_valid": 1,
            "total_steps": 1,
            "total_distance_m": 2.0,
        },
        [{
            "step_index": 0,
            "t_ms": 400,
            "heading_rad": 0.2,
            "step_length_m": 2.0,
            "x_m": 1.9,
            "y_m": 0.4,
        }],
    )
    assert payload["id"] == 8
    assert payload["source"] == "Quarto"
    assert payload["target"] == "Sala"
    assert payload["edge_id"] == 3
    assert payload["valid"] is True
    assert payload["steps_count"] == 1
    assert payload["distance_m"] == 2.0
    assert payload["points"][0]["t"] == pytest.approx(1_700_000_000.4)
    assert payload["points"][0]["t_rel"] == pytest.approx(0.4)
