"""Lê CSV de sensores nos dois formatos do projeto e o rótulo irmão."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = ("timestamp", "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z")

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "t"),
    "accel_x": ("accel_x", "ax", "acc_x"),
    "accel_y": ("accel_y", "ay", "acc_y"),
    "accel_z": ("accel_z", "az", "acc_z"),
    "gyro_x": ("gyro_x", "gx"),
    "gyro_y": ("gyro_y", "gy"),
    "gyro_z": ("gyro_z", "gz"),
    "mag_x": ("mag_x", "mx"),
    "mag_y": ("mag_y", "my"),
    "mag_z": ("mag_z", "mz"),
    "step_mark": ("step_mark", "stepmark"),
}


@dataclass
class WalkLabels:
    steps_real: int
    sample_rate_hz: float
    dt_median_ms: float
    dt_p95_ms: float
    scenario: str | None = None
    position: str | None = None
    device: str | None = None
    date: str | None = None
    notes: str | None = None
    step_times_s: list[float] | None = None
    time_base: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class WalkRecording:
    name: str
    path: Path
    samples: list[dict]
    timestamps: np.ndarray
    labels: WalkLabels


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(column).strip().lower(): column for column in frame.columns}
    renamed: dict[str, str] = {}
    missing: list[str] = []
    for canonical, aliases in COLUMN_ALIASES.items():
        found = next((alias for alias in aliases if alias in lookup), None)
        if found is None:
            if canonical in REQUIRED:
                missing.append(canonical)
            continue
        renamed[lookup[found]] = canonical
    if missing:
        found_cols = ", ".join(str(column) for column in frame.columns)
        raise ValueError(
            "CSV sem coluna obrigatória: "
            + ", ".join(missing)
            + f". Colunas encontradas: {found_cols}."
        )
    normalized = frame.rename(columns=renamed)
    keep = [column for column in list(REQUIRED) + ["mag_x", "mag_y", "mag_z", "step_mark"] if column in normalized.columns]
    return normalized[keep]


def load_sensor_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"CSV vazio: {path}")
    return _normalize_columns(frame)


def rate_stats(timestamps: np.ndarray) -> dict[str, float]:
    time = np.asarray(timestamps, dtype=np.float64)
    order = np.argsort(time)
    time = time[order]
    if time.size < 2 or not np.isfinite(time).all():
        raise ValueError("Timestamps insuficientes para calcular a taxa.")
    duration = float(time[-1] - time[0])
    if duration <= 0:
        raise ValueError("Duração nula: não dá para calcular sample_rate_hz.")
    dt = np.diff(time)
    positive = dt[dt > 0]
    if positive.size == 0:
        raise ValueError("Timestamps sem intervalo positivo.")
    return {
        "sample_rate_hz": float((time.size - 1) / duration),
        "dt_median_ms": float(np.median(positive) * 1000.0),
        "dt_p95_ms": float(np.percentile(positive, 95) * 1000.0),
    }


def load_labels(path: Path) -> WalkLabels:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "steps_real" not in data:
        raise ValueError(f"{path.name} sem steps_real.")
    for key in ("sample_rate_hz", "dt_median_ms", "dt_p95_ms"):
        if key not in data or data[key] is None:
            raise ValueError(
                f"{path.name} sem {key}. Calcule com tests/utils/make_labels.py, não à mão."
            )
    step_times = data.get("step_times_s")
    time_base = data.get("time_base")
    if step_times:
        if time_base not in ("epoch", "relative"):
            raise ValueError(
                f"{path.name} tem step_times_s mas time_base não é 'epoch' nem 'relative'."
            )
        step_times = [float(value) for value in step_times]
    else:
        step_times = None
        time_base = None
    return WalkLabels(
        steps_real=int(data["steps_real"]),
        sample_rate_hz=float(data["sample_rate_hz"]),
        dt_median_ms=float(data["dt_median_ms"]),
        dt_p95_ms=float(data["dt_p95_ms"]),
        scenario=data.get("scenario"),
        position=data.get("position"),
        device=data.get("device"),
        date=data.get("date"),
        notes=data.get("notes"),
        step_times_s=step_times,
        time_base=time_base,
        raw=data,
    )


def frame_to_samples(frame: pd.DataFrame) -> list[dict]:
    samples: list[dict] = []
    for row in frame.itertuples(index=False):
        sample = {
            "timestamp": float(row.timestamp),
            "accel_x": float(row.accel_x),
            "accel_y": float(row.accel_y),
            "accel_z": float(row.accel_z),
            "gyro_x": float(row.gyro_x),
            "gyro_y": float(row.gyro_y),
            "gyro_z": float(row.gyro_z),
            "mag_x": float(getattr(row, "mag_x", 0.0) or 0.0),
            "mag_y": float(getattr(row, "mag_y", 0.0) or 0.0),
            "mag_z": float(getattr(row, "mag_z", 0.0) or 0.0),
        }
        samples.append(sample)
    return samples


def _apply_step_mark(frame: pd.DataFrame, labels: WalkLabels) -> WalkLabels:
    if labels.step_times_s or "step_mark" not in frame.columns:
        return labels
    marks = frame["step_mark"].fillna(0).astype(float).to_numpy()
    times = frame["timestamp"].to_numpy(dtype=np.float64)
    marked = times[marks >= 0.5]
    if marked.size == 0:
        return labels
    return WalkLabels(
        steps_real=labels.steps_real,
        sample_rate_hz=labels.sample_rate_hz,
        dt_median_ms=labels.dt_median_ms,
        dt_p95_ms=labels.dt_p95_ms,
        scenario=labels.scenario,
        position=labels.position,
        device=labels.device,
        date=labels.date,
        notes=labels.notes,
        step_times_s=[float(value) for value in marked],
        time_base=labels.time_base or "epoch",
        raw=labels.raw,
    )


def load_walk(csv_path: Path, labels_path: Path | None = None) -> WalkRecording:
    csv_path = Path(csv_path)
    frame = load_sensor_csv(csv_path)
    labels_path = labels_path or csv_path.with_suffix(".labels.json")
    if not Path(labels_path).exists():
        raise ValueError(f"Sem rótulo para {csv_path.name} ({labels_path}).")
    labels = _apply_step_mark(frame, load_labels(Path(labels_path)))
    timestamps = frame["timestamp"].to_numpy(dtype=np.float64)
    return WalkRecording(
        name=csv_path.stem,
        path=csv_path,
        samples=frame_to_samples(frame),
        timestamps=timestamps,
        labels=labels,
    )


def discover_walks(directory: Path) -> list[WalkRecording]:
    """Pares CSV + .labels.json. CSV sem rótulo não entra."""
    directory = Path(directory)
    if not directory.exists():
        return []
    recordings: list[WalkRecording] = []
    for csv_path in sorted(directory.glob("*.csv")):
        labels_path = csv_path.with_suffix(".labels.json")
        if not labels_path.exists():
            continue
        recordings.append(load_walk(csv_path, labels_path))
    return recordings
