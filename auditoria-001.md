# Plano de Implementação: Bússola/Seta de Navegação PDR

## Contexto
O projeto POV já possui um sistema completo de PDR (Pedestrian Dead Reckoning) com mapeamento topológico. O backend armazena arestas com `heading_rad` (ângulo absoluto em radianos relativo ao Norte magnético). O frontend já captura orientação do dispositivo via `DeviceOrientationEvent` (alpha/beta/gamma). 

**O que falta**: Um endpoint que retorne os segmentos da rota com seus headings/distance, e a lógica no frontend para calcular o delta entre a orientação atual do dispositivo e o heading do próximo segmento, aplicando rotação CSS na seta.

---

## Arquivos a Modificar

### 1. Backend: `/home/leozera/Projects/ecosystem/POV---prototipo/Backend/api/app.py`
- **Nova função**: `get_route_with_segments(start: str, end: str)` 
- **Novo endpoint**: `GET /api/compass_route?start=X&end=Y`
- **Retorno**: Lista de segmentos com `{source, target, distance_m, heading_rad, heading_deg}`

### 2. Backend: `/home/leozera/Projects/ecosystem/POV---prototipo/Backend/map/router.py`
- **Novo método**: `calculate_route_with_segments(start_node, end_node)` 
- Retorna lista de dicionários com detalhes de cada aresta do caminho

### 3. Frontend: `/home/leozera/Projects/ecosystem/POV---prototipo/frontend/index.html`
- **Nova seção UI**: Bússola/seta de navegação no painel de navegação
- **Nova lógica JS**: 
  - Fetch `/api/compass_route` ao selecionar destino
  - Capturar `DeviceOrientationEvent.alpha` (já existe em recorder.html, replicar)
  - Calcular `delta = normalizeAngle(target_heading - current_yaw)`
  - Aplicar `transform: rotate(${delta}rad)` na seta SVG/CSS

---

## Micro-Passos Detalhados

### Fase 1: Backend - Endpoint de Rota com Segmentos

#### Step 1.1: Estender TopologicalRouter
**Arquivo**: `Backend/map/router.py`
- Adicionar método `calculate_route_with_segments(start_node, end_node)`
- Usar Dijkstra existente + reconstruir caminho com detalhes das arestas
- Retornar: `[{"source": str, "target": str, "distance_m": float, "heading_rad": float, "heading_deg": float}, ...]`

#### Step 1.2: Criar endpoint /api/compass_route
**Arquivo**: `Backend/api/app.py`
- Importar novo método do router
- Endpoint GET `/api/compass_route?start=X&end=Y`
- Validação de nós existentes
- Retorno JSON estruturado

#### Step 1.3: Testar endpoint backend
- Verificar se retorna segmentos corretos com headings em radianos e graus

---

### Fase 2: Frontend - UI e Lógica da Bússola

#### Step 2.1: Adicionar elemento visual da bússola no index.html
**Arquivo**: `frontend/index.html`
- No `#panel-nav`, adicionar `<div id="compass">` com seta SVG
- Estilo CSS para seta centralizada, transição suave

#### Step 2.2: Capturar orientação do dispositivo (DeviceOrientationEvent)
**Arquivo**: `frontend/index.html`
- Reutilizar padrão do `recorder.html`: `window.addEventListener('deviceorientation', handleOrientation)`
- Extrair `event.alpha` (azimute em graus, 0=Norte) → converter para radianos
- `current_yaw_rad = (alpha * Math.PI / 180)` (ajustar convenção se necessário)

#### Step 2.3: Fetch da rota com segmentos ao selecionar destino
**Arquivo**: `frontend/index.html`
- Modificar `onRequestRoute()` para chamar `/api/compass_route`
- Armazenar `routeSegments` array global
- Identificar próximo segmento baseado no `currentNode`

#### Step 2.4: Calcular delta e rotacionar seta
**Arquivo**: `frontend/index.html`
- Função `updateCompass()`:
  - Encontrar segmento atual: `routeSegments.find(s => s.source === currentNode)`
  - `target_heading = segment.heading_rad`
  - `delta = normalizeAngle(target_heading - current_yaw_rad)`
  - `arrow.style.transform = `rotate(${delta}rad)``
- Chamar no `fetchUserLocation()` (já roda a cada 500ms)

#### Step 2.5: Função utilitária normalizeAngle
```javascript
function normalizeAngle(angle) {
    while (angle <= -Math.PI) angle += 2 * Math.PI;
    while (angle > Math.PI) angle -= 2 * Math.PI;
    return angle;
}
```

---

## Estrutura de Dados

### Resposta /api/compass_route
```json
{
  "status": "success",
  "origin": "Recepcao",
  "destination": "Sala 101",
  "segments": [
    {
      "source": "Recepcao",
      "target": "Corredor Central",
      "distance_m": 12.5,
      "heading_rad": 0.785,
      "heading_deg": 45.0
    },
    {
      "source": "Corredor Central", 
      "target": "Sala 101",
      "distance_m": 8.0,
      "heading_rad": 1.571,
      "heading_deg": 90.0
    }
  ],
  "total_distance_m": 20.5
}
```

### Convenções de Ângulo
- **Backend**: `heading_rad` = 0 = Norte magnético, sentido horário (padrão matemático polar)
- **Frontend DeviceOrientationEvent.alpha**: 0 = Norte, sentido horário (graus)
- **Conversão**: `yaw_rad = alpha * Math.PI / 180`
- **Delta**: `normalizeAngle(target_heading_rad - current_yaw_rad)`
- **CSS rotate**: Aceita radianos ou graus (`rotate(45deg)` ou `rotate(0.785rad)`)

---

## Verificação e Testes

### Testes Backend
1. `python -c "from map.router import TopologicalRouter; from map.topological_map import TopologicalMap; m=TopologicalMap(); m.add_checkpoint('A'); m.add_checkpoint('B'); m.connect_checkpoints('A','B',10,45); r=TopologicalRouter(m); print(r.calculate_route_with_segments('A','B'))"`
2. Iniciar servidor: `uvicorn api.app:app --reload`
3. Testar: `curl "http://127.0.0.1:8000/api/compass_route?start=Recepcao&end=Corredor%20Central"`

### Testes Frontend
1. Abrir `http://127.0.0.1:8000/` no navegador (mobile ou desktop com sensor mock)
2. Selecionar destino no dropdown
3. Verificar:
   - Seta aparece apontando na direção correta
   - Ao rotacionar dispositivo (ou simular), seta acompanha mantendo direção do destino
   - Delta calculado corretamente (seta aponta para frente quando dispositivo alinhado com corredor)

### Casos Edge
- Rota com 1 segmento (origem e destino adjacentes)
- Rota com múltiplos segmentos (atualizar target ao chegar no próximo nó)
- Dispositivo sem bússola (alpha = null) → mostrar mensagem "Calibre a bússola"
- Normalização de ângulos cruzando 0/360° (ex: 350° → 10° = +20°, não -340°)

---

## Referências de Código Existente para Reutilizar

| Funcionalidade | Arquivo | Linha/Função |
|---|---|---|
| DeviceOrientationEvent handling | `recorder.html` | `handleOrientation()` (linha 277-284) |
| Fetch de rota | `index.html` | `onRequestRoute()` (linha 208-218) |
| Polling de localização | `index.html` | `fetchUserLocation()` + `setInterval` (linha 193-304) |
| Estrutura TopologicalEdge | `topological_map.py` | Classe `TopologicalEdge` (linha 15-21) |
| connect_checkpoints com heading | `topological_map.py` | `connect_checkpoints()` (linha 40-66) |
| Carregamento heading do BD | `MapDatabaseManager.py` | `load_map_into_system()` (linha 73-78) |
| Dijkstra path | `router.py` | `calculate_route()` (linha 10-98) |

---

## Estimativa de Esforço
- **Backend**: ~2 horas (router + endpoint + teste)
- **Frontend**: ~3 horas (UI + orientação + lógica delta + teste em dispositivo)
- **Total**: ~5 horas