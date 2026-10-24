"""Gera EDITOR_PASSWORD_HASH (argon2id) sem gravar a senha.

A senha é pedida no terminal, com eco desligado, e conferida uma segunda
vez. Não passe a senha como argumento: ela iria para o histórico do shell.
Copie só a linha impressa para o ``.env`` da raiz, entre aspas se for colar
no shell. Não commite esse arquivo.

Uso, a partir de Backend/:

    python scripts/hash_password.py
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.editor_auth import make_password_hash


def main() -> int:
    if len(sys.argv) > 1:
        print("Não passe a senha como argumento. O script pergunta no terminal.", file=sys.stderr)
        return 2
    password = getpass.getpass("Senha do editor: ")
    confirm = getpass.getpass("Repita a senha: ")
    if password != confirm:
        print("As senhas não conferem.", file=sys.stderr)
        return 1
    if password == "":
        print("Senha vazia.", file=sys.stderr)
        return 1
    print(make_password_hash(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
