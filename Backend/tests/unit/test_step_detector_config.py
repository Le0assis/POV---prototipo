"""Defaults de StepDetectorConfig e injeção. Não há taxa fixa na config."""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np
import pytest

from pdr.sampling import prepare_timeline
from pdr.steps import PeakStepDetector, StepDetectorConfig

pytestmark = pytest.mark.unit


def test_step_detector_config_defaults_match_legacy_constants():
    config = StepDetectorConfig()
    assert config.min_height_abs == 10.3
    assert config.height_offset == 0.35
    assert config.min_step_interval_s == 0.33
    assert config.min_prominence_abs == 0.45
    assert config.prominence_std_factor == 0.30
    assert config.min_window_std == 0.35
    assert config.max_window_std == 3.8
    assert config.walk_band_hz == (0.8, 2.8)
    assert config.shake_band_hz == (3.2, 15.0)
    assert config.shake_energy_ratio == 1.5
    assert config.shake_energy_min == 18.0
    assert config.max_mean_jerk == 50.0
    assert config.max_local_jerk == 65.0
    assert config.max_mean_gyro == 2.8
    assert config.max_local_gyro == 3.0
    assert config.gyro_peak_limit == 7.5
    assert config.gyro_mean_limit == 4.0
    assert config.max_peak_abs == 15.5
    assert config.acc_diff_min == 1.2
    assert config.acc_diff_max == 5.0
    assert config.weinberg_k == 0.45
    assert config.step_length_min_m == 0.40
    assert config.step_length_max_m == 0.95
    assert config.lowpass_cutoff_hz == 2.2
    assert config.max_gap_s == 0.25


def test_step_detector_config_has_no_fixed_sample_rate():
    names = {item.name for item in fields(StepDetectorConfig)}
    assert "sample_rate_hz" not in names
    assert "sample_rate" not in names
    assert "target_hz" not in names


def test_injected_config_changes_detection():
    sample_rate = 50.0
    n = int(10 * sample_rate)
    time = np.arange(n) / sample_rate
    signal = 9.81 + 3.0 * np.sin(2 * np.pi * 2.0 * time)
    gyro = np.zeros(n)
    default_count = len(PeakStepDetector().detect(time, signal, gyro))
    longer_refractory = replace(StepDetectorConfig(), min_step_interval_s=0.9)
    sparse_count = len(PeakStepDetector(config=longer_refractory).detect(time, signal, gyro))
    assert default_count >= 18
    assert sparse_count < default_count

    hit = np.full(n, 9.81)
    hit[200:230] += np.hanning(30) * 4.0
    assert len(PeakStepDetector().detect(time, hit, gyro)) == 0
    single_ok = replace(StepDetectorConfig(), min_consecutive_steps=1)
    assert len(PeakStepDetector(config=single_ok).detect(time, hit, gyro)) == 1


def test_max_gap_s_changes_how_a_hole_is_split():
    """0,25 s parte um vão de 0,4 s; 0,5 s (Chrome/MIUI engasgado) mantém um segmento."""
    samples = []
    for index in range(20):
        samples.append({
            "timestamp": index / 50.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.81,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        })
    hole = samples[-1]["timestamp"] + 0.40
    for index in range(20):
        samples.append({
            "timestamp": hole + index / 50.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.81,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        })
    assert StepDetectorConfig().max_gap_s == 0.25
    assert len(prepare_timeline(samples, max_gap_s=StepDetectorConfig().max_gap_s)) == 2
    assert len(prepare_timeline(samples, max_gap_s=0.5)) == 1


def test_weinberg_k_argument_overrides_config_default():
    detector = PeakStepDetector(weinberg_k=0.48)
    assert detector.config.weinberg_k == 0.48
    assert StepDetectorConfig().weinberg_k == 0.45
