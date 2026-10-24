"""Ambiente: produção, desenvolvimento e o MySQL do XAMPP."""

from __future__ import annotations

import os

import pytest

from api.settings import DEV_ORIGINS, PRODUCTION_ORIGINS, get_settings

pytestmark = pytest.mark.unit


def test_production_refuses_to_start_without_the_database_account(monkeypatch):
    from api.settings import DatabaseConfigError, assert_production_database

    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.setenv("DB_PASSWORD", "segredo-que-nao-sai")
    for name in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(DatabaseConfigError) as exc:
        assert_production_database()
    text = str(exc.value)
    assert "DB_HOST" in text and "DB_USER" in text
    assert "segredo-que-nao-sai" not in text

    for name, value in (
        ("DB_HOST", "db.internal"),
        ("DB_PORT", "3306"),
        ("DB_NAME", "POV"),
        ("DB_USER", "root"),
    ):
        monkeypatch.setenv(name, value)
    with pytest.raises(DatabaseConfigError) as root_exc:
        assert_production_database()
    assert "segredo-que-nao-sai" not in str(root_exc.value)
    assert "root" in str(root_exc.value)

    monkeypatch.setenv("DB_USER", "pov")
    monkeypatch.setenv("DB_PASSWORD", "")
    with pytest.raises(DatabaseConfigError) as empty_exc:
        assert_production_database()
    assert "DB_PASSWORD" in str(empty_exc.value)

    monkeypatch.setenv("DB_PASSWORD", "segredo-que-nao-sai")
    assert_production_database()


def test_production_refuses_a_short_database_password(monkeypatch):
    from api.settings import DatabaseConfigError, assert_production_database

    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_NAME", "POV")
    monkeypatch.setenv("DB_USER", "pov")
    short = "abcdefghijk"
    assert len(short) == 11
    monkeypatch.setenv("DB_PASSWORD", short)
    with pytest.raises(DatabaseConfigError) as exc:
        assert_production_database()
    text = str(exc.value)
    assert "DB_PASSWORD com menos de 12 caracteres" in text
    assert "12 caracteres ou mais" in text
    assert short not in text

    monkeypatch.setenv("DB_PASSWORD", "abcdefghijkl")
    assert len(os.environ["DB_PASSWORD"]) == 12
    assert_production_database()

    padded = "  abcdefghijk"
    assert len(padded.strip()) == 11
    monkeypatch.setenv("DB_PASSWORD", padded)
    with pytest.raises(DatabaseConfigError) as padded_exc:
        assert_production_database()
    assert padded not in str(padded_exc.value)
    assert padded.strip() not in str(padded_exc.value)
    monkeypatch.setenv("DB_PASSWORD", "  abcdefghijkl")
    assert len(os.environ["DB_PASSWORD"].strip()) == 12
    assert_production_database()


def test_boot_refuses_a_short_password_without_a_traceback(monkeypatch, capsys):
    from api.settings import assert_production_database, boot_or_exit

    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_NAME", "POV")
    monkeypatch.setenv("DB_USER", "pov")
    short = "abcdefghijk"
    monkeypatch.setenv("DB_PASSWORD", short)

    def load() -> None:
        assert_production_database()

    with pytest.raises(SystemExit) as exc:
        boot_or_exit(load)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "Traceback" not in err
    assert short not in err
    assert "12" in err


def test_development_and_test_accept_a_short_database_password(monkeypatch):
    from api.settings import assert_production_database

    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_NAME", "POV")
    monkeypatch.setenv("DB_USER", "pov")
    monkeypatch.setenv("DB_PASSWORD", "ab")
    for env in ("development", "test", "dev"):
        monkeypatch.setenv("POV_ENV", env)
        assert_production_database()


def test_unset_env_is_development_with_xampp_defaults(monkeypatch):
    for name in (
        "POV_ENV",
        "CORS_ORIGINS",
        "POV_ENABLE_TEST_ROUTES",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    cfg = get_settings()
    assert cfg.pov_env == "development"
    assert cfg.allowed_origins() == list(DEV_ORIGINS)
    assert cfg.pov_enable_test_routes is False
    assert cfg.db_host == "localhost"
    assert cfg.db_port == 3306
    assert cfg.db_name == "POV"
    assert cfg.db_user is None
    assert cfg.db_password is None
    assert not hasattr(cfg, "db_admin_user")
    assert not hasattr(cfg, "db_admin_password")


def test_production_origins_are_only_the_pages_hosts(monkeypatch):
    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    origins = get_settings().allowed_origins()
    assert origins == list(PRODUCTION_ORIGINS)
    assert "http://localhost" not in origins
    assert "http://127.0.0.1:8000" not in origins


def test_cors_origins_replaces_the_list(monkeypatch):
    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", " https://example.test , http://localhost:9999 ")
    assert get_settings().allowed_origins() == [
        "https://example.test",
        "http://localhost:9999",
    ]


def test_dev_origins_include_the_vite_port():
    assert "http://localhost:5173" in DEV_ORIGINS
    assert "http://127.0.0.1:5173" in DEV_ORIGINS


def test_wildcard_origin_is_dropped(monkeypatch):
    monkeypatch.setenv("POV_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    assert get_settings().allowed_origins() == list(PRODUCTION_ORIGINS)
    monkeypatch.setenv("CORS_ORIGINS", " *, https://pov-unimar.com ")
    assert get_settings().allowed_origins() == ["https://pov-unimar.com"]


def test_create_tables_uses_db_settings(monkeypatch):
    from datasets.create_tables import conexao_from_settings

    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_NAME", "pov_test")
    monkeypatch.setenv("DB_USER", "pov")
    monkeypatch.setenv("DB_PASSWORD", "local-only")
    conn = conexao_from_settings()
    assert conn.host == "db.internal"
    assert conn.port == 3307
    assert conn.database == "pov_test"
    assert conn.user == "pov"
    assert conn.password == "local-only"
    assert conn.connection is None


def test_test_routes_flag_parses_common_words(monkeypatch):
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "on")
    assert get_settings().pov_enable_test_routes is True
    monkeypatch.setenv("POV_ENABLE_TEST_ROUTES", "0")
    assert get_settings().pov_enable_test_routes is False
