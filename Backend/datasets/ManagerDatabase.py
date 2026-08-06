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

    def conectar(self):
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password
            )
            if self.connection.is_connected():
                # dictionary=True faz o fetchall retornar uma lista de dicionários 
                # em vez de tuplas. É muito melhor para ler colunas pelo nome depois!
                self.cursor = self.connection.cursor(dictionary=True)
                print("Conexão com o banco de dados estabelecida com sucesso!")
        except Error as e:
            print(f"Erro ao conectar ao banco de dados: {e}")

    def executar_consulta(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            resultado = self.cursor.fetchall()
            return resultado
        except Error as e:
            print(f"Erro ao executar consulta: {e}")
            return None

    def executar_comando(self, sql, params=None):
        try:
            self.cursor.execute(sql, params)
            # CORRIGIDO: alterado de self.conexao para self.connection
            self.connection.commit()
            print("Comando executado com sucesso!")
            return True
        except Error as e:
            if self.connection:
                self.connection.rollback()
            print(f"Erro ao executar comando: {e}")
            return False

    def desconectar(self):
        # CORRIGIDO: alterado de self.conexao para self.connection
        if self.connection and self.connection.is_connected():
            self.cursor.close()
            self.connection.close()
            print("Conexão encerrada.")


#db = ConexaoBD(host="localhost", database="POV", user="root", password="")
#db.conectar()