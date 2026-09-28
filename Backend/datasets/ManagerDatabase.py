import mysql.connector
from mysql.connector import Error

class ConexaoBD:
    """
    Classe responsável por gerenciar a conexão física com o MySQL
    e executar buscas e comandos com suporte a reconexão automática.
    """
    def __init__(self, host="localhost", database="POV", user="root", password=""):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.connection = None
        self.cursor = None

    # ==========================================
    # 1. GERENCIAMENTO DE CONEXÃO
    # ==========================================
    def connect(self):
        """Abre a conexão com o banco e inicializa o cursor em formato dicionário."""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password
            )
            if self.connection.is_connected():
                # dictionary=True retorna cada linha como um dicionário Python (ex: {'id': 1, 'session_id': 'abc'})
                self.cursor = self.connection.cursor(dictionary=True)
                print("[BANCO] Conexão com o MySQL estabelecida com sucesso!")
                return True
        except Error as e:
            print(f"[BANCO ERRO] Falha ao conectar ao MySQL: {e}")
            self.connection = None
            self.cursor = None
            return False

    def _ensure_connection(self):
        """Garante que a conexão e o cursor estejam ativos antes de rodar SQL."""
        if not self.connection or not self.connection.is_connected() or not self.cursor:
            print("[BANCO AVISO] Conexão perdida. Tentando reconectar...")
            return self.connect()
        return True

    # ==========================================
    # 2. EXECUÇÃO DE CONSULTAS (SELECT)
    # ==========================================
    def execute_search(self, sql, params=None):
        """
        Executa consultas SELECT.
        :param sql: String SQL com placeholders %s
        :param params: Tupla com os valores (incluindo session_id se houver no SQL)
        :return: Lista de dicionários ou None se falhar
        """
        if not self._ensure_connection():
            return None

        try:
            self.cursor.execute(sql, params or ())
            return self.cursor.fetchall()
        except Error as e:
            print(f"[BANCO ERRO] Erro ao executar consulta SQL: {e}")
            return None

    # ==========================================
    # 3. EXECUÇÃO DE COMANDOS (INSERT, UPDATE, DELETE)
    # ==========================================
    def execute_query(self, sql, params=None):
        """
        Executa comandos de escrita no banco de dados com Commit / Rollback.
        :param sql: String SQL com placeholders %s
        :param params: Tupla com os valores a serem inseridos
        :return: True se teve sucesso, False se falhou
        """
        if not self._ensure_connection():
            return False

        try:
            self.cursor.execute(sql, params or ())
            self.connection.commit()
            print("[BANCO] Comando executado e gravado com sucesso!")
            return True
        except Error as e:
            if self.connection:
                self.connection.rollback()
            print(f"[BANCO ERRO] Erro ao executar comando no banco: {e}")
            return False

    # ==========================================
    # 4. ENCERRAMENTO DE SESSÃO DO BANCO
    # ==========================================
    def disconnect(self):
        """Encerra o cursor e a conexão de forma limpa."""
        if self.connection and self.connection.is_connected():
            if self.cursor:
                self.cursor.close()
            self.connection.close()
            print("[BANCO] Conexão encerrada com sucesso.")