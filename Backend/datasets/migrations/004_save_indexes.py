"""Migração idempotente 004: índices da gravação.

Não há ferramenta de migração no projeto. ``create_tables`` chama ``apply``
depois da 003. Rodar de novo não duplica índice.

O InnoDB já cria sozinho um índice na coluna de FK quando ela não é a
primeira de um índice existente (``edges.target_node``,
``walk_traces.sensors_log_id``, e as outras). Esse índice some se alguém
recriar a FK na mão. A migração só cria o que não tiver a coluna como
primeira chave.

O que o salvamento realmente usa, e o índice automático não cobre, é o
filtro ``(source_node, target_node, is_valid)``. Sem ele o plano da mediana
pode ir pelo índice só de ``target_node``, ler trajetória de outro corredor
e segurar a transação (e o lock do checkpoint) por mais tempo.
"""

from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")

SQL_TABLE_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.tables "
    "WHERE table_schema = DATABASE() AND table_name = %s"
)
SQL_INDEX_NAME = (
    "SELECT 1 AS ok FROM information_schema.statistics "
    "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s"
)
SQL_LEFTMOST = (
    "SELECT 1 AS ok FROM information_schema.statistics "
    "WHERE table_schema = DATABASE() AND table_name = %s "
    "AND column_name = %s AND seq_in_index = 1"
)

# (tabela, nome, colunas, pular se a primeira coluna já for leftmost de algum índice)
INDEXES = (
    ("edges", "idx_edges_target_node", "target_node", True),
    ("edges", "idx_edges_active_trace", "active_trace_id", True),
    ("walk_traces", "idx_walk_traces_sensors_log", "sensors_log_id", True),
    ("walk_traces", "idx_walk_traces_saved_route", "saved_route_id", True),
    ("walk_traces", "idx_walk_traces_target_node", "target_node", True),
    (
        "walk_traces",
        "idx_trace_median",
        "source_node, target_node, is_valid, total_distance_m",
        False,
    ),
    (
        "walk_traces",
        "idx_trace_latest",
        "source_node, target_node, is_valid, started_at, id",
        False,
    ),
    ("saved_routes", "idx_saved_routes_start_node", "start_node", True),
    ("saved_routes", "idx_saved_routes_end_node", "end_node", True),
)

_OPTIONAL_TABLES = frozenset({"saved_routes"})


def _fetch(db, sql: str, params=None):
    rows = db.execute_search(sql, params)
    if rows is None:
        raise RuntimeError(f"Falha ao consultar o banco: {sql}")
    return rows


def _table_exists(db, name: str) -> bool:
    return bool(_fetch(db, SQL_TABLE_EXISTS, (name,)))


def _index_named(db, table: str, index_name: str) -> bool:
    return bool(_fetch(db, SQL_INDEX_NAME, (table, index_name)))


def _leftmost(db, table: str, column: str) -> bool:
    return bool(_fetch(db, SQL_LEFTMOST, (table, column)))


def _exec(db, sql: str) -> None:
    if db.execute_query(sql) is not True:
        raise RuntimeError(f"Migração abortada; o comando falhou: {sql}")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise RuntimeError(f"Identificador inesperado: {name}")
    return name


def apply(db) -> None:
    """Cria os índices que ainda não existem. Comando que falha aborta."""
    seen_tables: set[str] = set()
    for table, index_name, columns, skip_if_leftmost in INDEXES:
        table = _check_ident(table)
        index_name = _check_ident(index_name)
        column_names = [_check_ident(part.strip()) for part in columns.split(",")]
        if table not in seen_tables:
            seen_tables.add(table)
            if not _table_exists(db, table):
                if table in _OPTIONAL_TABLES:
                    print(f"[M04] {table} ausente; índices dessa tabela ficam para depois.")
                    continue
                raise RuntimeError(f"{table} não existe. Rode as migrações 002 e 003 antes da 004.")
        if not _table_exists(db, table):
            continue
        if _index_named(db, table, index_name):
            continue
        if skip_if_leftmost and _leftmost(db, table, column_names[0]):
            continue
        column_sql = ", ".join(column_names)
        _exec(db, f"ALTER TABLE {table} ADD INDEX {index_name} ({column_sql})")
        print(f"[M04] índice {index_name} em {table} ({column_sql})")
