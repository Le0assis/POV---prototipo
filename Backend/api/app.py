import numpy as np
from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from map.router import TopologicalRouter
from map.topological_matcher import TopologicalMatcher

# --- IMPORTE SEUS MÓDULOS DE FILTRAGEM E PDR ---
from filters.butterworth import ButterworthLowPassFilter
from filters.madgwick import MadgwickAttitudeEstimator
from pdr.steps import PeakStepDetector


# --- CLASSE AUXILIAR DE COMPATIBILIDADE ---
class StepEventAdapter:
    def __init__(self, step_length_m: float):
        self.step_length_m = step_length_m


# --- INICIALIZAÇÃO DA INFRAESTRUTURA DA API ---
app = FastAPI(
    title="Indoor IPS API Server",
    description="Backend HTTP para mapeamento e localização indoor em tempo real via sensores mobile."
)

origins = [
    "https://pov-unimar.com",
    "https://www.pov-unimar.com",
    "http://localhost",
    "http://127.0.0.1:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

db = ConexaoBD(host="localhost", database="POV", user="root", password="")
db.conectar()

if not db.connection:
    print("[ERRO CRÍTICO] Não foi possível conectar ao banco MySQL. Verifique o XAMPP.")

map_db_manager = MapDatabaseManager(db)
topo_map = TopologicalMap()
router = TopologicalRouter(topo_map)

try:
    map_db_manager.load_map_into_system(topo_map)
    print(f"[SISTEMA] Mapa carregado com sucesso. Nós em memória: {list(topo_map.nodes.keys())}")
except Exception as e:
    print(f"[AVISO] Falha ao carregar o mapa inicial ou banco vazio. Erro: {e}")

starting_node = "Recepcao"
matcher = TopologicalMatcher(topo_map, starting_node=starting_node)
visited_path = [starting_node]


# --- CONFIGURAÇÃO DOS SCHEMAS (PYDANTIC) ---
class CheckpointSchema(BaseModel):
    name: str

class EdgeSchema(BaseModel):
    source: str
    target: str
    distance_m: float
    heading_rad: float

class StepSensorSchema(BaseModel):
    step_length_m: float
    yaw_rad: float

# SCHEMAS PARA O ENVIOS DAS AMOSTRAS BRUTAS (GRAVAÇÃO DO CELULAR)
class RawSampleSchema(BaseModel):
    timestamp: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0

    # Propriedades de compatibilidade com os seus adaptadores
    @property
    def gx(self) -> float: return self.gyro_x
    @property
    def gy(self) -> float: return self.gyro_y
    @property
    def gz(self) -> float: return self.gyro_z
    @property
    def ax(self) -> float: return self.accel_x
    @property
    def ay(self) -> float: return self.accel_y
    @property
    def az(self) -> float: return self.accel_z
    @property
    def mx(self) -> float: return self.mag_x
    @property
    def my(self) -> float: return self.mag_y
    @property
    def mz(self) -> float: return self.mag_z

class ProcessRawEdgeSchema(BaseModel):
    source: str
    target: str
    samples: List[RawSampleSchema]


# --- ROTAS DA API ---

# NOVO ENDPOINT: ZERAR O ESTADO DO MATCHER E SENSORES
@app.post("/api/reset")
def reset_session():
    """Zera o estado do matcher e a lista de nós visitados para nova gravação/localização."""
    global matcher, visited_path
    matcher = TopologicalMatcher(topo_map, starting_node=starting_node)
    visited_path = [starting_node]
    return {"status": "success", "message": "Estado do PDR e sensores resetados."}


# NOVO ENDPOINT: PROCESSA O CHACOALHADO E A GRAVAÇÃO COM GIROSCÓPIO
@app.post("/api/edges/process-raw", status_code=status.HTTP_201_CREATED)
def process_raw_edge(payload: ProcessRawEdgeSchema):
    """Recebe amostras brutas dos sensores, aplica o giroscópio para barrar chacoalhados
    e salva a aresta no banco de dados.
    """
    samples = payload.samples
    if not samples or len(samples) < 20:
        raise HTTPException(status_code=400, detail="Amostras insuficientes (mínimo 20).")

    # 1. Converte e extrai vetores NumPy
    timestamps = np.array([s.timestamp for s in samples], dtype=np.float64)
    ax = np.array([s.accel_x for s in samples])
    ay = np.array([s.accel_y for s in samples])
    az = np.array([s.accel_z for s in samples])
    
    gx = np.array([s.gyro_x for s in samples])
    gy = np.array([s.gyro_y for s in samples])
    gz = np.array([s.gyro_z for s in samples])

    # 2. CALCULA A MAGNITUDE DO GIROSCÓPIO (RAD/S) PARA TRAVAR O CHACOALHADO
    gyro_magnitude = np.sqrt(gx**2 + gy**2 + gz**2)

    # 3. FILTRO BUTTERWORTH NA MAGNITUDE DA ACELERAÇÃO
    raw_acc_magnitude = np.sqrt(ax**2 + ay**2 + az**2)
    bw_filter = ButterworthLowPassFilter(cutoff=3.0, fs=50.0, order=4)
    filtered_magnitude = bw_filter.apply(raw_acc_magnitude)

    # 4. DETECÇÃO DE PASSOS COM A TRAVA DE GIROSCÓPIO ATIVADA
    detector = PeakStepDetector(sample_rate_hz=50.0, weinberg_k=0.48)
    step_events = detector.detect(
        timestamps=timestamps,
        filtered_magnitude=filtered_magnitude,
        gyro_magnitude=gyro_magnitude  # <--- Giroscópio bloqueia sacudidas de mão aqui
    )

    if not step_events:
        return {
            "status": "warning",
            "message": "Nenhum passo humano detectado no trecho (movimento descartado como chacoalhado/repouso).",
            "steps_count": 0,
            "distance_m": 0.0
        }

    # 5. CÁLCULO DA DISTÂNCIA TOTAL (WEINBERG) E YAW MÉDIO (MADGWICK)
    total_distance_m = sum(s.step_length_m for s in step_events)
    
    estimator = MadgwickAttitudeEstimator(gain=0.033)
    quaternions = estimator.update_series(samples)
    mean_yaw_rad = float(np.mean([q.yaw for q in quaternions]))

    # 6. PERSISTÊNCIA NO BANCO MYSQL E MEMÓRIA DO GRAFO
    map_db_manager.save_edge(payload.source, payload.target, total_distance_m, mean_yaw_rad)
    angle_deg = float(np.degrees(mean_yaw_rad))
    topo_map.connect_checkpoints(payload.source, payload.target, distance=total_distance_m, angle_deg=angle_deg)

    return {
        "status": "success",
        "source": payload.source,
        "target": payload.target,
        "steps_count": len(step_events),
        "distance_m": round(total_distance_m, 2),
        "mean_yaw_rad": round(mean_yaw_rad, 4)
    }


@app.post("/api/checkpoints", status_code=status.HTTP_201_CREATED)
def create_checkpoint(checkpoint: CheckpointSchema):
    node_name = checkpoint.name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    
    success = map_db_manager.save_checkpoint(node_name)
    if success:
        if node_name not in topo_map.nodes:
            topo_map.add_checkpoint(node_name)
        return {"status": "success", "message": f"Checkpoint '{node_name}' integrado com sucesso."}
    else:
        raise HTTPException(status_code=500, detail="Falha interna ao persistir checkpoint no banco.")


@app.post("/api/localize", status_code=status.HTTP_200_OK)
def localize_user(sensor_data: StepSensorSchema):
    if not topo_map.nodes:
        raise HTTPException(status_code=400, detail="O mapa do sistema está vazio.")
        
    try:
        step_event = StepEventAdapter(step_length_m=sensor_data.step_length_m)
        current_node = matcher.process_step(step=step_event, current_yaw_rad=sensor_data.yaw_rad) #type: ignore
        
        if visited_path and visited_path[-1] != current_node:
            visited_path.append(current_node)
        
        return {
            "status": "success",
            "current_node": current_node,
            "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no PDR: {str(e)}")


@app.get("/api/route", status_code=status.HTTP_200_OK)
def get_route(start: str = Query(...), end: str = Query(...)):
    if start not in topo_map.nodes or end not in topo_map.nodes:
        raise HTTPException(status_code=404, detail="Nó de partida ou destino não encontrados.")
        
    calculated_path = router.calculate_route(start, end)
    if not calculated_path:
        raise HTTPException(status_code=404, detail=f"Sem caminho viável entre '{start}' e '{end}'.")
        
    return {
        "status": "success",
        "origin": start,
        "destination": end,
        "path_sequence": calculated_path,
        "total_nodes_to_cross": len(calculated_path)
    }

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/api/current_location")
def get_current_location():
    return {
        "current_node": getattr(matcher, 'current_node', getattr(matcher, 'current_state', 'Desconhecido')),
        "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0),
        "visited_path": visited_path
    }

@app.get("/api/map", status_code=status.HTTP_200_OK)
def get_map_layout():
    layout = topo_map.get_map_layout()
    return {
        "status": "success",
        "nodes": layout["nodes"],
        "edges": layout["edges"]
    }

@app.get("/")
def read_index():
    return FileResponse("recorder.html")

@app.on_event("shutdown")
def shutdown_event():
    db.desconectar()