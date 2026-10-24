"""Configuração do processo, lida de novo a cada chamada.

O ``.env`` entra antes, por ``load_env_file`` (o shell ganha, e o hash
argon2id tem ``=``). Aqui só lemos o ambiente já montado: um teste troca
a variável e a próxima chamada vê o valor novo.
"""

from __future__ import annotations

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
    # DB_USER, DB_PASSWORD. Sem ambiente a conta é pov, não root.
    # DB_ADMIN_USER e DB_ADMIN_PASSWORD não são lidas. A API não cria schema.
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "POV"
    db_user: str = "pov"
    db_password: str = ""

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
