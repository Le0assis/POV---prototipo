"""Campo opcional steps na resposta de process-raw. DB mockado, sem MySQL."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.schema import ProcessRawEdgeSchema
from datasets.generate_sample_dataset import generate_walking_dataset
from pdr.processor import RawEdgeProcessor
from tests.conftest import TARGETS

pytestmark = pytest.mark.integration


class _FakeDB:
    def __init__(self) -> None:
        self.logs = 0
        self.edges = 0

    def save_sensor_log(self, source, target, csv_data):
        self.logs += 1
        return True

    def save_edge(self, source, target, distance, heading_rad):
        self.edges += 1
        return True


class _FakeMap:
    def __init__(self) -> None:
        self.links = []

    def connect_checkpoints(self, source, target, distance, angle_deg):
        self.links.append((source, target, distance, angle_deg))


def _client():
    database = _FakeDB()
    topo = _FakeMap()
    processor = RawEdgeProcessor(database, topo)
    app = FastAPI()

    @app.post("/api/edges/process-raw", status_code=201)
    def process_raw_edge(payload: ProcessRawEdgeSchema):
        return processor.process_samples(payload.source, payload.target, payload.samples)

    return TestClient(app), database, topo


def _payload_from_generator(**kwargs) -> dict:
    frame = generate_walking_dataset(**kwargs)
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
    return {"source": "A", "target": "B", "samples": samples}


def test_process_raw_response_includes_optional_steps():
    client, database, topo = _client()
    response = client.post("/api/edges/process-raw", json=_payload_from_generator(seed=42))
    assert response.status_code == 201
    body = response.json()
    for key in ("status", "valid", "source", "target", "message", "steps_count", "distance_m", "mean_yaw_rad", "steps"):
        assert key in body
    expected = TARGETS["A3_sample_walk_steps"]
    tolerance = TARGETS["A3_sample_walk_tolerance"]
    assert abs(body["steps_count"] - expected) <= tolerance
    assert body["valid"] is True
    assert len(body["steps"]) == body["steps_count"]
    assert database.logs == 1
    assert database.edges == 1
    assert topo.links

    stamps = []
    t0 = _payload_from_generator(seed=42)["samples"][0]["timestamp"]
    for step in body["steps"]:
        assert set(step) >= {"t", "length_m", "cadence_spm", "t_rel"}
        assert step["t_rel"] == pytest.approx(step["t"] - t0, abs=1e-6)
        stamps.append(step["t"])
    assert stamps == sorted(stamps)
    assert np.min(np.diff(stamps)) >= 0.33 - 1e-3


def test_process_raw_short_recording_is_400():
    client, database, _topo = _client()
    samples = [
        {
            "timestamp": index / 50.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        }
        for index in range(5)
    ]
    response = client.post(
        "/api/edges/process-raw",
        json={"source": "A", "target": "B", "samples": samples},
    )
    assert response.status_code == 400
    assert database.logs == 0


def test_process_raw_zero_steps_keeps_steps_list():
    client, database, topo = _client()
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
    response = client.post(
        "/api/edges/process-raw",
        json={"source": "A", "target": "B", "samples": samples},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["steps_count"] == 0
    assert body["steps"] == []
    assert body["valid"] is False
    assert database.edges == 0
    assert topo.links == []
