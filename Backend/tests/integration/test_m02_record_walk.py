"""process-raw grava a trajetória do sentido andado e não chama save_edge."""

from __future__ import annotations

import pytest

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

    def record_walk(self, source, target, sensors_log_id, started_at, ended_at, built):
        self.walk = {
            "source": source,
            "target": target,
            "sensors_log_id": sensors_log_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "built": built,
        }
        return {
            "path": {"id": 1, "source": source, "target": target, "points": []},
            "edge_distance_m": 3.0,
            "edge_heading_rad": 0.25,
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
    assert body["path"]["source"] == "Quarto"
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
