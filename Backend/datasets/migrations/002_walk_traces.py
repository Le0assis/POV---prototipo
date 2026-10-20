"""Migração idempotente 002: aresta única por sentido e trajetória da gravação.

Não há ferramenta de migração no projeto. ``create_tables`` chama ``apply``.
Rodar de novo não recria o snapshot nem apaga aresta que já é única.

Causa dos duplicados (confirmada no código, não em saved_routes):
``edges`` não tinha UNIQUE (source_node, target_node); ``save_edge`` só
insería e gravava os dois sentidos; ``load_map_into_system`` chamava
``connect_checkpoints``, que espelhava cada linha de novo.

``sensors_log_id ON DELETE CASCADE`` é intencional: a trajetória é derivada
do log bruto. ``source_node``/``target_node`` copiam o tipo exato de
``checkpoints.name`` (no DDL do projeto, VARCHAR(100)).
"""

from __future__ import annotations

import re

from map.edge_rules import split_duplicate_edges

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """


def _add_column(db, table: str, column: str, definition: str) -> None:
    if _column_exists(db, table, column):
        return
    db.execute_query(f"ALTER TABLE {table} ADD COLUMN {definition}")


def backup_edges_once(db) -> None:
    """Snapshot anterior ao dedupe. Se a tabela já existe, não mexe nela."""
    if _table_exists(db, "edges_backup_m02"):
        print("[M02] edges_backup_m02 já existe; snapshot original preservado.")
        return
    db.execute_query(SQL_BACKUP)
    print("[M02] Snapshot edges_backup_m02 criado antes do dedupe.")


def dedupe_edges(db) -> list[dict]:
    rows = _fetch(db, SQL_SELECT_EDGES)
    _kept, removed = split_duplicate_edges(rows)
    for row in removed:
        print(
            "[M02] removida edges "
            f"id={row['id']} {row['source_node']}->{row['target_node']} "
            f"distance_m={row['distance_m']} heading_rad={row['heading_rad']} "
            "(mantido o maior id do sentido)"
        )
    if removed:
        ids = tuple(int(row["id"]) for row in removed)
        placeholders = ", ".join(["%s"] * len(ids))
        db.execute_query(f"DELETE FROM edges WHERE id IN ({placeholders})", ids)
    return removed


def apply(db) -> list[dict]:
    """Aplica a migração. Devolve as linhas de ``edges`` apagadas nesta execução."""
    db.execute_query(SQL_INNODB)
    backup_edges_once(db)

    _add_column(db, "checkpoints", "pos_x_px", "pos_x_px DOUBLE NULL")
    _add_column(db, "checkpoints", "pos_y_px", "pos_y_px DOUBLE NULL")
    _add_column(
        db,
        "edges",
        "origin",
        "origin ENUM('manual','recorded') NOT NULL DEFAULT 'manual'",
    )
    _add_column(
        db,
        "edges",
        "updated_at",
        "updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    )

    removed = dedupe_edges(db)

    if not _fetch(db, SQL_UNIQUE_EXISTS):
        db.execute_query(
            "ALTER TABLE edges ADD UNIQUE KEY uq_edges_direction (source_node, target_node)"
        )

    meta_rows = _fetch(db, SQL_COLUMN_META)
    if not meta_rows:
        raise RuntimeError("checkpoints.name não encontrado; crie a tabela antes da migração.")
    node_sql = node_column_sql(meta_rows[0])
    if not _table_exists(db, "walk_traces"):
        db.execute_query(walk_traces_sql(node_sql))
    if not _table_exists(db, "walk_steps"):
        db.execute_query(walk_steps_sql())

    _add_column(db, "edges", "active_trace_id", "active_trace_id INT NULL")
    if not _fetch(db, SQL_FK_EXISTS):
        db.execute_query(
            "ALTER TABLE edges ADD CONSTRAINT fk_edges_active_trace "
            "FOREIGN KEY (active_trace_id) REFERENCES walk_traces(id) ON DELETE SET NULL"
        )

    if not _table_exists(db, "map_config"):
        db.execute_query(SQL_CREATE_MAP)
    if not _fetch(db, SQL_MAP_EXISTS_ROW):
        db.execute_query(SQL_MAP_INSERT)

    print(
        "[M02] Edges pré-existentes ficam origin=manual. "
        "O comprimento sobrevivente não é trocado pela mediana; "
        "active_trace_id ainda recebe a gravação válida mais recente."
    )
    return removed
