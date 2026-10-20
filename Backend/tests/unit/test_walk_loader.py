"""Loader dos dois formatos de CSV, rótulos e timestamps tortos (TC-S07, TC-S08)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pdr.pipeline import detect_steps_from_samples
from tests.conftest import SAMPLE_WALK_CSV
from tests.utils.make_labels import build_labels
from tests.utils.walk_loader import discover_walks, load_sensor_csv, load_walk, rate_stats

pytestmark = pytest.mark.unit


def _samples_from_frame(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for record in frame.to_dict(orient="records"):
        rows.append({
            "timestamp": float(record["timestamp"]),
            "accel_x": float(record["accel_x"]),
            "accel_y": float(record["accel_y"]),
            "accel_z": float(record["accel_z"]),
            "gyro_x": float(record["gyro_x"]),
            "gyro_y": float(record["gyro_y"]),
            "gyro_z": float(record["gyro_z"]),
        })
    return rows


def test_walk_loader_reads_dataset_and_recorder_column_names(tmp_path):
    dataset = load_sensor_csv(SAMPLE_WALK_CSV)
    recorder = dataset.rename(columns={
        "accel_x": "accel_x",
        "accel_y": "accel_y",
        "accel_z": "accel_z",
        "gyro_x": "gyro_x",
        "gyro_y": "gyro_y",
        "gyro_z": "gyro_z",
    })
    # O sample_walk já foi normalizado para accel_*. Regrava nos nomes do recorder
    # e também confere que o arquivo original (ax/gx) normaliza para o mesmo vetor.
    raw = pd.read_csv(SAMPLE_WALK_CSV)
    exported = raw.rename(columns={
        "ax": "accel_x", "ay": "accel_y", "az": "accel_z",
        "gx": "gyro_x", "gy": "gyro_y", "gz": "gyro_z",
        "mx": "mag_x", "my": "mag_y", "mz": "mag_z",
    })
    exported_path = tmp_path / "recorder_export.csv"
    exported.to_csv(exported_path, index=False)
    from_export = load_sensor_csv(exported_path)
    assert list(dataset["accel_z"]) == pytest.approx(list(from_export["accel_z"]))
    left = detect_steps_from_samples(_samples_from_frame(dataset))
    right = detect_steps_from_samples(_samples_from_frame(from_export))
    assert left.steps_count == right.steps_count
    assert recorder.shape[0] == dataset.shape[0]


def test_walk_loader_missing_column_names_the_gap(tmp_path):
    broken = tmp_path / "broken.csv"
    pd.DataFrame({"timestamp": [0.0, 0.02], "ax": [0.0, 0.1]}).to_csv(broken, index=False)
    with pytest.raises(ValueError, match="accel_y"):
        load_sensor_csv(broken)


def test_make_labels_records_sample_walk_rate():
    payload = build_labels(SAMPLE_WALK_CSV, steps_real=20, scenario="sintetico")
    assert payload["steps_real"] == 20
    assert payload["sample_rate_hz"] == pytest.approx(50.0, abs=0.05)
    assert payload["dt_median_ms"] == pytest.approx(20.0, abs=0.05)
    stats = rate_stats(pd.read_csv(SAMPLE_WALK_CSV)["timestamp"].to_numpy())
    assert stats["dt_p95_ms"] == pytest.approx(payload["dt_p95_ms"], abs=0.05)


def test_pipeline_duplicate_and_shuffled_timestamps_do_not_raise():
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    samples = _samples_from_frame(frame)
    clean = detect_steps_from_samples(samples)

    duplicated = [dict(sample) for sample in samples]
    for index in range(1, len(duplicated), 10):
        duplicated[index]["timestamp"] = duplicated[index - 1]["timestamp"]
    with_dups = detect_steps_from_samples(duplicated)
    assert abs(with_dups.steps_count - clean.steps_count) <= 1

    shuffled = [dict(sample) for sample in samples]
    rng = np.random.default_rng(7)
    rng.shuffle(shuffled)
    reordered = detect_steps_from_samples(shuffled)
    assert reordered.steps_count == clean.steps_count


def test_walk_loader_step_mark_becomes_step_times(tmp_path):
    frame = load_sensor_csv(SAMPLE_WALK_CSV).head(40).copy()
    frame["step_mark"] = 0
    frame.loc[frame.index[5], "step_mark"] = 1
    frame.loc[frame.index[15], "step_mark"] = 1
    csv_path = tmp_path / "marked.csv"
    frame.to_csv(csv_path, index=False)
    stats = rate_stats(frame["timestamp"].to_numpy())
    labels = {
        "steps_real": 2,
        "sample_rate_hz": stats["sample_rate_hz"],
        "dt_median_ms": stats["dt_median_ms"],
        "dt_p95_ms": stats["dt_p95_ms"],
        "step_times_s": None,
        "time_base": None,
    }
    labels_path = csv_path.with_suffix(".labels.json")
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    recording = load_walk(csv_path, labels_path)
    assert recording.labels.step_times_s is not None
    assert len(recording.labels.step_times_s) == 2
    assert recording.labels.time_base == "epoch"


def test_discover_walks_skips_csv_without_labels(tmp_path):
    frame = load_sensor_csv(SAMPLE_WALK_CSV).head(5)
    frame.to_csv(tmp_path / "orphan.csv", index=False)
    assert discover_walks(tmp_path) == []
