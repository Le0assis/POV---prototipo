from datasets.ManagerDatabase import ConexaoBD  # Ajuste o import conforme o nome exato do seu arquivo

def criar_tabelas_sistema(db: ConexaoBD):
    print("\n[SETUP] Iniciando a criação das tabelas no banco de dados...")

    # 1. TABELA DE CHECKPOINTS (Os Nós)
    # Guarda o nome semântico de cada ponto de interesse mapeado.
    sql_checkpoints = """
    CREATE TABLE IF NOT EXISTS checkpoints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE
    ) ENGINE=InnoDB;
    """

    # 2. TABELA DE EDGES (As Conexões / Corredores)
    # Guarda a relação de vizinhança entre os checkpoints, distância e orientação.
    sql_edges = """
    CREATE TABLE IF NOT EXISTS edges (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source_node VARCHAR(100) NOT NULL,
        target_node VARCHAR(100) NOT NULL,
        distance_m FLOAT NOT NULL,
        heading_rad FLOAT NOT NULL,
        FOREIGN KEY (source_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        FOREIGN KEY (target_node) REFERENCES checkpoints(name) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """

    # 3. TABELA DE SENSOR LOGS (Histórico de Sensores Brutos)
    # Útil se você quiser gravar a caminhada real para simulações futuras.
    sql_sensor_logs = """
    CREATE TABLE IF NOT EXISTS sensor_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        timestamp DOUBLE NOT NULL,
        acc_x FLOAT NOT NULL,
        acc_y FLOAT NOT NULL,
        acc_z FLOAT NOT NULL,
        gyro_x FLOAT NOT NULL,
        gyro_y FLOAT NOT NULL,
        gyro_z FLOAT NOT NULL,
        mag_x FLOAT NOT NULL,
        mag_y FLOAT NOT NULL,
        mag_z FLOAT NOT NULL
    ) ENGINE=InnoDB;
    """

    # Execução dos comandos utilizando a sua infraestrutura
    print("Criando tabela 'checkpoints'...")
    db.executar_comando(sql_checkpoints)

    print("Criando tabela 'edges'...")
    db.executar_comando(sql_edges)

    print("Criando tabela 'sensor_logs'...")
    db.executar_comando(sql_sensor_logs)
    
    print("[SETUP] Processo de criação de tabelas concluído.\n")

if __name__ == "__main__":
    # Script para você rodar de forma isolada uma única vez e preparar o XAMPP
    # Certifique-se de que o banco 'POV' já foi criado no phpMyAdmin!
    conexao = ConexaoBD(host="localhost", database="POV", user="root", password="")
    conexao.conectar()
    
    if conexao.connection:
        criar_tabelas_sistema(conexao)
        conexao.desconectar()