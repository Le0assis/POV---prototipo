"""Slug estável do checkpoint, gerado uma vez a partir do nome.

Minúsculo, sem acento, qualquer sequência não alfanumérica vira um hífen.
No máximo 64 caracteres. Colisão no mesmo prédio recebe ``-2``, ``-3``...
Quem renomeia o checkpoint não passa por aqui: o slug gravado permanece.
"""

from __future__ import annotations

import re
import unicodedata

SLUG_MAX_LENGTH = 64
DEFAULT_BUILDING_ID = 1
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_FALLBACK = "checkpoint"


def display_checkpoint_name(name: str | None) -> str:
    """Rótulo para gravar um nome novo.

    ``strip`` e um espaço entre palavras. A caixa e o acento ficam como
    foram digitados. Não é a chave de comparação.
    """
    return " ".join(str(name or "").strip().split())


def checkpoint_name_key(name: str | None) -> str:
    """Chave de comparação. Não substitui o nome exibido.

    ``strip``, colapso de espaços e ``casefold`` (Unicode; melhor que
    ``lower``). O acento fica: ``Recepção`` e ``Recepcao`` já podem ser
    checkpoints diferentes, cada um com o seu slug. Tirar o acento
    fundiria esses nomes.
    """
    return display_checkpoint_name(name).casefold()


def slugify(name: str, max_length: int = SLUG_MAX_LENGTH) -> str:
    """Forma o slug base. Não consulta o banco e não numera colisão."""
    decomposed = unicodedata.normalize("NFD", name or "")
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    hyphenated = _NON_ALNUM.sub("-", without_marks.lower()).strip("-")
    if len(hyphenated) > max_length:
        hyphenated = hyphenated[:max_length].rstrip("-")
    if not hyphenated:
        hyphenated = _FALLBACK[:max_length]
    return hyphenated


def _with_suffix(base: str, number: int, max_length: int) -> str:
    suffix = f"-{number}"
    room = max_length - len(suffix)
    if room < 1:
        raise RuntimeError("O sufixo do slug não cabe em VARCHAR(64).")
    trimmed = base[:room].rstrip("-")
    if not trimmed:
        trimmed = _FALLBACK[:room]
    return f"{trimmed}{suffix}"


def allocate_slug(name: str, taken: set[str], max_length: int = SLUG_MAX_LENGTH) -> str:
    """Próximo slug livre dentro de ``taken`` (slugs já usados naquele prédio).

    Não altera ``taken``. O chamador grava o valor e, se for gerar outro
    no mesmo lote, inclui o slug devolvido no conjunto.
    """
    base = slugify(name, max_length=max_length)
    if base not in taken:
        return base
    number = 2
    while number <= 10000:
        candidate = _with_suffix(base, number, max_length)
        if candidate not in taken:
            return candidate
        number += 1
    raise RuntimeError(f"Não há slug livre para '{name}'.")
