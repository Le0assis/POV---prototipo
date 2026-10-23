import logging
import math
from fastapi import Depends, FastAPI, HTTPException, Response, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from datasets.ManagerDatabase import (
    ConexaoBD,
    DatabaseBusy,
    DatabaseQueryError,
    DatabaseUnavailable,
    drain_pool,
    request_session,
)
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from map.router import TopologicalRouter
from map.topological_matcher import TopologicalMatcher
from pdr.processor import RawEdgeProcessor
from .cors import OriginCORSMiddleware
from .editor_auth import require_editor_password
from .envfile import load_env_file
from .settings import get_settings

load_env_file()

logger = logging.getLogger(__name__)


def _internal_error(
    detail: str,
    exc: BaseException | None = None,
    *,
    status_code: int = 500,
    note: str,
) -> HTTPException:
    """Corpo genérico. A causa fica no log do processo."""
    if exc is None:
        logger.error("%s", note)
    else:
        logger.error("%s", note, exc_info=exc)
    return HTTPException(status_code=status_code, detail=detail)
from map.MapDatabaseManager import (
    CheckpointConflictError,
    CheckpointLookupError,
    UnknownCategoryError,
)
from .schema import (
    ProcessRawEdgeSchema,
    CheckpointSchema,
    CheckpointCategorySchema,
    CheckpointPositionSchema,
    EdgeSchema,
    StepSensorSchema,
    RouteCreateSchema,
    MapConfigSchema,
)
from pdr.steps import StepDetectorConfig, pdr_config_payload


class StepEventAdapter:
    """Passo já medido, no formato que o matcher de teste consome."""
    def __init__(self, step_length_m: float):
        self.step_length_m = step_length_m


# --- INICIALIZAÇÃO DA INFRAESTRUTURA DA API ---
app = FastAPI(
    title="Indoor IPS API Server",
    description="Backend HTTP para mapeamento e localização indoor em tempo real via sensores mobile."
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = (BASE_DIR / "../../frontend").resolve()


def database_from_settings() -> ConexaoBD:
    """Sessão modelo. Padrão de dev é o XAMPP local; produção vem do ambiente."""
    cfg = get_settings()
    return ConexaoBD(
        host=cfg.db_host,
        database=cfg.db_name,
        user=cfg.db_user,
        password=cfg.db_password,
        port=cfg.db_port,
    )


db = database_from_settings()
map_db_manager = MapDatabaseManager(db, per_request=True)

# Por fora das rotas: o preflight não abre MySQL.
app.add_middleware(OriginCORSMiddleware)


@app.exception_handler(DatabaseUnavailable)
async def mysql_unavailable(_request, exc: DatabaseUnavailable):
    """Connect falhou. Não segue com a conexão modelo do processo."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(DatabaseBusy)
async def mysql_busy(_request, exc: DatabaseBusy):
    """Lock ou pool esgotado depois da nova tentativa."""
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": "5"},
    )


@app.exception_handler(DatabaseQueryError)
async def mysql_query_failed(_request, exc: DatabaseQueryError):
    """Erro de SQL que não é lock. Não vira 404 de recurso ausente."""
    return JSONResponse(status_code=500, content={"detail": str(exc)})


topo_map = TopologicalMap()
router = TopologicalRouter(topo_map)

def _load_map_once() -> None:
    """Carrega o grafo na subida e devolve a sessão. Não fica aberta no processo."""
    try:
        with request_session(db):
            map_db_manager.load_map_into_system(topo_map)
            print(f"[SISTEMA] Mapa carregado com sucesso. Nós em memória: {list(topo_map.nodes.keys())}")
    except DatabaseUnavailable:
        print("[ERRO CRÍTICO] Não foi possível conectar ao banco MySQL. Verifique o XAMPP.")
    except Exception as exc:
        print(f"[AVISO] Falha ao carregar o mapa inicial ou banco vazio. Erro: {exc}")


_load_map_once()

starting_node = "Recepcao"
matcher = TopologicalMatcher(topo_map, starting_node=starting_node)
visited_path = [starting_node]

# --- ROTAS DA API ---

edge_processor = RawEdgeProcessor(map_db_manager, topo_map)


def require_test_routes() -> None:
    """As rotas de localização fixa só existem com a flag. Sem ela, 404."""
    if not get_settings().pov_enable_test_routes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@app.get("/api/health")
def health():
    """Ping do status. Não abre MySQL nem as rotas de teste."""
    return {"status": "ok"}

@app.get("/api/auth/check", status_code=status.HTTP_204_NO_CONTENT)
def check_editor_auth(_editor: None = Depends(require_editor_password)):
    """Confirma a senha do editor. 204 se confere; 401 ou 503 vêm da dependência."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/api/edges/process-raw", status_code=status.HTTP_201_CREATED)
def process_raw_edge(
    payload: ProcessRawEdgeSchema,
    _editor: None = Depends(require_editor_password),
):
    """Recebe amostras brutas, grava a trajetória e atualiza só o sentido andado."""
    if payload.source not in topo_map.nodes or payload.target not in topo_map.nodes:
        raise HTTPException(status_code=404, detail="Nó de origem ou destino não encontrados.")
    if payload.source == payload.target:
        raise HTTPException(status_code=400, detail="Origem e destino não podem ser o mesmo nó.")
    return edge_processor.process_samples(payload.source, payload.target, payload.samples)

@app.post("/api/checkpoints", status_code=status.HTTP_201_CREATED)
def create_checkpoint(
    checkpoint: CheckpointSchema,
    _editor: None = Depends(require_editor_password),
):
    node_name = checkpoint.name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    
    try:
        if checkpoint.category_code is None:
            success = map_db_manager.save_checkpoint(node_name)
        else:
            success = map_db_manager.save_checkpoint(node_name, checkpoint.category_code)
    except UnknownCategoryError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Categoria '{exc.code}' não existe.",
        ) from exc
    except CheckpointLookupError as exc:
        raise _internal_error(
            "Erro interno ao salvar.",
            exc,
            note="POST /api/checkpoints",
        ) from exc
    except CheckpointConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="O slug gerado ainda está em uso neste prédio. Tente de novo.",
        ) from exc
    if success:
        if node_name not in topo_map.nodes:
            topo_map.add_checkpoint(node_name)
        body = {
            "status": "success",
            "message": f"Checkpoint '{node_name}' integrado com sucesso.",
        }
        if isinstance(success, dict):
            body["checkpoint"] = success
        return body
    else:
        raise HTTPException(status_code=500, detail="Falha interna ao persistir checkpoint no banco.")


@app.post("/api/edges", status_code=status.HTTP_201_CREATED)
def create_edge(
    edge: EdgeSchema,
    _editor: None = Depends(require_editor_password),
):
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

    # Um registro por sentido, nos mesmos radianos gravados no banco.
    inverse_heading = (edge.heading_rad + math.pi) % (2 * math.pi)
    topo_map.upsert_directed_edge(edge.source, edge.target, edge.distance_m, edge.heading_rad)
    topo_map.upsert_directed_edge(edge.target, edge.source, edge.distance_m, inverse_heading)

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
def localize_user(
    sensor_data: StepSensorSchema,
    _test: None = Depends(require_test_routes),
):
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
def create_route(
    route_data: RouteCreateSchema,
    _editor: None = Depends(require_editor_password),
):
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
def delete_route(
    route_id: int,
    _editor: None = Depends(require_editor_password),
):
    """Remove uma rota salva."""
    success = map_db_manager.delete_route(route_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")

    return {"status": "success", "message": "Rota removida com sucesso."}

# Modificar reset para aceitar start_node dinâmico
@app.post("/api/reset")
def reset_session(
    start_node: str = Query(default="Recepcao"),
    _test: None = Depends(require_test_routes),
    _editor: None = Depends(require_editor_password),
):
    """Zera o estado do matcher e a lista de nós visitados para nova gravação/localização."""
    global matcher, visited_path
    if start_node not in topo_map.nodes:
        start_node = next(iter(topo_map.nodes), starting_node)
    matcher = TopologicalMatcher(topo_map, starting_node=start_node)
    visited_path = [start_node]
    return {"status": "success", "message": "Estado do PDR e sensores resetados.", "start_node": start_node}

# O front em Vite tirou frontend/js. Montar pasta ausente derruba o import da API.
for _mount, _folder in (("/css", "css"), ("/js", "js"), ("/assets", "assets"), ("/vendor", "vendor")):
    _directory = FRONTEND_DIR / _folder
    if _directory.is_dir():
        app.mount(_mount, StaticFiles(directory=_directory), name=_folder)

@app.get("/api/current_location")
def get_current_location(_test: None = Depends(require_test_routes)):
    return {
        "current_node": getattr(matcher, 'current_node', getattr(matcher, 'current_state', 'Desconhecido')),
        "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0),
        "steps_count": getattr(matcher, "steps_count", 0),
        "visited_path": visited_path
    }

def _checkpoint_meta(raw):
    """Tupla legada (x, y) ou o dict público do checkpoint."""
    if isinstance(raw, dict):
        return (
            raw.get("pos_x_px"),
            raw.get("pos_y_px"),
            raw.get("slug"),
            raw.get("building_id"),
            raw.get("category"),
        )
    if isinstance(raw, tuple) and len(raw) >= 2:
        return raw[0], raw[1], None, None, None
    return None, None, None, None, None


@app.get("/api/map", status_code=status.HTTP_200_OK)
def get_map_layout():
    """Nós com posição da planta e arestas só da tabela edges (já carregada sem espelho)."""
    layout = topo_map.get_map_layout()
    try:
        positions = map_db_manager.get_checkpoint_positions()
    except CheckpointLookupError as exc:
        raise _internal_error(
            "Erro interno.",
            exc,
            status_code=503,
            note="GET /api/map",
        ) from exc
    nodes = []
    for node in layout["nodes"]:
        pos_x, pos_y, slug, building_id, category = _checkpoint_meta(positions.get(node["id"]))
        nodes.append({
            **node,
            "pos_x_px": pos_x,
            "pos_y_px": pos_y,
            "slug": slug,
            "building_id": building_id,
            "category": category,
        })
    return {
        "status": "success",
        "nodes": nodes,
        "edges": layout["edges"]
    }


@app.get("/api/categories", status_code=status.HTTP_200_OK)
def list_categories():
    """Categorias de checkpoint, da menor sort_order para a maior."""
    categories = map_db_manager.list_categories()
    if categories is None:
        raise _internal_error("Erro interno.", note="GET /api/categories")
    return {"status": "success", "categories": categories}


@app.get("/api/checkpoints/resolve", status_code=status.HTTP_200_OK)
def resolve_checkpoint(
    b: int = Query(...),
    cp: str = Query(...),
):
    """Acha o checkpoint do QR ``cp`` (slug) no prédio ``b``."""
    slug = cp.strip()
    if not slug:
        raise HTTPException(status_code=422, detail="Informe o slug do checkpoint (cp).")
    try:
        found = map_db_manager.resolve_checkpoint(b, slug)
    except CheckpointLookupError as exc:
        raise _internal_error(
            "Erro interno.",
            exc,
            note="GET /api/checkpoints/resolve",
        ) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="Checkpoint não encontrado.")
    return {"status": "success", "checkpoint": found}


@app.patch("/api/checkpoints/{name}", status_code=status.HTTP_200_OK)
def update_checkpoint_category(
    name: str,
    body: CheckpointCategorySchema,
    _editor: None = Depends(require_editor_password),
):
    """Define ou limpa a categoria. ``category_code`` null remove. Slug não entra no corpo."""
    node_name = name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    try:
        saved = map_db_manager.update_checkpoint_category(node_name, body.category_code)
    except UnknownCategoryError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Categoria '{exc.code}' não existe.",
        ) from exc
    except CheckpointLookupError as exc:
        raise _internal_error(
            "Erro interno ao salvar.",
            exc,
            note="PATCH /api/checkpoints/{name}",
        ) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="Checkpoint não encontrado.")
    return {"status": "success", "checkpoint": saved}


@app.patch("/api/checkpoints/{name}/position", status_code=status.HTTP_200_OK)
def update_checkpoint_position(
    name: str,
    body: CheckpointPositionSchema,
    _editor: None = Depends(require_editor_password),
):
    """Posição do checkpoint na planta (origem no canto superior esquerdo, y para baixo)."""
    node_name = name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    saved = map_db_manager.update_checkpoint_position(node_name, body.pos_x_px, body.pos_y_px)
    if not saved:
        raise HTTPException(status_code=404, detail="Checkpoint não encontrado.")
    return {
        "status": "success",
        "checkpoint": {
            "name": node_name,
            "pos_x_px": body.pos_x_px,
            "pos_y_px": body.pos_y_px,
        },
    }


def _map_config_body(config: dict) -> dict:
    return {
        "status": "success",
        "map_config": {
            "plan_image": config.get("plan_image"),
            "px_per_m": config.get("px_per_m"),
            "rotation_rad": config.get("rotation_rad"),
        },
    }


@app.get("/api/map-config", status_code=status.HTTP_200_OK)
def get_map_config():
    config = map_db_manager.get_map_config()
    if config is None:
        raise _internal_error("Erro interno.", note="GET /api/map-config")
    return _map_config_body(config)


@app.put("/api/map-config", status_code=status.HTTP_200_OK)
def put_map_config(
    body: MapConfigSchema,
    _editor: None = Depends(require_editor_password),
):
    saved = map_db_manager.save_map_config(body.plan_image, body.px_per_m, body.rotation_rad)
    if saved is None:
        raise _internal_error("Erro interno ao salvar.", note="PUT /api/map-config")
    return _map_config_body(saved)


@app.get("/api/connections", status_code=status.HTTP_200_OK)
def get_connections(include_path: bool = Query(default=True)):
    """Um item por par físico. include_path default true; false omite path."""
    connections = map_db_manager.list_connections(include_path=include_path)
    if connections is None:
        raise _internal_error("Erro interno.", note="GET /api/connections")
    return {"status": "success", "frame": "edge_local", "connections": connections}


@app.get("/api/connections/{edge_id}", status_code=status.HTTP_200_OK)
def get_connection_by_id(edge_id: int):
    """O sentido do id pedido, mais as trajetórias desse sentido."""
    connection = map_db_manager.get_connection(edge_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return {"status": "success", "frame": "edge_local", **connection}


@app.get("/api/pdr/config", status_code=status.HTTP_200_OK)
def get_pdr_config():
    """Parâmetros do PDR no cliente. Leitura pública. min_samples é configurável."""
    return pdr_config_payload(StepDetectorConfig())
    
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

@app.get("/editor")
@app.get("/editor.html")
def read_editor():
    return _frontend_page("editor.html")

@app.get("/viewer")
@app.get("/viewer.html")
def read_viewer():
    return _frontend_page("viewer.html")

@app.get("/locate")
@app.get("/locate.html")
def read_locate():
    return _frontend_page("locate.html")

def _frontend_page(name: str):
    path = FRONTEND_DIR / name
    if path.exists():
        return FileResponse(path)
    return {"error": f"Arquivo {name} nao encontrado em frontend/"}

@app.get("/api/sensors_log/{log_id}/csv")
def download_sensor_log_csv(
    log_id: int,
    _editor: None = Depends(require_editor_password),
):
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
    drain_pool()
    db.disconnect()
