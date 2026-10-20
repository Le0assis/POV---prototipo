"""Regras puras da aresta: uma linha por sentido, manual vence, senão mediana."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def split_duplicate_edges(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Agrupa por sentido e fica com o maior ``id`` (inserção mais recente).

    As demais linhas são as que a migração apaga. A ordem de entrada não
    importa: o critério é só o id.
    """
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["source_node"], row["target_node"])
        grouped.setdefault(key, []).append(row)

    kept: list[dict] = []
    removed: list[dict] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: int(item["id"]))
        kept.append(ordered[-1])
        removed.extend(ordered[:-1])
    removed.sort(key=lambda item: int(item["id"]))
    return kept, removed


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("mediana de lista vazia")
    ordered = sorted(float(value) for value in values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def circular_mean(angles: list[float]) -> float:
    """Média circular em radianos, no intervalo de atan2 (-pi, pi]."""
    if not angles:
        raise ValueError("média circular de lista vazia")
    sin_sum = sum(math.sin(float(angle)) for angle in angles)
    cos_sum = sum(math.cos(float(angle)) for angle in angles)
    return math.atan2(sin_sum, cos_sum)


def _started_sort_key(value: Any) -> tuple:
    if isinstance(value, datetime):
        return (0, value.timestamp())
    if isinstance(value, (int, float)):
        return (0, float(value))
    return (1, str(value))


def resolve_recorded_edge(existing: dict | None, traces: list[dict]) -> dict:
    """Distância e heading do sentido depois de uma gravação válida.

    ``origin='manual'`` conserva distância e heading. Sem manual, a distância
    é a mediana das trajetórias válidas daquele sentido e o heading é a média
    circular dos ``net_heading_rad``. ``active_trace_id`` é sempre a válida
    mais recente (started_at, depois id).
    """
    valid = [trace for trace in traces if trace.get("is_valid", True)]
    if not valid:
        raise ValueError("não há trajetória válida para agregar a aresta")

    latest = max(valid, key=lambda trace: (_started_sort_key(trace["started_at"]), int(trace["id"])))
    active_id = int(latest["id"])
    if existing is not None and existing.get("origin") == "manual":
        return {
            "distance_m": float(existing["distance_m"]),
            "heading_rad": float(existing["heading_rad"]),
            "origin": "manual",
            "active_trace_id": active_id,
        }
    return {
        "distance_m": median([float(trace["total_distance_m"]) for trace in valid]),
        "heading_rad": circular_mean([float(trace["net_heading_rad"]) for trace in valid]),
        "origin": "recorded",
        "active_trace_id": active_id,
    }
