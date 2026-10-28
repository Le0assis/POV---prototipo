"""Rota gravada Quarto → Cozinha sai mesmo com outro componente no mapa.

A gravação só escreve o sentido andado. O layout publica cada componente,
sem raiz fixa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from map.router import TopologicalRouter
from map.topological_map import TopologicalMap

pytestmark = pytest.mark.unit


def test_rota_gravada_de_quarto_para_cozinha_sai():
    topo = TopologicalMap()
    topo.add_checkpoint("Recepcao")
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint("Cozinha")
    topo.upsert_directed_edge("Quarto", "Cozinha", 6.5, 0.4)

    route = TopologicalRouter(topo).calculate_route("Quarto", "Cozinha")
    assert route == ["Quarto", "Cozinha"]

    layout = topo.get_map_layout()
    edges = layout["edges"]
    assert {"source": "Quarto", "target": "Cozinha", "distance_m": 6.5} in edges
    placed = {node["id"]: (node["x"], node["y"]) for node in layout["nodes"]}
    assert placed["Quarto"] != placed["Cozinha"]
    assert "Recepcao" in placed


def test_layout_publica_todos_os_componentes_sem_raiz_fixa():
    topo = TopologicalMap()
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint("Cozinha")
    topo.add_checkpoint("Sala")
    topo.add_checkpoint("Copa")
    topo.upsert_directed_edge("Quarto", "Cozinha", 6.5, 0.0)
    topo.upsert_directed_edge("Sala", "Copa", 2.0, 1.2)

    layout = topo.get_map_layout()
    pairs = {(edge["source"], edge["target"]) for edge in layout["edges"]}
    assert ("Quarto", "Cozinha") in pairs
    assert ("Sala", "Copa") in pairs
    placed = {node["id"]: (node["x"], node["y"]) for node in layout["nodes"]}
    assert placed["Cozinha"] != (0.0, 0.0)
    assert placed["Copa"] != placed["Sala"]
    assert placed["Sala"] != placed["Quarto"]

    text = Path(__file__).resolve().parents[2].joinpath("map", "topological_map.py").read_text(encoding="utf-8")
    assert 'canonical_name("Recepcao")' not in text
