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

class TopologicalMap:
    """O Grafo que gerencia os nós e as conexões do prédio mapeado."""
    
    def __init__(self) -> None:
        self.nodes: dict[str, SemanticNode] = {}
        self.edges: list[TopologicalEdge] = []

    def add_checkpoint(self, name: str) -> None:
        """Adiciona um novo nó semântico ao mapa."""
        node = SemanticNode(
            name=name,
        )
        
        self.nodes[name] = node
        
        print(f"Checkpoint {name} ")
        

    def connect_checkpoints(self, from_node: str, to_node: str, distance: float, angle_deg: float) -> None:
        """Cria uma conexão de ida e volta entre dois checkpoints, salvando a distância 
            e calculando os ângulos absolutos de orientação para ambos os sentidos.
        """
        # 1. Validação de segurança
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError(f"Erro: Ambos os nós '{from_node}' e '{to_node}' devem existir antes de os conectar.")
        
        # 2. Sentido de Ida (From -> To)
        heading_ida = np.radians(angle_deg)
        edge_ida = TopologicalEdge(
            source=from_node,
            target=to_node,
            distance_m=distance,
            heading_rad=heading_ida
        )
        self.edges.append(edge_ida) 
        
        # 3. Sentido de Volta (To -> From) - Ângulo espelhado (+ 180 graus / + Pi radianos)
        heading_volta = (heading_ida + np.pi) % (2 * np.pi)
        edge_volta = TopologicalEdge(
            source=to_node,
            target=from_node,
            distance_m=distance,
            heading_rad=heading_volta
        )
        self.edges.append(edge_volta)

    def get_outgoing_edges(self, node_name: str) -> list[TopologicalEdge]:
        """Retorna todas as arestas/caminhos possíveis a partir de um nó específico."""
        
        connection: list[TopologicalEdge] = []
        
        if node_name not in self.nodes:
            raise ValueError(f"Erro: O no {node_name} deve existir.")
        
        for item in self.edges:
            if item.source == node_name:
                connection.append(item)
        
        return connection

    def get_map_layout(self) -> dict:
        """Gera as coordenadas (x, y) de todos os nós para o Canvas HTML5."""
        if not self.nodes:
            return {"status": "success", "nodes": [], "edges": []}

        # 1. Ponto inicial
        start_node = "Recepcao" if "Recepcao" in self.nodes else list(self.nodes.keys())[0]

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