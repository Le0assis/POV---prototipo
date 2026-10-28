"""Conexão MySQL (XAMPP) por requisição, com prazo e devolução ao pool.

O connect não roda no event loop. Fechar ou reutilizar a sessão esvazia o
cursor e desfaz a transação que ficou aberta antes de qualquer outro comando.

Autocommit fica ligado: um SELECT não segura read view. Aresta e caminhada
abrem a transação na mão. A sessão entra em READ COMMITTED, com
``innodb_lock_wait_timeout`` de 5s. ``FOUND_ROWS`` faz o rowcount do UPDATE
contar a linha achada, mesmo quando o valor não mudou.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import os
import re
import threading
import time

import mysql.connector
from mysql.connector import Error, IntegrityError
from mysql.connector.constants import ClientFlag

# Handshake. 0 no conector C significa "sem prazo".
CONNECT_TIMEOUT_S = 5
# Comando SQL. O conector zera o timeout do socket depois do login.
COMMAND_TIMEOUT_S = 30
POOL_MAX_IDLE = 8
POOL_MAX_TOTAL = 32
# Espera uma sessão livre antes de responder 503. Rajada curta não falha na hora.
POOL_WAIT_S = 2.5

# Conexão da requisição atual. Fora de uma requisição o valor é None:
# o processo não guarda uma sessão aberta só para pingar a cada GET.
request_connection: ContextVar["ConexaoBD | None"] = ContextVar(
    "request_connection",
    default=None,
)

_pool_lock = threading.Lock()
_pool_ready = threading.Condition(_pool_lock)
_idle: list["ConexaoBD"] = []
_open = 0


class DatabaseUnavailable(Exception):
    """O connect não abriu. A API responde 503 e não usa outra sessão."""


class DatabaseBusy(Exception):
    """Lock do InnoDB ou pool no limite, depois da nova tentativa."""

    def __init__(self, message: str = "O banco está ocupado. Tente de novo em alguns segundos.") -> None:
        super().__init__(message)


class DatabaseQueryError(Exception):
    """O SQL falhou. Não é lock e não é linha ausente."""


# innodb_lock_wait_timeout (1205) e deadlock (1213).
_LOCK_ERRNOS = (1205, 1213)
# Senha menor que isso não entra no replace: "a" ou "pov" comem a mensagem.
_MIN_SECRET_LEN = 6
# Corta depois de redigir. O corte antes deixava um pedaço da senha.
_REDACT_MAX_CHARS = 4096
# Caracteres de esquema (RFC 3986): letra, dígito, + . -
_SCHEME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+.-")
# Delimitador só encerra o userinfo quando vem depois de um @.
# Antes do @, / ; espaço ( , ' ? # < ainda podem ser a senha.
_URL_DELIMS = frozenset("/;()<>," + "'" + '" \t\r\n?#')
_WORD = re.compile(r"\w")


def _scheme_starts(text: str) -> list[tuple[int, int]]:
    """Início do esquema e fim de ``://`` para cada URL, em tempo linear.

    Equivale a ``\\b[A-Za-z][A-Za-z0-9+.-]*://``: para cada ``://`` volta só
    pela corrida de caracteres de esquema logo antes dele. As corridas não se
    sobrepõem (não contêm ``:`` nem ``/``), então o total é O(n).
    """
    found: list[tuple[int, int]] = []
    search = 0
    while True:
        sep = text.find("://", search)
        if sep < 0:
            return found
        search = sep + 3
        run = sep
        while run > 0 and text[run - 1] in _SCHEME_CHARS:
            run -= 1
        for start in range(run, sep):
            char = text[start]
            if not char.isascii() or not char.isalpha():
                continue
            if start == 0 or not _WORD.match(text[start - 1]):
                found.append((start, sep + 3))
                break


def _mask_url_userinfo(text: str) -> str:
    """``esquema://user:senha@host`` vira ``esquema://***@host``.

    A senha vai até o último ``@`` antes do primeiro delimitador que aparece
    depois de um ``@``. ``mysql://u:p@db/x;a@b.com`` preserva host e caminho.
    ``http://x/a:b@c`` não tem credencial e fica como está.

    Linear: tabelas de próximo ``@``, ``:`` e delimitador, e do último ``@``,
    calculadas uma vez. Antes cada esquema varria até o fim do texto (O(n²)).
    """
    size = len(text)
    if "://" not in text:
        return text
    next_at = [size] * (size + 1)
    next_colon = [size] * (size + 1)
    next_delim = [size] * (size + 1)
    for index in range(size - 1, -1, -1):
        char = text[index]
        next_at[index] = index if char == "@" else next_at[index + 1]
        next_colon[index] = index if char == ":" else next_colon[index + 1]
        next_delim[index] = index if char in _URL_DELIMS else next_delim[index + 1]
    prev_at = [-1] * size
    last = -1
    for index in range(size):
        if text[index] == "@":
            last = index
        prev_at[index] = last

    pieces: list[str] = []
    cursor = 0
    for start, body in _scheme_starts(text):
        if start < cursor:
            continue
        first_at = next_at[body]
        if first_at >= size:
            continue
        first_delim = next_delim[body]
        # Delimitador antes do @ só vale se já houve ``:`` (pode ser a senha).
        if first_delim < first_at and next_colon[body] > first_delim:
            continue
        stop = next_delim[first_at + 1]
        if next_colon[body] >= stop:
            continue
        last_at = prev_at[stop - 1]
        pieces.append(text[cursor:start])
        pieces.append(text[start:body])
        pieces.append("***@")
        cursor = last_at + 1
    pieces.append(text[cursor:])
    return "".join(pieces)


def _known_secrets(password: object) -> list[str]:
    """DB_PASSWORD e a senha da conexão. Só entram com 6 caracteres ou mais."""
    found: list[str] = []
    for value in (password, os.environ.get("DB_PASSWORD", "")):
        secret = str(value or "")
        if len(secret) >= _MIN_SECRET_LEN and secret not in found:
            found.append(secret)
    found.sort(key=len, reverse=True)
    return found


def _tcp_host(host: str) -> str:
    """127.0.0.1 em vez de localhost, para não cair em named pipe nem em ::1."""
    if str(host).strip().lower() == "localhost":
        return "127.0.0.1"
    return host


class ConexaoBD:
    def __init__(self, host, database, user, password, port: int = 3306):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.port = int(port)
        self.connection = None
        self.cursor = None
        self._explicit = False
        self.last_errno = None

    def connect(self, announce: bool = True, timeout: float | None = None):
        """Abre a sessão. ``timeout`` None usa ``CONNECT_TIMEOUT_S``.

        Falha de rede, senha ou handshake devolve ``connection is None``
        em vez de bloquear. ``use_pure`` evita a extensão C, cujo timeout 0
        e o named pipe de localhost não têm prazo.
        """
        self.connection = None
        self.cursor = None
        self._explicit = False
        self.last_errno = None
        wait = CONNECT_TIMEOUT_S if timeout is None else timeout
        try:
            # FOUND_ROWS: rowcount do UPDATE é o que casou, não só o que mudou.
            flags = ClientFlag.get_default() | ClientFlag.FOUND_ROWS
            self.connection = mysql.connector.connect(
                host=_tcp_host(self.host),
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connection_timeout=wait,
                autocommit=True,
                use_pure=True,
                client_flags=flags,
            )
            sock = getattr(self.connection, "_socket", None)
            if sock is not None:
                sock.set_connection_timeout(COMMAND_TIMEOUT_S)
            self.cursor = self.connection.cursor(dictionary=True, buffered=True)
            self.cursor.execute(
                "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"
            )
            self.cursor.execute("SET SESSION innodb_lock_wait_timeout = 5")
            if announce:
                print("Conexão com o banco de dados estabelecida com sucesso!")
        except (Error, OSError) as exc:
            failed = self.connection
            self.connection = None
            self.cursor = None
            if failed is not None:
                try:
                    failed.close()
                except (Error, OSError):
                    pass
            if announce:
                print(f"Erro ao conectar ao banco de dados: {self._redact(exc)}")

    def _note_error(self, exc: BaseException) -> None:
        self.last_errno = getattr(exc, "errno", None)

    def _attempt(self, operation, *, retry_lock: bool, cleanup, failed):
        """Roda ``operation``. 1205/1213 não viram None nem False.

        Fora da transação há uma nova tentativa (duas esperas de 5s, ~10s).
        Dentro dela o save da aresta ou da caminhada é quem repete: repetir
        o comando aqui também dobraria o prazo.
        """
        retried = False
        while True:
            try:
                result = operation()
            except Error as exc:
                self._note_error(exc)
                cleanup()
                if getattr(exc, "errno", None) in _LOCK_ERRNOS:
                    if retry_lock and not retried:
                        retried = True
                        continue
                    raise DatabaseBusy() from exc
                return failed(exc)
            self.last_errno = None
            return result

    def _rollback_autocommit(self) -> None:
        if self.connection:
            self.connection.rollback()
        self._explicit = False

    def _drain_unread(self) -> None:
        """Consome o resultado pendente antes de qualquer outro comando."""
        connection = self.connection
        if connection is None:
            return
        cursor = self.cursor
        pending = bool(getattr(connection, "unread_result", False))
        if cursor is not None and bool(getattr(cursor, "unread_result", False)):
            pending = True
        if not pending or cursor is None:
            return
        try:
            cursor.fetchall()
        except Error:
            try:
                cursor.close()
            except Error:
                pass
            self.cursor = None
            try:
                self.cursor = connection.cursor(dictionary=True, buffered=True)
            except Error:
                self.cursor = None

    def _ready(self) -> bool:
        return self.connection is not None and self.cursor is not None

    def execute_search(self, sql, params=None):
        if not self._ready():
            print("Erro ao executar consulta: sem conexão")
            return None

        def operation():
            self.cursor.execute(sql, params)
            return self.cursor.fetchall()

        def failed(exc):
            print(f"Erro ao executar consulta: {self._redact(exc)}")
            return None

        return self._attempt(
            operation,
            retry_lock=not self._explicit,
            cleanup=lambda: None,
            failed=failed,
        )

    def _outside_transaction(self) -> bool:
        """``execute_query`` e os irmãos dão commit. Dentro da transação, não."""
        if not self._explicit:
            return True
        print("Comando com commit no meio da transação. Use execute_within.")
        return False

    def execute_query(self, sql, params=None):
        """Um comando e commit. Não usar dentro de ``begin_transaction``."""
        if not self._outside_transaction():
            return False
        if not self._ready():
            print("Erro ao executar comando: sem conexão")
            return False

        def operation():
            self.cursor.execute(sql, params)
            self.connection.commit()
            self._explicit = False
            return True

        def failed(exc):
            if isinstance(exc, IntegrityError):
                raise exc
            print(f"Erro ao executar comando: {self._redact(exc)}")
            return False

        return self._attempt(
            operation,
            retry_lock=True,
            cleanup=self._rollback_autocommit,
            failed=failed,
        )

    def execute_update(self, sql, params=None):
        """UPDATE/DELETE. Devolve linhas casadas (FOUND_ROWS), ou None.

        None é erro de SQL. 0 é nenhuma linha. 1205/1213 sobem
        ``DatabaseBusy`` depois de uma nova tentativa.
        """
        if not self._outside_transaction():
            return None
        if not self._ready():
            print("Erro ao executar update: sem conexão")
            return None

        def operation():
            self.cursor.execute(sql, params)
            affected = int(self.cursor.rowcount)
            self.connection.commit()
            self._explicit = False
            return affected

        def failed(exc):
            print(f"Erro ao executar update: {self._redact(exc)}")
            return None

        return self._attempt(
            operation,
            retry_lock=True,
            cleanup=self._rollback_autocommit,
            failed=failed,
        )

    def execute_insert(self, sql, params=None):
        """INSERT (ou upsert com LAST_INSERT_ID). Devolve o id, ou None se falhar."""
        if not self._outside_transaction():
            return None
        if not self._ready():
            print("Erro ao executar insert: sem conexão")
            return None

        def operation():
            self.cursor.execute(sql, params)
            self.connection.commit()
            self._explicit = False
            return self.cursor.lastrowid

        def failed(exc):
            print(f"Erro ao executar insert: {self._redact(exc)}")
            return None

        return self._attempt(
            operation,
            retry_lock=True,
            cleanup=self._rollback_autocommit,
            failed=failed,
        )

    def execute_many(self, sql, seq):
        if not self._outside_transaction():
            return False
        if not self._ready():
            print("Erro ao executar lote: sem conexão")
            return False
        rows = list(seq)

        def operation():
            self.cursor.executemany(sql, rows)
            self.connection.commit()
            self._explicit = False
            return True

        def failed(exc):
            print(f"Erro ao executar lote: {self._redact(exc)}")
            return False

        return self._attempt(
            operation,
            retry_lock=True,
            cleanup=self._rollback_autocommit,
            failed=failed,
        )

    def begin_transaction(self):
        """Abre uma transação. Os métodos ``*_within`` não dão commit.

        Com autocommit ligado o SELECT não abre transação. Se ainda houver
        uma (retry, ou sessão antiga), ela é revertida: ``start_transaction``
        recusa com "Transaction already in progress". Resultado ainda não
        lido é consumido antes: senão o conector espera um pacote que não vem.
        Lock aqui sobe na hora: quem abre a transação já repete uma vez.
        """
        if not self.connection:
            return False

        def operation():
            self._drain_unread()
            if getattr(self.connection, "in_transaction", False):
                self.connection.rollback()
            self.connection.start_transaction()
            self._explicit = True
            return True

        def failed(exc):
            print(f"Erro ao abrir transação: {self._redact(exc)}")
            return False

        return self._attempt(
            operation,
            retry_lock=False,
            cleanup=lambda: setattr(self, "_explicit", False),
            failed=failed,
        )

    def commit_transaction(self):
        def operation():
            self.connection.commit()
            self._explicit = False
            return True

        def failed(exc):
            print(f"Erro ao confirmar transação: {self._redact(exc)}")
            return False

        return self._attempt(
            operation,
            retry_lock=False,
            cleanup=lambda: setattr(self, "_explicit", False),
            failed=failed,
        )

    def rollback_transaction(self):
        try:
            if self.connection:
                self._drain_unread()
                self.connection.rollback()
            self._explicit = False
            return True
        except Error as exc:
            self._explicit = False
            print(f"Erro ao reverter transação: {self._redact(exc)}")
            return False

    def execute_within(self, sql, params=None):
        if not self._ready():
            return False

        def operation():
            self.cursor.execute(sql, params)
            return True

        def failed(exc):
            print(f"Erro ao executar comando na transação: {self._redact(exc)}")
            return False

        return self._attempt(operation, retry_lock=False, cleanup=lambda: None, failed=failed)

    def insert_within(self, sql, params=None):
        if not self._ready():
            return None

        def operation():
            self.cursor.execute(sql, params)
            return self.cursor.lastrowid

        def failed(exc):
            print(f"Erro ao executar insert na transação: {self._redact(exc)}")
            return None

        return self._attempt(operation, retry_lock=False, cleanup=lambda: None, failed=failed)

    def executemany_within(self, sql, seq):
        if not self._ready():
            return False
        rows = list(seq)

        def operation():
            self.cursor.executemany(sql, rows)
            return True

        def failed(exc):
            print(f"Erro ao executar lote na transação: {self._redact(exc)}")
            return False

        return self._attempt(operation, retry_lock=False, cleanup=lambda: None, failed=failed)

    def _redact(self, exc: BaseException) -> str:
        """Troca senha e userinfo, e só então corta.

        O corte vem depois: senha que atravessa os 4096 não deixa pedaço.
        Senha curta no meio de ``user:pass@`` ainda some na máscara da URL.
        """
        text = str(exc)
        for secret in _known_secrets(getattr(self, "password", "")):
            text = text.replace(secret, "***")
        return _mask_url_userinfo(text)[:_REDACT_MAX_CHARS]

    def ensure_live(self) -> bool:
        """Ping da sessão ociosa. Se caiu, abre outra no mesmo objeto."""
        if self._ping():
            return self._cursor_ready()
        self.disconnect(announce=False)
        self.connect(announce=False)
        return self.connection is not None and self.cursor is not None

    def _ping(self) -> bool:
        connection = self.connection
        if connection is None:
            return False
        ping = getattr(connection, "ping", None)
        if not callable(ping):
            # Dobro de teste, sem COM_PING. Sessão real do conector tem ping.
            return self.cursor is not None
        try:
            self._drain_unread()
            ping(reconnect=False, attempts=1, delay=0)
            return True
        except (Error, OSError):
            return False

    def _cursor_ready(self) -> bool:
        if self.cursor is not None:
            return True
        connection = self.connection
        if connection is None:
            return False
        try:
            self.cursor = connection.cursor(dictionary=True, buffered=True)
            return self.cursor is not None
        except (Error, OSError):
            return False

    def reset_for_pool(self) -> bool:
        """Deixa a sessão limpa para outro request. O ping é no checkout."""
        if not self._ready():
            return False
        try:
            self._drain_unread()
            if self.cursor is not None:
                self.cursor.close()
            self.cursor = None
            if getattr(self.connection, "in_transaction", False):
                self.connection.rollback()
            self._explicit = False
            self.cursor = self.connection.cursor(dictionary=True, buffered=True)
            return self.cursor is not None
        except (Error, OSError):
            self._explicit = False
            return False

    def disconnect(self, announce: bool = True):
        """Fecha sem pingar. O ping com resultado pendente não retorna."""
        cursor = self.cursor
        connection = self.connection
        self.cursor = None
        self.connection = None
        self._explicit = False
        if cursor is not None:
            try:
                cursor.close()
            except (Error, OSError):
                pass
        if connection is None:
            return
        try:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
        except (Error, OSError):
            pass
        shutdown = getattr(connection, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except (Error, OSError):
                pass
        try:
            connection.close()
        except (Error, OSError):
            pass
        if announce:
            print("Conexão encerrada.")


def _release_slot() -> None:
    global _open
    with _pool_lock:
        if _open > 0:
            _open -= 1
        _pool_ready.notify()


def _reusable(conn: ConexaoBD) -> bool:
    """Ping e, se preciso, uma reconexão. Objeto de teste sem o método só checa o cursor."""
    ensure = getattr(conn, "ensure_live", None)
    if not callable(ensure):
        return conn.connection is not None and conn.cursor is not None
    return bool(ensure())


def checkout_connection(template: ConexaoBD) -> ConexaoBD:
    """Pega uma sessão ociosa ou abre outra, até ``POOL_MAX_TOTAL``.

    A ociosa faz ping fora do lock. Se caiu, reconecta uma vez; se ainda
    falhar, o lugar é liberado e abre outra, até o teto. Com o pool cheio,
    espera até ``POOL_WAIT_S``. ``DatabaseBusy`` só depois dessa espera.
    """
    global _open
    deadline = time.monotonic() + POOL_WAIT_S
    while True:
        with _pool_lock:
            if _idle:
                cached = _idle.pop()
                opening = False
            elif _open < POOL_MAX_TOTAL:
                _open += 1
                cached = None
                opening = True
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DatabaseBusy("Não há conexão livre no pool.")
                _pool_ready.wait(timeout=remaining)
                continue
        if not opening:
            if _reusable(cached):
                return cached
            cached.disconnect(announce=False)
            _release_slot()
            continue
        opened = ConexaoBD(
            template.host,
            template.database,
            template.user,
            template.password,
            template.port,
        )
        try:
            opened.connect(announce=False)
        except Exception:
            _release_slot()
            raise
        if opened.connection is None:
            _release_slot()
        return opened


def checkin_connection(conn: ConexaoBD | None) -> None:
    """Devolve a sessão ao pool, ou fecha se ela não ficou limpa."""
    if conn is None or conn.connection is None:
        return
    if not conn.reset_for_pool():
        conn.disconnect(announce=False)
        _release_slot()
        return
    with _pool_lock:
        if len(_idle) < POOL_MAX_IDLE:
            _idle.append(conn)
            _pool_ready.notify()
            return
    conn.disconnect(announce=False)
    _release_slot()


@contextmanager
def request_session(template: ConexaoBD):
    """Sessão só para este bloco de SQL. Reusa a que a task já abriu.

    Connect que falha levanta ``DatabaseUnavailable``. Não devolve a
    conexão modelo do processo.
    """
    current = request_connection.get()
    if current is not None:
        yield current
        return
    local = checkout_connection(template)
    if local.connection is None:
        raise DatabaseUnavailable("Não foi possível conectar ao MySQL.")
    token = request_connection.set(local)
    try:
        yield local
    finally:
        request_connection.reset(token)
        checkin_connection(local)


def drain_pool() -> None:
    """Fecha o que estiver ocioso. Usado no shutdown e entre testes."""
    global _open
    with _pool_lock:
        idle = list(_idle)
        _idle.clear()
        _open = max(0, _open - len(idle))
    for conn in idle:
        try:
            conn.disconnect(announce=False)
        except (Error, OSError):
            pass
