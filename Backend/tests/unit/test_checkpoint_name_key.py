"""Chave do checkpoint: caixa, espaço e rota. Acento continua distinto."""

from __future__ import annotations

import pytest

from map.checkpoint_slug import checkpoint_name_key, display_checkpoint_name
from map.router import TopologicalRouter
from map.topological_map import TopologicalMap

pytestmark = pytest.mark.unit


def test_key_strips_collapses_and_casefolds_without_dropping_accents():
    assert display_checkpoint_name("  QUARTO  ") == "QUARTO"
    assert display_checkpoint_name("quarto   de   visita") == "quarto de visita"
    assert checkpoint_name_key("Quarto") == checkpoint_name_key("  QUARTO ")
    assert checkpoint_name_key("quarto   de   visita") == checkpoint_name_key("QUARTO de visita")
    assert checkpoint_name_key("Straße") == checkpoint_name_key("STRASSE")
    assert checkpoint_name_key("Recepção") != checkpoint_name_key("Recepcao")
    assert checkpoint_name_key("  ") == ""


def test_route_accepts_case_and_space_and_keeps_the_stored_label():
    topo = TopologicalMap()
    topo.add_checkpoint("Quarto")
    topo.add_checkpoint("Cozinha")
    topo.add_checkpoint(" QUARTO ")
    topo.add_checkpoint("cozinha")
    topo.upsert_directed_edge("quarto", "  COZINHA ", 6.5, 0.4)

    assert list(topo.nodes) == ["Quarto", "Cozinha"]
    assert [(edge.source, edge.target) for edge in topo.edges] == [("Quarto", "Cozinha")]

    route = TopologicalRouter(topo).calculate_route("  quarto ", "COZINHA")
    assert route == ["Quarto", "Cozinha"]
    assert TopologicalRouter(topo).calculate_route("Quartô", "Cozinha") == []
