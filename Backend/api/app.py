import numpy as np
from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from map.router import TopologicalRouter
from map.topological_matcher import TopologicalMatcher
from pdr.processor import RawEdgeProcessor
from .schema import ProcessRawEdgeSchema, CheckpointSchema, StepSensorSchema

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

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "../../frontend"

db = ConexaoBD(host="localhost", database="POV", user="root", password="")
db.connect()

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

# --- ROTAS DA API ---

# NOVO ENDPOINT: ZERAR O ESTADO DO MATCHER E SENSORES
@app.post("/api/reset")
def reset_session():
    """Zera o estado do matcher e a lista de nós visitados para nova gravação/localização."""
    global matcher, visited_path
    matcher = TopologicalMatcher(topo_map, starting_node=starting_node)
    visited_path = [starting_node]
    return {"status": "success", "message": "Estado do PDR e sensores resetados."}

edge_processor = RawEdgeProcessor(map_db_manager, topo_map)

@app.post("/api/edges/process-raw", status_code=status.HTTP_201_CREATED)
def process_raw_edge(payload: ProcessRawEdgeSchema):
    """Recebe amostras brutas e repassa o processamento para a classe RawEdgeProcessor."""
    return edge_processor.process_samples(payload.source, payload.target, payload.samples)

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
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": f"Arquivo index.html nao encontrado no caminho {index_path}"}

@app.get("/recorder")
def read_recorder():
    recorder_path = FRONTEND_DIR / "recorder.html"
    if recorder_path.exists():
        return FileResponse(recorder_path)
    return {"error": "Arquivo recorder.html nao encontrado em frontend/"}

from fastapi import Response, HTTPException

@app.get("/api/sensors_log/{log_id}/csv")
def download_sensor_log_csv(log_id: int):
    """Retorna o CSV gravado no banco como um arquivo para download."""
    csv_data = map_db_manager.get_sensor_log_csv(log_id)
    
    if not csv_data:
        raise HTTPException(status_code=404, detail="Log de sensores não encontrado.")
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=sensor_log_{log_id}.csv"
        }
    )

@app.on_event("shutdown")
def shutdown_event():
    db.disconnect()