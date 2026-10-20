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


def _direction_of(row: dict) -> tuple[str, str]:
    return (row["source_node"], row["target_node"])


def _representative_edge(rows: list[dict]) -> dict:
    """Uma linha por sentido: a que tem trajetória ativa, senão o menor id."""
    traced = [row for row in rows if row.get("active_trace_id") is not None]
    pool = traced or rows
    return min(pool, key=lambda row: int(row["id"]))


def group_edge_pairs(rows: list[dict]) -> list[tuple[dict, dict | None]]:
    """Uma entrada por par físico.

    O sentido listado é o que tem ``active_trace_id``. Se os dois tiverem,
    ou se nenhum tiver, fica o de menor id. O outro sentido volta como
    reverso para o front não desenhar a linha duas vezes.
    """
    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = tuple(sorted((row["source_node"], row["target_node"])))
        buckets.setdefault(key, []).append(row)

    grouped: list[tuple[dict, dict | None]] = []
    ordered_keys = sorted(buckets, key=lambda key: min(int(item["id"]) for item in buckets[key]))
    for key in ordered_keys:
        by_direction: dict[tuple[str, str], list[dict]] = {}
        for row in buckets[key]:
            by_direction.setdefault(_direction_of(row), []).append(row)
        reps = [_representative_edge(group) for group in by_direction.values()]
        traced = [row for row in reps if row.get("active_trace_id") is not None]
        pool = traced or reps
        primary = min(pool, key=lambda row: int(row["id"]))
        reverse = None
        for candidate in reps:
            if _direction_of(candidate) == _direction_of(primary):
                continue
            if reverse is None or int(candidate["id"]) < int(reverse["id"]):
                reverse = candidate
        grouped.append((primary, reverse))
    return grouped


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
