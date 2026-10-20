"""process-raw grava a trajetória do sentido andado e não chama save_edge."""

from __future__ import annotations

import pytest

from fastapi import HTTPException

from datasets.generate_sample_dataset import generate_walking_dataset
from pdr.processor import RawEdgeProcessor

pytestmark = pytest.mark.integration


class _RecordingDB:
    def __init__(self) -> None:
        self.updated = None
        self.walk = None

    def save_sensor_log(self, source, target, csv_data):
        assert csv_data
        return 7

    def update_sensor_log(self, log_id, steps, distance, is_valid, message):
        self.updated = (log_id, steps, distance, is_valid, message)
        return True

    def record_walk(self, source, target, sensors_log_id, started_at, ended_at, built, is_valid=True):
        self.walk = {
            "source": source,
            "target": target,
            "sensors_log_id": sensors_log_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "built": built,
            "is_valid": is_valid,
        }
        return {
            "path": [{"x": 0.0, "y": 0.0, "t": 10.0}, {"x": 1.0, "y": 0.0, "t": 11.0}],
            "trace_id": 11,
            "edge_id": 3,
            "edge_distance_m": 3.0,
            "edge_heading_rad": 0.25,
            "edge_origin": "recorded",
        }


class _DirectedMap:
    def __init__(self) -> None:
        self.nodes = {"Quarto": "Quarto", "Sala": "Sala"}
        self.directed = []

    def add_checkpoint(self, name):
        self.nodes[name] = name

    def upsert_directed_edge(self, source, target, distance_m, heading_rad):
        self.directed.append((source, target, distance_m, heading_rad))


def _samples():
    frame = generate_walking_dataset(seed=42)
    samples = []
    for row in frame.itertuples(index=False):
        samples.append({
            "timestamp": float(row.timestamp),
            "accel_x": float(row.ax),
            "accel_y": float(row.ay),
            "accel_z": float(row.az),
            "gyro_x": float(row.gx),
            "gyro_y": float(row.gy),
            "gyro_z": float(row.gz),
            "mag_x": float(row.mx),
            "mag_y": float(row.my),
            "mag_z": float(row.mz),
        })
    return samples


def test_process_raw_persists_trace_and_one_direction():
    database = _RecordingDB()
    topo = _DirectedMap()
    body = RawEdgeProcessor(database, topo).process_samples("Quarto", "Sala", _samples())
    assert body["valid"] is True
    assert body["trace_id"] == 11
    assert body["edge_id"] == 3
    assert body["frame"] == "edge_local"
    assert body["edge_origin"] == "recorded"
    assert body["path"][0] == {"x": 0.0, "y": 0.0, "t": 10.0}
    assert database.walk["is_valid"] is True
    for step in body["steps"]:
        assert {"step_index", "x", "y", "heading_rad", "length_m"} <= set(step)
    assert database.updated[0] == 7
    assert database.updated[3] is True
    assert database.walk["sensors_log_id"] == 7
    assert database.walk["source"] == "Quarto"
    assert database.walk["target"] == "Sala"
    steps = database.walk["built"]["steps"]
    assert steps
    assert database.walk["built"]["polyline"][0] == [0.0, 0.0]
    for step in steps:
        assert {"t_ms", "heading_rad", "step_length_m", "x_m", "y_m", "step_index"} <= set(step)
    assert topo.directed == [("Quarto", "Sala", 3.0, 0.25)]


def test_invalid_walk_is_stored_without_updating_the_edge():
    database = _RecordingDB()
    topo = _DirectedMap()
    samples = []
    for index in range(80):
        samples.append({
            "timestamp": index / 50.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        })
    body = RawEdgeProcessor(database, topo).process_samples("Quarto", "Sala", samples)
    assert body["valid"] is False
    assert body["steps"] == []
    assert database.walk["is_valid"] is False
    assert body["trace_id"] == 11
    assert body["path"][0]["x"] == 0.0
    assert topo.directed == []


def test_record_walk_failure_is_500_and_does_not_touch_the_edge():
    database = _RecordingDB()
    database.record_walk = lambda *args, **kwargs: None
    topo = _DirectedMap()
    samples = []
    for index in range(80):
        samples.append({
            "timestamp": index / 50.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        })
    with pytest.raises(HTTPException) as exc:
        RawEdgeProcessor(database, topo).process_samples("Quarto", "Sala", samples)
    assert exc.value.status_code == 500
    assert topo.directed == []
