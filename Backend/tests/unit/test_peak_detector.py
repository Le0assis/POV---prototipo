"""PeakStepDetector em sinal já filtrado. A taxa sai dos timestamps."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pdr.steps import PeakStepDetector
from tests.conftest import SAMPLE_WALK_CSV, TARGETS

pytestmark = pytest.mark.unit


def _gait(duration_s=10.0, sample_rate=50.0, freq_hz=2.0, amplitude=3.0, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * sample_rate))
    time = np.arange(n) / sample_rate
    signal = 9.81 + amplitude * np.sin(2 * np.pi * freq_hz * time)
    if noise:
        signal = signal + rng.normal(0, noise, n)
    gyro = np.full(n, 0.05)
    return time, signal, gyro


def test_peak_detector_flat_signal_returns_zero(detector):
    rng = np.random.default_rng(0)
    n = 500
    time = np.arange(n) / 50.0
    signal = 9.81 + rng.normal(0, 0.05, n)
    assert detector.detect(time, signal, np.zeros(n)) == []


def test_peak_detector_single_impact_at_most_one(detector):
    time, signal, gyro = _gait(amplitude=0.0)
    signal = signal.copy()
    signal[200:230] += np.hanning(30) * 5.0
    assert len(detector.detect(time, signal, gyro)) <= 1


def test_peak_detector_refractory_spacing_follows_seconds(detector):
    """4 Hz é mais rápido que o refratário de 0,33 s: a série aceita fica mais espaçada."""
    time, signal, gyro = _gait(freq_hz=4.0, amplitude=3.0)
    steps = detector.detect(time, signal, gyro)
    assert len(steps) < 4.0 * 10
    intervals = np.diff([step.timestamp for step in steps])
    assert intervals.size
    assert float(intervals.min()) >= 0.33 - 1e-3


def test_peak_detector_below_threshold_returns_zero(detector):
    time, signal, gyro = _gait(amplitude=0.2, noise=0.02)
    assert detector.detect(time, signal, gyro) == []


def test_peak_detector_ignores_declared_sample_rate():
    time, signal, gyro = _gait()
    at_30 = PeakStepDetector(sample_rate_hz=30).detect(time, signal, gyro, sample_rate_hz=30)
    at_90 = PeakStepDetector(sample_rate_hz=90).detect(time, signal, gyro, sample_rate_hz=90)
    assert len(at_30) == len(at_90)
    assert [step.index for step in at_30] == [step.index for step in at_90]


def test_peak_detector_sample_walk_vertical_at_50hz_within_tolerance():
    """O az cru do sample_walk é 50 Hz. O teto de acc_diff=5,0 derrubava 4 picos (16)."""
    frame = pd.read_csv(SAMPLE_WALK_CSV)
    time = frame["timestamp"].to_numpy()
    vertical = frame["az"].to_numpy()
    gyro = np.sqrt(frame["gx"] ** 2 + frame["gy"] ** 2 + frame["gz"] ** 2)
    steps = PeakStepDetector().detect(time, vertical, gyro.to_numpy())
    expected = TARGETS["A3_sample_walk_steps"]
    tolerance = TARGETS["A3_sample_walk_tolerance"]
    assert abs(len(steps) - expected) <= tolerance, (
        f"sample_walk az @ taxa dos timestamps: N_det={len(steps)} N_real={expected}"
    )
    intervals = np.diff([step.timestamp for step in steps])
    assert float(intervals.min()) >= 0.33 - 1e-3


def test_peak_detector_pause_does_not_discard_the_walk(detector):
    """20 s parado + 10 s andando: a trava global de std < 0,35 devolvia 0."""
    sample_rate = 50.0
    n = int(30 * sample_rate)
    time = np.arange(n) / sample_rate
    signal = np.full(n, 9.81)
    walk = time >= 20.0
    signal[walk] += 1.6 * np.sin(2 * np.pi * 1.8 * (time[walk] - 20.0))
    steps = detector.detect(time, signal, np.full(n, 0.05))
    assert len(steps) >= 14, f"pausa zerou a caminhada: N_det={len(steps)}"


def test_peak_detector_events_share_input_time_base(detector):
    time, signal, gyro = _gait()
    steps = detector.detect(time, signal, gyro)
    stamps = [step.timestamp for step in steps]
    assert stamps == sorted(stamps)
    assert stamps[0] >= time[0]
    assert stamps[-1] <= time[-1]
    assert len(steps) == len({step.index for step in steps})


def test_peak_detector_duplicate_timestamps_do_not_raise(detector):
    time, signal, gyro = _gait()
    duplicated = time.copy()
    duplicated[1::10] = duplicated[0::10][: len(duplicated[1::10])]
    steps = detector.detect(duplicated, signal, gyro)
    assert isinstance(steps, list)
    assert len(steps) >= 15
