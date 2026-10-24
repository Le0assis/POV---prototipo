import heapq
from map.topological_map import TopologicalMap

class TopologicalRouter:
    """Menor caminho no grafo de checkpoints."""

    def __init__(self, topo_map: TopologicalMap) -> None:
        self.map = topo_map

    def calculate_route(self, start_node: str, end_node: str) -> list[str]:
        """Dijkstra. Lista vazia se algum nó não existe ou não há caminho."""
        start_node = self.map.canonical_name(start_node)
        end_node = self.map.canonical_name(end_node)
        if start_node is None or end_node is None:
            return []

        distances = {node: float("inf") for node in self.map.nodes}
        distances[start_node] = 0.0
        predecessors = {node: None for node in self.map.nodes}
        priority_queue = [(0.0, start_node)]

        while priority_queue:
            current_distance, current_node = heapq.heappop(priority_queue)
            if current_node == end_node:
                break
            if current_distance > distances[current_node]:
                continue
            for edge in self.map.get_outgoing_edges(current_node):
                neighbor = edge.target
                tentative_distance = current_distance + edge.distance_m
                if tentative_distance < distances[neighbor]:
                    distances[neighbor] = tentative_distance
                    predecessors[neighbor] = current_node
                    heapq.heappush(priority_queue, (tentative_distance, neighbor))

        if predecessors[end_node] is None and start_node != end_node:
            return []

        path = []
        step_node = end_node
        while step_node is not None:
            path.append(step_node)
            step_node = predecessors[step_node]
        return path[::-1]

    def calculate_route_with_segments(self, start_node: str, end_node: str) -> list[dict]:
        """Arestas do menor caminho: source, target, distance_m, heading_rad, heading_deg."""
        node_path = self.calculate_route(start_node, end_node)
        if not node_path or len(node_path) < 2:
            return []

        segments = []
        for i in range(len(node_path) - 1):
            source = node_path[i]
            target = node_path[i + 1]
            edge = next(
                (item for item in self.map.get_outgoing_edges(source) if item.target == target),
                None,
            )
            if edge:
                segments.append({
                    "source": source,
                    "target": target,
                    "distance_m": edge.distance_m,
                    "heading_rad": edge.heading_rad,
                    "heading_deg": edge.heading_rad * 180.0 / 3.141592653589793,
                })
        return segments
