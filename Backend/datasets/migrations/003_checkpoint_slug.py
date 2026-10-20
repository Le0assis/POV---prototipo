"""Migração idempotente 003: prédio, categoria e slug do checkpoint.

Não há ferramenta de migração no projeto. ``create_tables`` chama ``apply``
depois da 002. Rodar de novo não recria ``checkpoints_backup_m03`` nem
troca slug que já esteja preenchido.

O backup é o primeiro comando. Se ele não confirmar, nada é alterado.
Slug entra NULL, o backfill preenche uma vez (mesma regra da criação) e
só então a coluna vira NOT NULL e UNIQUE (building_id, slug).
"""

from __future__ import annotations

from map.checkpoint_slug import DEFAULT_BUILDING_ID, allocate_slug

BUILDING_NAME = "Unimar"
CATEGORY_SEEDS = (
    ("atendimento", "Atendimento", 1),
    ("banheiros", "Banheiros", 2),
    ("alimentacao", "Alimentação", 3),
    ("saidas", "Saídas", 4),
)

SQL_TABLE_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.tables "
    "WHERE table_schema = DATABASE() AND table_name = %s"
)
SQL_COLUMN_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.columns "
    "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s"
)
SQL_COLUMN_NULLABLE = (
    "SELECT IS_NULLABLE AS nullable FROM information_schema.columns "
    "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s"
)
SQL_INDEX_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.statistics "
    "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s"
)
SQL_FK_EXISTS = (
    "SELECT 1 AS ok FROM information_schema.table_constraints "
    "WHERE table_schema = DATABASE() AND table_name = %s "
    "AND constraint_name = %s AND constraint_type = 'FOREIGN KEY'"
)
SQL_BACKUP = "CREATE TABLE checkpoints_backup_m03 AS SELECT * FROM checkpoints"
SQL_CREATE_BUILDINGS = """
CREATE TABLE IF NOT EXISTS buildings (
    id INT NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
SQL_SEED_BUILDING = (
    "INSERT INTO buildings (id, name) VALUES (%s, %s) "
    "ON DUPLICATE KEY UPDATE id = id"
)
SQL_CREATE_CATEGORIES = """
CREATE TABLE IF NOT EXISTS checkpoint_categories (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    label VARCHAR(64) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
SQL_SEED_CATEGORIES = (
    "INSERT INTO checkpoint_categories (code, label, sort_order) VALUES "
    + ", ".join(["(%s, %s, %s)"] * len(CATEGORY_SEEDS))
    + " ON DUPLICATE KEY UPDATE label = VALUES(label), sort_order = VALUES(sort_order)"
)
SQL_SELECT_CHECKPOINTS = (
    "SELECT id, name, building_id, slug FROM checkpoints ORDER BY id"
)
SQL_UPDATE_SLUG = (
    "UPDATE checkpoints SET slug = %s WHERE id = %s AND slug IS NULL"
)
SQL_NULL_SLUGS = "SELECT id FROM checkpoints WHERE slug IS NULL OR slug = ''"
SQL_DUPLICATE_SLUGS = (
    "SELECT building_id, slug, COUNT(*) AS total FROM checkpoints "
    "GROUP BY building_id, slug HAVING COUNT(*) > 1"
)
SQL_SLUG_NOT_NULL = "ALTER TABLE checkpoints MODIFY COLUMN slug VARCHAR(64) NOT NULL"
SQL_UNIQUE_SLUG = (
    "ALTER TABLE checkpoints "
    "ADD UNIQUE KEY uq_checkpoints_building_slug (building_id, slug)"
)
SQL_INDEX_CATEGORY = (
    "ALTER TABLE checkpoints ADD INDEX idx_checkpoints_category_id (category_id)"
)
SQL_FK_CATEGORY = (
    "ALTER TABLE checkpoints ADD CONSTRAINT fk_checkpoints_category "
    "FOREIGN KEY (category_id) REFERENCES checkpoint_categories (id) "
    "ON DELETE SET NULL"
)
SQL_FK_BUILDING = (
    "ALTER TABLE checkpoints ADD CONSTRAINT fk_checkpoints_building "
    "FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE RESTRICT"
)
SQL_UNIQUE_MAP = (
    "ALTER TABLE map_config ADD UNIQUE KEY uq_map_config_building (building_id)"
)
SQL_FK_MAP = (
    "ALTER TABLE map_config ADD CONSTRAINT fk_map_config_building "
    "FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE RESTRICT"
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


def _index_exists(db, table: str, index_name: str) -> bool:
    return bool(_fetch(db, SQL_INDEX_EXISTS, (table, index_name)))


def _fk_exists(db, table: str, constraint_name: str) -> bool:
    return bool(_fetch(db, SQL_FK_EXISTS, (table, constraint_name)))


def _exec(db, sql: str, params=None) -> None:
    if db.execute_query(sql, params) is not True:
        raise RuntimeError(f"Migração abortada; o comando falhou: {sql}")


def _add_column(db, table: str, column: str, definition: str) -> None:
    if _column_exists(db, table, column):
        return
    _exec(db, f"ALTER TABLE {table} ADD COLUMN {definition}")


def backup_checkpoints_once(db) -> None:
    """Snapshot anterior a qualquer ALTER. Tabela já existente fica como está."""
    if _table_exists(db, "checkpoints_backup_m03"):
        print("[M03] checkpoints_backup_m03 já existe; snapshot original preservado.")
        return
    _exec(db, SQL_BACKUP)
    if not _table_exists(db, "checkpoints_backup_m03"):
        raise RuntimeError(
            "checkpoints_backup_m03 não foi confirmada após o CREATE. Migração abortada."
        )
    print("[M03] Snapshot checkpoints_backup_m03 criado antes das alterações.")


def _seed_params() -> tuple:
    values = []
    for code, label, sort_order in CATEGORY_SEEDS:
        values.extend((code, label, sort_order))
    return tuple(values)


def backfill_slugs(db) -> None:
    """Preenche só slug NULL, em ordem de id. Slug já gravado não é recalculado."""
    rows = _fetch(db, SQL_SELECT_CHECKPOINTS)
    taken: dict[int, set[str]] = {}
    pending = []
    for row in rows:
        building_id = int(row.get("building_id") or DEFAULT_BUILDING_ID)
        bucket = taken.setdefault(building_id, set())
        current = row.get("slug")
        if current:
            bucket.add(current)
        else:
            pending.append((row, building_id, bucket))
    for row, building_id, bucket in pending:
        slug = allocate_slug(str(row.get("name") or ""), bucket)
        bucket.add(slug)
        _exec(db, SQL_UPDATE_SLUG, (slug, int(row["id"])))
        print(
            f"[M03] slug id={row['id']} building_id={building_id} "
            f"name={row.get('name')!r} -> {slug}"
        )


def _assert_slugs_ready(db) -> None:
    missing = _fetch(db, SQL_NULL_SLUGS)
    if missing:
        raise RuntimeError(
            "Backfill de slug incompleto; há checkpoint sem slug. "
            "UNIQUE(building_id, slug) não foi criado."
        )
    duplicates = _fetch(db, SQL_DUPLICATE_SLUGS)
    if duplicates:
        raise RuntimeError(
            "Backfill gerou slug duplicado no mesmo prédio: "
            f"{duplicates}. UNIQUE(building_id, slug) não foi criado."
        )


def apply(db) -> None:
    """Aplica a migração. Qualquer comando que não confirme aborta."""
    backup_checkpoints_once(db)

    _exec(db, SQL_CREATE_BUILDINGS)
    _exec(db, SQL_SEED_BUILDING, (DEFAULT_BUILDING_ID, BUILDING_NAME))

    _exec(db, SQL_CREATE_CATEGORIES)
    _exec(db, SQL_SEED_CATEGORIES, _seed_params())

    _add_column(db, "checkpoints", "category_id", "category_id INT NULL")
    if not _index_exists(db, "checkpoints", "idx_checkpoints_category_id"):
        _exec(db, SQL_INDEX_CATEGORY)
    if not _fk_exists(db, "checkpoints", "fk_checkpoints_category"):
        _exec(db, SQL_FK_CATEGORY)

    _add_column(
        db,
        "checkpoints",
        "building_id",
        "building_id INT NOT NULL DEFAULT 1",
    )
    _add_column(db, "checkpoints", "slug", "slug VARCHAR(64) NULL")
    backfill_slugs(db)
    _assert_slugs_ready(db)

    nullable = _fetch(db, SQL_COLUMN_NULLABLE, ("checkpoints", "slug"))
    if not nullable:
        raise RuntimeError("checkpoints.slug não encontrado após o ALTER.")
    if str(nullable[0]["nullable"]).upper() == "YES":
        _exec(db, SQL_SLUG_NOT_NULL)

    if not _index_exists(db, "checkpoints", "uq_checkpoints_building_slug"):
        _exec(db, SQL_UNIQUE_SLUG)
    if not _fk_exists(db, "checkpoints", "fk_checkpoints_building"):
        _exec(db, SQL_FK_BUILDING)

    if not _table_exists(db, "map_config"):
        raise RuntimeError("map_config não existe. Rode a migração 002 antes da 003.")
    _add_column(
        db,
        "map_config",
        "building_id",
        "building_id INT NOT NULL DEFAULT 1",
    )
    if not _index_exists(db, "map_config", "uq_map_config_building"):
        _exec(db, SQL_UNIQUE_MAP)
    if not _fk_exists(db, "map_config", "fk_map_config_building"):
        _exec(db, SQL_FK_MAP)
