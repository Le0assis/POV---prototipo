"""O heading zera na pose do checkpoint, não no início de cada segmento."""

from __future__ import annotations

import numpy as np
import pytest
from dataclasses import replace

from pdr.pipeline import detect_steps_from_samples
from pdr.steps import StepDetectorConfig

pytestmark = pytest.mark.unit


def _burst(samples: list, t0: float, count: int, gyro_z: float) -> None:
    for index in range(count):
        t = t0 + index / 50.0
        samples.append({
            "timestamp": t,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81 + 3.0 * np.sin(2 * np.pi * 2.0 * (t - t0)),
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": gyro_z,
        })


def test_heading_is_not_reset_after_a_gap():
    config = replace(StepDetectorConfig(), min_consecutive_steps=1)
    samples: list[dict] = []
    gyro_z = 0.8
    _burst(samples, 0.0, 120, gyro_z)
    gap_start = 120 / 50.0 + 1.0
    _burst(samples, gap_start, 120, gyro_z)

    result = detect_steps_from_samples(samples, config)
    later = [step for step in result.steps if step.timestamp >= gap_start + 0.5]
    assert later, result.message
    # Giro constante ~0,8 rad/s. No segundo trecho o heading acumulado desde
    # o checkpoint passa de 1 rad. Recalibrar no gap deixaria o valor perto de 0.
    assert abs(later[0].heading_rad) > 1.0
