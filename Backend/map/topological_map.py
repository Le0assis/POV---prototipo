from dataclasses import dataclass, field
import numpy as np
import math
from collections import deque

from typing import Any, Dict

from map.checkpoint_slug import checkpoint_name_key


@dataclass
class SemanticNode:
    """Representa um checkpoint semântico no prédio."""
    name: str  # Ex: "Corredor A1", "Recepção"

@dataclass
class TopologicalEdge:
    """Representa o caminho real entre dois checkpoints."""
    source: str       # Nome do nó de origem
    target: str       # Nome do nó de destino
    distance_m: float # Distância física real entre eles (mapeada por você antes)
    heading_rad: float # Ângulo absoluto (Yaw) desse corredor em relação ao Norte magnético

class TopologicalMap:
    """O Grafo que gerencia os nós e as conexões do prédio mapeado."""
    
    def __init__(self) -> None:
        self.nodes: dict[str, SemanticNode] = {}
        self.edges: list[TopologicalEdge] = []

    def canonical_name(self, name: str) -> str | None:
        """Nome já gravado cuja chave casa com ``name``.

        A chave é ``strip``, espaços colapsados e ``casefold``. O texto
        devolvido é o que está no grafo, para exibir e para a aresta.
        ``quarto`` casa com ``Quarto``. ``Recepção`` não casa com ``Recepcao``.
        """
        key = checkpoint_name_key(name)
        if not key:
            return None
        for stored in self.nodes:
            if checkpoint_name_key(stored) == key:
                return stored
        return None

    def add_checkpoint(self, name: str) -> None:
        """Adiciona o rótulo recebido. A mesma chave não duplica.

        Quem grava um nome novo manda o rótulo já limpo. Quem carrega o
        banco manda o texto da linha, para a aresta continuar batendo.
        """
        if not checkpoint_name_key(name):
            return
        if self.canonical_name(name) is not None:
            return
        self.nodes[name] = SemanticNode(name=name)
        print(f"Checkpoint {name} ")

    def upsert_directed_edge(self, source: str, target: str, distance_m: float, heading_rad: float) -> None:
        """Uma aresta em memória por sentido. Não cria a volta.

        As pontas passam por ``canonical_name``. Outra caixa ou espaço
        reusa o rótulo já gravado. Outro acento continua outro nó.
        """
        source_name = self.canonical_name(source)
        target_name = self.canonical_name(target)
        if source_name is None or target_name is None:
            raise ValueError(f"Erro: Ambos os nós '{source}' e '{target}' devem existir antes de os conectar.")

        for edge in self.edges:
            if edge.source == source_name and edge.target == target_name:
                edge.distance_m = float(distance_m)
                edge.heading_rad = float(heading_rad)
                return

        self.edges.append(TopologicalEdge(
            source=source_name,
            target=target_name,
            distance_m=float(distance_m),
            heading_rad=float(heading_rad),
        ))

    def load_directed_edges(self, rows: list) -> None:
        """Carrega linhas de ``edges`` sem espelhar. O maior id do sentido prevalece."""
        ordered = sorted(rows, key=lambda row: int(row.get("id", 0)))
        for row in ordered:
            self.upsert_directed_edge(
                row["source_node"],
                row["target_node"],
                float(row["distance_m"]),
                float(row["heading_rad"]),
            )

    def connect_checkpoints(self, from_node: str, to_node: str, distance: float, angle_deg: float) -> None:
        """Cria ou atualiza ida e volta. Chamar de novo não duplica o sentido."""
        if self.canonical_name(from_node) is None or self.canonical_name(to_node) is None:
            raise ValueError(f"Erro: Ambos os nós '{from_node}' e '{to_node}' devem existir antes de os conectar.")

        heading_ida = float(np.radians(angle_deg))
        self.upsert_directed_edge(from_node, to_node, distance, heading_ida)
        heading_volta = float((heading_ida + np.pi) % (2 * np.pi))
        self.upsert_directed_edge(to_node, from_node, distance, heading_volta)

    def get_outgoing_edges(self, node_name: str) -> list[TopologicalEdge]:
        """Retorna todas as arestas/caminhos possíveis a partir de um nó específico."""
        
        connection: list[TopologicalEdge] = []
        
        resolved = self.canonical_name(node_name)
        if resolved is None:
            raise ValueError(f"Erro: O no {node_name} deve existir.")
        node_name = resolved
        
        for item in self.edges:
            if item.source == node_name:
                connection.append(item)
        
        return connection

    def get_map_layout(self) -> dict:
        """Coordenadas de cada componente. Publica toda aresta gravada.

        Não há raiz fixa. Cada componente fraco começa no primeiro nó
        ainda sem posição, na ordem em que entrou no grafo. O seguinte
        fica à direita do que já foi colocado, para não empilhar em (0, 0).
        """
        if not self.nodes:
            return {"status": "success", "nodes": [], "edges": []}

        formatted_edges = []
        seen_pairs = set()
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                continue
            pair = tuple(sorted((edge.source, edge.target)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            formatted_edges.append({
                "source": edge.source,
                "target": edge.target,
                "distance_m": edge.distance_m,
            })

        adjacency: dict[str, list[tuple[str, float, float, bool]]] = {
            name: [] for name in self.nodes
        }
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                continue
            adjacency[edge.source].append((edge.target, edge.distance_m, edge.heading_rad, True))
            adjacency[edge.target].append((edge.source, edge.distance_m, edge.heading_rad, False))

        positions: dict[str, tuple[float, float]] = {}
        cursor_x = 0.0
        for root in self.nodes:
            if root in positions:
                continue
            positions[root] = (round(cursor_x, 2), 0.0)
            queue = deque([root])
            while queue:
                current = queue.popleft()
                curr_x, curr_y = positions[current]
                for neighbor, dist, heading, forward in adjacency[current]:
                    if neighbor in positions:
                        continue
                    angle = heading if forward else heading + math.pi
                    positions[neighbor] = (
                        round(curr_x + dist * math.cos(angle), 2),
                        round(curr_y + dist * math.sin(angle), 2),
                    )
                    queue.append(neighbor)
            cursor_x = max(point[0] for point in positions.values()) + 1.0

        formatted_nodes = [
            {"id": node, "label": node, "x": positions[node][0], "y": positions[node][1]}
            for node in self.nodes
        ]
        return {
            "status": "success",
            "nodes": formatted_nodes,
            "edges": formatted_edges,
        }