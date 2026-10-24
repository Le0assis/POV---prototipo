"""Cria o schema de DB_NAME e o GRANT do usuário pov, sem apagar nada.

No Linux, ``lower_case_table_names=0`` (padrão): ``POV`` e ``pov`` são
bancos diferentes. A API usa o nome exato de ``DB_NAME`` (padrão ``POV``).
Conectar nesse nome quando o schema não existe responde 1049 antes de
qualquer tabela.

O script não dá DROP, RENAME nem TRUNCATE. Usuário pov que já existe
mantém a senha. ``CREATE USER`` só roda se ``DB_POV_PASSWORD`` estiver
definida, ou se ``DB_USER=pov`` e ``DB_PASSWORD`` estiver definida.
"""

from __future__ import annotations

import os
import re

import mysql.connector
from mysql.connector import Error

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
POV_USER = "pov"
POV_HOSTS = ("localhost", "127.0.0.1")
# 1133/1410: conta ainda não existe. Não criamos com senha vazia no escuro.
_MISSING_ACCOUNT = frozenset({1133, 1410, 1141})


def quote_ident(name: str) -> str:
    """Identificador já validado, entre crases. Recusa qualquer outra coisa."""
    if not _IDENT.match(name or ""):
        raise RuntimeError(
            f"Nome de banco inválido: {name!r}. Use letras, números e _."
        )
    return f"`{name}`"


def create_database_sql(name: str) -> str:
    """utf8mb4 explícito. O default do servidor (latin1 no XAMPP antigo) quebra a FK."""
    return (
        f"CREATE DATABASE IF NOT EXISTS {quote_ident(name)} "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


def grant_sql(name: str, host: str) -> str:
    if host not in POV_HOSTS:
        raise RuntimeError(f"Host de grant inesperado: {host}")
    return f"GRANT ALL PRIVILEGES ON {quote_ident(name)}.* TO '{POV_USER}'@'{host}'"


def create_user_sql(host: str) -> str:
    if host not in POV_HOSTS:
        raise RuntimeError(f"Host de grant inesperado: {host}")
    return f"CREATE USER IF NOT EXISTS '{POV_USER}'@'{host}' IDENTIFIED BY %s"


def _password_for_new_account(app_user: str, app_password: str) -> str | None:
    """Senha só para conta que ainda não existe. Conta velha não é alterada."""
    if "DB_POV_PASSWORD" in os.environ:
        return os.environ["DB_POV_PASSWORD"]
    if app_user == POV_USER:
        return app_password
    if os.environ.get("DB_USER", "").strip() == POV_USER and "DB_PASSWORD" in os.environ:
        return os.environ["DB_PASSWORD"]
    return None


def _connect_server(host: str, port: int, user: str, password: str):
    """Sem database: o 1049 acontece justamente quando o schema ainda não existe."""
    return mysql.connector.connect(
        host="127.0.0.1" if str(host).strip().lower() == "localhost" else host,
        port=int(port),
        user=user,
        password=password,
        connection_timeout=5,
        autocommit=True,
        use_pure=True,
    )


def _open_admin(host: str, port: int, app_user: str, app_password: str):
    admin_user = os.environ.get("DB_ADMIN_USER", "root")
    admin_password = os.environ.get("DB_ADMIN_PASSWORD", "")
    attempts = [(admin_user, admin_password)]
    if app_user and (app_user, app_password) not in attempts:
        attempts.append((app_user, app_password))
    errors: list[str] = []
    for user, password in attempts:
        try:
            return _connect_server(host, port, user, password), user
        except Error as exc:
            errors.append(f"{user}: {exc}")
    raise RuntimeError(
        "Não conectou no MySQL sem schema para criar o banco. "
        "Rode com o root do XAMPP (DB_ADMIN_USER/DB_ADMIN_PASSWORD) "
        "ou com um usuário que possa CREATE DATABASE. "
        + " | ".join(errors)
    )


def ensure_app_database(name: str, host: str, port: int, app_user: str, app_password: str) -> None:
    """CREATE DATABASE IF NOT EXISTS e GRANT para pov. Não remove schema nem conta."""
    sql = create_database_sql(name)
    connection, admin = _open_admin(host, port, app_user, app_password)
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW VARIABLES LIKE 'lower_case_table_names'")
        found = cursor.fetchall()
        if found and str(found[0][1]) == "0" and name != name.lower():
            print(
                f"[SETUP] lower_case_table_names=0: o schema é exatamente '{name}'. "
                f"'{name.lower()}' seria outro banco e não é criado nem apagado."
            )
        cursor.execute(sql)
        print(f"[SETUP] Schema '{name}' garantido (utf8mb4), via '{admin}'.")
        password = _password_for_new_account(app_user, app_password)
        for account_host in POV_HOSTS:
            if password is not None:
                cursor.execute(create_user_sql(account_host), (password,))
            try:
                cursor.execute(grant_sql(name, account_host))
                print(f"[SETUP] GRANT de {name}.* para {POV_USER}@{account_host}.")
            except Error as exc:
                if getattr(exc, "errno", None) in _MISSING_ACCOUNT and password is None:
                    print(
                        f"[SETUP] {POV_USER}@{account_host} ainda não existe. "
                        "Defina DB_POV_PASSWORD e rode de novo para criar a conta. "
                        "Nenhuma senha existente foi trocada."
                    )
                    continue
                raise
        cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()
