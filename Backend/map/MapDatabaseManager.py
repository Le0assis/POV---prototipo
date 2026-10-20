import json
import threading

import numpy as np

from datasets.ManagerDatabase import ConexaoBD, request_connection
from map.checkpoint_slug import DEFAULT_BUILDING_ID, allocate_slug
from map.edge_rules import group_edge_pairs, resolve_recorded_edge
from pdr.trajectory import (
    displacement_m,
    isoformat_utc,
    path_points,
    straight_path,
    trace_payload,
)

class UnknownCategoryError(Exception):
    """``category_code`` não existe em ``checkpoint_categories``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CheckpointLookupError(Exception):
    """A consulta de checkpoint ou categoria falhou."""


_CHECKPOINT_COLUMNS = """
    SELECT c.id, c.name, c.slug, c.building_id, c.pos_x_px, c.pos_y_px,
           cat.code AS category_code, cat.label AS category_label
    FROM checkpoints c
    LEFT JOIN checkpoint_categories cat ON cat.id = c.category_id
"""


class MapDatabaseManager:
    """Responsável por salvar e carregar o grafo diretamente do MySQL do XAMPP."""

    def __init__(self, database: ConexaoBD, per_request: bool = False):
        self._database = database
        self._per_request = per_request
        self._walk_lock = threading.Lock()

    @property
    def db(self):
        """Na API, a conexão aberta para esta requisição. Fora dela, a de boot."""
        if self._per_request:
            current = request_connection.get()
            if current is not None:
                return current
        return self._database
    
    def save_checkpoint(self, name: str, category_code: str | None = None):
        """Salva um novo nó. O slug nasce aqui e não é recalculado depois."""
        category_id = None
        if category_code is not None:
            category_id = int(self._require_category(category_code)["id"])
        taken = self._slugs_for_building(DEFAULT_BUILDING_ID)
        slug = allocate_slug(name, taken)
        sql = """INSERT INTO checkpoints (name, building_id, slug, category_id) VALUES (%s, %s, %s, %s)"""
        success = self.db.execute_query(sql, (name, DEFAULT_BUILDING_ID, slug, category_id))
        if success:
            print(f"Checkpoint {name} adicionado com sucesso")
            loaded = self.get_checkpoint_by_name(name)
            if loaded is not None:
                return loaded
            return _public_checkpoint({
                "name": name,
                "slug": slug,
                "building_id": DEFAULT_BUILDING_ID,
                "category_code": category_code,
                "category_label": None,
                "pos_x_px": None,
                "pos_y_px": None,
            })
        print(f"Erro ao adicionar checkpoint {name}")
        return False

    def update_checkpoint_name(self, name: str, new_name: str) -> bool:
        """Troca o nome e mantém o slug gerado na criação."""
        cleaned = new_name.strip()
        if not cleaned:
            return False
        current = self.db.execute_search(
            "SELECT slug FROM checkpoints WHERE name = %s",
            (name,),
        )
        if current is None:
            raise CheckpointLookupError("Falha ao buscar checkpoint.")
        if not current:
            return False
        previous_slug = current[0]["slug"]
        updated = self.db.execute_query(
            "UPDATE checkpoints SET name = %s WHERE name = %s",
            (cleaned, name),
        )
        if not updated:
            return False
        renamed = self.db.execute_search(
            "SELECT slug FROM checkpoints WHERE name = %s",
            (cleaned,),
        )
        if renamed is None:
            raise CheckpointLookupError("Falha ao buscar checkpoint.")
        if not renamed:
            return False
        return renamed[0]["slug"] == previous_slug

    def update_checkpoint_category(self, name: str, category_code: str | None) -> dict | None:
        """Grava a categoria, ou NULL quando ``category_code`` é None. Não mexe no slug."""
        category_id = None
        if category_code is not None:
            category_id = int(self._require_category(category_code)["id"])
        found = self.db.execute_search(
            "SELECT name FROM checkpoints WHERE name = %s",
            (name,),
        )
        if found is None:
            raise CheckpointLookupError("Falha ao buscar checkpoint.")
        if not found:
            return None
        updated = self.db.execute_query(
            "UPDATE checkpoints SET category_id = %s WHERE name = %s",
            (category_id, name),
        )
        if not updated:
            return None
        return self.get_checkpoint_by_name(name)

    def list_categories(self) -> list | None:
        rows = self.db.execute_search(
            "SELECT code, label, sort_order FROM checkpoint_categories "
            "ORDER BY sort_order ASC, code ASC"
        )
        if rows is None:
            return None
        return [
            {
                "code": row["code"],
                "label": row["label"],
                "sort_order": int(row["sort_order"]),
            }
            for row in rows
        ]

    def resolve_checkpoint(self, building_id: int, slug: str) -> dict | None:
        rows = self.db.execute_search(
            _CHECKPOINT_COLUMNS + " WHERE c.building_id = %s AND c.slug = %s",
            (building_id, slug),
        )
        if rows is None:
            raise CheckpointLookupError("Falha ao resolver checkpoint.")
        if not rows:
            return None
        return _public_checkpoint(rows[0])

    def get_checkpoint_by_name(self, name: str) -> dict | None:
        rows = self.db.execute_search(
            _CHECKPOINT_COLUMNS + " WHERE c.name = %s",
            (name,),
        )
        if rows is None:
            raise CheckpointLookupError("Falha ao buscar checkpoint.")
        if not rows:
            return None
        return _public_checkpoint(rows[0])

    def _require_category(self, code: str) -> dict:
        rows = self.db.execute_search(
            "SELECT id, code, label FROM checkpoint_categories WHERE code = %s",
            (code,),
        )
        if rows is None:
            raise CheckpointLookupError("Falha ao consultar checkpoint_categories.")
        if not rows:
            raise UnknownCategoryError(code)
        return rows[0]

    def _slugs_for_building(self, building_id: int) -> set[str]:
        rows = self.db.execute_search(
            "SELECT slug FROM checkpoints WHERE building_id = %s AND slug IS NOT NULL",
            (building_id,),
        )
        if rows is None:
            raise CheckpointLookupError("Falha ao listar slugs.")
        return {row["slug"] for row in rows if row.get("slug")}
        
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
        is_valid: bool = True,
    ) -> dict | None:
        """Grava trace, passos e (se válida) a aresta numa única transação.

        ``started_at``/``ended_at`` já vêm em UTC (DATETIME naive). Caminhada
        inválida persiste ``is_valid=0`` e não altera ``edges``.
        """
        # Serializa o agregado da aresta. Cada requisição tem a própria
        # conexão; o lock evita duas medianas lendo o mesmo par ao mesmo tempo.
        with self._walk_lock:
            if not self.db.begin_transaction():
                print("Erro ao abrir transação de walk_trace")
                return None
            try:
                payload = self._write_walk(
                    source, target, sensors_log_id, started_at, ended_at, built, bool(is_valid),
                )
                if not self.db.commit_transaction():
                    raise RuntimeError("commit da trajetória falhou")
                return payload
            except Exception as exc:
                print(f"Trajetória revertida: {exc}")
                self.db.rollback_transaction()
                return None

    def _write_walk(
        self,
        source: str,
        target: str,
        sensors_log_id: int,
        started_at: str,
        ended_at: str,
        built: dict,
        is_valid: bool,
    ) -> dict:
        trace_sql = """
            INSERT INTO walk_traces (
                sensors_log_id, edge_id, saved_route_id, source_node, target_node,
                started_at, ended_at, total_steps, total_distance_m, net_heading_rad,
                polyline_json, is_valid
            ) VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        trace_id = self.db.insert_within(trace_sql, (
            int(sensors_log_id),
            source,
            target,
            started_at,
            ended_at,
            len(built["steps"]),
            float(built["total_distance_m"]),
            float(built["net_heading_rad"]),
            json.dumps(built["polyline"]),
            1 if is_valid else 0,
        ))
        if type(trace_id) is not int or trace_id <= 0:
            raise RuntimeError("falha ao gravar walk_trace")

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
            if not self.db.executemany_within(step_sql, params):
                raise RuntimeError("falha ao gravar walk_steps")

        base = {
            "trace_id": int(trace_id),
            "path": path_points(started_at, built["steps"]),
            "net_heading_rad": float(built["net_heading_rad"]),
            "displacement_m": displacement_m(built["steps"]),
            "is_valid": is_valid,
        }
        if not is_valid:
            existing = self._edge_row(source, target)
            base.update(_edge_public(existing))
            return base

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
            raise RuntimeError("falha ao ler trajetórias da aresta")

        resolved = resolve_recorded_edge(
            _edge_view(existing_rows[0]) if existing_rows else None,
            [_trace_view(row) for row in traces],
        )
        samples_count = len(traces)
        edge_id = self._upsert_recorded_direction(source, target, resolved, samples_count)
        if not edge_id:
            raise RuntimeError("falha ao atualizar a aresta gravada")
        linked = self.db.execute_within(
            "UPDATE walk_traces SET edge_id = %s WHERE id = %s",
            (edge_id, trace_id),
        )
        if not linked:
            raise RuntimeError("falha ao ligar walk_trace à aresta")

        stored = self._edge_row(source, target)
        if not stored:
            raise RuntimeError("aresta gravada não encontrada")
        base.update(_edge_public(stored))
        base["samples_count"] = samples_count
        return base

    def _edge_row(self, source: str, target: str) -> dict | None:
        rows = self.db.execute_search(
            """
            SELECT id, distance_m, heading_rad, origin
            FROM edges
            WHERE source_node = %s AND target_node = %s
            """,
            (source, target),
        )
        if not rows:
            return None
        return rows[0]

    def _upsert_recorded_direction(
        self,
        source: str,
        target: str,
        resolved: dict,
        samples_count: int,
    ) -> int | None:
        sql = """
            INSERT INTO edges (
                source_node, target_node, distance_m, heading_rad, origin,
                active_trace_id, samples_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                distance_m = IF(origin = 'manual', distance_m, VALUES(distance_m)),
                heading_rad = IF(origin = 'manual', heading_rad, VALUES(heading_rad)),
                origin = IF(origin = 'manual', origin, VALUES(origin)),
                active_trace_id = VALUES(active_trace_id),
                samples_count = VALUES(samples_count),
                updated_at = CURRENT_TIMESTAMP,
                id = LAST_INSERT_ID(id)
        """
        edge_id = self.db.insert_within(sql, (
            source,
            target,
            float(resolved["distance_m"]),
            float(resolved["heading_rad"]),
            resolved["origin"],
            int(resolved["active_trace_id"]),
            int(samples_count),
        ))
        if type(edge_id) is not int or edge_id <= 0:
            found = self._edge_row(source, target)
            if not found:
                return None
            return int(found["id"])
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

    def list_connections(self, include_path: bool = True) -> list[dict] | None:
        """Um item por par físico. O sentido com trajetória ativa é o listado."""
        rows = self.db.execute_search(
            """
            SELECT id, source_node, target_node, distance_m, heading_rad,
                   origin, active_trace_id, samples_count
            FROM edges
            ORDER BY id
            """
        )
        if rows is None:
            return None
        connections = []
        for primary, reverse in group_edge_pairs(rows):
            reverse_id = None if reverse is None else int(reverse["id"])
            connections.append(self._connection_view(primary, reverse_id, include_path))
        return connections

    def get_connection(self, edge_id: int) -> dict | None:
        """O sentido pedido, mesmo que seja o reverso da lista agrupada."""
        rows = self.db.execute_search(
            """
            SELECT id, source_node, target_node, distance_m, heading_rad,
                   origin, active_trace_id, samples_count
            FROM edges
            WHERE id = %s
            """,
            (int(edge_id),),
        )
        if not rows:
            return None
        row = rows[0]
        reverse = self.db.execute_search(
            """
            SELECT id FROM edges
            WHERE source_node = %s AND target_node = %s
            ORDER BY id
            """,
            (row["target_node"], row["source_node"]),
        )
        reverse_id = int(reverse[0]["id"]) if reverse else None
        item = self._connection_view(row, reverse_id, include_path=True)
        item["traces"] = self._traces_for_direction(row["source_node"], row["target_node"])
        return item

    def _connection_view(self, row: dict, reverse_id: int | None, include_path: bool) -> dict:
        active_id = None if row.get("active_trace_id") is None else int(row["active_trace_id"])
        trace = self._trace_row(active_id) if active_id else None
        item = {
            "edge_id": int(row["id"]),
            "source": row["source_node"],
            "target": row["target_node"],
            "distance_m": float(row["distance_m"]),
            "heading_rad": float(row["heading_rad"]),
            "origin": row.get("origin") or "manual",
            "samples_count": int(row.get("samples_count") or 0),
            "reverse_edge_id": reverse_id,
            "active_trace_id": active_id,
            "recorded_at": None if trace is None else isoformat_utc(trace.get("started_at")),
            "steps_count": None if trace is None else int(trace["total_steps"]),
        }
        if include_path:
            item["path"] = self._path_for(row, trace)
        return item

    def _trace_row(self, trace_id: int) -> dict | None:
        rows = self.db.execute_search(
            """
            SELECT id, started_at, total_steps, total_distance_m, is_valid, polyline_json
            FROM walk_traces
            WHERE id = %s
            """,
            (int(trace_id),),
        )
        if not rows:
            return None
        return rows[0]

    def _steps_for_trace(self, trace_id: int) -> list[dict] | None:
        return self.db.execute_search(
            """
            SELECT step_index, t_ms, heading_rad, step_length_m, x_m, y_m
            FROM walk_steps
            WHERE trace_id = %s
            ORDER BY step_index
            """,
            (int(trace_id),),
        )

    def _path_for(self, row: dict, trace: dict | None) -> list[dict]:
        if trace is None:
            return straight_path(float(row["distance_m"]), float(row["heading_rad"]))
        steps = self._steps_for_trace(int(trace["id"]))
        if steps:
            return path_points(trace["started_at"], steps)
        polyline = trace.get("polyline_json")
        if isinstance(polyline, str) and polyline:
            polyline = json.loads(polyline)
        if polyline:
            return [
                {"x": float(point[0]), "y": float(point[1]), "t": None}
                for point in polyline
            ]
        return path_points(trace.get("started_at"), [])

    def _traces_for_direction(self, source: str, target: str) -> list[dict]:
        rows = self.db.execute_search(
            """
            SELECT id, started_at, total_steps, total_distance_m, is_valid, polyline_json
            FROM walk_traces
            WHERE source_node = %s AND target_node = %s
            ORDER BY started_at, id
            """,
            (source, target),
        )
        if not rows:
            return []
        traces = []
        for row in rows:
            traces.append({
                "trace_id": int(row["id"]),
                "recorded_at": isoformat_utc(row.get("started_at")),
                "total_steps": int(row["total_steps"]),
                "total_distance_m": float(row["total_distance_m"]),
                "is_valid": bool(row.get("is_valid")),
                "path": self._path_for(
                    {"distance_m": row["total_distance_m"], "heading_rad": 0.0},
                    row,
                ),
            })
        return traces

    def get_checkpoint_positions(self) -> dict:
        rows = self.db.execute_search(_CHECKPOINT_COLUMNS)
        if not rows:
            return {}
        return {row["name"]: _public_checkpoint(row) for row in rows}

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


def _public_checkpoint(row: dict) -> dict:
    code = row.get("category_code")
    category = None
    if code:
        category = {"code": code, "label": row.get("category_label")}
    pos_x = row.get("pos_x_px")
    pos_y = row.get("pos_y_px")
    payload = {
        "name": row["name"],
        "slug": row.get("slug"),
        "building_id": None if row.get("building_id") is None else int(row["building_id"]),
        "category": category,
        "pos_x_px": None if pos_x is None else float(pos_x),
        "pos_y_px": None if pos_y is None else float(pos_y),
    }
    if row.get("id") is not None:
        payload["id"] = int(row["id"])
    return payload


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
    return isoformat_utc(value)


def _edge_public(row: dict | None) -> dict:
    if not row:
        return {
            "edge_id": None,
            "edge_distance_m": None,
            "edge_heading_rad": None,
            "edge_origin": None,
        }
    return {
        "edge_id": int(row["id"]),
        "edge_distance_m": float(row["distance_m"]),
        "edge_heading_rad": float(row["heading_rad"]),
        "edge_origin": row.get("origin") or "manual",
    }