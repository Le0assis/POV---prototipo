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

# --- CLASSE AUXILIAR DE COMPATIBILIDADE ---
class StepEvent:
    """Garante que os dados vindos da Web via JSON se adaptem à interface 
    esperada pelo seu process_step do Módulo 2 (PDR).
    """
    def __init__(self, step_length_m: float):
        self.step_length_m = step_length_m


# --- INICIALIZAÇÃO DA INFRAESTRUTURA DA API ---
app = FastAPI(
    title="Indoor IPS API Server",
    description="Backend HTTP para mapeamento e localização indoor em tempo real via sensores mobile."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Libera acesso para qualquer origem (Swagger, Celular, Web)
    allow_credentials=True,
    allow_methods=["*"],      # Libera todos os métodos HTTP (POST, GET, OPTIONS, etc)
    allow_headers=["*"],      # Libera todos os cabeçalhos
)

db = ConexaoBD(host="localhost", database="POV", user="root", password="")
db.conectar()

if not db.connection:
    print("[ERRO CRÍTICO] Não foi possível conectar ao banco MySQL. Verifique o XAMPP.")

map_db_manager = MapDatabaseManager(db)

topo_map = TopologicalMap()
router = TopologicalRouter(topo_map)

# Carrega o mapa salvo do banco de dados para a memória imediatamente ao iniciar o servidor
try:
    # Nota: Certifique-se de que sua classe MapDatabaseManager implementa o carregamento populando o topo_map
    map_db_manager.load_map_into_system(topo_map)
    print(f"[SISTEMA] Mapa carregado com sucesso. Nós em memória: {list(topo_map.nodes.keys())}")
except Exception as e:
    print(f"[AVISO] Falha ao carregar o mapa inicial ou banco vazio. Iniciando grafo limpo. Erro: {e}")

# 4. Inicializa o Matcher de localização (Ponto padrão de inicialização: 'Recepcao')
# Caso a 'Recepcao' não exista inicialmente no banco, o matcher tratará o estado assim que definido.
starting_node = "Recepcao"
matcher = TopologicalMatcher(topo_map, starting_node=starting_node)


# --- CONFIGURAÇÃO DOS SCHEMAS DE VALIDAÇÃO (PYDANTIC) ---
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


# --- ROTAS / ENDPOINTS DA API ---

# --- ENDPOINT 1: SALVAR NOVO CHECKPOINT (FASE DE MAPEAMENTO) ---
@app.post("/api/checkpoints", status_code=status.HTTP_201_CREATED)
def create_checkpoint(checkpoint: CheckpointSchema):
    """Recebe um novo nó semântico enviado pelo celular e persiste no banco e na memória."""
    node_name = checkpoint.name.strip()
    if not node_name:
        raise HTTPException(status_code=400, detail="O nome do checkpoint não pode ser vazio.")
    
    # Salva na persistência do MySQL
    success = map_db_manager.save_checkpoint(node_name)
    
    if success:
        # Sincroniza a memória do servidor imediatamente para o Dijkstra/Matcher usarem sem reiniciar
        if node_name not in topo_map.nodes:
            topo_map.add_checkpoint(node_name)
        return {"status": "success", "message": f"Checkpoint '{node_name}' integrado com sucesso."}
    else:
        raise HTTPException(status_code=500, detail="Falha interna ao persistir checkpoint no banco.")


# --- ENDPOINT 2: SALVAR CONEXÃO/CORREDOR (FASE DE MAPEAMENTO) ---
@app.post("/api/edges", status_code=status.HTTP_201_CREATED)
def create_edge(edge: EdgeSchema):
    """Recebe as métricas de distância e orientação de um corredor recém-caminhado e salva."""
    # Valida a existência dos nós locais na memória antes de processar
    if edge.source not in topo_map.nodes or edge.target not in topo_map.nodes:
        raise HTTPException(
            status_code=400, 
            detail="Origem ou Destino informados não existem na malha de checkpoints cadastrados."
        )
        
    # Grava no banco de dados MySQL via Manager
    success = map_db_manager.save_edge(edge.source, edge.target, edge.distance_m, edge.heading_rad)
    
    if success:
        # Atualiza o grafo em memória dinamicamente convertendo para graus se sua classe base exigir
        angle_deg = float(np.degrees(edge.heading_rad))
        topo_map.connect_checkpoints(edge.source, edge.target, distance=edge.distance_m, angle_deg=angle_deg)
        return {"status": "success", "message": f"Conexão criada entre '{edge.source}' e '{edge.target}'."}
    else:
        raise HTTPException(status_code=500, detail="Erro de persistência ao inserir aresta no MySQL.")


# --- ENDPOINT 3: LOCALIZAÇÃO ONLINE EM TEMPO REAL (PROCESSAMENTO DOS SENSORES) ---
@app.post("/api/localize", status_code=status.HTTP_200_OK)
def localize_user(sensor_data: StepSensorSchema):
    """Recebe o passo calculado transmitido pelo celular pela Web e retorna o ponto exato atual no mapa."""
    if not topo_map.nodes:
        raise HTTPException(status_code=400, detail="O mapa do sistema está vazio. Cadastre checkpoints primeiro.")
        
    try:
        # Adaptador para envelopar a requisição HTTP no formato que seu PDR process_step exige
        step_event = StepEvent(step_length_m=sensor_data.step_length_m)
        
        # Invoca o algoritmo de correspondência topológica (Máquina de Estados)
        current_node = matcher.process_step(step=step_event, current_yaw_rad=sensor_data.yaw_rad) #type: ignore
        
        return {
            "status": "success",
            "current_node": current_node,
            "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar localização do PDR: {str(e)}")


# --- ENDPOINT 4: NAVEGAÇÃO E PLANEJAMENTO DE ROTA (DIJKSTRA) ---
@app.get("/api/route", status_code=status.HTTP_200_OK)
def get_route(
    start: str = Query(..., description="Nó de partida do usuário"), 
    end: str = Query(..., description="Nó de destino final")
):
    """Calcula matematicamente a rota mais curta entre dois pontos usando o algoritmo de Dijkstra."""
    if start not in topo_map.nodes or end not in topo_map.nodes:
        raise HTTPException(
            status_code=404, 
            detail="Nó de partida ou destino não foram encontrados na base cartográfica."
        )
        
    # Executa o cálculo puro do algoritmo do Roteador (Módulo 3)
    calculated_path = router.calculate_route(start, end)
    
    if not calculated_path:
        raise HTTPException(
            status_code=404, 
            detail=f"Não existe caminho conectivo viável entre '{start}' e '{end}'."
        )
        
    return {
        "status": "success",
        "origin": start,
        "destination": end,
        "path_sequence": calculated_path,
        "total_nodes_to_cross": len(calculated_path)
    }

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- ENDPOINT DA LOCALIZAÇÃO ATUAL ---
@app.get("/api/current_location")
def get_current_location():
    """Retorna o nó atual e a distância acumulada onde o usuário está no momento."""
    return {
        "current_node": getattr(matcher, 'current_node', getattr(matcher, 'current_state', 'Desconhecido')),
        "accumulated_distance_m": getattr(matcher, 'accumulated_distance', 0.0)
    }
    
#EndPoint raiz do projeto
@app.get("/")
def read_index():
    return FileResponse("static/index.html")

# --- FINALIZAÇÃO LIMPA DO SERVIDOR ---
@app.on_event("shutdown")
def shutdown_event():
    """Fecha os seletores de conexão de rede de forma limpa ao derrubar o servidor Uvicorn."""
    db.desconectar()
    