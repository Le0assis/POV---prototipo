"""O schema POV é criado pelo nome exato, sem DROP."""

from __future__ import annotations

import pytest

from datasets.bootstrap_db import (
    admin_db_config,
    app_db_config,
    create_database_sql,
    create_user_sql,
    grant_sql,
    quote_ident,
)

pytestmark = pytest.mark.unit


def test_database_sql_is_create_if_not_exists_utf8mb4():
    sql = create_database_sql("POV")
    assert sql == (
        "CREATE DATABASE IF NOT EXISTS `POV` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    assert "DROP" not in sql
    assert "pov" not in sql.replace("utf8mb4", "")


def test_grant_covers_tcp_and_socket_for_the_same_schema():
    assert grant_sql("POV", "localhost") == "GRANT ALL PRIVILEGES ON `POV`.* TO 'pov'@'localhost'"
    assert grant_sql("POV", "127.0.0.1") == (
        "GRANT ALL PRIVILEGES ON `POV`.* TO 'pov'@'127.0.0.1'"
    )
    user_sql = create_user_sql("localhost")
    assert user_sql.startswith("CREATE USER IF NOT EXISTS 'pov'@'localhost'")
    assert "IDENTIFIED BY %s" in user_sql


def test_app_and_admin_credentials_come_from_the_environment(monkeypatch):
    for key in (
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_ADMIN_USER",
        "DB_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="DB_USER"):
        app_db_config()
    with pytest.raises(SystemExit, match="DB_ADMIN_USER") as missing_admin:
        admin_db_config()
    assert missing_admin.value.code != 0
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_NAME", "POV")
    monkeypatch.setenv("DB_USER", "pov")
    monkeypatch.setenv("DB_PASSWORD", "local-only")
    monkeypatch.setenv("DB_ADMIN_USER", "root")
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "")
    app = app_db_config()
    assert app["user"] == "pov"
    assert app["password"] == "local-only"
    assert admin_db_config() == ("root", "")


def test_seed_refuses_any_account_other_than_pov():
    from others.seed_map import assert_seed_account

    assert_seed_account("pov")
    with pytest.raises(RuntimeError, match="pov"):
        assert_seed_account("root")


def test_quote_ident_rejects_anything_that_is_not_a_name():
    assert quote_ident("pov_save_repro") == "`pov_save_repro`"
    with pytest.raises(RuntimeError):
        quote_ident("POV; DROP DATABASE POV")
    with pytest.raises(RuntimeError):
        quote_ident("")
