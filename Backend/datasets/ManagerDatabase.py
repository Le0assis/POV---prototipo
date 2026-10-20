import mysql.connector
from mysql.connector import Error

class ConexaoBD:
    def __init__(self, host, database, user, password):
        # REMOVIDAS AS VÍRGULAS DO FINAL: Agora guardam strings limpas
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.connection = None
        self.cursor = None

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password
            )
            if self.connection.is_connected():
                # dictionary=True faz o fetchall retornar uma lista de dicionários 
                # em vez de tuplas.
                self.cursor = self.connection.cursor(dictionary=True)
                print("Conexão com o banco de dados estabelecida com sucesso!")
        except Error as e:
            print(f"Erro ao conectar ao banco de dados: {e}")

    def execute_search(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            resultado = self.cursor.fetchall()
            return resultado
        except Error as e:
            print(f"Erro ao executar consulta: {e}")
            return None

    def execute_query(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            self.connection.commit()
            print("Comando executado com sucesso!")
            return True
        except Error as e:
            if self.connection:
                self.connection.rollback()
            print(f"Erro ao executar comando: {e}")
            return False

    def execute_insert(self, sql, params=None):
        """INSERT (ou upsert com LAST_INSERT_ID). Devolve o id, ou None se falhar."""
        try:
            self.cursor.execute(sql, params)
            self.connection.commit()
            return self.cursor.lastrowid
        except Error as e:
            if self.connection:
                self.connection.rollback()
            print(f"Erro ao executar insert: {e}")
            return None

    def execute_many(self, sql, seq):
        try:
            self.cursor.executemany(sql, list(seq))
            self.connection.commit()
            return True
        except Error as e:
            if self.connection:
                self.connection.rollback()
            print(f"Erro ao executar lote: {e}")
            return False

    def begin_transaction(self):
        """Abre uma transação. Os métodos ``*_within`` não dão commit."""
        try:
            if not self.connection:
                return False
            self.connection.start_transaction()
            return True
        except Error as e:
            print(f"Erro ao abrir transação: {e}")
            return False

    def commit_transaction(self):
        try:
            self.connection.commit()
            return True
        except Error as e:
            print(f"Erro ao confirmar transação: {e}")
            return False

    def rollback_transaction(self):
        try:
            if self.connection:
                self.connection.rollback()
            return True
        except Error as e:
            print(f"Erro ao reverter transação: {e}")
            return False

    def execute_within(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            return True
        except Error as e:
            print(f"Erro ao executar comando na transação: {e}")
            return False

    def insert_within(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            return self.cursor.lastrowid
        except Error as e:
            print(f"Erro ao executar insert na transação: {e}")
            return None

    def executemany_within(self, sql, seq):
        try:
            self.cursor.executemany(sql, list(seq))
            return True
        except Error as e:
            print(f"Erro ao executar lote na transação: {e}")
            return False

    def disconnect(self):
            if self.connection and self.connection.is_connected():
                self.cursor.close()
                self.connection.close()
                print("Conexão encerrada.")


#db = ConexaoBD(host="localhost", database="POV", user="root", password="")
#db.conectar()