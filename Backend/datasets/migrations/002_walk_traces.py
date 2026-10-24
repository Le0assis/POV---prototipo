"""Migração idempotente 002: aresta única por sentido e trajetória da gravação.

Não há ferramenta de migração no projeto. ``create_tables`` chama ``apply``.
Rodar de novo não recria o snapshot nem mexe em aresta que já é única.

Causa dos duplicados (confirmada no código, não em saved_routes):
``edges`` não tinha UNIQUE (source_node, target_node); ``save_edge`` só
insería e gravava os dois sentidos; ``load_map_into_system`` chamava
``connect_checkpoints``, que espelhava cada linha de novo.

O unique usa a collation da coluna. ``Sala`` e ``sala`` são a mesma chave
em utf8mb4_unicode_ci e o Python não via. O ALTER caía em 1062 depois de
já ter apagado as cópias exatas. Agora nenhuma linha sai de ``edges``:
a de maior id do grupo (a comparação é a do banco) fica com ``dup_rank`` 0
e as outras recebem 1, 2, ... O unique inclui ``dup_rank`` quando há extra.

``sensors_log_id ON DELETE CASCADE`` é intencional: a trajetória é derivada
do log bruto. ``source_node``/``target_node`` copiam o tipo exato de
``checkpoints.name`` (no DDL do projeto, VARCHAR(100)).

``walk_traces.started_at`` e ``ended_at`` são DATETIME(3) naive em UTC:
a gravação escreve o relógio UTC e a leitura trata o valor sem fuso como UTC.

``edges.origin`` fica ``recorded`` só na criação da coluna, e quando já
existe qualquer ``sensors_log`` do par (o ``is_valid`` antigo vinha 0 porque
o campo não era preenchido). Sem log, fica ``manual``. Uma execução seguinte
não reclassifica. ``is_valid`` vale para gravações novas, não para esta
classificação.
"""

from __future__ import annotations

import re

_VARCHAR = re.compile(r"^varchar\(\d+\)$", re.IGNORECASE)
_IDENT = re.compile(r"^[A-Za-z0-9_]+$")

SQL_TABLE_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.tables "
    "WHERE table_schema = DATABASE() AND table_name = %s"
)
SQL_COLUMN_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.columns "
    "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s"
)
SQL_COLUMN_META = (
    "SELECT COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME "
    "FROM information_schema.columns "
    "WHERE table_schema = DATABASE() AND table_name = 'checkpoints' AND column_name = 'name'"
)
SQL_UNIQUE_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.statistics "
    "WHERE table_schema = DATABASE() AND table_name = 'edges' "
    "AND index_name = 'uq_edges_direction'"
)
SQL_FK_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.table_constraints "
    "WHERE table_schema = DATABASE() AND table_name = 'edges' "
    "AND constraint_name = 'fk_edges_active_trace'"
)
SQL_SELECT_EDGES = (
    "SELECT id, source_node, target_node, distance_m, heading_rad "
    "FROM edges ORDER BY id"
)
SQL_ENGINE = (
    "SELECT ENGINE AS engine FROM information_schema.tables "
    "WHERE table_schema = DATABASE() AND table_name = 'sensors_log'"
)
SQL_DUP_GROUPS = (
    "SELECT e.id AS id, e.source_node AS source_node, e.target_node AS target_node, "
    "k.keep_id AS keep_id "
    "FROM edges e "
    "JOIN ("
    "SELECT source_node, target_node, MAX(id) AS keep_id "
    "FROM edges GROUP BY source_node, target_node HAVING COUNT(*) > 1"
    ") k ON k.source_node = e.source_node AND k.target_node = e.target_node "
    "ORDER BY k.keep_id, e.id"
)
SQL_SET_RANK = "UPDATE edges SET dup_rank = %s WHERE id = %s AND dup_rank = 0"
SQL_UNIQUE_PAIR = (
    "ALTER TABLE edges ADD UNIQUE KEY uq_edges_direction (source_node, target_node)"
)
SQL_UNIQUE_RANKED = (
    "ALTER TABLE edges ADD UNIQUE KEY uq_edges_direction "
    "(source_node, target_node, dup_rank)"
)
SQL_BACKUP = "CREATE TABLE edges_backup_m02 AS SELECT * FROM edges"
SQL_INNODB = "ALTER TABLE sensors_log ENGINE=InnoDB"
SQL_MAP_EXISTS_ROW = "SELECT id FROM map_config WHERE id = 1"
SQL_MAP_INSERT = (
    "INSERT INTO map_config (id, plan_image, px_per_m, rotation_rad) "
    "VALUES (1, NULL, NULL, 0)"
)
SQL_CREATE_MAP = """
CREATE TABLE IF NOT EXISTS map_config (
    id INT NOT NULL PRIMARY KEY,
    plan_image VARCHAR(512) NULL,
    px_per_m DOUBLE NULL,
    rotation_rad DOUBLE NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
"""
# origin='recorded' se existir qualquer sensors_log do par, válido ou não.
# Logs antigos ficaram com is_valid=0 porque o campo não era preenchido.
# A regra de is_valid vale só para gravações novas (mediana, samples_count).
# Roda só quando a coluna origin acaba de ser criada.
SQL_CLASSIFY_RECORDED = (
    "UPDATE edges e SET origin = 'recorded' "
    "WHERE EXISTS ("
    "SELECT 1 FROM sensors_log s "
    "WHERE s.source = e.source_node AND s.target = e.target_node"
    ")"
)
SQL_BACKFILL_SAMPLES = (
    "UPDATE edges e SET samples_count = ("
    "SELECT COUNT(*) FROM walk_traces w "
    "WHERE w.source_node = e.source_node AND w.target_node = e.target_node "
    "AND w.is_valid = 1"
    ")"
)


def _fetch(db, sql: str, params=None):
    rows = db.execute_search(sql, params)
    if rows is None:
        raise RuntimeError(f"Falha ao consultar o banco: {sql}")
    return rows


def _table_exists(db, name: str) -> bool:
    return bool(_fetch(db, SQL_TABLE_EXISTS, (name,)))


def _column_exists(db, table: str, column: str) -> bool:
    return bool(_fetch(db, SQL_COLUMN_EXISTS, (table, column)))


def node_column_sql(column_meta: dict) -> str:
    """Fragmento DDL igual ao de checkpoints.name (tipo, charset, collation)."""
    column_type = str(column_meta["COLUMN_TYPE"]).strip()
    charset = str(column_meta["CHARACTER_SET_NAME"]).strip()
    collation = str(column_meta["COLLATION_NAME"]).strip()
    if not _VARCHAR.match(column_type):
        raise RuntimeError(f"checkpoints.name não é VARCHAR: {column_type}")
    if not _IDENT.match(charset) or not _IDENT.match(collation):
        raise RuntimeError(f"charset/collation inesperados: {charset} {collation}")
    return f"{column_type} CHARACTER SET {charset} COLLATE {collation}"


def walk_traces_sql(node_sql: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS walk_traces (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sensors_log_id INT NOT NULL,
        edge_id INT NULL,
        saved_route_id INT NULL,
        source_node {node_sql} NOT NULL,
        target_node {node_sql} NOT NULL,
        started_at DATETIME(3) NOT NULL,
        ended_at DATETIME(3) NOT NULL,
        total_steps INT NOT NULL,
        total_distance_m DOUBLE NOT NULL,
        net_heading_rad DOUBLE NULL,
        polyline_json JSON NULL,
        is_valid TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_walk_traces_sensors_log
            FOREIGN KEY (sensors_log_id) REFERENCES sensors_log(id) ON DELETE CASCADE,
        CONSTRAINT fk_walk_traces_edge
            FOREIGN KEY (edge_id) REFERENCES edges(id) ON DELETE SET NULL,
        CONSTRAINT fk_walk_traces_saved_route
            FOREIGN KEY (saved_route_id) REFERENCES saved_routes(id) ON DELETE SET NULL,
        CONSTRAINT fk_walk_traces_source
            FOREIGN KEY (source_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        CONSTRAINT fk_walk_traces_target
            FOREIGN KEY (target_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        INDEX idx_trace_pair (source_node, target_node),
        INDEX idx_trace_edge (edge_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
    """


def walk_steps_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS walk_steps (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        trace_id INT NOT NULL,
        step_index INT NOT NULL,
        t_ms INT NOT NULL,
        heading_rad DOUBLE NOT NULL,
        step_length_m DOUBLE NOT NULL,
        x_m DOUBLE NOT NULL,
        y_m DOUBLE NOT NULL,
        UNIQUE KEY uq_trace_step (trace_id, step_index),
        CONSTRAINT fk_walk_steps_trace
            FOREIGN KEY (trace_id) REFERENCES walk_traces(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci
    """


def _exec(db, sql: str, params=None) -> None:
    """DDL ou DML da migração. False aborta: não segue para o dedupe."""
    if db.execute_query(sql, params) is not True:
        raise RuntimeError(f"Migração abortada; o comando falhou: {sql}")


def _add_column(db, table: str, column: str, definition: str) -> bool:
    """True se a coluna foi criada agora."""
    if _column_exists(db, table, column):
        return False
    _exec(db, f"ALTER TABLE {table} ADD COLUMN {definition}")
    return True


def backup_edges_once(db) -> None:
    """Snapshot anterior ao dup_rank. Tabela já existente conta como confirmada."""
    if _table_exists(db, "edges_backup_m02"):
        print("[M02] edges_backup_m02 já existe; snapshot original preservado.")
        return
    _exec(db, SQL_BACKUP)
    if not _table_exists(db, "edges_backup_m02"):
        raise RuntimeError(
            "edges_backup_m02 não foi confirmada após o CREATE. Ajuste abortado."
        )
    print("[M02] Snapshot edges_backup_m02 criado. Nenhuma aresta é apagada.")


def preserve_duplicate_edges(db) -> list[dict]:
    """Numera cópias do mesmo sentido. Não apaga linha.

    O grupo é o do banco (collation), não o do Python. A de maior id fica
    com dup_rank 0, que é a linha do mapa e do upsert.
    """
    _add_column(db, "edges", "dup_rank", "dup_rank INT NOT NULL DEFAULT 0")
    if _fetch(db, SQL_UNIQUE_EXISTS):
        return []
    grouped = _fetch(db, SQL_DUP_GROUPS)
    by_keep: dict[int, list[dict]] = {}
    for row in grouped:
        by_keep.setdefault(int(row["keep_id"]), []).append(row)
    preserved: list[dict] = []
    for keep_id, group in by_keep.items():
        rank = 1
        for row in sorted(group, key=lambda item: int(item["id"])):
            if int(row["id"]) == keep_id:
                continue
            _exec(db, SQL_SET_RANK, (rank, int(row["id"])))
            print(
                "[M02] edges "
                f"id={row['id']} {row['source_node']}->{row['target_node']} "
                f"permanece com dup_rank={rank} (canônica id={keep_id})"
            )
            preserved.append(row)
            rank += 1
    if grouped:
        _exec(db, SQL_UNIQUE_RANKED)
    else:
        _exec(db, SQL_UNIQUE_PAIR)
    return preserved


def apply(db) -> list[dict]:
    """Aplica a migração. Devolve as arestas extras numeradas nesta execução.

    Nenhuma linha de ``edges`` é apagada. Qualquer DDL que não confirme aborta.
    O ajuste só roda com ``edges_backup_m02`` já existente.
    """
    engine_rows = _fetch(db, SQL_ENGINE)
    if not engine_rows:
        raise RuntimeError("sensors_log não existe. Crie a tabela antes da migração 002.")
    engine = next(iter(engine_rows[0].values()))
    if str(engine).lower() != "innodb":
        _exec(db, SQL_INNODB)
    backup_edges_once(db)

    _add_column(db, "checkpoints", "pos_x_px", "pos_x_px DOUBLE NULL")
    _add_column(db, "checkpoints", "pos_y_px", "pos_y_px DOUBLE NULL")
    origin_added = _add_column(
        db,
        "edges",
        "origin",
        "origin ENUM('manual','recorded') NOT NULL DEFAULT 'manual'",
    )
    if origin_added:
        _exec(db, SQL_CLASSIFY_RECORDED)
        print(
            "[M02] origin='recorded' onde já havia qualquer sensors_log "
            "do par source/target, mesmo com is_valid=0. Sem log, fica manual. "
            "Esta classificação não roda de novo."
        )
    _add_column(
        db,
        "edges",
        "updated_at",
        "updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    )
    _add_column(
        db,
        "edges",
        "samples_count",
        "samples_count INT NOT NULL DEFAULT 0",
    )

    preserved = preserve_duplicate_edges(db)

    meta_rows = _fetch(db, SQL_COLUMN_META)
    if not meta_rows:
        raise RuntimeError("checkpoints.name não encontrado; crie a tabela antes da migração.")
    node_sql = node_column_sql(meta_rows[0])
    if not _table_exists(db, "walk_traces"):
        _exec(db, walk_traces_sql(node_sql))
    if not _table_exists(db, "walk_steps"):
        _exec(db, walk_steps_sql())

    _add_column(db, "edges", "active_trace_id", "active_trace_id INT NULL")
    if not _fetch(db, SQL_FK_EXISTS):
        _exec(
            db,
            "ALTER TABLE edges ADD CONSTRAINT fk_edges_active_trace "
            "FOREIGN KEY (active_trace_id) REFERENCES walk_traces(id) ON DELETE SET NULL",
        )

    if _table_exists(db, "walk_traces"):
        _exec(db, SQL_BACKFILL_SAMPLES)

    if not _table_exists(db, "map_config"):
        _exec(db, SQL_CREATE_MAP)
    if not _fetch(db, SQL_MAP_EXISTS_ROW):
        _exec(db, SQL_MAP_INSERT)

    return preserved
