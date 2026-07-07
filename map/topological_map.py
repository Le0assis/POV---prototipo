from dataclasses import dataclass, field
import numpy as np

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
        
        