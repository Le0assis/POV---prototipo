from map.topological_map import TopologicalMap
from pdr.steps import StepEvent
import numpy as np

class TopologicalMatcher:
    """Gerencia a localização atual do usuário dentro do grafo semântico."""
    
    def __init__(self, topo_map: TopologicalMap, starting_node: str) -> None:
        self.map = topo_map
        self.current_node_name: str = starting_node
        
        # Acumuladores de caminhada dentro do corredor atual
        self.accumulated_distance: float = 0.0

    def process_step(self, step: StepEvent, current_yaw_rad: float) -> str:
        """
        Invocada a cada passo detectado pelo PDR. Atualiza a posição do utilizador
        dentro do grafo semântico/topológico se ele atingir um checkpoint.
        """
        # 1. Acumular a distância percorrida pelo passo atual
        self.accumulated_distance += step.step_length_m

        # 2. Buscar no mapa todas as arestas/corredores que saem do nó atual
        outgoing_edges = self.map.get_outgoing_edges(self.current_node_name)

        # 3. Definir uma tolerância angular aceitável (ex: 30 graus convertidos para radianos)
        # Se a diferença entre o Yaw do celular e o Yaw do corredor for menor que isso,
        # significa que o utilizador está a caminhar neste corredor.
        angle_tolerance_rad = np.radians(30.0)

        # 4. Procurar a aresta correta baseando-se na direção (Yaw)
        matching_edge = None
        for edge in outgoing_edges:
            # Truque matemático: diferença circular de ângulos usando arctan2(sin, cos)
            # Isto evita problemas quando um ângulo é 1° e o outro é 359° (a diferença real é 2°)
            angle_diff = np.arctan2(
                np.sin(current_yaw_rad - edge.heading_rad),
                np.cos(current_yaw_rad - edge.heading_rad)
            )
            
            # Se o módulo do erro angular estiver dentro da tolerância, achámos o corredor!
            if abs(angle_diff) <= angle_tolerance_rad:
                matching_edge = edge
                break  # Encontrou o corredor atual, pode parar a busca

        # 5. Se encontrámos o corredor ativo, verificar se o utilizador chegou ao fim dele
        if matching_edge is not None:
            # Se a distância acumulada pelo utilizador atingiu ou passou a distância da aresta
            if self.accumulated_distance >= matching_edge.distance_m:
                # Transição de Estado: O utilizador acabou de chegar ao checkpoint de destino
                self.current_node_name = matching_edge.target
                
                # Zera o odômetro para começar a contar o próximo corredor do zero
                self.accumulated_distance = 0.0
                
                print(f"[Matcher] CHECKPOINT ALCANCADO: Chegou a '{self.current_node_name}'!")
        else:
            # Caso o utilizador mude de direção brusca ou o sensor ruede muito e não ache aresta,
            # como Sênior, uma boa prática é reduzir ligeiramente ou manter a distância para debug.
            pass

        # 6. Retorna sempre onde o utilizador está agora (seja o mesmo nó ou o novo)
        return self.current_node_name
    
    @property
    def current_node(self) -> str:
        """Expose o nó atual de forma limpa para a API."""
        return self.current_node_name