"""Rota gravada Quarto → Cozinha tem de sair mesmo com a Recepção no mapa.

A gravação só escreve o sentido andado. O layout não pode descartar essa
aresta só porque o BFS começa na Recepção, que não chega nela.
"""

from __future__ import annotations

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

    edges = topo.get_map_layout()["edges"]
    assert {"source": "Quarto", "target": "Cozinha", "distance_m": 6.5} in edges
