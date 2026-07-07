import heapq
from map.topological_map import TopologicalMap

class TopologicalRouter:
    """Responsável por calcular caminhos e rotas dentro do grafo semântico."""

    def __init__(self, topo_map: TopologicalMap) -> None:
        self.map = topo_map

    def calculate_route(self, start_node: str, end_node: str) -> list[str]:
        """Calcula a rota mais curta entre dois checkpoints usando o Algoritmo de Dijkstra.

        Args:
            start_node: Nome do checkpoint de origem (ex: 'Quarto')
            end_node: Nome do checkpoint de destino (ex: 'Cozinha')

        Returns:
            Uma lista ordenada com os nomes dos nós (ex: ['Quarto', 'Corredor 1', 'Cozinha'])
            Retorna uma lista vazia [] se não houver caminho possível.
        """
        # 1. VALIDAÇÃO INICIAL
        # Verifique se start_node e end_node existem no dicionário self.map.nodes.
        # Se algum não existir, retorne uma lista vazia [] imediatamente.
        if start_node not in self.map.nodes or end_node not in self.map.nodes:
            return []

        # 2. ESTRUTURAS DE CONTROLE
        # Crie um dicionário chamado 'distances' onde a chave é o nome do nó e o valor é float('inf')
        # Em seguida, defina que a distância para o start_node é 0.0
        distances = {node: float('inf') for node in self.map.nodes}
        distances[start_node] = 0.0

        # Crie um dicionário chamado 'predecessors' para guardar quem é o "pai" de cada nó
        # Inicialize todas as chaves (nós) com None
        predecessors = {node: None for node in self.map.nodes}

        # 3. A FILA DE PRIORIDADE (Min-Heap)
        # Em Python, guardamos tuplas na fila: (distancia_acumulada, nome_do_no)
        # O heapq sempre deixa o menor valor no topo.
        priority_queue = [(0.0, start_node)]

        # 4. O LOOP PRINCIPAL
        while priority_queue:
            # Extraia o nó com a menor distância usando heapq.heappop
            current_distance, current_node = heapq.heappop(priority_queue)

            # Otimização: Se já chegamos no nó de destino, podemos parar o cálculo!
            if current_node == end_node:
                break

            # Se a distância extraída for maior do que a distância que já temos gravada,
            # significa que encontramos um caminho obsoleto na fila. Apenas ignore (continue).
            if current_distance > distances[current_node]:
                continue

            # 5. EXPLORANDO OS VIZINHOS
            # Busque as arestas que saem de current_node usando self.map.get_outgoing_edges
            outgoing_edges = self.map.get_outgoing_edges(current_node)
            
            for edge in outgoing_edges:
                neighbor = edge.target
                
                # Calcule o custo para ir até esse vizinho passando por aqui
                # Custo = distância acumulada do current_node + o peso da aresta (edge.distance_m)
                tentative_distance = current_distance + edge.distance_m

                # Se esse novo custo for MENOR do que o que estava gravado para o vizinho:
                if tentative_distance < distances[neighbor]:
                    # A) Atualize o dicionário 'distances' do vizinho com o tentative_distance
                    distances[neighbor] = tentative_distance
                    
                    # B) Atualize o dicionário 'predecessors' do vizinho dizendo que o pai dele é o current_node
                    predecessors[neighbor] = current_node
                    
                    # C) Insira essa nova descoberta na fila usando heapq.heappush(priority_queue, (tentative_distance, neighbor))
                    heapq.heappush(priority_queue, (tentative_distance, neighbor))

        # 6. RECONSTRUÇÃO DO CAMINHO (BACKTRACKING)
        # Se o loop acabou e o predecessors[end_node] continuar None (e end_node != start_node), 
        # significa que é impossível chegar lá. Retorne []
        if predecessors[end_node] is None and start_node != end_node:
            return []

        # Crie uma lista chamada 'path'
        path = []
        step_node = end_node
        
        # Monte o caminho de trás para frente:
        # Enquanto step_node não for None:
        #   Insira step_node na lista path
        #   Mude step_node para predecessors[step_node]
        while step_node is not None:
            path.append(step_node)
            step_node = predecessors[step_node]

        # Como o caminho foi montado de trás para frente (Destino -> Origem), 
        # inverta a lista antes de retornar! (Dica Python: path.reverse() ou path[::-1])
        return path[::-1]