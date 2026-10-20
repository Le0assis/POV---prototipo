"""
sampling.py — tempo real das amostras de IMU.

A taxa de amostragem não é uma constante do detector. Ela sai dos
timestamps (mediana de dt), depois de ordenar, descartar duplicados e
cortar buracos. A reamostragem, quando acontece, usa essa taxa medida
para o filtro ter um dt uniforme — não os 30 Hz que o pipeline antigo
gravava fixo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.interpolate import interp1d


# Limites só para não alimentar o Butterworth com uma taxa absurda
# (timestamp repetido que escapou, ou rajada de 0,1 ms). Não são a taxa
# esperada do aparelho: dentro da faixa, o valor medido passa intacto.
RATE_SANITY_MIN_HZ = 10.0
RATE_SANITY_MAX_HZ = 100.0


@dataclass(frozen=True, slots=True)
class ImuSample:
    timestamp: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0


def _read(sample: object, *names: str, default: float | None = None) -> float:
    for name in names:
        if isinstance(sample, dict) and name in sample:
            value = sample[name]
        else:
            value = getattr(sample, name, None)
        if value is not None:
            return float(value)
    if default is not None:
        return float(default)
    raise KeyError(f"Amostra sem campo obrigatório ({', '.join(names)}).")


def coerce_samples(samples: list) -> list[ImuSample]:
    """Aceita dict, modelo Pydantic ou objeto com accel_*/ax e gyro_*/gx."""
    coerced: list[ImuSample] = []
    for sample in samples:
        coerced.append(
            ImuSample(
                timestamp=_read(sample, "timestamp"),
                accel_x=_read(sample, "accel_x", "ax"),
                accel_y=_read(sample, "accel_y", "ay"),
                accel_z=_read(sample, "accel_z", "az"),
                gyro_x=_read(sample, "gyro_x", "gx"),
                gyro_y=_read(sample, "gyro_y", "gy"),
                gyro_z=_read(sample, "gyro_z", "gz"),
                mag_x=_read(sample, "mag_x", "mx", default=0.0),
                mag_y=_read(sample, "mag_y", "my", default=0.0),
                mag_z=_read(sample, "mag_z", "mz", default=0.0),
            )
        )
    return coerced


def estimate_sample_rate_hz(timestamps: npt.ArrayLike) -> float:
    """Mediana de 1/dt. Robusta a um buraco isolado; não usa taxa fixa."""
    time = np.asarray(timestamps, dtype=np.float64)
    if time.size < 2:
        return float("nan")
    dt = np.diff(time)
    positive = dt[np.isfinite(dt) & (dt > 1e-4)]
    if positive.size == 0:
        return float("nan")
    return float(1.0 / np.median(positive))


def sanitize_rate_hz(sample_rate_hz: float) -> float:
    """Corta só valores fora da faixa física de um celular. 50 Hz continua 50."""
    if not np.isfinite(sample_rate_hz):
        return float("nan")
    return float(np.clip(sample_rate_hz, RATE_SANITY_MIN_HZ, RATE_SANITY_MAX_HZ))


def prepare_timeline(
    samples: list,
    max_gap_s: float,
) -> list[list[ImuSample]]:
    """Ordena, remove timestamps duplicados/não finitos e corta gaps longos.

    Um gap maior que ``max_gap_s`` vira outro segmento. Interpolar por cima
    inventaria aceleração no meio de uma pausa de captura (Chrome agrupa
    eventos, e a tela bloqueada pode furar o ``devicemotion``).
    """
    cleaned: list[ImuSample] = []
    for sample in coerce_samples(samples):
        values = (
            sample.timestamp,
            sample.accel_x, sample.accel_y, sample.accel_z,
            sample.gyro_x, sample.gyro_y, sample.gyro_z,
        )
        if not all(np.isfinite(values)):
            continue
        cleaned.append(sample)

    cleaned.sort(key=lambda sample: sample.timestamp)

    unique: list[ImuSample] = []
    for sample in cleaned:
        if unique and sample.timestamp <= unique[-1].timestamp:
            continue
        unique.append(sample)

    if not unique:
        return []

    segments: list[list[ImuSample]] = [[unique[0]]]
    for sample in unique[1:]:
        if sample.timestamp - segments[-1][-1].timestamp > max_gap_s:
            segments.append([sample])
        else:
            segments[-1].append(sample)
    return segments


def resample_segment(
    segment: list[ImuSample],
    sample_rate_hz: float,
) -> tuple[npt.NDArray[np.float64], dict[str, npt.NDArray[np.float64]]] | None:
    """Grade uniforme na taxa medida. Os extremos continuam os timestamps originais."""
    if len(segment) < 2 or not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        return None

    t_orig = np.array([sample.timestamp for sample in segment], dtype=np.float64)
    duration = float(t_orig[-1] - t_orig[0])
    if duration <= 0:
        return None

    # +1 porque a grade inclui os dois extremos (n = duração * taxa + 1).
    num_points = int(round(duration * sample_rate_hz)) + 1
    if num_points < 4:
        return None

    t_uniform = np.linspace(t_orig[0], t_orig[-1], num_points)
    channels = {
        "accel_x": np.array([sample.accel_x for sample in segment], dtype=np.float64),
        "accel_y": np.array([sample.accel_y for sample in segment], dtype=np.float64),
        "accel_z": np.array([sample.accel_z for sample in segment], dtype=np.float64),
        "gyro_x": np.array([sample.gyro_x for sample in segment], dtype=np.float64),
        "gyro_y": np.array([sample.gyro_y for sample in segment], dtype=np.float64),
        "gyro_z": np.array([sample.gyro_z for sample in segment], dtype=np.float64),
    }
    resampled = {
        name: interp1d(t_orig, values, kind="linear", fill_value="extrapolate")(t_uniform)
        for name, values in channels.items()
    }
    return t_uniform, resampled
