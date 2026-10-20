import json

import numpy as np

from datasets.ManagerDatabase import ConexaoBD
from map.edge_rules import resolve_recorded_edge
from pdr.trajectory import trace_payload

class MapDatabaseManager:
    """Responsável por salvar e carregar o grafo diretamente do MySQL do XAMPP."""

    def __init__(self, database: ConexaoBD):
        self.db = database
    
    def save_checkpoint(self, name: str):
        """Salva um novo nó semântico no banco de dados."""
        sql = """INSERT INTO checkpoints (name) VALUES (%s)"""
        # IMPORTANTE: Notar a vírgula (name,) para o Python entender que é uma tupla de 1 elemento
        succsses = self.db.execute_query(sql, (name,))
        
        if succsses:
            print(f"Checkpoint {name} adicionado com sucesso")
            return True
        else:
            print(f"Erro ao adicionar checkpoint {name}")
            return False
        
    def save_edge(self, source: str, target: str, distance: float, heading_rad: float):
        """Upsert manual dos dois sentidos. Uma linha por sentido; manual vence."""
        inverse_heading = (heading_rad + np.pi) % (2 * np.pi)
        forward = self._upsert_manual_direction(source, target, distance, heading_rad)
        backward = self._upsert_manual_direction(target, source, distance, inverse_heading)

        if forward and backward:
            print(f"Edge {source} <-> {target} gravada (upsert manual)")
            return True
        print(f"Erro ao adicionar edge com {target, source}")
        return False

    def _upsert_manual_direction(self, source: str, target: str, distance: float, heading_rad: float) -> bool:
        sql = """
            INSERT INTO edges (source_node, target_node, distance_m, heading_rad, origin)
            VALUES (%s, %s, %s, %s, 'manual')
            ON DUPLICATE KEY UPDATE
                distance_m = VALUES(distance_m),
                heading_rad = VALUES(heading_rad),
                origin = 'manual',
                updated_at = CURRENT_TIMESTAMP,
                id = LAST_INSERT_ID(id)
        """
        return bool(self.db.execute_query(sql, (source, target, distance, heading_rad)))
                
    def load_map_into_system(self, topo_map) -> None:
        """Carrega todos os dados persistidos no MySQL e reconstrói o grafo na memória."""
        
        # --- PASSO 1: CARREGAR OS CHECKPOINTS ---
        sql_nodes = "SELECT name FROM checkpoints"
        # O executar_consulta vai te retornar uma lista de dicionários se você usou dictionary=True
        # Ex: [{'name': 'Recepcao'}, {'name': 'Corredor Central'}]
        rows_nodes = self.db.execute_search(sql_nodes)
        
        if rows_nodes:
            for row in rows_nodes:
                # Extraia o nome do nó e adicione ao topo_map usando a função add_checkpoint
                node_name = row['name']
                topo_map.add_checkpoint(node_name)
                print(f"[BD -> Sistema] Checkpoint carregado: {node_name}")

        # --- PASSO 2: CARREGAR AS ARESTAS ---
        # Cada linha já é um sentido. Não criar a volta aqui: isso duplicaria a aresta.
        sql_edges = (
            "SELECT id, source_node, target_node, distance_m, heading_rad "
            "FROM edges ORDER BY id"
        )
        rows_edges = self.db.execute_search(sql_edges)

        if rows_edges:
            topo_map.load_directed_edges(rows_edges)
            for row in rows_edges:
                print(
                    f"[BD -> Sistema] Conexão carregada: {row['source_node']} -> "
                    f"{row['target_node']} ({row['distance_m']}m)"
                )
                
    def save_sensor_log(self, source: str, target: str, csv_data: str):
        query = """
            INSERT INTO sensors_log (source, target, steps_detected, distance_m, is_valid, message, raw_csv)
            VALUES (%s, %s, 0, 0, 0, %s, %s)
        """
        log_id = self.db.execute_insert(query, (source, target, "gravado", csv_data))
        if log_id:
            print("Log salvo com sucesso")
            return int(log_id)
        print("Erro ao processar log")
        return None

    def update_sensor_log(self, log_id: int, steps: int, distance: float, is_valid: bool, message: str) -> bool:
        query = """
            UPDATE sensors_log
            SET steps_detected = %s, distance_m = %s, is_valid = %s, message = %s
            WHERE id = %s
        """
        return bool(self.db.execute_query(query, (
            int(steps),
            float(distance),
            1 if is_valid else 0,
            (message or "")[:255],
            int(log_id),
        )))
        
    def get_sensor_log_csv(self, log_id: int) -> str | None:
        """Busca o conteúdo CSV de um log específico pelo ID."""
        query = "SELECT raw_csv FROM sensors_log WHERE id = %s"
        result = self.db.execute_search(query, (log_id,))
        
        # Ajuste a extração conforme o retorno do seu DB (tuple ou dict)
        if result and len(result) > 0:
            return result[0]['raw_csv'] if isinstance(result[0], dict) else result[0][0]
        return None

    def save_route(self, name: str, start_node: str, end_node: str, segments: list, path_sequence: list):
        """Salva uma rota calculada com todos os segmentos no banco de dados."""
        import json

        total_distance = sum(s["distance_m"] for s in segments)
        # Estimativa: passo médio de 0.75m
        total_steps_estimated = int(round(total_distance / 0.75))

        sql = """
            INSERT INTO saved_routes (name, start_node, end_node, total_distance_m, total_steps_estimated, segments_json, path_sequence_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        success = self.db.execute_query(sql, (
            name, start_node, end_node, total_distance, total_steps_estimated,
            json.dumps(segments), json.dumps(path_sequence)
        ))

        if success:
            print(f"Rota '{name}' salva com sucesso ({len(segments)} segmentos, {total_distance:.1f}m)")
            return True
        else:
            print(f"Erro ao salvar rota '{name}'")
            return False

    def get_all_routes(self):
        """Lista todas as rotas salvas (resumo para UI)."""
        sql = """
            SELECT id, name, start_node, end_node, total_distance_m, total_steps_estimated, created_at
            FROM saved_routes
            ORDER BY created_at DESC
        """
        rows = self.db.execute_search(sql)
        if rows:
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "start_node": row["start_node"],
                    "end_node": row["end_node"],
                    "total_distance_m": row["total_distance_m"],
                    "total_steps_estimated": row["total_steps_estimated"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]
        return []

    def get_route_by_id(self, route_id: int):
        """Carrega uma rota completa com todos os segmentos para modo teste."""
        sql = """
            SELECT id, name, start_node, end_node, total_distance_m, total_steps_estimated,
                   segments_json, path_sequence_json, created_at
            FROM saved_routes
            WHERE id = %s
        """
        rows = self.db.execute_search(sql, (route_id,))
        if rows and len(rows) > 0:
            row = rows[0]
            import json
            return {
                "id": row["id"],
                "name": row["name"],
                "start_node": row["start_node"],
                "end_node": row["end_node"],
                "total_distance_m": row["total_distance_m"],
                "total_steps_estimated": row["total_steps_estimated"],
                "segments": json.loads(row["segments_json"]),
                "path_sequence": json.loads(row["path_sequence_json"]),
                "created_at": row["created_at"]
            }
        return None

    def delete_route(self, route_id: int):
        """Remove uma rota salva."""
        sql = "DELETE FROM saved_routes WHERE id = %s"
        success = self.db.execute_query(sql, (route_id,))
        if success:
            print(f"Rota {route_id} removida com sucesso")
        return success

    def record_walk(
        self,
        source: str,
        target: str,
        sensors_log_id: int,
        started_at: str,
        ended_at: str,
        built: dict,
    ) -> dict | None:
        """Grava a trajetória do sentido andado e atualiza a aresta (upsert)."""
        trace_sql = """
            INSERT INTO walk_traces (
                sensors_log_id, edge_id, saved_route_id, source_node, target_node,
                started_at, ended_at, total_steps, total_distance_m, net_heading_rad,
                polyline_json, is_valid
            ) VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        """
        trace_id = self.db.execute_insert(trace_sql, (
            int(sensors_log_id),
            source,
            target,
            started_at,
            ended_at,
            len(built["steps"]),
            float(built["total_distance_m"]),
            float(built["net_heading_rad"]),
            json.dumps(built["polyline"]),
        ))
        if type(trace_id) is not int or trace_id <= 0:
            print("Erro ao gravar walk_trace")
            return None

        if built["steps"]:
            step_sql = """
                INSERT INTO walk_steps (
                    trace_id, step_index, t_ms, heading_rad, step_length_m, x_m, y_m
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = [
                (
                    trace_id,
                    int(step["step_index"]),
                    int(step["t_ms"]),
                    float(step["heading_rad"]),
                    float(step["step_length_m"]),
                    float(step["x_m"]),
                    float(step["y_m"]),
                )
                for step in built["steps"]
            ]
            if not self.db.execute_many(step_sql, params):
                print("Erro ao gravar walk_steps")
                return None

        traces = self.db.execute_search(
            """
            SELECT id, total_distance_m, net_heading_rad, started_at, is_valid
            FROM walk_traces
            WHERE source_node = %s AND target_node = %s AND is_valid = 1
            """,
            (source, target),
        )
        existing_rows = self.db.execute_search(
            """
            SELECT id, distance_m, heading_rad, origin
            FROM edges
            WHERE source_node = %s AND target_node = %s
            """,
            (source, target),
        )
        if traces is None or existing_rows is None:
            return None

        resolved = resolve_recorded_edge(
            _edge_view(existing_rows[0]) if existing_rows else None,
            [_trace_view(row) for row in traces],
        )
        edge_id = self._upsert_recorded_direction(source, target, resolved)
        if not edge_id:
            return None
        linked = self.db.execute_query(
            "UPDATE walk_traces SET edge_id = %s WHERE id = %s",
            (edge_id, trace_id),
        )
        if not linked:
            return None

        stored = self.db.execute_search(
            """
            SELECT id, distance_m, heading_rad
            FROM edges
            WHERE source_node = %s AND target_node = %s
            """,
            (source, target),
        )
        if not stored:
            return None
        return {
            "path": self.get_trace_payload(trace_id),
            "edge_id": int(stored[0]["id"]),
            "edge_distance_m": float(stored[0]["distance_m"]),
            "edge_heading_rad": float(stored[0]["heading_rad"]),
        }

    def _upsert_recorded_direction(self, source: str, target: str, resolved: dict) -> int | None:
        sql = """
            INSERT INTO edges (
                source_node, target_node, distance_m, heading_rad, origin, active_trace_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                distance_m = IF(origin = 'manual', distance_m, VALUES(distance_m)),
                heading_rad = IF(origin = 'manual', heading_rad, VALUES(heading_rad)),
                origin = IF(origin = 'manual', origin, VALUES(origin)),
                active_trace_id = VALUES(active_trace_id),
                updated_at = CURRENT_TIMESTAMP,
                id = LAST_INSERT_ID(id)
        """
        edge_id = self.db.execute_insert(sql, (
            source,
            target,
            float(resolved["distance_m"]),
            float(resolved["heading_rad"]),
            resolved["origin"],
            int(resolved["active_trace_id"]),
        ))
        if type(edge_id) is not int or edge_id <= 0:
            found = self.db.execute_search(
                "SELECT id FROM edges WHERE source_node = %s AND target_node = %s",
                (source, target),
            )
            if not found:
                return None
            return int(found[0]["id"])
        return int(edge_id)

    def get_trace_payload(self, trace_id: int) -> dict | None:
        rows = self.db.execute_search(
            """
            SELECT id, edge_id, source_node, target_node, started_at, created_at,
                   total_steps, total_distance_m, is_valid
            FROM walk_traces
            WHERE id = %s
            """,
            (int(trace_id),),
        )
        if not rows:
            return None
        steps = self.db.execute_search(
            """
            SELECT step_index, t_ms, heading_rad, step_length_m, x_m, y_m
            FROM walk_steps
            WHERE trace_id = %s
            ORDER BY step_index
            """,
            (int(trace_id),),
        )
        if steps is None:
            return None
        return trace_payload(rows[0], steps)

    def list_connections(self, include_path: bool = False) -> list[dict] | None:
        rows = self.db.execute_search(
            """
            SELECT id, source_node, target_node, distance_m, heading_rad,
                   origin, active_trace_id, updated_at
            FROM edges
            ORDER BY source_node, target_node, id
            """
        )
        if rows is None:
            return None
        connections = []
        for row in rows:
            item = {
                "id": int(row["id"]),
                "source": row["source_node"],
                "target": row["target_node"],
                "distance_m": float(row["distance_m"]),
                "heading_rad": float(row["heading_rad"]),
                "origin": row.get("origin") or "manual",
                "active_trace_id": None if row.get("active_trace_id") is None else int(row["active_trace_id"]),
                "updated_at": _iso_or_none(row.get("updated_at")),
            }
            if include_path:
                active = item["active_trace_id"]
                item["path"] = self.get_trace_payload(active) if active else None
            connections.append(item)
        return connections

    def get_checkpoint_positions(self) -> dict:
        rows = self.db.execute_search("SELECT name, pos_x_px, pos_y_px FROM checkpoints")
        if not rows:
            return {}
        positions = {}
        for row in rows:
            positions[row["name"]] = (
                None if row.get("pos_x_px") is None else float(row["pos_x_px"]),
                None if row.get("pos_y_px") is None else float(row["pos_y_px"]),
            )
        return positions

    def update_checkpoint_position(self, name: str, pos_x_px, pos_y_px) -> bool:
        found = self.db.execute_search("SELECT name FROM checkpoints WHERE name = %s", (name,))
        if not found:
            return False
        return bool(self.db.execute_query(
            "UPDATE checkpoints SET pos_x_px = %s, pos_y_px = %s WHERE name = %s",
            (pos_x_px, pos_y_px, name),
        ))

    def get_map_config(self) -> dict | None:
        rows = self.db.execute_search(
            "SELECT id, plan_image, px_per_m, rotation_rad, updated_at FROM map_config WHERE id = 1"
        )
        if rows is None:
            return None
        if not rows:
            return {
                "id": 1,
                "plan_image": None,
                "px_per_m": None,
                "rotation_rad": 0.0,
                "updated_at": None,
            }
        row = rows[0]
        return {
            "id": int(row["id"]),
            "plan_image": row.get("plan_image"),
            "px_per_m": None if row.get("px_per_m") is None else float(row["px_per_m"]),
            "rotation_rad": float(row.get("rotation_rad") or 0.0),
            "updated_at": _iso_or_none(row.get("updated_at")),
        }

    def save_map_config(self, plan_image, px_per_m, rotation_rad: float) -> dict | None:
        sql = """
            INSERT INTO map_config (id, plan_image, px_per_m, rotation_rad)
            VALUES (1, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                plan_image = VALUES(plan_image),
                px_per_m = VALUES(px_per_m),
                rotation_rad = VALUES(rotation_rad),
                updated_at = CURRENT_TIMESTAMP
        """
        if not self.db.execute_query(sql, (plan_image, px_per_m, float(rotation_rad))):
            return None
        return self.get_map_config()


def _edge_view(row: dict) -> dict:
    return {
        "distance_m": float(row["distance_m"]),
        "heading_rad": float(row["heading_rad"]),
        "origin": row.get("origin") or "manual",
    }


def _trace_view(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "total_distance_m": float(row["total_distance_m"]),
        "net_heading_rad": float(row["net_heading_rad"] or 0.0),
        "started_at": row["started_at"],
        "is_valid": bool(row["is_valid"]),
    }


def _iso_or_none(value):
    from pdr.trajectory import isoformat_utc
    return isoformat_utc(value)