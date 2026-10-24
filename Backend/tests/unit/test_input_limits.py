"""Limites de entrada, id da rota gravada e leitura só da aresta canônica."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.app import route_label
from api.schema import (
    MAX_RAW_SAMPLES,
    NAME_MAX,
    CheckpointSchema,
    EdgeSchema,
    MapConfigSchema,
    ProcessRawEdgeSchema,
    RouteCreateSchema,
)
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from pdr.processor import RawEdgeProcessor

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]


def test_checkpoint_and_edge_reject_overlong_and_non_finite_values():
    with pytest.raises(ValidationError):
        CheckpointSchema(name="N" * (NAME_MAX + 1))
    with pytest.raises(ValidationError):
        CheckpointSchema(name="Sala", category_code="c" * 33)
    with pytest.raises(ValidationError):
        EdgeSchema(source="A", target="B", distance_m=float("nan"), heading_rad=0.0)
    with pytest.raises(ValidationError):
        EdgeSchema(source="A", target="B", distance_m=float("inf"), heading_rad=0.0)
    with pytest.raises(ValidationError):
        EdgeSchema(source="A", target="B", distance_m=1.0, heading_rad=float("nan"))
    with pytest.raises(ValidationError):
        MapConfigSchema(px_per_m=float("nan"))
    with pytest.raises(ValidationError):
        MapConfigSchema(plan_image="a" * 513, px_per_m=10)
    route = RouteCreateSchema(start_node="A", end_node="B", name="  ")
    assert route.name is None
    samples = ProcessRawEdgeSchema.model_json_schema()["properties"]["samples"]
    assert samples["maxItems"] == MAX_RAW_SAMPLES


def test_route_label_fits_the_name_column():
    auto = route_label(None, "A" * NAME_MAX, "B" * NAME_MAX)
    assert len(auto) == NAME_MAX
    assert route_label("  Corredor  ", "A", "B") == "Corredor"
    assert route_label(None, "Sala", "Quarto") == "Sala → Quarto"


def test_save_route_returns_the_insert_id():
    class _DB:
        def execute_insert(self, sql, params=None):
            self.sql = sql
            self.params = params
            return 15

    database = _DB()
    route_id = MapDatabaseManager(database).save_route(
        "Rota", "Sala", "Quarto",
        [{"distance_m": 2.0}],
        ["Sala", "Quarto"],
    )
    assert route_id == 15
    assert "INSERT INTO saved_routes" in database.sql
    assert database.params[0] == "Rota"

    class _Fail(_DB):
        def execute_insert(self, sql, params=None):
            return None

    assert MapDatabaseManager(_Fail()).save_route(
        "Rota", "Sala", "Quarto", [{"distance_m": 1.0}], ["Sala"],
    ) is None


def test_map_load_keeps_the_canonical_edge():
    class _DB:
        def execute_search(self, sql, params=None):
            if "FROM checkpoints" in sql or "SELECT name FROM checkpoints" in sql:
                return [{"name": "Sala"}, {"name": "Quarto"}]
            if "FROM edges" in sql:
                rows = [
                    {
                        "id": 9,
                        "source_node": "Sala",
                        "target_node": "Quarto",
                        "distance_m": 999.0,
                        "heading_rad": 2.0,
                        "dup_rank": 1,
                    },
                    {
                        "id": 2,
                        "source_node": "Sala",
                        "target_node": "Quarto",
                        "distance_m": 4.0,
                        "heading_rad": 0.1,
                        "dup_rank": 0,
                    },
                ]
                if "dup_rank = 0" not in sql:
                    return rows
                return [row for row in rows if row["dup_rank"] == 0]
            raise AssertionError(sql)

    topo = TopologicalMap()
    MapDatabaseManager(_DB()).load_map_into_system(topo)
    edges = topo.get_outgoing_edges("Sala")
    assert len(edges) == 1
    assert edges[0].distance_m == 4.0
    assert edges[0].target == "Quarto"


def test_traces_by_id_does_not_emit_an_empty_in():
    class _DB:
        def execute_search(self, sql, params=None):
            raise AssertionError(sql)

    assert MapDatabaseManager(_DB())._traces_by_id([]) == {}


def test_too_many_samples_never_open_the_log():
    class _DB:
        def save_sensor_log(self, *args, **kwargs):
            raise AssertionError("log")

    samples = [{"timestamp": 0.0}] * (MAX_RAW_SAMPLES + 1)
    with pytest.raises(HTTPException) as exc:
        RawEdgeProcessor(_DB(), TopologicalMap()).process_samples("A", "B", samples)
    assert exc.value.status_code == 400
    assert "máximo" in exc.value.detail


def test_session_state_and_the_pool_stay_where_they_were():
    database = (BACKEND / "datasets" / "ManagerDatabase.py").read_text(encoding="utf-8")
    app = (BACKEND / "api" / "app.py").read_text(encoding="utf-8")
    walk = (BACKEND / "api" / "walk_session.py").read_text(encoding="utf-8")
    assert "MySQLConnectionPool" not in database
    assert "MySQLConnectionPool" not in app
    assert "def checkout_connection" in database
    assert "global matcher" not in app
    assert "visited_path = [" not in app
    assert "self.visited_path" in walk
    assert "self.matcher" in walk
