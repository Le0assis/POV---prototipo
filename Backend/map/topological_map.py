from dataclasses import dataclass, field
import numpy as np
import math
from collections import deque

from typing import Any, Dict


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

def _casefold_node(name: str) -> str:
    """Mesma ideia da collation utf8mb4_unicode_ci: ignora maiúsculas, não o acento."""
    return str(name).casefold()


class TopologicalMap:
    """O Grafo que gerencia os nós e as conexões do prédio mapeado."""
    
    def __init__(self) -> None:
        self.nodes: dict[str, SemanticNode] = {}
        self.edges: list[TopologicalEdge] = []
        # casefold → grafia gravada no checkpoint. O acerto exato não passa por aqui.
        self._folded: dict[str, str] = {}

    def canonical_name(self, name: str) -> str | None:
        """Grafia de ``checkpoints.name``. ``Sala`` e ``sala`` são o mesmo nó.

        Se o texto já é a chave, devolve essa mesma string. Acento continua
        distinto: ``Recepção`` não é ``Recepcao``.
        """
        if name in self.nodes:
            return name
        return self._folded.get(_casefold_node(name))

    def add_checkpoint(self, name: str) -> None:
        """Adiciona um novo nó semântico ao mapa. A primeira grafia fica."""
        if self.canonical_name(name) is not None:
            return
        self.nodes[name] = SemanticNode(name=name)
        self._folded[_casefold_node(name)] = name
        print(f"Checkpoint {name} ")

    def upsert_directed_edge(self, source: str, target: str, distance_m: float, heading_rad: float) -> None:
        """Uma aresta em memória por sentido. Não cria a volta.

        A ponta grava o nome do checkpoint, não a caixa da aresta antiga.
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
        """Gera as coordenadas (x, y) de todos os nós para o Canvas HTML5."""
        if not self.nodes:
            return {"status": "success", "nodes": [], "edges": []}

        # 1. Ponto inicial
        start_node = self.canonical_name("Recepcao") or next(iter(self.nodes))

        positions = {start_node: (0.0, 0.0)}
        visited = {start_node}
        queue = deque([start_node])
        formatted_edges = [] #type: ignore

        # 2. Algoritmo BFS percorrendo o grafo via get_outgoing_edges
        while queue:
            curr_node = queue.popleft()
            curr_x, curr_y = positions[curr_node]

            outgoing_edges = self.get_outgoing_edges(curr_node)

            for edge in outgoing_edges:
                neighbor = edge.target

                # Pega a distância e o ângulo do objeto TopologicalEdge
                dist = getattr(edge, 'distance_m', getattr(edge, 'distance', 0.0))
                
                # Se o ângulo estiver em graus ou radianos no seu objeto
                if hasattr(edge, 'angle_deg'):
                    angle_deg = edge.angle_deg
                elif hasattr(edge, 'heading_rad'):
                    angle_deg = math.degrees(edge.heading_rad)
                else:
                    angle_deg = getattr(edge, 'angle', 0.0)

                # Registra a aresta formatada para o Canvas desenhar a linha
                edge_id = tuple(sorted([curr_node, neighbor]))
                if not any(e['id'] == edge_id for e in formatted_edges):
                    formatted_edges.append({
                        "id": edge_id,
                        "source": curr_node,
                        "target": neighbor,
                        "distance_m": dist
                    })

                # Se o nó vizinho ainda não foi visitado, calcula a posição (x, y) dele
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

                    angle_rad = math.radians(angle_deg)
                    next_x = curr_x + dist * math.cos(angle_rad)
                    next_y = curr_y + dist * math.sin(angle_rad)

                    positions[neighbor] = (round(next_x, 2), round(next_y, 2))

        # Garantia: Se existir algum nó isolado fora do BFS, adiciona ele no mapa
        for node in self.nodes:
            if node not in positions:
                positions[node] = (0.0, 0.0)

        # 3. Formata os Nós para o front-end
        formatted_nodes = [
            {"id": node, "label": node, "x": pos[0], "y": pos[1]}
            for node, pos in positions.items()
        ]

        clean_edges = [
            {"source": e["source"], "target": e["target"], "distance_m": e["distance_m"]}
            for e in formatted_edges
        ]

        return {
            "status": "success",
            "nodes": formatted_nodes,
            "edges": clean_edges
        }