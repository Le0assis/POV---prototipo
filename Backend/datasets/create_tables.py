import re
import sys

from datasets.ManagerDatabase import ConexaoBD  # Ajuste o import conforme o nome exato do seu arquivo

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")

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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
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
        dup_rank INT NOT NULL DEFAULT 0,
        active_trace_id INT NULL,
        updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_edges_direction (source_node, target_node),
        FOREIGN KEY (source_node) REFERENCES checkpoints(name) ON DELETE CASCADE,
        FOREIGN KEY (target_node) REFERENCES checkpoints(name) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
    """

    # Execução dos comandos utilizando a sua infraestrutura
    print("Criando tabela 'checkpoints'...")
    _run_ddl(db, sql_checkpoints, "checkpoints")

    print("Criando tabela 'edges'...")
    _run_ddl(db, _match_checkpoint_strings(db, sql_edges), "edges")

    print("Criando tabela 'sensor_logs'...")
    _run_ddl(db, sql_sensor_logs, "sensors_log")
    
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
    """
    print("Criando tabela 'saved_routes'...")
    _run_ddl(db, _match_checkpoint_strings(db, sql_saved_routes), "saved_routes")

    print("Aplicando migração 002 (preserva cópias de edges, trajetória, planta)...")
    aplicar_migracao_002(db)
    print("Aplicando migração 003 (prédio, categoria, slug)...")
    aplicar_migracao_003(db)
    print("Aplicando migração 004 (índices do salvamento)...")
    aplicar_migracao_004(db)
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
    module.apply(db)


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


def aplicar_migracao_004(db: ConexaoBD) -> None:
    """Carrega datasets/migrations/004_save_indexes.py (o nome começa com dígito)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent / "migrations" / "004_save_indexes.py"
    spec = importlib.util.spec_from_file_location("migration_004_save_indexes", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Migração não encontrada: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply(db)

def _run_ddl(db: ConexaoBD, sql: str, label: str) -> None:
    if db.execute_query(sql) is not True:
        raise RuntimeError(
            f"Não foi possível criar {label}. Nenhum dado existente foi apagado."
        )


def _match_checkpoint_strings(db: ConexaoBD, template: str) -> str:
    """FK de nome usa o mesmo charset de checkpoints.name. Tabela nova não herda latin1."""
    rows = db.execute_search(
        "SELECT COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME "
        "FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'checkpoints' "
        "AND column_name = 'name'"
    )
    if rows is None:
        raise RuntimeError("Não li o charset de checkpoints.name. Nada foi apagado.")
    if not rows:
        return template
    meta = {str(key).upper(): value for key, value in rows[0].items()}
    column_type = str(meta["COLUMN_TYPE"]).strip()
    charset = str(meta["CHARACTER_SET_NAME"]).strip()
    collation = str(meta["COLLATION_NAME"]).strip()
    if not _IDENT.match(charset) or not _IDENT.match(collation):
        raise RuntimeError(f"charset/collation inesperados em checkpoints.name: {charset} {collation}")
    if not re.match(r"^varchar\(\d+\)$", column_type, re.IGNORECASE):
        raise RuntimeError(f"checkpoints.name não é VARCHAR: {column_type}")
    node = f"{column_type} CHARACTER SET {charset} COLLATE {collation}"
    return template.replace("VARCHAR(100) NOT NULL", f"{node} NOT NULL")


def conexao_from_settings() -> ConexaoBD:
    """Lê o ``.env`` e monta a conexão com DB_HOST/PORT/NAME/USER/PASSWORD.

    Não consulta o default da API. Sem essas variáveis, para com erro
    em vez de entrar como root.
    """
    from api.envfile import load_env_file
    from api.settings import assert_production_database
    from datasets.bootstrap_db import app_db_config

    load_env_file()
    assert_production_database()
    cfg = app_db_config()
    return ConexaoBD(
        host=str(cfg["host"]),
        database=str(cfg["name"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        port=int(cfg["port"]),
    )


def main() -> None:
    """Cria o schema. Em produção, senha curta sai com código 1 e sem traceback.

    Se a conta pov não abre sessão, sai com código 1. A mensagem não leva a senha.
    CREATE DATABASE/USER/GRANT usam DB_ADMIN_*. Tabelas usam DB_USER (pov).
    Não apaga um schema que já exista com outro nome.
    """
    from api.envfile import load_env_file
    from api.settings import boot_or_exit
    from datasets.bootstrap_db import ensure_app_database

    load_env_file()
    conexao = boot_or_exit(conexao_from_settings)
    ensure_app_database(
        str(conexao.database),
        str(conexao.host),
        int(conexao.port),
        str(conexao.user),
        str(conexao.password),
    )
    conexao.connect()
    if not conexao.connection:
        print(
            "Não conectou como pov. Confira DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    criar_tabelas_sistema(conexao)
    conexao.disconnect()


if __name__ == "__main__":
    main()