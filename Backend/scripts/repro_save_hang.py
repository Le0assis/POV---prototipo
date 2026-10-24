"""Reproduz a travada do connect sem prazo.

Sobe um TCP que aceita e não manda o handshake do MySQL. O connect antigo
(timeout nulo, que a extensão C lê como 0) fica preso nessa leitura. Aqui
o prazo é curto: o script termina sozinho.

Uso, a partir de Backend/:

    python scripts/repro_save_hang.py

Código 0: o connect desistiu dentro do prazo. Código 1: ainda bloqueou.
Não precisa do MySQL do XAMPP.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from datasets.ManagerDatabase import ConexaoBD


def main() -> int:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    held: list[socket.socket] = []

    def accept_and_hold() -> None:
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        held.append(conn)
        time.sleep(3)

    thread = threading.Thread(target=accept_and_hold, daemon=True)
    thread.start()
    # O handshake não chega a autenticar. O usuário é o da aplicação.
    database = ConexaoBD("localhost", "POV", "pov", "", port=port)
    started = time.perf_counter()
    try:
        database.connect(announce=False, timeout=0.4)
    finally:
        listener.close()
        for conn in held:
            conn.close()
    elapsed = time.perf_counter() - started
    if database.connection is not None or elapsed >= 2:
        print(f"ainda bloqueou: conexao={database.connection!r} tempo={elapsed:.2f}s")
        return 1
    print(f"connect desistiu em {elapsed:.2f}s (prazo 0.4s), sem sessão aberta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
