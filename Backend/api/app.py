import math
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
from .schema import ProcessRawEdgeSchema, CheckpointSchema, EdgeSchema, StepSensorSchema, RouteCreateSchema

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
FRONTEND_DIR = (BASE_DIR / "../../frontend").resolve()

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


@app.post("/api/edges", status_code=status.HTTP_201_CREATED)
def create_edge(edge: EdgeSchema):
    """Cadastra manualmente uma conexão (ida e volta) entre dois checkpoints."""
    if edge.source not in topo_map.nodes or edge.target not in topo_map.nodes:
        raise HTTPException(status_code=404, detail="Nó de origem ou destino não encontrados.")

    if edge.source == edge.target:
        raise HTTPException(status_code=400, detail="Origem e destino não podem ser o mesmo nó.")

    if edge.distance_m <= 0:
        raise HTTPException(status_code=400, detail="A distância deve ser maior que zero.")

    success = map_db_manager.save_edge(edge.source, edge.target, edge.distance_m, edge.heading_rad)
    if not success:
        raise HTTPException(status_code=500, detail="Falha interna ao persistir conexão no banco.")

    # connect_checkpoints recebe GRAUS e já cria os sentidos de ida e volta
    topo_map.connect_checkpoints(edge.source, edge.target, edge.distance_m, math.degrees(edge.heading_rad))

    return {
        "status": "success",
        "message": f"Conexão '{edge.source}' <-> '{edge.target}' criada com sucesso.",
        "edge": {
            "source": edge.source,
            "target": edge.target,
            "distance_m": edge.distance_m,
            "heading_rad": edge.heading_rad
        }
    }


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


@app.get("/api/compass_route", status_code=status.HTTP_200_OK)
def get_compass_route(start: str = Query(...), end: str = Query(...)):
    """Retorna a rota com segmentos detalhados (heading, distance) para navegação por bússola."""
    if start not in topo_map.nodes or end not in topo_map.nodes:
        raise HTTPException(status_code=404, detail="Nó de partida ou destino não encontrados.")

    segments = router.calculate_route_with_segments(start, end)
    if not segments:
        raise HTTPException(status_code=404, detail=f"Sem caminho viável entre '{start}' e '{end}'.")

    total_distance = sum(s["distance_m"] for s in segments)

    return {
        "status": "success",
        "origin": start,
        "destination": end,
        "segments": segments,
        "path_sequence": [start] + [s["target"] for s in segments],
        "total_distance_m": round(total_distance, 2)
    }

# --- ENDPOINTS DE ROTAS SALVAS ---

@app.get("/api/routes", status_code=status.HTTP_200_OK)
def get_all_routes():
    """Lista todas as rotas salvas (resumo)."""
    routes = map_db_manager.get_all_routes()
    return {
        "status": "success",
        "routes": routes
    }

@app.post("/api/routes", status_code=status.HTTP_201_CREATED)
def create_route(route_data: RouteCreateSchema):
    """Cria e salva uma nova rota calculando via Dijkstra."""
    start = route_data.start_node
    end = route_data.end_node

    if start not in topo_map.nodes or end not in topo_map.nodes:
        raise HTTPException(status_code=404, detail="Nó de partida ou destino não encontrados.")

    segments = router.calculate_route_with_segments(start, end)
    if not segments:
        raise HTTPException(status_code=404, detail=f"Sem caminho viável entre '{start}' e '{end}'.")

    path_sequence = router.calculate_route(start, end)

    # Nome automático se não fornecido
    name = route_data.name or f"{start} → {end}"

    success = map_db_manager.save_route(name, start, end, segments, path_sequence)
    if not success:
        raise HTTPException(status_code=500, detail="Falha ao salvar rota no banco.")

    # Retorna a rota criada (busca pelo último ID)
    routes = map_db_manager.get_all_routes()
    new_route = routes[0] if routes else None

    return {
        "status": "success",
        "message": f"Rota '{name}' salva com sucesso.",
        "route": new_route
    }

@app.get("/api/routes/{route_id}", status_code=status.HTTP_200_OK)
def get_saved_route(route_id: int):
    """Retorna uma rota completa com todos os segmentos para modo teste."""
    route = map_db_manager.get_route_by_id(route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    return {
        "status": "success",
        "route": route
    }

@app.delete("/api/routes/{route_id}", status_code=status.HTTP_200_OK)
def delete_route(route_id: int):
    """Remove uma rota salva."""
    success = map_db_manager.delete_route(route_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rota não encontrada ou erro ao remover.")

    return {"status": "success", "message": "Rota removida com sucesso."}

# Modificar reset para aceitar start_node dinâmico
@app.post("/api/reset")
def reset_session(start_node: str = Query(default="Recepcao")):
    """Zera o estado do matcher e a lista de nós visitados para nova gravação/localização."""
    global matcher, visited_path
    if start_node not in topo_map.nodes:
        start_node = next(iter(topo_map.nodes), starting_node)
    matcher = TopologicalMatcher(topo_map, starting_node=start_node)
    visited_path = [start_node]
    return {"status": "success", "message": "Estado do PDR e sensores resetados.", "start_node": start_node}

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

@app.get("/api/current_location")
def get_current_location():
    return {
        "current_node": getattr(matcher, 'current_node', getattr(matcher, 'current_state', 'Desconhecido')),
        "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0),
        "steps_count": getattr(matcher, "steps_count", 0),
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
@app.get("/index.html")
def read_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": f"Arquivo index.html nao encontrado no caminho {index_path}"}

@app.get("/recorder")
@app.get("/recorder.html")
def read_recorder():
    recorder_path = FRONTEND_DIR / "recorder.html"
    if recorder_path.exists():
        return FileResponse(recorder_path)
    return {"error": "Arquivo recorder.html nao encontrado em frontend/"}

@app.get("/routes")
@app.get("/routes.html")
def read_routes():
    routes_path = FRONTEND_DIR / "routes.html"
    if routes_path.exists():
        return FileResponse(routes_path)
    return {"error": "Arquivo routes.html nao encontrado em frontend/"}

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
