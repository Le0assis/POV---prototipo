"""Senha do editor do mapa.

``EDITOR_PASSWORD`` vem só do ambiente do processo. Não carregamos arquivo
``.env`` (sem python-dotenv). Sem a variável, a escrita fecha com 503.
Header ausente ou diferente: 401. A comparação é o digest SHA-256 em tempo
constante, para o tamanho da senha não vazar no ``compare_digest``.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Header, HTTPException


def check_editor_password(provided: str | None) -> None:
    expected = os.environ.get("EDITOR_PASSWORD")
    if expected is None or expected == "":
        raise HTTPException(
            status_code=503,
            detail="EDITOR_PASSWORD não está definida no ambiente do servidor.",
        )
    given = provided if isinstance(provided, str) else ""
    matches = hmac.compare_digest(
        hashlib.sha256(given.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )
    if not matches:
        raise HTTPException(status_code=401, detail="Senha do editor ausente ou inválida.")


def require_editor_password(x_editor_password: str | None = Header(default=None)) -> None:
    check_editor_password(x_editor_password)
