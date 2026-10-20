"""
pipeline.py — detecção de passos sem banco e sem HTTP.

``detect_steps_from_samples`` é o miolo de ``RawEdgeProcessor.process_samples``:
reamostragem na taxa medida, Madgwick só com acelerômetro e giroscópio
(o campo ``mag_*`` do recorder é ângulo de orientação, não magnetômetro),
aceleração vertical, Butterworth e picos. Os timestamps dos passos ficam
na mesma base de tempo das amostras de entrada.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from filters.butterworth import ButterworthLowPassFilter
from filters.madgwick import MadgwickAttitudeEstimator

from pdr.trajectory import wrap_pi

from .sampling import (
    estimate_sample_rate_hz,
    prepare_timeline,
    resample_segment,
    sanitize_rate_hz,
)
from .steps import StepDetectorConfig, StepEvent, PeakStepDetector


@dataclass(frozen=True, slots=True)
class StepResult:
    steps: list[StepEvent]
    sample_rate_hz: float
    distance_m: float
    mean_yaw_rad: float
    valid: bool
    message: str
    time_valid: bool = True

    @property
    def steps_count(self) -> int:
        return len(self.steps)


def detect_steps_from_samples(
    samples: list,
    config: StepDetectorConfig | None = None,
) -> StepResult:
    """Conta passos a partir de amostras brutas. Não grava nada e não lança HTTP."""
    config = config or StepDetectorConfig()
    if not samples:
        return _empty("Amostras insuficientes.", time_valid=False)

    segments = prepare_timeline(samples, max_gap_s=config.max_gap_s)
    usable = [segment for segment in segments if len(segment) >= config.min_samples]
    if not usable:
        span_ok = len(segments) > 0 and any(len(segment) >= 2 for segment in segments)
        return _empty(
            "Amostras insuficientes." if not span_ok else "Tempo de amostragem inválido.",
            time_valid=span_ok,
        )

    all_timestamps = [sample.timestamp for segment in usable for sample in segment]
    measured = estimate_sample_rate_hz(all_timestamps)
    if not np.isfinite(measured):
        return _empty("Tempo de amostragem inválido.", time_valid=False)

    detector = PeakStepDetector(config=config)
    events: list[StepEvent] = []
    yaw_chunks: list[np.ndarray] = []
    rates: list[float] = []
    # Um Madgwick para a gravação inteira. O heading zera na pose do
    # checkpoint (primeira amostra), não de novo a cada gap.
    estimator = MadgwickAttitudeEstimator(gain=config.madgwick_gain)
    recording_yaw0: float | None = None
    previous_timestamp: float | None = None

    for segment in usable:
        rate = sanitize_rate_hz(estimate_sample_rate_hz(
            [sample.timestamp for sample in segment]
        ))
        resampled = resample_segment(segment, rate)
        if resampled is None:
            continue
        timestamps, channels = resampled
        if len(timestamps) < 2:
            continue
        used_rate = float((len(timestamps) - 1) / (timestamps[-1] - timestamps[0]))
        rates.append(used_rate)

        dt = np.diff(timestamps)
        vertical = np.empty(len(timestamps), dtype=np.float64)
        yaws = np.empty(len(timestamps), dtype=np.float64)
        for index in range(len(timestamps)):
            if previous_timestamp is None:
                sample_dt = float(dt[0])
            else:
                # O primeiro sample do segmento seguinte usa o dt do gap.
                sample_dt = float(timestamps[index] - previous_timestamp)
            if not np.isfinite(sample_dt) or sample_dt <= 0:
                sample_dt = float(dt[0])
            previous_timestamp = float(timestamps[index])
            quaternion = estimator.update_imu(
                gx=float(channels["gyro_x"][index]),
                gy=float(channels["gyro_y"][index]),
                gz=float(channels["gyro_z"][index]),
                ax=float(channels["accel_x"][index]),
                ay=float(channels["accel_y"][index]),
                az=float(channels["accel_z"][index]),
                dt=sample_dt,
            )
            vertical[index] = quaternion.get_vertical_acceleration(
                float(channels["accel_x"][index]),
                float(channels["accel_y"][index]),
                float(channels["accel_z"][index]),
            )
            yaws[index] = quaternion.yaw
        yaw_chunks.append(yaws)
        if recording_yaw0 is None and len(yaws):
            recording_yaw0 = float(yaws[0])

        gyro_magnitude = np.sqrt(
            channels["gyro_x"] ** 2 + channels["gyro_y"] ** 2 + channels["gyro_z"] ** 2
        )
        lowpass = ButterworthLowPassFilter(
            cutoff_hz=config.lowpass_cutoff_hz,
            sample_rate_hz=used_rate,
            order=config.lowpass_order,
        )
        filtered = lowpass.apply(vertical, sample_rate_hz=used_rate)
        segment_events = detector.detect(
            timestamps=timestamps,
            filtered_magnitude=filtered,
            gyro_magnitude=gyro_magnitude,
        )
        # Recalibra uma vez, na pose do checkpoint (primeira amostra da gravação).
        yaw0 = recording_yaw0 if recording_yaw0 is not None else 0.0
        for event in segment_events:
            index = event.index
            yaw = float(yaws[index]) if 0 <= index < len(yaws) else yaw0
            events.append(replace(event, heading_rad=wrap_pi(yaw - yaw0)))

    events = _enforce_refractory(events, config.min_step_interval_s)
    events = _recompute_cadence(events)
    distance = float(sum(step.step_length_m for step in events))
    if yaw_chunks:
        mean_yaw = float(np.mean(np.concatenate(yaw_chunks)))
    else:
        mean_yaw = 0.0
    sample_rate = float(np.median(rates)) if rates else float(measured)

    if not events:
        return StepResult(
            steps=[],
            sample_rate_hz=sample_rate,
            distance_m=0.0,
            mean_yaw_rad=mean_yaw,
            valid=False,
            message="Nenhum passo identificado.",
            time_valid=True,
        )

    return StepResult(
        steps=events,
        sample_rate_hz=sample_rate,
        distance_m=distance,
        mean_yaw_rad=mean_yaw,
        valid=True,
        message="Trecho validado com sucesso!",
        time_valid=True,
    )


def _empty(message: str, time_valid: bool) -> StepResult:
    return StepResult(
        steps=[],
        sample_rate_hz=float("nan"),
        distance_m=0.0,
        mean_yaw_rad=0.0,
        valid=False,
        message=message,
        time_valid=time_valid,
    )


def _enforce_refractory(events: list[StepEvent], min_interval_s: float) -> list[StepEvent]:
    """O refratário também vale na emenda de dois segmentos separados por um gap."""
    kept: list[StepEvent] = []
    for event in events:
        if kept and event.timestamp - kept[-1].timestamp < min_interval_s - 1e-3:
            continue
        kept.append(event)
    return kept


def _recompute_cadence(events: list[StepEvent]) -> list[StepEvent]:
    """Cadência contra o último passo aceito, não contra um pico rejeitado."""
    recomputed: list[StepEvent] = []
    previous: float | None = None
    for event in events:
        if previous is None:
            cadence = 0.0
        else:
            dt = event.timestamp - previous
            cadence = float(60.0 / dt) if dt > 0 else 0.0
        previous = event.timestamp
        recomputed.append(replace(event, cadence_spm=cadence))
    return recomputed
