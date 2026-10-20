"""Trajetória de uma gravação: integração na escrita, projeção na leitura.

O banco guarda ``t_ms`` relativo a ``started_at``. A API expõe ``t`` em
segundos de epoch (``started_at + t_ms/1000``) e ``t_rel`` em segundos.
Cadência (passos/minuto) e deslocamento (odômetro, soma dos comprimentos)
não têm coluna: saem dos passos na hora de ler.

Eixos: x para a direita, y para cima, metros, heading anti-horário relativo
à pose no checkpoint (já recalibrado ao gravar).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def wrap_pi(angle: float) -> float:
    """Leva um ângulo para (-pi, pi]."""
    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


def epoch_to_sql_datetime(epoch: float) -> str:
    """DATETIME(3) em UTC, sem fuso gravado (o tipo é naive de propósito)."""
    moment = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def as_epoch_seconds(value: Any) -> float:
    """Interpreta DATETIME naive como UTC, que é como gravamos ``started_at``."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    raise TypeError(f"instante não suportado: {type(value)!r}")


def isoformat_utc(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat(timespec="milliseconds") + "Z"
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return str(value)


def integrate_walk(events: list, t0: float) -> dict:
    """Posição acumulada a partir dos passos já com heading recalibrado.

    ``events`` precisa de ``timestamp``, ``heading_rad`` e ``step_length_m``.
    A polilinha começa em (0, 0), o checkpoint de origem.
    """
    x = 0.0
    y = 0.0
    steps: list[dict] = []
    for index, event in enumerate(events):
        heading = float(event.heading_rad)
        length = float(event.step_length_m)
        x += length * math.cos(heading)
        y += length * math.sin(heading)
        t_ms = int(round((float(event.timestamp) - float(t0)) * 1000.0))
        steps.append({
            "step_index": index,
            "t_ms": t_ms,
            "heading_rad": heading,
            "step_length_m": length,
            "x_m": x,
            "y_m": y,
        })

    total = float(sum(step["step_length_m"] for step in steps))
    if abs(x) > 1e-12 or abs(y) > 1e-12:
        net_heading = math.atan2(y, x)
    elif steps:
        net_heading = float(steps[-1]["heading_rad"])
    else:
        net_heading = 0.0

    return {
        "steps": steps,
        "total_distance_m": total,
        "net_heading_rad": net_heading,
        "polyline": [[0.0, 0.0]] + [[step["x_m"], step["y_m"]] for step in steps],
    }


def points_for_api(started_at: Any, steps: list[dict]) -> list[dict]:
    """Pontos na ordem de ``step_index``. Cadência e deslocamento só aqui."""
    started_epoch = as_epoch_seconds(started_at)
    ordered = sorted(steps, key=lambda step: int(step["step_index"]))
    points: list[dict] = []
    previous_t: float | None = None
    displacement = 0.0
    for step in ordered:
        t_rel = int(step["t_ms"]) / 1000.0
        length = float(step["step_length_m"])
        displacement += length
        if previous_t is None or t_rel <= previous_t:
            cadence = 0.0
        else:
            cadence = 60.0 / (t_rel - previous_t)
        points.append({
            "x": float(step["x_m"]),
            "y": float(step["y_m"]),
            "t": started_epoch + t_rel,
            "t_rel": t_rel,
            "heading": float(step["heading_rad"]),
            "step_length": length,
            "cadence": cadence,
            "displacement": displacement,
        })
        previous_t = t_rel
    return points


def trace_payload(trace: dict, steps: list[dict]) -> dict:
    """Contrato de leitura de uma gravação."""
    return {
        "id": int(trace["id"]),
        "source": trace["source_node"],
        "target": trace["target_node"],
        "edge_id": None if trace.get("edge_id") is None else int(trace["edge_id"]),
        "created_at": isoformat_utc(trace.get("created_at")),
        "started_at": isoformat_utc(trace.get("started_at")),
        "valid": bool(trace.get("is_valid", True)),
        "steps_count": int(trace["total_steps"]),
        "distance_m": float(trace["total_distance_m"]),
        "points": points_for_api(trace["started_at"], steps),
    }
