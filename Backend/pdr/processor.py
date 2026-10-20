"""Orquestra a gravação de uma aresta: persiste o CSV e delega a contagem.

A detecção em si está em ``pdr.pipeline.detect_steps_from_samples``, que não
abre banco e não lança HTTP. Dá para testar o mesmo caminho do
``POST /api/edges/process-raw`` sem MySQL.
"""

import csv
import io
import math

from fastapi import HTTPException

from pdr.trajectory import epoch_to_sql_datetime, integrate_walk

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
        log_result = self.db_manager.save_sensor_log(
            source=source,
            target=target,
            csv_data=csv_string,
        )
        log_id = log_result if type(log_result) is int else None

        result = detect_steps_from_samples(samples, config=self.config)
        if log_id is not None and hasattr(self.db_manager, "update_sensor_log"):
            self.db_manager.update_sensor_log(
                log_id,
                result.steps_count if result.time_valid else 0,
                result.distance_m if result.time_valid else 0.0,
                bool(result.valid and result.time_valid),
                result.message,
            )
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
            "path": None,
        }
        if not result.steps:
            return body

        # Gravação real: só o sentido andado, com a trajetória. Gerenciadores
        # antigos (e o teste que os imita) não têm record_walk e seguem o
        # save_edge + connect_checkpoints de antes.
        if log_id is not None and hasattr(self.db_manager, "record_walk"):
            saved = self.db_manager.record_walk(
                source=source,
                target=target,
                sensors_log_id=log_id,
                started_at=epoch_to_sql_datetime(t0),
                ended_at=epoch_to_sql_datetime(_last_timestamp(samples)),
                built=integrate_walk(result.steps, t0),
            )
            if saved:
                body["path"] = saved.get("path")
                self._remember_directed(
                    source,
                    target,
                    float(saved["edge_distance_m"]),
                    float(saved["edge_heading_rad"]),
                )
            return body

        self.db_manager.save_edge(source, target, result.distance_m, result.mean_yaw_rad)
        angle_deg = float(math.degrees(result.mean_yaw_rad))
        self.topo_map.connect_checkpoints(source, target, distance=result.distance_m, angle_deg=angle_deg)
        return body

    def _remember_directed(self, source: str, target: str, distance_m: float, heading_rad: float) -> None:
        """Atualiza só o sentido andado. Não espelha a volta."""
        if not hasattr(self.topo_map, "upsert_directed_edge"):
            return
        nodes = getattr(self.topo_map, "nodes", None)
        if isinstance(nodes, dict) and hasattr(self.topo_map, "add_checkpoint"):
            if source not in nodes:
                self.topo_map.add_checkpoint(source)
            if target not in nodes:
                self.topo_map.add_checkpoint(target)
        self.topo_map.upsert_directed_edge(source, target, distance_m, heading_rad)


def _timestamps(samples: list) -> list[float]:
    stamps = []
    for sample in samples:
        if isinstance(sample, dict):
            stamps.append(float(sample["timestamp"]))
        else:
            stamps.append(float(sample.timestamp))
    return stamps


def _first_timestamp(samples: list) -> float:
    stamps = _timestamps(samples)
    return min(stamps) if stamps else 0.0


def _last_timestamp(samples: list) -> float:
    stamps = _timestamps(samples)
    return max(stamps) if stamps else 0.0

