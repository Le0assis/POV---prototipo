"""Lista agrupada e detalhe do sentido pedido. Sem MySQL."""

from __future__ import annotations

from datetime import datetime

import pytest

from map.MapDatabaseManager import MapDatabaseManager

pytestmark = pytest.mark.unit

STARTED = datetime(2026, 10, 20, 16, 5, 11, 20000)


class _MemDB:
    def __init__(self) -> None:
        self.edges = [
            {
                "id": 7,
                "source_node": "Recepcao",
                "target_node": "Corredor",
                "distance_m": 4.5,
                "heading_rad": 0.0,
                "origin": "manual",
                "active_trace_id": None,
                "samples_count": 0,
            },
            {
                "id": 8,
                "source_node": "Corredor",
                "target_node": "Recepcao",
                "distance_m": 4.5,
                "heading_rad": 3.14,
                "origin": "manual",
                "active_trace_id": None,
                "samples_count": 0,
            },
            {
                "id": 42,
                "source_node": "Quarto",
                "target_node": "Sala",
                "distance_m": 2.62,
                "heading_rad": 0.031,
                "origin": "recorded",
                "active_trace_id": 17,
                "samples_count": 3,
            },
            {
                "id": 43,
                "source_node": "Sala",
                "target_node": "Quarto",
                "distance_m": 2.62,
                "heading_rad": 3.1,
                "origin": "manual",
                "active_trace_id": None,
                "samples_count": 0,
            },
        ]
        self.traces = [{
            "id": 17,
            "source_node": "Quarto",
            "target_node": "Sala",
            "started_at": STARTED,
            "total_steps": 1,
            "total_distance_m": 2.6,
            "is_valid": 1,
            "polyline_json": None,
        }]
        self.steps = [{
            "trace_id": 17,
            "step_index": 0,
            "t_ms": 1000,
            "heading_rad": 0.02,
            "step_length_m": 2.6,
            "x_m": 2.6,
            "y_m": 0.08,
        }]

    def execute_search(self, sql, params=None):
        params = params or ()
        if "FROM walk_steps" in sql and " IN (" in sql:
            ids = set(params)
            return [step for step in self.steps if step["trace_id"] in ids]
        if "FROM walk_steps" in sql:
            return [step for step in self.steps if step["trace_id"] == params[0]]
        if "FROM walk_traces" in sql and " IN (" in sql:
            ids = set(params)
            return [row for row in self.traces if row["id"] in ids]
        if "FROM walk_traces" in sql and "WHERE id = %s" in sql:
            return [row for row in self.traces if row["id"] == params[0]]
        if "FROM walk_traces" in sql:
            return [
                row for row in self.traces
                if row["source_node"] == params[0] and row["target_node"] == params[1]
            ]
        if "FROM edges" in sql and "WHERE id = %s" in sql:
            return [row for row in self.edges if row["id"] == params[0]]
        if "FROM edges" in sql and "CAST(source_node AS BINARY)" in sql:
            return [
                row for row in self.edges
                if row["source_node"] == params[0] and row["target_node"] == params[1]
            ]
        if "FROM edges" in sql:
            return list(self.edges)
        raise AssertionError(sql)


def test_list_groups_pairs_and_manual_path_is_straight():
    listed = MapDatabaseManager(_MemDB()).list_connections(include_path=True)
    assert [item["edge_id"] for item in listed] == [7, 42]
    manual = listed[0]
    assert manual["reverse_edge_id"] == 8
    assert manual["samples_count"] == 0
    assert manual["steps_count"] is None
    assert manual["recorded_at"] is None
    assert manual["path"][0] == {"x": 0.0, "y": 0.0, "t": None}
    assert manual["path"][1]["x"] == pytest.approx(4.5)
    assert manual["path"][1]["y"] == pytest.approx(0.0)
    assert manual["path"][1]["t"] is None
    recorded = listed[1]
    assert recorded["reverse_edge_id"] == 43
    assert recorded["samples_count"] == 3
    assert recorded["origin"] == "recorded"
    assert recorded["steps_count"] == 1
    assert recorded["recorded_at"] == "2026-10-20T16:05:11.020Z"
    assert len(recorded["path"]) == 2
    assert recorded["path"][0]["x"] == 0.0
    assert recorded["path"][1]["x"] == pytest.approx(2.6)
    assert recorded["path"][0]["t"] is not None


def test_include_path_false_omits_the_key():
    listed = MapDatabaseManager(_MemDB()).list_connections(include_path=False)
    assert "path" not in listed[0]
    assert listed[0]["reverse_edge_id"] == 8


def test_list_connections_is_not_n_plus_one():
    class _Counting(_MemDB):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def execute_search(self, sql, params=None):
            self.calls += 1
            return super().execute_search(sql, params)

    database = _Counting()
    listed = MapDatabaseManager(database).list_connections(include_path=True)
    assert len(listed) == 2
    assert database.calls == 3
    without_path = _Counting()
    MapDatabaseManager(without_path).list_connections(include_path=False)
    assert without_path.calls == 2


def test_detail_returns_the_requested_direction():
    detail = MapDatabaseManager(_MemDB()).get_connection(43)
    assert detail["edge_id"] == 43
    assert detail["source"] == "Sala"
    assert detail["target"] == "Quarto"
    assert detail["reverse_edge_id"] == 42
    assert detail["traces"] == []
    forward = MapDatabaseManager(_MemDB()).get_connection(42)
    assert forward["traces"][0]["trace_id"] == 17
    assert forward["traces"][0]["is_valid"] is True
    assert len(forward["traces"][0]["path"]) == 2
    assert MapDatabaseManager(_MemDB()).get_connection(99) is None
