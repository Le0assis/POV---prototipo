"""A1/A2 nas caminhadas rotuladas e o cenário sintético parado/manuseio.

Os CSV reais do Poco 6 Pro entram em tests/fixtures/walks/ com o
.labels.json irmão. Enquanto a pasta só tem o README, a meta por
caminhada não tem o que avaliar — o gancho abaixo passa a coletá-las
sozinho. O parado/manuseio sintético já roda.
"""

from __future__ import annotations

import numpy as np
import pytest

from pdr.pipeline import detect_steps_from_samples
from tests.conftest import TARGETS, WALKS_DIR
from tests.utils.step_metrics import count_error_pct
from tests.utils.walk_loader import WalkRecording, discover_walks

pytestmark = pytest.mark.integration


def _pack(time, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z) -> list[dict]:
    samples = []
    for index in range(len(time)):
        samples.append({
            "timestamp": float(time[index]),
            "accel_x": float(accel_x[index]),
            "accel_y": float(accel_y[index]),
            "accel_z": float(accel_z[index]),
            "gyro_x": float(gyro_x[index]),
            "gyro_y": float(gyro_y[index]),
            "gyro_z": float(gyro_z[index]),
        })
    return samples


def assert_walk_target(
    name: str,
    n_real: int,
    n_det: int,
    rate_hz: float,
    tolerance_steps: int | None = None,
) -> None:
    if tolerance_steps is not None:
        message = (
            f"{name}: N_real={n_real} N_det={n_det} "
            f"(meta ±{tolerance_steps}), taxa {rate_hz:.2f} Hz"
        )
        assert abs(n_det - n_real) <= tolerance_steps, message
        return
    if n_real <= 0:
        message = (
            f"{name}: N_real=0 N_det={n_det} fantasmas "
            f"(meta ≤ {TARGETS['A2_phantoms_max']}), taxa {rate_hz:.2f} Hz"
        )
        assert n_det <= TARGETS["A2_phantoms_max"], message
        return
    error = count_error_pct(n_det, n_real)
    message = (
        f"{name}: N_real={n_real} N_det={n_det} erro={error:.2f}% "
        f"(meta ≤ {TARGETS['A1_per_walk_error_pct']}%), taxa {rate_hz:.2f} Hz"
    )
    assert error <= TARGETS["A1_per_walk_error_pct"], message


def test_pipeline_standing_still_phantoms_at_most_2():
    rng = np.random.default_rng(0)
    sample_rate = 50.0
    n = int(30 * sample_rate)
    time = np.arange(n) / sample_rate
    samples = _pack(
        time,
        rng.normal(0, 0.05, n),
        rng.normal(0, 0.05, n),
        9.81 + rng.normal(0, 0.05, n),
        rng.normal(0, 0.01, n),
        rng.normal(0, 0.01, n),
        rng.normal(0, 0.01, n),
    )
    result = detect_steps_from_samples(samples)
    assert_walk_target("parado_30s_sintetico", 0, result.steps_count, result.sample_rate_hz)


def test_pipeline_handling_phantoms_at_most_2():
    """Celular na mão, sem andar: toques e giro irregular, não uma passada."""
    rng = np.random.default_rng(4)
    sample_rate = 50.0
    n = int(30 * sample_rate)
    time = np.arange(n) / sample_rate
    accel_z = 9.81 + rng.normal(0, 0.3, n)
    accel_x = rng.normal(0, 0.4, n)
    accel_y = rng.normal(0, 0.4, n)
    gyro_x = rng.normal(0, 0.8, n)
    gyro_y = rng.normal(0, 0.8, n)
    gyro_z = rng.normal(0, 0.8, n)
    for center in (1.1, 2.4, 3.3, 5.0, 7.7, 8.2, 11.0, 14.4, 18.8, 21.0, 23.3, 26.6, 28.1):
        start = int(center * sample_rate)
        width = 12
        accel_z[start:start + width] += np.linspace(0.0, 3.5, width)
        gyro_x[start:start + width] += 2.2
    result = detect_steps_from_samples(_pack(time, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z))
    assert_walk_target("manuseio_30s_sintetico", 0, result.steps_count, result.sample_rate_hz)


def test_labeled_walk_directory_is_ready_for_recordings():
    assert WALKS_DIR.is_dir()
    assert (WALKS_DIR / "README.md").is_file()
    found = discover_walks(WALKS_DIR)
    assert isinstance(found, list)


def test_labeled_walks_directory_is_not_empty():
    walks = discover_walks(WALKS_DIR)
    assert walks, (
        "Backend/tests/fixtures/walks está vazia. "
        "Falta CSV rotulado do Poco 6 Pro (arquivo + .labels.json)."
    )


def test_count_target_helper_rejects_large_error():
    with pytest.raises(AssertionError, match="N_real=50"):
        assert_walk_target("demo", n_real=50, n_det=10, rate_hz=50.0)


_WALKS = discover_walks(WALKS_DIR)


def _bind_labeled_walks() -> None:
    if not _WALKS:
        return

    @pytest.mark.integration
    @pytest.mark.parametrize("walk", _WALKS, ids=[walk.name for walk in _WALKS])
    def test_pipeline_walk_count_error_within_target(walk: WalkRecording):
        result = detect_steps_from_samples(walk.samples)
        assert_walk_target(
            walk.name,
            walk.labels.steps_real,
            result.steps_count,
            result.sample_rate_hz,
            walk.labels.tolerance_steps,
        )

    globals()["test_pipeline_walk_count_error_within_target"] = test_pipeline_walk_count_error_within_target

    @pytest.mark.integration
    @pytest.mark.parametrize("walk", _WALKS, ids=[walk.name for walk in _WALKS])
    def test_pipeline_walk_count_holds_when_downsampled_to_50hz(walk: WalkRecording):
        """Sensor Logger é ~100 Hz. O Chrome no Android entrega ~50 Hz.

        A mesma gravação, interpolada para 50 Hz, continua na meta. O
        detector não pode depender da taxa nativa do app.
        """
        result = detect_steps_from_samples(_downsample(walk.samples, 50.0))
        assert_walk_target(
            f"{walk.name}@50Hz",
            walk.labels.steps_real,
            result.steps_count,
            result.sample_rate_hz,
            walk.labels.tolerance_steps,
        )

    globals()["test_pipeline_walk_count_holds_when_downsampled_to_50hz"] = (
        test_pipeline_walk_count_holds_when_downsampled_to_50hz
    )


def _downsample(samples: list[dict], hz: float) -> list[dict]:
    time = np.array([sample["timestamp"] for sample in samples], dtype=np.float64)
    order = np.argsort(time, kind="mergesort")
    time = time[order]
    keep = np.ones(len(time), dtype=bool)
    keep[1:] = np.diff(time) > 1e-4
    time = time[keep]
    keys = [key for key in samples[0] if key != "timestamp"]
    columns = {
        key: np.array([samples[index][key] for index in order], dtype=np.float64)[keep]
        for key in keys
    }
    count = int(round((time[-1] - time[0]) * hz)) + 1
    grid = np.linspace(time[0], time[-1], count)
    interpolated = {key: np.interp(grid, time, values) for key, values in columns.items()}
    return [
        {"timestamp": float(grid[index]), **{key: float(interpolated[key][index]) for key in keys}}
        for index in range(count)
    ]


_bind_labeled_walks()
