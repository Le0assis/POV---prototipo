"""Conexão MySQL (XAMPP) por requisição, com prazo e devolução ao pool.

O conector usa a extensão C por padrão e trata ``connection_timeout`` nulo
como 0, isto é, espera sem limite. No Windows, ``host=localhost`` ainda pode
ir para named pipe. Um ``connect()`` ou um ``ping`` nessa situação, feito
dentro do middleware async, trava o event loop: o salvamento não anda, e
arquivo estático nenhum precisa de banco.

``is_connected()`` manda PING. Se ainda houver resultado não lido, o servidor
não responde outro comando e o cliente espera para sempre. Por isso fechar
ou reutilizar a sessão nunca começa por um ping: primeiro esvazia o cursor,
desfaz a transação implícita (autocommit desligado) e só então devolve ou
derruba o socket.
"""

from __future__ import annotations

from contextvars import ContextVar
import threading

import mysql.connector
from mysql.connector import Error, IntegrityError

# Handshake. 0 no conector C significa "sem prazo".
CONNECT_TIMEOUT_S = 5
# Comando SQL. O conector zera o timeout do socket depois do login.
COMMAND_TIMEOUT_S = 30
POOL_MAX_IDLE = 8

# Conexão da requisição atual. Fora de uma requisição o valor é None:
# o processo não guarda uma sessão aberta só para pingar a cada GET.
request_connection: ContextVar["ConexaoBD | None"] = ContextVar(
    "request_connection",
    default=None,
)

_pool_lock = threading.Lock()
_idle: list["ConexaoBD"] = []


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

    def connect(self, announce: bool = True, timeout: float | None = None):
        """Abre a sessão. ``timeout`` None usa ``CONNECT_TIMEOUT_S``.

        Falha de rede, senha ou handshake devolve ``connection is None``
        em vez de bloquear. ``use_pure`` evita a extensão C, cujo timeout 0
        e o named pipe de localhost não têm prazo.
        """
        self.connection = None
        self.cursor = None
        self._explicit = False
        wait = CONNECT_TIMEOUT_S if timeout is None else timeout
        try:
            self.connection = mysql.connector.connect(
                host=_tcp_host(self.host),
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connection_timeout=wait,
                autocommit=False,
                use_pure=True,
            )
            sock = getattr(self.connection, "_socket", None)
            if sock is not None:
                sock.set_connection_timeout(COMMAND_TIMEOUT_S)
            self.cursor = self.connection.cursor(dictionary=True, buffered=True)
            if announce:
                print("Conexão com o banco de dados estabelecida com sucesso!")
        except (Error, OSError) as exc:
            self.connection = None
            self.cursor = None
            if announce:
                print(f"Erro ao conectar ao banco de dados: {exc}")

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
        try:
            self.cursor.execute(sql, params)
            return self.cursor.fetchall()
        except Error as exc:
            print(f"Erro ao executar consulta: {exc}")
            return None

    def execute_query(self, sql, params=None):
        if not self._ready():
            print("Erro ao executar comando: sem conexão")
            return False
        try:
            self.cursor.execute(sql, params)
            self.connection.commit()
            self._explicit = False
            return True
        except IntegrityError:
            if self.connection:
                self.connection.rollback()
            self._explicit = False
            raise
        except Error as exc:
            if self.connection:
                self.connection.rollback()
            self._explicit = False
            print(f"Erro ao executar comando: {exc}")
            return False

    def execute_insert(self, sql, params=None):
        """INSERT (ou upsert com LAST_INSERT_ID). Devolve o id, ou None se falhar."""
        if not self._ready():
            print("Erro ao executar insert: sem conexão")
            return None
        try:
            self.cursor.execute(sql, params)
            self.connection.commit()
            self._explicit = False
            return self.cursor.lastrowid
        except Error as exc:
            if self.connection:
                self.connection.rollback()
            self._explicit = False
            print(f"Erro ao executar insert: {exc}")
            return None

    def execute_many(self, sql, seq):
        if not self._ready():
            print("Erro ao executar lote: sem conexão")
            return False
        try:
            self.cursor.executemany(sql, list(seq))
            self.connection.commit()
            self._explicit = False
            return True
        except Error as exc:
            if self.connection:
                self.connection.rollback()
            self._explicit = False
            print(f"Erro ao executar lote: {exc}")
            return False

    def begin_transaction(self):
        """Abre uma transação. Os métodos ``*_within`` não dão commit.

        Um SELECT anterior (autocommit desligado) deixa transação implícita.
        Resultado ainda não lido é consumido antes do ROLLBACK e do
        ``START TRANSACTION``: senão o conector espera um pacote que não vem.
        """
        try:
            if not self.connection:
                return False
            self._drain_unread()
            if getattr(self.connection, "in_transaction", False):
                self.connection.rollback()
            self.connection.start_transaction()
            self._explicit = True
            return True
        except Error as exc:
            self._explicit = False
            print(f"Erro ao abrir transação: {exc}")
            return False

    def commit_transaction(self):
        try:
            self.connection.commit()
            self._explicit = False
            return True
        except Error as exc:
            self._explicit = False
            print(f"Erro ao confirmar transação: {exc}")
            return False

    def rollback_transaction(self):
        try:
            if self.connection:
                self._drain_unread()
                self.connection.rollback()
            self._explicit = False
            return True
        except Error as exc:
            self._explicit = False
            print(f"Erro ao reverter transação: {exc}")
            return False

    def execute_within(self, sql, params=None):
        if not self._ready():
            return False
        try:
            self.cursor.execute(sql, params)
            return True
        except Error as exc:
            print(f"Erro ao executar comando na transação: {exc}")
            return False

    def insert_within(self, sql, params=None):
        if not self._ready():
            return None
        try:
            self.cursor.execute(sql, params)
            return self.cursor.lastrowid
        except Error as exc:
            print(f"Erro ao executar insert na transação: {exc}")
            return None

    def executemany_within(self, sql, seq):
        if not self._ready():
            return False
        try:
            self.cursor.executemany(sql, list(seq))
            return True
        except Error as exc:
            print(f"Erro ao executar lote na transação: {exc}")
            return False

    def reset_for_pool(self) -> bool:
        """Deixa a sessão limpa para outro request. Não manda PING antes."""
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


def checkout_connection(template: ConexaoBD) -> ConexaoBD:
    """Pega uma sessão ociosa ou abre outra. Não bloqueia se o pool acabar."""
    with _pool_lock:
        while _idle:
            cached = _idle.pop()
            if cached.connection is not None and cached.cursor is not None:
                return cached
    opened = ConexaoBD(
        template.host,
        template.database,
        template.user,
        template.password,
        template.port,
    )
    opened.connect(announce=False)
    return opened


def checkin_connection(conn: ConexaoBD | None) -> None:
    """Devolve a sessão ao pool, ou fecha se ela não ficou limpa."""
    if conn is None or conn.connection is None:
        return
    if not conn.reset_for_pool():
        conn.disconnect(announce=False)
        return
    with _pool_lock:
        if len(_idle) < POOL_MAX_IDLE:
            _idle.append(conn)
            return
    conn.disconnect(announce=False)


def drain_pool() -> None:
    """Fecha o que estiver ocioso. Usado no shutdown e entre testes."""
    with _pool_lock:
        idle = list(_idle)
        _idle.clear()
    for conn in idle:
        try:
            conn.disconnect(announce=False)
        except (Error, OSError):
            pass
