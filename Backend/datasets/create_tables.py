from datasets.ManagerDatabase import ConexaoBD  # Ajuste o import conforme o nome exato do seu arquivo

def criar_tabelas_sistema(db: ConexaoBD):
    print("\n[SETUP] Iniciando a criação das tabelas no banco de dados...")

    # 1. TABELA DE CHECKPOINTS (Os Nós)
    # Guarda o nome semântico de cada ponto de interesse mapeado.
    sql_checkpoints = """
    CREATE TABLE IF NOT EXISTS checkpoints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        pos_x_px DOUBLE NULL,
        pos_y_px DOUBLE NULL,
        category_id INT NULL,
        building_id INT NOT NULL DEFAULT 1,
        slug VARCHAR(64) NULL,
        INDEX idx_checkpoints_category_id (category_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    # 2. TABELA DE EDGES (As Conexões / Corredores)
    # Guarda a relação de vizinhança entre os checkpoints, distância e orientação.
    # Uma linha por sentido. active_trace_id ganha a FK na migração 002,
    # depois que walk_traces existe. origin manual não é sobrescrito por gravação.
    sql_edges = """
    CREATE TABLE IF NOT EXISTS edges (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source_node VARCHAR(100) NOT NULL,
        target_node VARCHAR(100) NOT NULL,
        distance_m FLOAT NOT NULL,
        heading_rad FLOAT NOT NULL,
        origin ENUM('manual','recorded') NOT NULL DEFAULT 'manual',
        samples_count INT NOT NULL DEFAULT 0,
        active_trace_id INT NULL,
        updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_edges_direction (source_node, target_node),
        FOREIGN KEY (source_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        FOREIGN KEY (target_node) REFERENCES checkpoints(name) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    # 3. TABELA DE SENSOR LOGS (Histórico de Sensores Brutos)
    # Útil se você quiser gravar a caminhada real para simulações futuras.
    # InnoDB explícito: walk_traces.sensors_log_id referencia esta tabela.
    sql_sensor_logs = """
      CREATE TABLE IF NOT EXISTS sensors_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source VARCHAR(50),
        target VARCHAR(50),
        steps_detected INT DEFAULT 0,
        distance_m FLOAT DEFAULT 0.0,
        is_valid BOOLEAN DEFAULT FALSE,
        message VARCHAR(255),
        raw_csv LONGTEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    # Execução dos comandos utilizando a sua infraestrutura
    print("Criando tabela 'checkpoints'...")
    db.execute_query(sql_checkpoints)

    print("Criando tabela 'edges'...")
    db.execute_query(sql_edges)

    print("Criando tabela 'sensor_logs'...")
    db.execute_query(sql_sensor_logs)
    
    print("[SETUP] Processo de criação de tabelas concluído.\n")

    # 4. TABELA DE ROTAS SALVAS
    # Guarda rotas calculadas com segmentos completos para navegação offline/teste
    sql_saved_routes = """
    CREATE TABLE IF NOT EXISTS saved_routes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        start_node VARCHAR(100) NOT NULL,
        end_node VARCHAR(100) NOT NULL,
        total_distance_m FLOAT NOT NULL,
        total_steps_estimated INT NOT NULL,
        segments_json JSON NOT NULL,
        path_sequence_json JSON NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (start_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        FOREIGN KEY (end_node) REFERENCES checkpoints(name) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """
    print("Criando tabela 'saved_routes'...")
    db.execute_query(sql_saved_routes)

    print("Aplicando migração 002 (dedupe de edges, trajetória, planta)...")
    aplicar_migracao_002(db)
    print("Aplicando migração 003 (prédio, categoria, slug)...")
    aplicar_migracao_003(db)
    print("[SETUP] Processo de criação de tabelas concluído.\n")


def aplicar_migracao_002(db: ConexaoBD) -> None:
    """Carrega datasets/migrations/002_walk_traces.py (o nome começa com dígito)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent / "migrations" / "002_walk_traces.py"
    spec = importlib.util.spec_from_file_location("migration_002_walk_traces", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Migração não encontrada: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    removed = module.apply(db)
    print(f"[M02] Linhas de edges removidas nesta execução: {len(removed)}")


def aplicar_migracao_003(db: ConexaoBD) -> None:
    """Carrega datasets/migrations/003_checkpoint_slug.py (o nome começa com dígito)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent / "migrations" / "003_checkpoint_slug.py"
    spec = importlib.util.spec_from_file_location("migration_003_checkpoint_slug", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Migração não encontrada: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply(db)

if __name__ == "__main__":
    # Script para você rodar de forma isolada uma única vez e preparar o XAMPP
    # Certifique-se de que o banco 'POV' já foi criado no phpMyAdmin!
    conexao = ConexaoBD(host="localhost", database="POV", user="root", password="")
    conexao.connect()
    
    if conexao.connection:
        criar_tabelas_sistema(conexao)
        conexao.disconnect()