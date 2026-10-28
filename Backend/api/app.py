import logging
import math
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath, Query, Request, Response, status
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
from map.checkpoint_slug import SLUG_MAX_LENGTH
from map.MapDatabaseManager import MapDatabaseManager
from map.topological_map import TopologicalMap
from map.topological_matcher import PositionUndefined
from map.router import TopologicalRouter
from pdr.processor import RawEdgeProcessor
from .cors import OriginCORSMiddleware
from .editor_auth import client_key, require_editor_password
from .envfile import load_env_file
from .settings import BootRefusal, assert_production_database, boot_or_exit, get_settings
from .walk_session import (
    SESSION_LIMIT_DETAIL,
    InvalidSessionId,
    SessionLimit,
    WalkSessions,
    parse_session_id,
)

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
    NAME_MAX,
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
    """Sessão modelo com DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD.

    Sem usuário no ambiente a conta fica vazia: não vira root. Em produção,
    root ou senha vazia impede a subida, e a mensagem não cita a senha.
    O pool é o de ``ManagerDatabase`` (checkout por request). CREATE DATABASE
    e GRANT ficam no create_tables (DB_ADMIN_*).
    """
    assert_production_database()
    cfg = get_settings()
    user = (cfg.db_user or "").strip()
    password = "" if cfg.db_password is None else cfg.db_password
    return ConexaoBD(
        host=cfg.db_host,
        database=cfg.db_name,
        user=user,
        password=password,
        port=cfg.db_port,
    )


db = boot_or_exit(database_from_settings)
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
    """Erro de SQL que não é lock. O texto fica no log, não no cliente."""
    logger.error("Erro de SQL", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno."})


topo_map = TopologicalMap()
router = TopologicalRouter(topo_map)


class MapLoadError(BootRefusal):
    """Produção não sobe sem grafo. A mensagem não leva senha nem SQL."""


class MapLoad:
    """Resultado da carga da subida. O health lê isto e não abre MySQL."""

    def __init__(self) -> None:
        self.status = "error"
        self.detail = "Mapa ainda não carregado."

    def set(self, status: str, detail: str) -> None:
        self.status = status
        self.detail = detail


map_load = MapLoad()


def classify_loaded_map(*, failed: bool, node_count: int, edge_count: int) -> tuple[str, str]:
    """``error`` se a carga estourou, ``empty`` sem nó ou sem aresta, senão ``ok``."""
    if failed:
        return "error", "Falha ao carregar o grafo."
    if node_count <= 0 or edge_count <= 0:
        return "empty", "Grafo vazio."
    return "ok", "ok"


def _raise_if_production_map_unusable() -> None:
    """Em produção o processo para. Em desenvolvimento só o health fica 503."""
    if map_load.status == "ok":
        return
    if get_settings().pov_env.strip().lower() != "production":
        return
    raise MapLoadError(f"Produção não sobe: {map_load.detail}")


def _load_map_once() -> None:
    """Carrega o grafo na subida e devolve a sessão. Não fica aberta no processo."""
    failed = False
    try:
        with request_session(db):
            map_db_manager.load_map_into_system(topo_map)
            print(f"[SISTEMA] Mapa carregado com sucesso. Nós em memória: {list(topo_map.nodes.keys())}")
    except DatabaseUnavailable:
        failed = True
        print("[ERRO CRÍTICO] Não foi possível conectar ao banco MySQL. Verifique o XAMPP.")
        logger.error("MySQL indisponível ao carregar o mapa")
    except Exception as exc:
        failed = True
        print(f"[ERRO] Falha ao carregar o mapa inicial. Erro: {exc}")
        logger.error("Falha ao carregar o mapa", exc_info=exc)
    status_name, detail = classify_loaded_map(
        failed=failed,
        node_count=len(topo_map.nodes),
        edge_count=len(topo_map.edges),
    )
    map_load.set(status_name, detail)
    if status_name == "empty":
        print("[ERRO] Grafo vazio: sem nó ou sem aresta.")
        logger.error("Grafo vazio na subida")
    _raise_if_production_map_unusable()


boot_or_exit(_load_map_once)

walk_sessions = WalkSessions(topo_map)

# --- ROTAS DA API ---

edge_processor = RawEdgeProcessor(map_db_manager, topo_map)


def require_test_routes() -> None:
    """As rotas de localização fixa só existem com a flag. Sem ela, 404."""
    if not get_settings().pov_enable_test_routes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def require_session_id(x_pov_session: str | None = Header(default=None)) -> str:
    """Id do aparelho. A rota declara a flag de teste antes desta dependência."""
    try:
        return parse_session_id(x_pov_session)
    except InvalidSessionId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@contextmanager
def hold_session(session_id: str, request: Request, **kwargs):
    """Sessão deste IP. O IP é o mesmo do limite de senha. Cheio responde 429."""
    try:
        with walk_sessions.hold(session_id, client_ip=client_key(request), **kwargs) as state:
            yield state
    except SessionLimit as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=SESSION_LIMIT_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@app.get("/health")
@app.get("/api/health")
def health():
    """Grafo carregado na subida. Não abre MySQL. Vazio ou erro é 503."""
    if map_load.status != "ok":
        return JSONResponse(
            status_code=503,
            content={"status": map_load.status, "detail": map_load.detail},
        )
    return {"status": "ok"}


def _canonical_pair(source: str, target: str, *, missing: str) -> tuple[str, str]:
    """Nomes exatos do checkpoint. ``Sala`` não casa com ``sala``."""
    resolved_source = topo_map.canonical_name(source)
    resolved_target = topo_map.canonical_name(target)
    if resolved_source is None or resolved_target is None:
        raise HTTPException(status_code=404, detail=missing)
    return resolved_source, resolved_target

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
    source, target = _canonical_pair(
        payload.source,
        payload.target,
        missing="Nó de origem ou destino não encontrados.",
    )
    if source == target:
        raise HTTPException(status_code=400, detail="Origem e destino não podem ser o mesmo nó.")
    return edge_processor.process_samples(source, target, payload.samples)

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
        if topo_map.canonical_name(node_name) is None:
            topo_map.add_checkpoint(node_name)
        body = {
            "status": "success",
            "message": f"Checkpoint '{node_name}' integrado com sucesso.",
        }
        if isinstance(success, dict):
            body["checkpoint"] = success
        return body
    else:
        raise _internal_error("Erro interno ao salvar.", note="POST /api/checkpoints sem confirmação")


@app.post("/api/edges", status_code=status.HTTP_201_CREATED)
def create_edge(
    edge: EdgeSchema,
    _editor: None = Depends(require_editor_password),
):
    """Cadastra manualmente uma conexão (ida e volta) entre dois checkpoints."""
    source, target = _canonical_pair(
        edge.source,
        edge.target,
        missing="Nó de origem ou destino não encontrados.",
    )
    if source == target:
        raise HTTPException(status_code=400, detail="Origem e destino não podem ser o mesmo nó.")

    if edge.distance_m <= 0:
        raise HTTPException(status_code=400, detail="A distância deve ser maior que zero.")

    success = map_db_manager.save_edge(source, target, edge.distance_m, edge.heading_rad)
    if not success:
        raise _internal_error("Erro interno ao salvar.", note="POST /api/edges")

    # Um registro por sentido, nos mesmos radianos gravados no banco.
    inverse_heading = (edge.heading_rad + math.pi) % (2 * math.pi)
    topo_map.upsert_directed_edge(source, target, edge.distance_m, edge.heading_rad)
    topo_map.upsert_directed_edge(target, source, edge.distance_m, inverse_heading)

    return {
        "status": "success",
        "message": f"Conexão '{source}' <-> '{target}' criada com sucesso.",
        "edge": {
            "source": source,
            "target": target,
            "distance_m": edge.distance_m,
            "heading_rad": edge.heading_rad
        }
    }


@app.post("/api/localize", status_code=status.HTTP_200_OK)
def localize_user(
    sensor_data: StepSensorSchema,
    request: Request,
    _test: None = Depends(require_test_routes),
    session_id: str = Depends(require_session_id),
):
    if not topo_map.nodes:
        raise HTTPException(status_code=400, detail="O mapa do sistema está vazio.")

    try:
        step_event = StepEventAdapter(step_length_m=sensor_data.step_length_m)
        with hold_session(session_id, request) as state:
            try:
                current_node = state.matcher.process_step(
                    step=step_event,
                    current_yaw_rad=sensor_data.yaw_rad,
                )
            except PositionUndefined as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if not state.visited_path or state.visited_path[-1] != current_node:
                state.visited_path.append(current_node)
            distance_m = state.matcher.accumulated_distance
        return {
            "status": "success",
            "current_node": current_node,
            "accumulated_distance_m": distance_m,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Erro interno.", exc, note="POST /api/localize") from exc


@app.get("/api/route", status_code=status.HTTP_200_OK)
def get_route(
    start: str = Query(..., max_length=NAME_MAX),
    end: str = Query(..., max_length=NAME_MAX),
):
    start, end = _canonical_pair(
        start,
        end,
        missing="Nó de partida ou destino não encontrados.",
    )

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
def get_compass_route(
    start: str = Query(..., max_length=NAME_MAX),
    end: str = Query(..., max_length=NAME_MAX),
):
    """Retorna a rota com segmentos detalhados (heading, distance) para navegação por bússola."""
    start, end = _canonical_pair(
        start,
        end,
        missing="Nó de partida ou destino não encontrados.",
    )

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

def route_label(given: str | None, start: str, end: str) -> str:
    """Nome gravado em saved_routes.name (VARCHAR 100). Sem nome, usa os nós."""
    chosen = (given or "").strip()
    if not chosen:
        chosen = f"{start} → {end}"
    if len(chosen) > NAME_MAX:
        chosen = chosen[:NAME_MAX].rstrip() or chosen[:NAME_MAX]
    return chosen


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
    start, end = _canonical_pair(
        route_data.start_node,
        route_data.end_node,
        missing="Nó de partida ou destino não encontrados.",
    )

    segments = router.calculate_route_with_segments(start, end)
    if not segments:
        raise HTTPException(status_code=404, detail=f"Sem caminho viável entre '{start}' e '{end}'.")

    path_sequence = router.calculate_route(start, end)

    name = route_label(route_data.name, start, end)

    route_id = map_db_manager.save_route(name, start, end, segments, path_sequence)
    if type(route_id) is not int or route_id <= 0:
        raise _internal_error("Erro interno ao salvar.", note="POST /api/routes")

    created = map_db_manager.get_route_by_id(route_id)
    if created is None:
        created = {
            "id": route_id,
            "name": name,
            "start_node": start,
            "end_node": end,
        }

    return {
        "status": "success",
        "message": f"Rota '{name}' salva com sucesso.",
        "route": created,
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

@app.post("/api/reset")
def reset_session(
    request: Request,
    start_node: str | None = Query(default=None, max_length=NAME_MAX),
    _test: None = Depends(require_test_routes),
    _editor: None = Depends(require_editor_password),
    session_id: str = Depends(require_session_id),
):
    """Zera o matcher desta sessão. Sem nome, a posição fica vazia."""
    asked = (start_node or "").strip()
    if not asked:
        resolved = ""
    else:
        resolved = topo_map.canonical_name(asked)
        if resolved is None:
            raise HTTPException(
                status_code=404,
                detail="Checkpoint não encontrado. Informe um ponto que já existe no mapa.",
            )
    with hold_session(session_id, request, reset=True, start_node=resolved or None) as state:
        started = state.visited_path[0] if state.visited_path else None
    if started:
        message = f"Posição definida em '{started}'."
    else:
        message = "Nenhuma posição definida. Informe o checkpoint ao reiniciar a posição."
    return {
        "status": "success",
        "message": message,
        "start_node": started,
    }

# O front em Vite tirou frontend/js. Montar pasta ausente derruba o import da API.
for _mount, _folder in (("/css", "css"), ("/js", "js"), ("/assets", "assets"), ("/vendor", "vendor")):
    _directory = FRONTEND_DIR / _folder
    if _directory.is_dir():
        app.mount(_mount, StaticFiles(directory=_directory), name=_folder)

@app.get("/api/current_location")
def get_current_location(
    request: Request,
    _test: None = Depends(require_test_routes),
    session_id: str = Depends(require_session_id),
):
    with hold_session(session_id, request) as state:
        current = state.matcher.current_node or None
        return {
            "current_node": current,
            "accumulated_distance_m": state.matcher.accumulated_distance,
            "steps_count": getattr(state.matcher, "steps_count", 0),
            "visited_path": list(state.visited_path),
            "detail": None if current else "Nenhuma posição definida. Informe o checkpoint ao reiniciar a posição.",
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
    b: int = Query(..., ge=1, le=2_147_483_647),
    cp: str = Query(..., max_length=SLUG_MAX_LENGTH),
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
    name: Annotated[str, ApiPath(max_length=NAME_MAX)],
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
    name: Annotated[str, ApiPath(max_length=NAME_MAX)],
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
    return _frontend_page("index.html")

@app.get("/recorder")
@app.get("/recorder.html")
def read_recorder():
    return _frontend_page("recorder.html")

@app.get("/routes")
@app.get("/routes.html")
def read_routes():
    return _frontend_page("routes.html")

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
    """Página do Vite. O editor e o gravador ficam em ``frontend/admin``."""
    for path in (FRONTEND_DIR / name, FRONTEND_DIR / "admin" / name):
        if path.is_file():
            return FileResponse(path)
    return JSONResponse(status_code=404, content={"detail": "Não encontrado."})

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
