from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager

# ======================================
# CONEXÃO
# ======================================

db = ConexaoBD(
    host="localhost",
    database="POV",
    user="root",
    password=""
)

db.conectar()

if not db.connection:
    raise Exception("Erro ao conectar ao banco.")

manager = MapDatabaseManager(db)

# ======================================
# CHECKPOINTS
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

print("Inserindo checkpoints...")

for checkpoint in checkpoints:
    manager.save_checkpoint(checkpoint)

# ======================================
# EDGES
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

print("Inserindo conexões...")

for source, target, distance, heading in edges:
    manager.save_edge(
        source,
        target,
        distance,
        heading
    )

print("Mapa criado com sucesso!")

db.desconectar()