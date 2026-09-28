from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager

# Identificador padrão para o mapa base compartilhado por todos os usuários
DEFAULT_SESSION_ID = "default_session"

# ======================================
# CONEXÃO COM O BANCO DE DADOS
# ======================================

db = ConexaoBD(
    host="localhost",
    database="POV",
    user="root",
    password=""
)

db.connect()

if not db.connection:
    raise Exception("Erro ao conectar ao banco de dados.")

manager = MapDatabaseManager(db)

# ======================================
# CHECKPOINTS (LOCAIS)
# ======================================

checkpoints = [
    "Recepcao",
    "Corredor A",
    "Sala 101",
    "Sala 102",
    "Sala 103",
    "Corredor B",
    "Banheiro",
    "Escada"
]

print("Inserindo checkpoints base para todos os usuários...")

for checkpoint in checkpoints:
    # Repassa o ID de sessão padrão e o nome do cômodo
    manager.save_checkpoint(DEFAULT_SESSION_ID, checkpoint)

# ======================================
# ARESTAS / CONEXÕES (CORREDORES)
# distance = metros
# heading = radianos
# ======================================

edges = [
    ("Recepcao", "Corredor A", 4.5, 0.0),
    ("Corredor A", "Sala 101", 2.0, 1.57),
    ("Corredor A", "Sala 102", 5.0, 1.57),
    ("Corredor A", "Corredor B", 8.0, 0.0),
    ("Corredor B", "Sala 103", 3.0, 1.57),
    ("Corredor B", "Banheiro", 2.5, -1.57),
    ("Corredor B", "Escada", 4.0, 0.0),
]

print("Inserindo conexões base para todos os usuários...")

for source, target, distance, heading in edges:
    manager.save_edge(
        DEFAULT_SESSION_ID,
        source,
        target,
        distance,
        heading
    )

print("Mapa base populado com sucesso para a sessão padrão ('default_session')!")

db.disconnect()