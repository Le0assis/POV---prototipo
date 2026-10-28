"""Seed do mapa de exemplo. Pode rodar de novo: não apaga e não sobrescreve.

Entra com ``DB_USER=pov`` e a senha de ``DB_PASSWORD``. Só consulta e
insere. Não usa ``DB_ADMIN_*`` e não aceita a conta root. Checkpoint com
a mesma chave (caixa e espaço) fica com o rótulo já gravado. Acento
diferente continua outro nome; se a unique do MySQL juntar as duas
grafias, a transação desfaz. Aresta que já existe não muda distância nem
origin. Rode depois de ``python -m datasets.create_tables``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets.create_tables import conexao_from_settings
from map.checkpoint_slug import (
    DEFAULT_BUILDING_ID,
    allocate_slug,
    checkpoint_name_key,
    display_checkpoint_name,
)

CHECKPOINTS = [
    "Recepcao",
    "Corredor A",
    "Sala 101",
    "Sala 102",
    "Sala 103",
    "Corredor B",
    "Banheiro",
    "Escada",
]

# source, target, metros, radianos. O sentido inverso é outra linha.
EDGES = [
    ("Recepcao", "Corredor A", 4.5, 0.0),
    ("Corredor A", "Sala 101", 2.0, 1.57),
    ("Corredor A", "Sala 102", 5.0, 1.57),
    ("Corredor A", "Corredor B", 8.0, 0.0),
    ("Corredor B", "Sala 103", 3.0, 1.57),
    ("Corredor B", "Banheiro", 2.5, -1.57),
    ("Corredor B", "Escada", 4.0, 0.0),
]

# Leitura de uma vez, antes de qualquer INSERT. O resolve?cp= continua na collation.
# A unique de name é da tabela, não do prédio: o conflito de caixa olha todos.
SQL_NAMES = "SELECT name FROM checkpoints"
SQL_EXISTING = "SELECT name, slug FROM checkpoints WHERE building_id = %s"
# Mesma regra do grafo: Sala não é sala.
SQL_NAME = (
    "SELECT slug FROM checkpoints WHERE CAST(name AS BINARY) = CAST(%s AS BINARY)"
)
SQL_CHECKPOINT = (
    "INSERT INTO checkpoints (name, building_id, slug) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE name = name"
)
SQL_EDGE = (
    "INSERT INTO edges (source_node, target_node, distance_m, heading_rad, origin) "
    "VALUES (%s, %s, %s, %s, 'manual') "
    "ON DUPLICATE KEY UPDATE id = id"
)


class SeedConflict(RuntimeError):
    """Outra caixa já ocupa a unique. O script sai com 1, sem traceback."""


def _inverse_heading(heading: float) -> float:
    import math
    return (heading + math.pi) % (2 * math.pi)


def _exact_checkpoint(db, name: str):
    """Linha cujo nome é o texto exato. Outra caixa não conta."""
    rows = db.execute_search(SQL_NAME, (name,))
    if rows is None:
        raise RuntimeError(f"Não leu o checkpoint {name}.")
    return rows


def _alias_from(rows) -> dict[str, str]:
    """Chave → rótulo já gravado. A primeira linha fica com a exibição."""
    found: dict[str, str] = {}
    for row in rows:
        stored = row.get("name")
        if stored:
            found.setdefault(checkpoint_name_key(stored), stored)
    return found


def _write_seed(db, rows) -> None:
    taken = {row["slug"] for row in rows if row.get("slug")}
    alias = _alias_from(rows)
    print("Inserindo checkpoints...")
    for name in CHECKPOINTS:
        key = checkpoint_name_key(name)
        if key in alias:
            continue
        label = display_checkpoint_name(name)
        slug = allocate_slug(label, taken)
        if not db.execute_within(SQL_CHECKPOINT, (label, DEFAULT_BUILDING_ID, slug)):
            raise RuntimeError(f"Não gravou o checkpoint {label}. Nada foi gravado.")
        # A unique de name segue a collation e também junta acento. Se o
        # INSERT não deixou este texto, a transação desfaz a rodada.
        if not _exact_checkpoint(db, label):
            raise SeedConflict(
                f"Conflito de grafia: '{label}' não foi gravado. "
                "A unique de checkpoints.name junta essa grafia com outra já existente. "
                "Nada foi gravado e nenhuma aresta foi criada."
            )
        alias[key] = label
        taken.add(slug)
    print("Inserindo conexões...")
    for source, target, distance, heading in EDGES:
        src_name = alias.get(checkpoint_name_key(source))
        tgt_name = alias.get(checkpoint_name_key(target))
        if not src_name or not tgt_name:
            raise RuntimeError(
                f"Não achou o checkpoint de {source}->{target}. Nada foi gravado."
            )
        directions = (
            (src_name, tgt_name, distance, heading),
            (tgt_name, src_name, distance, _inverse_heading(heading)),
        )
        for src, tgt, dist, rad in directions:
            if not db.execute_within(SQL_EDGE, (src, tgt, dist, rad)):
                raise RuntimeError(f"Não gravou a aresta {src}->{tgt}. Nada foi gravado.")


def seed(db) -> None:
    known = db.execute_search(SQL_NAMES)
    if known is None:
        raise RuntimeError("Não leu os checkpoints. Rode create_tables antes do seed.")
    rows = db.execute_search(SQL_EXISTING, (DEFAULT_BUILDING_ID,))
    if rows is None:
        raise RuntimeError("Não leu os checkpoints. Rode create_tables antes do seed.")
    if not db.begin_transaction():
        raise RuntimeError("Não abriu a transação do seed. Nada foi gravado.")
    try:
        _write_seed(db, rows)
        if not db.commit_transaction():
            raise RuntimeError("Não confirmou o seed. Nada foi gravado.")
    except Exception:
        db.rollback_transaction()
        raise
    print("Mapa de exemplo garantido. Linha que já existia não foi alterada.")


_DSN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_PASSWORD_RE = re.compile(r"(?i)\b(password|pwd|passwd)\s*[:=]\s*\S+")


def _secrets(db) -> list[str]:
    """Senha do ambiente e a da conexão. Vazio não entra: apagaria o texto."""
    found = []
    values = [os.environ.get("DB_PASSWORD", "")]
    if db is not None:
        values.append(getattr(db, "password", ""))
    for value in values:
        secret = str(value or "")
        if secret and secret not in found:
            found.append(secret)
    return found


def _short_error(exc: BaseException, db) -> str:
    """Tipo e mensagem, numa linha. Sem traceback, senha ou DSN."""
    text = " ".join(str(exc).split())
    for secret in _secrets(db):
        text = text.replace(secret, "***")
    text = _DSN_RE.sub("[DSN omitido]", text)
    text = _PASSWORD_RE.sub(r"\1=***", text)
    trace_at = text.find("Traceback (most recent call last)")
    if trace_at != -1:
        text = text[:trace_at].rstrip()
    name = type(exc).__name__
    return f"{name}: {text}" if text else name


def cli(db=None) -> int:
    """Erro: código 1 e uma linha no stderr. O traceback fica de fora.

    Sem ``db``, a conexão sai de ``conexao_from_settings`` aqui dentro:
    porta inválida ou variável ausente também vira essa linha. Conflito
    de grafia (a unique juntou um acento) mantém a mensagem já combinada.
    Qualquer outra exceção vira tipo + mensagem, sem senha e sem DSN.
    O rollback continua em ``seed``.
    """
    created = None
    try:
        if db is None:
            db = conexao_from_settings()
            created = db
            assert_seed_account(str(db.user))
            db.connect()
            if not db.connection:
                raise SystemExit(
                    "Erro ao conectar como pov. Confira DB_HOST, DB_PORT, DB_NAME, "
                    "DB_USER e DB_PASSWORD. O seed não usa a conta administrativa."
                )
        seed(db)
    except SeedConflict as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(_short_error(exc, db), file=sys.stderr)
        return 1
    finally:
        if created is not None:
            created.disconnect()
    return 0


def assert_seed_account(user: str) -> None:
    """O seed é a conta pov. Root e o admin do CREATE DATABASE ficam de fora."""
    account = (user or "").strip()
    if account != "pov":
        raise RuntimeError(
            "O seed entra com DB_USER=pov e só lê e insere. "
            f"DB_USER está como {user!r}. "
            "DB_ADMIN_USER (no XAMPP local, root sem senha) não serve para o seed."
        )


if __name__ == "__main__":
    code = cli()
    if code:
        raise SystemExit(code)
