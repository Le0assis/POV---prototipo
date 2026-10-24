"""Configuração do processo, lida de novo a cada chamada.

O ``.env`` entra antes, por ``load_env_file`` (o shell ganha, e o hash
argon2id tem ``=``). Aqui só lemos o ambiente já montado: um teste troca
a variável e a próxima chamada vê o valor novo.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Pages. Em produção a lista é esta, a menos que CORS_ORIGINS substitua.
PRODUCTION_ORIGINS = (
    "https://pov-unimar.com",
    "https://www.pov-unimar.com",
)

# Live Server, o uvicorn e o Pages local. Não vale em produção.
DEV_ORIGINS = (
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Vite (frontend/vite). A origem do browser é esta, não a da API.
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    pov_env: str = "development"
    cors_origins: str = ""
    pov_enable_test_routes: bool = False
    # Mesmos nomes de create_tables e do seed: DB_HOST, DB_PORT, DB_NAME,
    # DB_USER, DB_PASSWORD. Host, porta e schema têm default de desenvolvimento.
    # Usuário e senha não: None não vira root nem senha vazia. DB_ADMIN_* não é lido.
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "POV"
    db_user: str | None = None
    db_password: str | None = None

    def allowed_origins(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw:
            # ``*`` não entra: a resposta reflete a origem e não usa credencial.
            chosen = [
                part.strip()
                for part in raw.split(",")
                if part.strip() and part.strip() != "*"
            ]
            if chosen:
                return chosen
        if self.pov_env.strip().lower() == "production":
            return list(PRODUCTION_ORIGINS)
        return list(DEV_ORIGINS)


def get_settings() -> Settings:
    return Settings()


# Produção não herda conta. Senha vazia e usuário root param a subida.
_PRODUCTION_DB_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
_PRODUCTION_DB_NONEMPTY = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER")


class DatabaseConfigError(RuntimeError):
    """Conta do MySQL inválida em produção. A mensagem não leva a senha."""


def assert_production_database() -> None:
    """Para a subida em produção sem conta de aplicação.

    Falta variável, ``DB_USER`` root ou senha vazia. Fora de produção não
    inventa usuário nem senha.
    """
    if get_settings().pov_env.strip().lower() != "production":
        return
    missing: list[str] = []
    for key in _PRODUCTION_DB_KEYS:
        if key not in os.environ:
            missing.append(key)
            continue
        if key in _PRODUCTION_DB_NONEMPTY and not os.environ[key].strip():
            missing.append(key)
    user = os.environ.get("DB_USER", "").strip()
    password = os.environ.get("DB_PASSWORD", "")
    refused: list[str] = []
    if user.casefold() == "root":
        refused.append("DB_USER=root")
    if "DB_PASSWORD" in os.environ and not str(password).strip() and "DB_PASSWORD" not in missing:
        refused.append("DB_PASSWORD vazia")
    problems = missing + refused
    if not problems:
        return
    raise DatabaseConfigError(
        "Produção sem conta de aplicação ("
        + ", ".join(problems)
        + "). Defina DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD. "
        "DB_USER não pode ser root e a senha não pode ser vazia. "
        "A API não lê DB_ADMIN_*."
    )
