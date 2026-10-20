"""Orquestra a gravação de uma aresta: persiste o CSV e delega a contagem.

A detecção em si está em ``pdr.pipeline.detect_steps_from_samples``, que não
abre banco e não lança HTTP. Dá para testar o mesmo caminho do
``POST /api/edges/process-raw`` sem MySQL.
"""

import csv
import io
import math

from fastapi import HTTPException

from .pipeline import detect_steps_from_samples
from .steps import StepDetectorConfig, StepEvent


def _sample_dict(sample) -> dict:
    if isinstance(sample, dict):
        return sample
    if hasattr(sample, "model_dump"):
        return sample.model_dump()
    return sample.dict()


def generate_sensors_csv(samples: list) -> str:
    """Converte a lista de dicionários/amostras em uma string CSV."""
    output = io.StringIO()
    if not samples:
        return ""

    rows = [_sample_dict(sample) for sample in samples]
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def steps_payload(events: list[StepEvent], t0: float) -> list[dict]:
    """Campo opcional da API. ``t`` está na mesma base dos samples de entrada."""
    payload = []
    for event in events:
        payload.append({
            "t": float(event.timestamp),
            "t_rel": float(event.timestamp - t0),
            "length_m": float(event.step_length_m),
            "cadence_spm": float(event.cadence_spm),
        })
    return payload


class RawEdgeProcessor:
    def __init__(self, db_manager, topo_map, config: StepDetectorConfig | None = None):
        self.db_manager = db_manager
        self.topo_map = topo_map
        self.config = config or StepDetectorConfig()

    def process_samples(self, source: str, target: str, samples: list):
        if not samples or len(samples) < 20:
            raise HTTPException(status_code=400, detail="Amostras insuficientes (mínimo 20).")

        csv_string = generate_sensors_csv(samples)
        self.db_manager.save_sensor_log(
            source=source,
            target=target,
            csv_data=csv_string,
        )

        result = detect_steps_from_samples(samples, config=self.config)
        if not result.time_valid:
            raise HTTPException(status_code=400, detail="Tempo de amostragem inválido.")

        t0 = _first_timestamp(samples)
        body = {
            "status": "success" if result.valid else "warning",
            "valid": result.valid,
            "source": source,
            "target": target,
            "message": result.message,
            "steps_count": result.steps_count,
            "distance_m": round(result.distance_m, 2),
            "mean_yaw_rad": round(result.mean_yaw_rad, 4),
            "steps": steps_payload(result.steps, t0),
        }
        if not result.steps:
            return body

        self.db_manager.save_edge(source, target, result.distance_m, result.mean_yaw_rad)
        angle_deg = float(math.degrees(result.mean_yaw_rad))
        self.topo_map.connect_checkpoints(source, target, distance=result.distance_m, angle_deg=angle_deg)
        return body


def _first_timestamp(samples: list) -> float:
    stamps = []
    for sample in samples:
        if isinstance(sample, dict):
            stamps.append(float(sample["timestamp"]))
        else:
            stamps.append(float(sample.timestamp))
    return min(stamps) if stamps else 0.0

