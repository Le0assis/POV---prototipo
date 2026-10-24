"""Seed do mapa de exemplo. Pode rodar de novo: não apaga e não sobrescreve.

Usa DB_NAME / DB_USER do ambiente (padrão POV / root), o mesmo da API.
Checkpoint repetido fica como está. Aresta que já existe não muda distância
nem origin. Rode depois de ``python -m datasets.create_tables``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.create_tables import conexao_from_settings
from map.checkpoint_slug import DEFAULT_BUILDING_ID, allocate_slug

CHECKPOINTS = [
    "Recepcao",
    "Corredor A",
    "Sala 101",
    "Sala 102",
    "Sala 103",
    "Corredor B",
    "Banheiro",
    "Escada",
]

# source, target, metros, radianos. O sentido inverso é outra linha.
EDGES = [
    ("Recepcao", "Corredor A", 4.5, 0.0),
    ("Corredor A", "Sala 101", 2.0, 1.57),
    ("Corredor A", "Sala 102", 5.0, 1.57),
    ("Corredor A", "Corredor B", 8.0, 0.0),
    ("Corredor B", "Sala 103", 3.0, 1.57),
    ("Corredor B", "Banheiro", 2.5, -1.57),
    ("Corredor B", "Escada", 4.0, 0.0),
]

SQL_SLUGS = "SELECT slug FROM checkpoints WHERE building_id = %s AND slug IS NOT NULL"
SQL_CHECKPOINT = (
    "INSERT INTO checkpoints (name, building_id, slug) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE name = name"
)
SQL_EDGE = (
    "INSERT INTO edges (source_node, target_node, distance_m, heading_rad, origin) "
    "VALUES (%s, %s, %s, %s, 'manual') "
    "ON DUPLICATE KEY UPDATE id = id"
)


def _inverse_heading(heading: float) -> float:
    import math
    return (heading + math.pi) % (2 * math.pi)


def seed(db) -> None:
    rows = db.execute_search(SQL_SLUGS, (DEFAULT_BUILDING_ID,))
    if rows is None:
        raise RuntimeError("Não leu os slugs. Rode create_tables antes do seed.")
    taken = {row["slug"] for row in rows if row.get("slug")}
    print("Inserindo checkpoints...")
    for name in CHECKPOINTS:
        current = db.execute_search("SELECT slug FROM checkpoints WHERE name = %s", (name,))
        if current is None:
            raise RuntimeError(f"Não leu o checkpoint {name}.")
        if current:
            if current[0].get("slug"):
                taken.add(current[0]["slug"])
            continue
        slug = allocate_slug(name, taken)
        if not db.execute_query(SQL_CHECKPOINT, (name, DEFAULT_BUILDING_ID, slug)):
            raise RuntimeError(f"Não gravou o checkpoint {name}. Nada foi apagado.")
        taken.add(slug)
    print("Inserindo conexões...")
    for source, target, distance, heading in EDGES:
        directions = (
            (source, target, distance, heading),
            (target, source, distance, _inverse_heading(heading)),
        )
        for src, tgt, dist, rad in directions:
            if not db.execute_query(SQL_EDGE, (src, tgt, dist, rad)):
                raise RuntimeError(f"Não gravou a aresta {src}->{tgt}. Nada foi apagado.")
    print("Mapa de exemplo garantido. Linha que já existia não foi alterada.")


if __name__ == "__main__":
    db = conexao_from_settings()
    db.connect()
    if not db.connection:
        raise SystemExit("Erro ao conectar. Confira DB_HOST, DB_NAME, DB_USER e DB_PASSWORD.")
    try:
        seed(db)
    finally:
        db.disconnect()
