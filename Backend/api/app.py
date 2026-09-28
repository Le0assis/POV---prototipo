import numpy as np
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, status, Query, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# --- IMPORTE DOS SEUS MÓDULOS INTERNOS ---
from datasets.ManagerDatabase import ConexaoBD
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from map.router import TopologicalRouter
from map.topological_matcher import TopologicalMatcher
from pdr.processor import RawEdgeProcessor
from .schema import ProcessRawEdgeSchema, CheckpointSchema, StepSensorSchema

from filters.butterworth import ButterworthLowPassFilter
from filters.madgwick import MadgwickAttitudeEstimator
from pdr.steps import PeakStepDetector


# ==========================================
# 1. CLASSES AUXILIARES E ESTRUTURAS DE DADOS
# ==========================================
class StepEventAdapter:
    """Adaptador de compatibilidade para eventos de passo."""
    def __init__(self, step_length_m: float):
        self.step_length_m = step_length_m


# ==========================================
# 2. INICIALIZAÇÃO DA API E CORS
# ==========================================
app = FastAPI(
    title="Indoor IPS API Server",
    description="Backend HTTP para mapeamento e localização indoor em tempo real via sensores mobile."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "../../frontend"


# ==========================================
# 3. BANCO DE DADOS E GRAFO EM MEMÓRIA
# ==========================================
db = ConexaoBD(host="localhost", database="POV", user="root", password="")
db.connect()

if not db.connection:
    print("[ERRO CRÍTICO] Não foi possível conectar ao banco MySQL. Verifique o XAMPP.")

map_db_manager = MapDatabaseManager(db)
topo_map = TopologicalMap()
router = TopologicalRouter(topo_map)
edge_processor = RawEdgeProcessor(map_db_manager, topo_map)

try:
    map_db_manager.load_map_into_system(topo_map, session_id="default_session")
    print(f"[SISTEMA] Mapa carregado com sucesso. Nós em memória: {list(topo_map.nodes.keys())}")
except Exception as e:
    print(f"[AVISO] Falha ao carregar o mapa inicial ou banco vazio. Erro: {e}")


# ==========================================
# 4. GERENCIAMENTO DE SESSÕES POR USUÁRIO
# ==========================================
active_sessions = {}

def get_session_state(session_id: str):
    """Cria ou recupera o estado de navegação PDR para um usuário específico."""
    if session_id not in active_sessions:
        starting_node = "Recepcao" # Ponto padrão de inicialização
        active_sessions[session_id] = {
            "matcher": TopologicalMatcher(topo_map, starting_node=starting_node),
            "visited_path": [starting_node]
        }
    return active_sessions[session_id]


# ==========================================
# 5. ENDPOINTS DA API: SESSÃO E PDR
# ==========================================
@app.post("/api/reset")
def reset_session(x_session_id: str = Header(default="default_session")):
    """Zera o estado do matcher e a lista de nós para a sessão atual do usuário."""
    starting_node = "Recepcao"
    active_sessions[x_session_id] = {
        "matcher": TopologicalMatcher(topo_map, starting_node=starting_node),
        "visited_path": [starting_node]
    }
    return {"status": "success", "message": f"Estado resetado para a sessão '{x_session_id}'."}


@app.post("/api/localize", status_code=status.HTTP_200_OK)
def localize_user(
    sensor_data: StepSensorSchema, 
    x_session_id: str = Header(default="default_session")
):
    """Processa um passo do usuário e atualiza a localização dentro da sessão dele."""
    if not topo_map.nodes:
        raise HTTPException(status_code=400, detail="O mapa do sistema está vazio.")
        
    try:
        # Recupera o estado PDR isolado deste usuário
        session_state = get_session_state(x_session_id)
        matcher = session_state["matcher"]
        visited_path = session_state["visited_path"]

        step_event = StepEventAdapter(step_length_m=sensor_data.step_length_m)
        current_node = matcher.process_step(step=step_event, current_yaw_rad=sensor_data.yaw_rad)
        
        if visited_path and visited_path[-1] != current_node:
            visited_path.append(current_node)
        
        return {
            "session_id": x_session_id,
            "status": "success",
            "current_node": current_node,
            "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no PDR: {str(e)}")


@app.get("/api/current_location")
def get_current_location(x_session_id: str = Header(default="default_session")):
    """Retorna a localização atual e histórico da sessão do usuário."""
    session_state = get_session_state(x_session_id)
    matcher = session_state["matcher"]
    visited_path = session_state["visited_path"]

    return {
        "session_id": x_session_id,
        "current_node": getattr(matcher, 'current_node', getattr(matcher, 'current_state', 'Desconhecido')),
        "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0),
        "visited_path": visited_path
    }


# ==========================================
# 6. ENDPOINTS DA API: GRAFO E CHECKPOINTS
# ==========================================
@app.post("/api/checkpoints", status_code=status.HTTP_201_CREATED)
def create_checkpoint(
    checkpoint: CheckpointSchema, 
    x_session_id: str = Header(default="default_session")
):
    """Cria um novo checkpoint e associa ao session_id informado."""
    node_name = checkpoint.name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    
    success = map_db_manager.save_checkpoint(x_session_id, node_name)
    if success:
        if node_name not in topo_map.nodes:
            topo_map.add_checkpoint(node_name)
        return {"status": "success", "message": f"Checkpoint '{node_name}' integrado com sucesso."}
    else:
        raise HTTPException(status_code=500, detail="Falha interna ao persistir checkpoint no banco.")


@app.post("/api/edges/process-raw", status_code=status.HTTP_201_CREATED)
def process_raw_edge(
    payload: ProcessRawEdgeSchema,
    x_session_id: str = Header(default="default_session")
):
    """Recebe amostras brutas e repassa para o processador de arestas gravando a sessão."""
    return edge_processor.process_samples(x_session_id, payload.source, payload.target, payload.samples)


@app.get("/api/route", status_code=status.HTTP_200_OK)
def get_route(start: str = Query(...), end: str = Query(...)):
    """Calcula a rota óptima via Dijkstra no grafo topológico."""
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


@app.get("/api/map", status_code=status.HTTP_200_OK)
def get_map_layout():
    """Retorna o mapa topológico completo em JSON para renderização 2D."""
    layout = topo_map.get_map_layout()
    return {
        "status": "success",
        "nodes": layout["nodes"],
        "edges": layout["edges"]
    }


@app.get("/api/sensors_log/{log_id}/csv")
def download_sensor_log_csv(log_id: int):
    """Retorna o CSV gravado no banco como um arquivo para download."""
    csv_data = map_db_manager.get_sensor_log_csv(log_id)
    
    if not csv_data:
        raise HTTPException(status_code=404, detail="Log de sensores não encontrado.")
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=sensor_log_{log_id}.csv"}
    )


# ==========================================
# 7. ROTAS PARA ARQUIVOS ESTÁTICOS / FRONTEND
# ==========================================
@app.get("/")
def read_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": f"Arquivo index.html não encontrado no caminho {index_path}"}

@app.get("/recorder")
def read_recorder():
    recorder_path = FRONTEND_DIR / "recorder.html"
    if recorder_path.exists():
        return FileResponse(recorder_path)
    return {"error": "Arquivo recorder.html não encontrado em frontend/"}


# ==========================================
# 8. EVENTS (SHUTDOWN)
# ==========================================
@app.on_event("shutdown")
def shutdown_event():
    db.disconnect()