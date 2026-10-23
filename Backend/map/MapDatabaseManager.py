import json
import threading
from contextlib import contextmanager
from functools import wraps

import numpy as np
from mysql.connector import IntegrityError

from datasets.ManagerDatabase import (
    ConexaoBD,
    DatabaseUnavailable,
    request_connection,
    request_session,
)
from map.checkpoint_slug import DEFAULT_BUILDING_ID, allocate_slug
from map.edge_rules import group_edge_pairs
from pdr.trajectory import (
    displacement_m,
    isoformat_utc,
    path_points,
    straight_path,
    trace_payload,
)

def _sql_method(method):
    """Abre a sessão em volta do método. A detecção de passos fica de fora."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._session():
            return method(self, *args, **kwargs)

    return wrapper


class UnknownCategoryError(Exception):
    """``category_code`` não existe em ``checkpoint_categories``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CheckpointLookupError(Exception):
    """A consulta de checkpoint ou categoria falhou."""


class CheckpointConflictError(Exception):
    """UNIQUE(building_id, slug) ainda colidiu depois de gerar o slug de novo."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug


_CHECKPOINT_COLUMNS = """
    SELECT c.id, c.name, c.slug, c.building_id, c.pos_x_px, c.pos_y_px,
           cat.code AS category_code, cat.label AS category_label
    FROM checkpoints c
    LEFT JOIN checkpoint_categories cat ON cat.id = c.category_id
"""


class MapDatabaseManager:
    """Responsável por salvar e carregar o grafo diretamente do MySQL do XAMPP."""

    # Um lock por par físico, compartilhado por todas as instâncias.
    # O lock global segurava todo salvamento atrás de um corredor só.
    # Lock por sentido deixa Sala→Quarto e Quarto→Sala correrem juntos e
    # deadlocarem no unique da aresta. Este lock não é o do InnoDB: a ordem
    # que evita o 1213 está no FOR UPDATE (checkpoints por nome, depois a
    # aresta). Pegar este lock depois de ter lock no banco inverte a ordem.
    _pair_locks: dict[tuple[str, str], threading.Lock] = {}
    _pair_locks_guard = threading.Lock()

    def __init__(self, database: ConexaoBD, per_request: bool = False):
        self._database = database
        self._per_request = per_request

    @property
    def db(self):
        """Sessão desta chamada. Na API, sem sessão aberta, não usa a de boot."""
        if self._per_request:
            current = request_connection.get()
            if current is None:
                raise DatabaseUnavailable("Não foi possível conectar ao MySQL.")
            return current
        return self._database

    @contextmanager
    def _session(self):
        """Checkout só enquanto o método fala com o MySQL."""
        if not self._per_request:
            yield
            return
        with request_session(self._database):
            yield

    def _lock_for(self, source: str, target: str) -> threading.Lock:
        key = tuple(sorted((source, target)))
        with self._pair_locks_guard:
            lock = self._pair_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._pair_locks[key] = lock
            return lock

    def _lock_for_pair(self, source: str, target: str) -> threading.Lock:
        return self._lock_for(source, target)

    def _clear_lock_error(self) -> None:
        if hasattr(self.db, "last_errno"):
            self.db.last_errno = None

    def _lock_conflict(self) -> bool:
        # 1213 deadlock, 1205 lock wait. O timeout da sessão é 5 s.
        return getattr(self.db, "last_errno", None) in (1205, 1213)

    def _lock_checkpoints(self, source: str, target: str) -> None:
        """X lock nos dois checkpoints, sempre na ordem do nome no banco."""
        first, second = sorted((source, target))
        rows = self.db.execute_search(
            "SELECT name FROM checkpoints WHERE name IN (%s, %s) ORDER BY name FOR UPDATE",
            (first, second),
        )
        if rows is None:
            raise RuntimeError("falha ao travar checkpoints")

    @_sql_method
    def save_checkpoint(self, name: str, category_code: str | None = None):
        """Salva um novo nó. O slug nasce aqui e não é recalculado depois.

        Dois POST ao mesmo tempo podem escolher o mesmo slug. A primeira
        colisão em UNIQUE(building_id, slug) gera o slug de novo, já vendo
        a linha que ganhou a corrida. A segunda vira conflito.
        """
        category_id = None
        if category_code is not None:
            category_id = int(self._require_category(category_code)["id"])
        sql = """INSERT INTO checkpoints (name, building_id, slug, category_id) VALUES (%s, %s, %s, %s)"""
        slug = ""
        for attempt in range(2):
            taken = self._slugs_for_building(DEFAULT_BUILDING_ID)
            slug = allocate_slug(name, taken)
            try:
                success = self.db.execute_query(
                    sql, (name, DEFAULT_BUILDING_ID, slug, category_id)
                )
            except IntegrityError:
                print(
                    f"[M03] Conflito ao gravar slug '{slug}' "
                    f"(tentativa {attempt + 1} de 2)."
                )
                if attempt == 0:
                    continue
                raise CheckpointConflictError(slug)
            if not success:
                print(f"Erro ao adicionar checkpoint {name}")
                return False
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
        raise CheckpointConflictError(slug)

    @_sql_method
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

    @_sql_method
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

    @_sql_method
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

    @_sql_method
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

    @_sql_method
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
        """Upsert manual dos dois sentidos numa transação só.

        A ordem é sempre o par (source, target) ordenado. Os dois sentidos
        em transações separadas, cada uma começando pelo seu source, dá
        deadlock 1213 no unique (source_node, target_node). Dois commits
        separados deixavam um sentido gravado se o segundo falhasse.
        """
        inverse_heading = (heading_rad + np.pi) % (2 * np.pi)
        directions = sorted(
            (
                (source, target, float(distance), float(heading_rad)),
                (target, source, float(distance), float(inverse_heading)),
            ),
            key=lambda item: (item[0], item[1]),
        )
        for attempt in range(2):
            with self._lock_for(source, target):
                with self._session():
                    self._clear_lock_error()
                    if not self.db.begin_transaction():
                        if self._lock_conflict() and attempt == 0:
                            continue
                        return False
                    try:
                        self._lock_checkpoints(source, target)
                        for src, tgt, dist, heading in directions:
                            self._lock_edge(src, tgt)
                            if not self._upsert_manual_direction(src, tgt, dist, heading):
                                raise RuntimeError("falha ao gravar um sentido da aresta")
                        if not self.db.commit_transaction():
                            raise RuntimeError("commit da aresta falhou")
                        return True
                    except Exception as exc:
                        print(f"Aresta revertida: {exc}")
                        self.db.rollback_transaction()
                        if self._lock_conflict() and attempt == 0:
                            continue
                        return False
        return False

    def _lock_edge(self, source: str, target: str) -> dict | None:
        rows = self.db.execute_search(
            """
            SELECT id, distance_m, heading_rad, origin
            FROM edges
            WHERE source_node = %s AND target_node = %s
            FOR UPDATE
            """,
            (source, target),
        )
        if rows is None:
            raise RuntimeError("falha ao travar aresta")
        if not rows:
            return None
        return rows[0]

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
        return bool(self.db.execute_within(sql, (source, target, distance, heading_rad)))
                
    @_sql_method
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
                
    @_sql_method
    def save_sensor_log(self, source: str, target: str, csv_data: str):
        query = """
            INSERT INTO sensors_log (source, target, steps_detected, distance_m, is_valid, message, raw_csv)
            VALUES (%s, %s, 0, 0, 0, %s, %s)
        """
        log_id = self.db.execute_insert(query, (source, target, "gravado", csv_data))
        if log_id:
            return int(log_id)
        print("Erro ao processar log")
        return None

    @_sql_method
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
        
    @_sql_method
    def get_sensor_log_csv(self, log_id: int) -> str | None:
        """Busca o conteúdo CSV de um log específico pelo ID."""
        query = "SELECT raw_csv FROM sensors_log WHERE id = %s"
        result = self.db.execute_search(query, (log_id,))
        
        # Ajuste a extração conforme o retorno do seu DB (tuple ou dict)
        if result and len(result) > 0:
            return result[0]['raw_csv'] if isinstance(result[0], dict) else result[0][0]
        return None

    @_sql_method
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
            return True
        print(f"Erro ao salvar rota '{name}'")
        return False

    @_sql_method
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

    @_sql_method
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

    @_sql_method
    def delete_route(self, route_id: int):
        """Remove uma rota salva."""
        sql = "DELETE FROM saved_routes WHERE id = %s"
        return bool(self.db.execute_query(sql, (route_id,)))

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

        O lock de processo é do par, não do servidor inteiro. Dentro da
        transação a mediana sai em SQL (não traz o histórico para o Python)
        e os checkpoints são travados por nome antes da aresta.
        """
        for attempt in range(2):
            with self._lock_for(source, target):
                with self._session():
                    self._clear_lock_error()
                    if not self.db.begin_transaction():
                        print("Erro ao abrir transação de walk_trace")
                        if self._lock_conflict() and attempt == 0:
                            continue
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
                        if self._lock_conflict() and attempt == 0:
                            continue
                        return None
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
        # Checkpoints antes da aresta, nos dois fluxos (gravação e aresta manual).
        self._lock_checkpoints(source, target)
        existing = self._lock_edge(source, target)
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
            base.update(_edge_public(existing))
            return base

        samples_count, heading_rad, active_trace_id = self._aggregate_direction(source, target)
        if existing is not None and (existing.get("origin") or "manual") == "manual":
            distance_m = float(existing["distance_m"])
            heading_rad = float(existing["heading_rad"])
            origin = "manual"
        else:
            distance_m = self._median_distance(source, target, samples_count)
            origin = "recorded"
        resolved = {
            "distance_m": distance_m,
            "heading_rad": heading_rad,
            "origin": origin,
            "active_trace_id": active_trace_id,
        }
        edge_id = self._upsert_recorded_direction(source, target, resolved, samples_count)
        if not edge_id:
            raise RuntimeError("falha ao atualizar a aresta gravada")
        linked = self.db.execute_within(
            "UPDATE walk_traces SET edge_id = %s WHERE id = %s",
            (edge_id, trace_id),
        )
        if not linked:
            raise RuntimeError("falha ao ligar walk_trace à aresta")

        base.update({
            "edge_id": int(edge_id),
            "edge_distance_m": float(distance_m),
            "edge_heading_rad": float(heading_rad),
            "edge_origin": origin,
        })
        base["samples_count"] = samples_count
        return base

    def _aggregate_direction(self, source: str, target: str) -> tuple[int, float, int]:
        """Contagem, média circular e id mais recente. Não traz o histórico."""
        stats = self.db.execute_search(
            """
            SELECT COUNT(*) AS samples_count,
                   ATAN2(
                       SUM(SIN(COALESCE(net_heading_rad, 0))),
                       SUM(COS(COALESCE(net_heading_rad, 0)))
                   ) AS heading_rad
            FROM walk_traces
            WHERE source_node = %s AND target_node = %s AND is_valid = 1
            """,
            (source, target),
        )
        if not stats or stats[0].get("samples_count") in (None, 0):
            raise RuntimeError("falha ao agregar trajetórias da aresta")
        samples_count = int(stats[0]["samples_count"])
        heading = stats[0].get("heading_rad")
        if samples_count <= 0 or heading is None:
            raise RuntimeError("não há trajetória válida para agregar a aresta")
        latest = self.db.execute_search(
            """
            SELECT id
            FROM walk_traces
            WHERE source_node = %s AND target_node = %s AND is_valid = 1
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (source, target),
        )
        if not latest:
            raise RuntimeError("falha ao escolher a trajetória ativa")
        return samples_count, float(heading), int(latest[0]["id"])

    def _median_distance(self, source: str, target: str, samples_count: int) -> float:
        """Mediana com LIMIT/OFFSET. Par ímpar: o do meio. Par: a média dos dois."""
        if samples_count % 2:
            offset = samples_count // 2
            limit = 1
        else:
            offset = samples_count // 2 - 1
            limit = 2
        rows = self.db.execute_search(
            f"""
            SELECT total_distance_m
            FROM walk_traces
            WHERE source_node = %s AND target_node = %s AND is_valid = 1
            ORDER BY total_distance_m
            LIMIT {int(limit)} OFFSET {int(offset)}
            """,
            (source, target),
        )
        if not rows:
            raise RuntimeError("falha ao calcular a mediana da distância")
        return sum(float(row["total_distance_m"]) for row in rows) / len(rows)

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

    @_sql_method
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

    @_sql_method
    def list_connections(self, include_path: bool = True) -> list[dict] | None:
        """Um item por par físico. O sentido com trajetória ativa é o listado.

        Três consultas no máximo (arestas, traces ativos, passos). Uma por
        aresta segurava o GET que o editor espera depois de salvar.
        """
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
        pairs = group_edge_pairs(rows)
        active_ids = [
            int(primary["active_trace_id"])
            for primary, _reverse in pairs
            if primary.get("active_trace_id") is not None
        ]
        traces_by_id = self._traces_by_id(active_ids) if active_ids else {}
        if traces_by_id is None:
            return None
        steps_by_trace = None
        if include_path and traces_by_id:
            steps_by_trace = self._steps_by_trace_id(list(traces_by_id))
            if steps_by_trace is None:
                return None
        connections = []
        for primary, reverse in pairs:
            reverse_id = None if reverse is None else int(reverse["id"])
            connections.append(self._connection_view(
                primary,
                reverse_id,
                include_path,
                traces_by_id=traces_by_id,
                steps_by_trace=steps_by_trace,
            ))
        return connections

    @_sql_method
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

    def _connection_view(
        self,
        row: dict,
        reverse_id: int | None,
        include_path: bool,
        traces_by_id: dict | None = None,
        steps_by_trace: dict | None = None,
    ) -> dict:
        active_id = None if row.get("active_trace_id") is None else int(row["active_trace_id"])
        if active_id is None:
            trace = None
        elif traces_by_id is not None:
            trace = traces_by_id.get(active_id)
        else:
            trace = self._trace_row(active_id)
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
            prefetched = None
            if steps_by_trace is not None and trace is not None:
                prefetched = steps_by_trace.get(int(trace["id"]), [])
            item["path"] = self._path_for(
                row,
                trace,
                None if steps_by_trace is None else prefetched,
            )
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

    def _path_for(self, row: dict, trace: dict | None, steps: list | None = None) -> list[dict]:
        if trace is None:
            return straight_path(float(row["distance_m"]), float(row["heading_rad"]))
        if steps is None:
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
        grouped = self._steps_by_trace_id([int(row["id"]) for row in rows]) or {}
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
                    grouped.get(int(row["id"]), []),
                ),
            })
        return traces

    def _traces_by_id(self, trace_ids: list[int]) -> dict[int, dict] | None:
        placeholders = ", ".join(["%s"] * len(trace_ids))
        rows = self.db.execute_search(
            f"""
            SELECT id, started_at, total_steps, total_distance_m, is_valid, polyline_json
            FROM walk_traces
            WHERE id IN ({placeholders})
            """,
            tuple(int(trace_id) for trace_id in trace_ids),
        )
        if rows is None:
            return None
        return {int(row["id"]): row for row in rows}

    def _steps_by_trace_id(self, trace_ids: list[int]) -> dict[int, list] | None:
        if not trace_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(trace_ids))
        rows = self.db.execute_search(
            f"""
            SELECT trace_id, step_index, t_ms, heading_rad, step_length_m, x_m, y_m
            FROM walk_steps
            WHERE trace_id IN ({placeholders})
            ORDER BY trace_id, step_index
            """,
            tuple(int(trace_id) for trace_id in trace_ids),
        )
        if rows is None:
            return None
        grouped: dict[int, list] = {}
        for row in rows:
            grouped.setdefault(int(row["trace_id"]), []).append(row)
        return grouped

    @_sql_method
    def get_checkpoint_positions(self) -> dict:
        """Posições e slug. Consulta que falha não vira mapa sem posições.

        ``execute_search`` devolve None quando o SQL quebra (migração 003
        ainda não aplicada). Lista vazia continua sendo “não há checkpoints”.
        """
        rows = self.db.execute_search(_CHECKPOINT_COLUMNS)
        if rows is None:
            print(
                "[M03] Falha ao ler checkpoints para /api/map. "
                "Execute a migração 003."
            )
            raise CheckpointLookupError(
                "Falha ao ler checkpoints. Execute a migração 003."
            )
        if not rows:
            return {}
        return {row["name"]: _public_checkpoint(row) for row in rows}

    @_sql_method
    def update_checkpoint_position(self, name: str, pos_x_px, pos_y_px) -> bool:
        """Um UPDATE pelo UNIQUE(name). Sem SELECT antes, que abria transação."""
        affected = self.db.execute_update(
            "UPDATE checkpoints SET pos_x_px = %s, pos_y_px = %s WHERE name = %s",
            (pos_x_px, pos_y_px, name),
        )
        return bool(affected)

    @_sql_method
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

    @_sql_method
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