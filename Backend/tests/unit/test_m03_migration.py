"""Migração 003: backup, backfill de slug e segunda execução. Sem MySQL."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _migration():
    path = BACKEND_ROOT / "datasets" / "migrations" / "003_checkpoint_slug.py"
    spec = importlib.util.spec_from_file_location("migration_003_checkpoint_slug", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return [
        {"id": 1, "name": "Recepção"},
        {"id": 2, "name": "Recepcao"},
        {"id": 3, "name": "Recepcao-2"},
        {"id": 4, "name": "Ação"},
        {"id": 5, "name": "São João"},
    ]


class _MigrationDB:
    def __init__(self, checkpoints=None) -> None:
        self.checkpoints = [dict(row) for row in (checkpoints if checkpoints is not None else _rows())]
        self.tables = {"checkpoints", "map_config"}
        self.columns: set[tuple[str, str]] = {
            ("checkpoints", "name"),
            ("checkpoints", "pos_x_px"),
            ("checkpoints", "pos_y_px"),
            ("map_config", "id"),
        }
        self.nullable: set[tuple[str, str]] = set()
        self.indexes: set[tuple[str, str]] = set()
        self.fks: set[tuple[str, str]] = set()
        self.statements: list[tuple] = []
        self.backup: list[dict] | None = None
        self.building = None
        self.category_params = None
        self.fail_exact: set[str] = set()
        self.hide_backup = False

    def execute_search(self, sql, params=None):
        module = _migration()
        params = params or ()
        if sql == module.SQL_TABLE_EXISTS:
            return [{"ok": 1}] if params[0] in self.tables else []
        if sql == module.SQL_COLUMN_EXISTS:
            return [{"ok": 1}] if (params[0], params[1]) in self.columns else []
        if sql == module.SQL_COLUMN_NULLABLE:
            key = (params[0], params[1])
            if key not in self.columns:
                return []
            return [{"nullable": "YES" if key in self.nullable else "NO"}]
        if sql == module.SQL_INDEX_EXISTS:
            return [{"ok": 1}] if (params[0], params[1]) in self.indexes else []
        if sql == module.SQL_FK_EXISTS:
            return [{"ok": 1}] if (params[0], params[1]) in self.fks else []
        if sql == module.SQL_SELECT_CHECKPOINTS:
            return [dict(row) for row in self.checkpoints]
        if sql == module.SQL_NULL_SLUGS:
            return [
                {"id": row["id"]}
                for row in self.checkpoints
                if not row.get("slug")
            ]
        if sql == module.SQL_DUPLICATE_SLUGS:
            counts: dict[tuple, int] = {}
            for row in self.checkpoints:
                key = (row.get("building_id"), row.get("slug"))
                counts[key] = counts.get(key, 0) + 1
            return [
                {"building_id": key[0], "slug": key[1], "total": total}
                for key, total in counts.items()
                if total > 1
            ]
        raise AssertionError(sql)

    def execute_query(self, sql, params=None):
        module = _migration()
        self.statements.append((sql, params))
        if sql in self.fail_exact:
            return False
        if sql == module.SQL_BACKUP and self.hide_backup:
            return True
        if sql == module.SQL_BACKUP:
            self.backup = [dict(row) for row in self.checkpoints]
            self.tables.add("checkpoints_backup_m03")
            return True
        if "CREATE TABLE" in sql and "checkpoint_categories" in sql:
            self.tables.add("checkpoint_categories")
            return True
        if "CREATE TABLE" in sql and "buildings" in sql:
            self.tables.add("buildings")
            return True
        if sql == module.SQL_SEED_BUILDING:
            self.building = {"id": params[0], "name": params[1]}
            return True
        if sql == module.SQL_SEED_CATEGORIES:
            self.category_params = params
            return True
        if sql.startswith("ALTER TABLE checkpoints ADD COLUMN category_id"):
            self.columns.add(("checkpoints", "category_id"))
            self.nullable.add(("checkpoints", "category_id"))
            for row in self.checkpoints:
                row.setdefault("category_id", None)
            return True
        if sql.startswith("ALTER TABLE checkpoints ADD COLUMN building_id"):
            self.columns.add(("checkpoints", "building_id"))
            for row in self.checkpoints:
                row.setdefault("building_id", 1)
            return True
        if sql.startswith("ALTER TABLE checkpoints ADD COLUMN slug"):
            self.columns.add(("checkpoints", "slug"))
            self.nullable.add(("checkpoints", "slug"))
            for row in self.checkpoints:
                row.setdefault("slug", None)
            return True
        if sql.startswith("ALTER TABLE map_config ADD COLUMN building_id"):
            self.columns.add(("map_config", "building_id"))
            return True
        if sql == module.SQL_INDEX_CATEGORY:
            self.indexes.add(("checkpoints", "idx_checkpoints_category_id"))
            return True
        if sql == module.SQL_FK_CATEGORY:
            self.fks.add(("checkpoints", "fk_checkpoints_category"))
            return True
        if sql == module.SQL_UPDATE_SLUG:
            slug, checkpoint_id = params
            for row in self.checkpoints:
                if row["id"] == checkpoint_id and not row.get("slug"):
                    row["slug"] = slug
            return True
        if sql == module.SQL_SLUG_NOT_NULL:
            self.nullable.discard(("checkpoints", "slug"))
            return True
        if sql == module.SQL_UNIQUE_SLUG:
            self.indexes.add(("checkpoints", "uq_checkpoints_building_slug"))
            return True
        if sql == module.SQL_FK_BUILDING:
            self.fks.add(("checkpoints", "fk_checkpoints_building"))
            return True
        if sql == module.SQL_UNIQUE_MAP:
            self.indexes.add(("map_config", "uq_map_config_building"))
            return True
        if sql == module.SQL_FK_MAP:
            self.fks.add(("map_config", "fk_map_config_building"))
            return True
        raise AssertionError(sql)


def test_migration_backfills_unique_slugs_and_is_idempotent():
    module = _migration()
    db = _MigrationDB()
    module.apply(db)

    assert db.statements[0][0] == module.SQL_BACKUP
    assert db.backup is not None
    assert all("slug" not in row for row in db.backup)
    assert db.building == {"id": 1, "name": "Unimar"}
    assert "ON DUPLICATE KEY UPDATE" in module.SQL_SEED_CATEGORIES
    assert module.SQL_FK_CATEGORY.endswith("ON DELETE SET NULL")
    assert "ON DELETE RESTRICT" in module.SQL_FK_BUILDING
    assert "UNIQUE KEY uq_checkpoints_building_slug (building_id, slug)" in module.SQL_UNIQUE_SLUG
    codes = []
    params = db.category_params
    for index in range(0, len(params), 3):
        codes.append(params[index])
    assert codes == ["atendimento", "banheiros", "alimentacao", "saidas"]

    by_name = {row["name"]: row["slug"] for row in db.checkpoints}
    assert by_name == {
        "Recepção": "recepcao",
        "Recepcao": "recepcao-2",
        "Recepcao-2": "recepcao-2-2",
        "Ação": "acao",
        "São João": "sao-joao",
    }
    assert len(set(by_name.values())) == len(by_name)
    assert ("checkpoints", "uq_checkpoints_building_slug") in db.indexes
    assert ("checkpoints", "slug") not in db.nullable
    assert ("map_config", "building_id") in db.columns
    assert ("map_config", "uq_map_config_building") in db.indexes
    assert ("map_config", "fk_map_config_building") in db.fks

    module.apply(db)
    assert [row["slug"] for row in db.checkpoints] == [
        "recepcao",
        "recepcao-2",
        "recepcao-2-2",
        "acao",
        "sao-joao",
    ]
    backups = [sql for sql, _params in db.statements if sql == module.SQL_BACKUP]
    uniques = [sql for sql, _params in db.statements if sql == module.SQL_UNIQUE_SLUG]
    updates = [sql for sql, _params in db.statements if sql == module.SQL_UPDATE_SLUG]
    assert backups == [module.SQL_BACKUP]
    assert uniques == [module.SQL_UNIQUE_SLUG]
    assert len(updates) == 5


def test_same_slug_is_allowed_in_another_building():
    module = _migration()
    db = _MigrationDB(checkpoints=[
        {"id": 1, "name": "Sala", "building_id": 1, "slug": None},
        {"id": 2, "name": "Sala", "building_id": 2, "slug": None},
    ])
    db.columns.add(("checkpoints", "building_id"))
    db.columns.add(("checkpoints", "slug"))
    db.nullable.add(("checkpoints", "slug"))
    module.apply(db)
    assert [row["slug"] for row in db.checkpoints] == ["sala", "sala"]


def test_duplicate_slugs_abort_before_the_unique_key():
    module = _migration()
    db = _MigrationDB(checkpoints=[
        {"id": 1, "name": "Sala", "building_id": 1, "slug": "igual"},
        {"id": 2, "name": "Outra", "building_id": 1, "slug": "igual"},
    ])
    db.columns.update({
        ("checkpoints", "category_id"),
        ("checkpoints", "building_id"),
        ("checkpoints", "slug"),
    })
    db.nullable.add(("checkpoints", "slug"))
    with pytest.raises(RuntimeError, match="duplicado"):
        module.apply(db)
    assert module.SQL_UNIQUE_SLUG not in [sql for sql, _params in db.statements]
    assert module.SQL_SLUG_NOT_NULL not in [sql for sql, _params in db.statements]


def test_backup_failure_aborts_before_any_change():
    module = _migration()
    db = _MigrationDB()
    db.fail_exact.add(module.SQL_BACKUP)
    with pytest.raises(RuntimeError):
        module.apply(db)
    assert "checkpoints_backup_m03" not in db.tables
    assert "buildings" not in db.tables
    assert all("slug" not in row for row in db.checkpoints)
    assert not any(sql.startswith("ALTER TABLE") for sql, _params in db.statements)


def test_unconfirmed_backup_aborts_before_any_change():
    module = _migration()
    db = _MigrationDB()
    db.hide_backup = True
    with pytest.raises(RuntimeError, match="não foi confirmada"):
        module.apply(db)
    assert "buildings" not in db.tables
    assert not any(sql.startswith("ALTER TABLE") for sql, _params in db.statements)


def test_existing_slug_is_not_rewritten():
    module = _migration()
    db = _MigrationDB(checkpoints=[
        {"id": 1, "name": "Recepção", "building_id": 1, "slug": "custom"},
        {"id": 2, "name": "Sala", "building_id": 1, "slug": None},
    ])
    db.columns.update({
        ("checkpoints", "building_id"),
        ("checkpoints", "slug"),
    })
    db.nullable.add(("checkpoints", "slug"))
    module.apply(db)
    by_id = {row["id"]: row["slug"] for row in db.checkpoints}
    assert by_id == {1: "custom", 2: "sala"}
