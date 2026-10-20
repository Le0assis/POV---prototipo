"""Pipeline completo no sample_walk (50 Hz) e nas variações de taxa."""

from __future__ import annotations

import numpy as np
import pytest

from datasets.generate_sample_dataset import generate_walking_dataset
from pdr.pipeline import detect_steps_from_samples
from tests.conftest import SAMPLE_WALK_CSV, TARGETS
from tests.utils.walk_loader import frame_to_samples, load_sensor_csv

pytestmark = pytest.mark.integration


def _count_within(count: int, expected: float, tolerance: int = 1) -> None:
    assert abs(count - expected) <= tolerance, f"N_det={count} esperado {expected} ±{tolerance}"


def test_pipeline_sample_walk_counts_20_steps():
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    result = detect_steps_from_samples(frame_to_samples(frame))
    expected = TARGETS["A3_sample_walk_steps"]
    tolerance = TARGETS["A3_sample_walk_tolerance"]
    assert result.time_valid
    assert abs(result.steps_count - expected) <= tolerance, (
        f"sample_walk: N_real={expected} N_det={result.steps_count} "
        f"erro={abs(result.steps_count - expected) / expected * 100:.2f}% "
        f"taxa={result.sample_rate_hz:.2f} Hz"
    )
    assert result.sample_rate_hz == pytest.approx(50.0, abs=0.5)
    assert result.steps_count == len(result.steps)


def test_pipeline_sample_walk_is_deterministic():
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    samples = frame_to_samples(frame)
    first = detect_steps_from_samples(samples)
    second = detect_steps_from_samples(samples)
    assert [step.timestamp for step in first.steps] == [step.timestamp for step in second.steps]
    assert first.steps_count == second.steps_count


def test_pipeline_step_events_use_input_time_base_and_refractory():
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    samples = frame_to_samples(frame)
    result = detect_steps_from_samples(samples)
    t0 = min(sample["timestamp"] for sample in samples)
    t1 = max(sample["timestamp"] for sample in samples)
    stamps = [step.timestamp for step in result.steps]
    assert stamps == sorted(stamps)
    assert stamps[0] >= t0
    assert stamps[-1] <= t1
    intervals = np.diff(stamps)
    assert float(intervals.min()) >= 0.33 - 1e-3


@pytest.mark.parametrize("sample_rate", [30.0, 50.0, 60.0])
def test_pipeline_resampled_and_jittered_rates_stay_within_one(sample_rate):
    frame = load_sensor_csv(SAMPLE_WALK_CSV)
    time = frame["timestamp"].to_numpy()
    duration = float(time[-1] - time[0])
    rng = np.random.default_rng(3)

    def run(timestamps: np.ndarray) -> int:
        columns = {
            name: np.interp(timestamps, time, frame[name].to_numpy())
            for name in ("accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z")
        }
        samples = []
        for index, stamp in enumerate(timestamps):
            samples.append({
                "timestamp": float(stamp),
                "accel_x": float(columns["accel_x"][index]),
                "accel_y": float(columns["accel_y"][index]),
                "accel_z": float(columns["accel_z"][index]),
                "gyro_x": float(columns["gyro_x"][index]),
                "gyro_y": float(columns["gyro_y"][index]),
                "gyro_z": float(columns["gyro_z"][index]),
            })
        return detect_steps_from_samples(samples).steps_count

    n = int(round(duration * sample_rate)) + 1
    uniform = np.linspace(time[0], time[-1], n)
    dt = np.full(n - 1, 1.0 / sample_rate)
    dt = np.clip(dt + rng.uniform(-0.2 / sample_rate, 0.2 / sample_rate, dt.size), 0.45 / sample_rate, 2.2 / sample_rate)
    jittered = np.concatenate([[time[0]], time[0] + np.cumsum(dt)])
    jittered = time[0] + (jittered - jittered[0]) / (jittered[-1] - jittered[0]) * duration

    expected = TARGETS["A3_sample_walk_steps"]
    uniform_count = run(uniform)
    jitter_count = run(jittered)
    _count_within(uniform_count, expected)
    _count_within(jitter_count, expected)
    assert abs(uniform_count - jitter_count) <= 1


@pytest.mark.parametrize("freq_hz", [1.2, 2.0, 2.5])
def test_pipeline_step_frequency_counts_cycles(freq_hz):
    duration = 10.0
    frame = generate_walking_dataset(
        duration_s=duration,
        sample_rate_hz=50.0,
        step_frequency_hz=freq_hz,
        seed=42,
    )
    renamed = frame.rename(columns={
        "ax": "accel_x", "ay": "accel_y", "az": "accel_z",
        "gx": "gyro_x", "gy": "gyro_y", "gz": "gyro_z",
    })
    result = detect_steps_from_samples(frame_to_samples(renamed))
    _count_within(result.steps_count, freq_hz * duration)


def test_pipeline_gyro_spike_does_not_discard_the_walk():
    """Um pico de giro > 7,5 rad/s zerava a gravação inteira no processor antigo."""
    frame = generate_walking_dataset(seed=42)
    renamed = frame.rename(columns={
        "ax": "accel_x", "ay": "accel_y", "az": "accel_z",
        "gx": "gyro_x", "gy": "gyro_y", "gz": "gyro_z",
    })
    samples = frame_to_samples(renamed)
    samples[10]["gyro_x"] = 8.0
    result = detect_steps_from_samples(samples)
    expected = TARGETS["A3_sample_walk_steps"]
    assert result.steps_count >= expected - 2, (
        f"pico de giro descartou a caminhada: N_det={result.steps_count}"
    )


def test_pipeline_gap_does_not_invent_steps_across_the_hole():
    frame = generate_walking_dataset(duration_s=5.0, step_frequency_hz=2.0, seed=42)
    renamed = frame.rename(columns={
        "ax": "accel_x", "ay": "accel_y", "az": "accel_z",
        "gx": "gyro_x", "gy": "gyro_y", "gz": "gyro_z",
    })
    first = frame_to_samples(renamed)
    gap = 2.0
    shift = first[-1]["timestamp"] + gap
    second = []
    for sample in frame_to_samples(renamed):
        moved = dict(sample)
        moved["timestamp"] = sample["timestamp"] + shift
        second.append(moved)
    result = detect_steps_from_samples(first + second)
    # 2 Hz * 5 s de cada lado. A emenda não pode virar uma rampa de passos.
    assert 16 <= result.steps_count <= 22, f"N_det={result.steps_count}"
