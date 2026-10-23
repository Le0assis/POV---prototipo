# Contexto do Projeto — Sistema POV (Pedestrian Dead Reckoning & Topological Mapping)

Base de conhecimento central do POV. Leia antes de qualquer tarefa. Atualize a seção **12. Estado atual** ao fim de cada auditoria.

## 1. Visão geral

- **Nome:** POV (Ponto de Origem / Vista) — protótipo PDR.
- **Objetivo:** navegação e rastreamento de pedestres em ambientes fechados usando só IMU (acelerômetro + giroscópio) do smartphone, sem GPS. Descarta falsos positivos (chacoalhos), detecta passos, calcula distância e direção (yaw) e grava trajetos em um grafo topológico.
- **Uso:** hospitais, universidades, shoppings, galpões; auditoria de dados inerciais para calibrar o PDR.
- **Foco atual:** visão do **Administrador** (mapear, cadastrar, testar e simular rotas). A visão do usuário final vem depois.

## 2. Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.10+, FastAPI + Uvicorn, NumPy, SciPy (`find_peaks`, Butterworth) |
| Banco | MySQL (XAMPP local), acesso via `ConexaoBD` e `MapDatabaseManager` |
| Frontend | TypeScript, Vite, Preact (`@preact/signals`), Leaflet |
| APIs de hardware | `DeviceMotionEvent`, `DeviceOrientationEvent`, Page Visibility |
| Infra | Cloudflare Tunnel (`api.pov-unimar.com` → `:8000`), GitHub Pages (build do Vite em `frontend/dist`, `.github/workflows/pages.yml`) |

## 3. Estrutura de pastas

```
POV---prototipo/
├── Backend/
│   ├── api/            app.py (FastAPI, endpoints, serve o front), schema.py (Pydantic)
│   ├── datasets/       create_tables.py, ManagerDatabase.py, generate_sample_dataset.py, sample_walk.csv
│   ├── filters/        madgwick.py, quaternion.py, butterworth.py, moving_average.py, signal_filter.py, attitude_estimator.py
│   ├── map/            MapDatabaseManager.py, router.py (Dijkstra), topological_map.py, topological_matcher.py
│   ├── pdr/            processor.py (pipeline), steps.py (picos + Weinberg), magnitude.py, altitude.py
│   ├── sensors/        accelerometer.py, gyroscope.py, magnetometer.py, barometer.py, sensor_sample.py
│   ├── others/         seed_map.py, evaluate_steps.py
│   ├── static/         páginas legadas (index.html, mapa-2d.html, sensors_upload.html)
│   └── tests/
├── frontend/           visão do administrador (css/, js/, index, recorder, routes)
├── auditorias/         planos de execução: auditoria-001.md, 002, 003
├── cloudflared-config.yml
└── README.md
```

## 4. Pipeline PDR (`Backend/pdr/processor.py`)

1. Reamostragem uniforme em **`TARGET_HZ = 30`** (corrigido: versões antigas deste doc diziam 50).
2. Madgwick (`gain=0.033`), instância nova por requisição.
3. Aceleração vertical real (projeção pelo quaternion).
4. Trava anti-shake: `max_gyro > 5.5 rad/s` **ou** `mean_gyro > 2.2 rad/s` → `status:"warning"`, `valid:false`, log gravado.
5. Butterworth passa-baixas, 2ª ordem, corte 2,2 Hz.
6. Picos (`PeakStepDetector`, `weinberg_k=0.45` no processor): 0 passos → descarta e loga.
7. Yaw médio da caminhada (`mean_yaw_rad`).
8. Persistência: CSV em `sensors_log` + aresta no grafo.

Regras do detector (`pdr/steps.py`): altura dinâmica `max(9.95, média + 0.12)` m/s²; distância mínima entre picos 0,33 s; `0.55 ≤ Δa ≤ 4.5` m/s²; passo Weinberg `L = k·Δa^0.25`, limitado a **[0,40; 0,95] m**; janela de giroscópio por passo > 3,0 rad/s invalida o pico.

## 5. Grafo topológico e localização

- Nós = checkpoints; arestas = trajetos `{source, target, distance_m, heading_rad}`. `connect_checkpoints` cria ida e volta (volta = heading + π).
- **`heading_rad` = yaw do Madgwick**: anti-horário (ZYX), **relativo à pose inicial do aparelho, NÃO é Norte magnético**.
- `TopologicalMatcher.process_step(step, yaw)`: soma `step_length_m` em `accumulated_distance`; aceita a aresta se `|yaw − heading| ≤ 30°`; ao atingir `distance_m` troca de nó e **zera o odômetro**. Passos fora do cone são ignorados.
- `get_map_layout()` (BFS a partir de `Recepcao` ou do 1º nó): `x = d·cos(h)`, `y = d·sin(h)` (convenção matemática).
- `router.calculate_route(a, b)` → lista de nós (Dijkstra); `calculate_route_with_segments` → lista de `{source, target, distance_m, heading_rad, heading_deg}`.

## 6. Endpoints (`Backend/api/app.py`)

| Método | Rota | Entrada | Saída / nota |
|---|---|---|---|
| GET | `/api/map` | – | `{nodes:[{id,label,x,y}], edges:[...]}` |
| POST | `/api/checkpoints` | `{name}` | cria nó |
| POST | `/api/edges/process-raw` | `{source,target,samples[]}` | processa caminhada e grava aresta |
| POST | `/api/localize` | `{step_length_m, yaw_rad}` | `{current_node, accumulated_distance_m}` |
| GET | `/api/current_location` | – | `{current_node, accumulated_distance_m, visited_path}` |
| POST | `/api/reset` | query `start_node` | zera matcher (⚠ duplicado no código até a T1 da auditoria 003) |
| GET | `/api/route` | `start,end` | `path_sequence` |
| GET | `/api/compass_route` | `start,end` | `segments`, `total_distance_m` (`path_sequence` entra na T1) |
| GET/POST | `/api/routes` | `{start_node,end_node,name?}` | lista/salva rota (tabela `saved_routes`) |
| GET/DELETE | `/api/routes/{id}` | – | rota completa (`segments`, `path_sequence`) / remove |
| GET | `/api/sensors_log/{id}/csv` | – | CSV bruto para calibração |
| GET | `/`, `/recorder`, `/routes` | – | HTML do `frontend/` |

Tabelas: `checkpoints`, arestas, `sensors_log` (`is_valid`, `steps_detected`, `distance_m`, `raw_csv`), `saved_routes` (`segments_json`, `path_sequence_json`, `total_steps_estimated` = distância/0,75).

## 7. Convenções de ângulo (crítico para a bússola)

| Referencial | Origem | Sentido | Onde |
|---|---|---|---|
| Heading do grafo / yaw PDR | pose inicial | anti-horário | backend |
| Rumo de bússola (`webkitCompassHeading`, `360 − alpha`) | Norte | horário | frontend |
| `DeviceOrientationEvent.alpha` | relativo (Android) ou absoluto (`deviceorientationabsolute`) | anti-horário | navegador |

A conversão fica isolada em `frontend/js/sensors/angles.js` (`HEADING_CONVENTION`, `backendHeadingToBearing`, `bearingToBackendYaw`), com **offset de calibração** por segmento (localStorage).

## 8. Frontend (estrutura-alvo da auditoria 003)

```
frontend/
├── index.html (dashboard admin)  recorder.html  routes.html  manifest.json
├── css/  base.css  dashboard.css  recorder.css  routes.css  compass.css
└── js/
    ├── core/        config.js  api.js  dom.js  toast.js
    ├── components/  nav.js  compass.js
    ├── sensors/     angles.js  heading.js  step-detector.js
    ├── routes/      navigation-session.js  route-simulator.js
    └── pages/       dashboard.js  recorder.js  routes.js
```

Regras: HTML sem `<style>`/`<script>` inline; ES modules; sem `alert/confirm`; HTTP só em `js/core/api.js`; URL da API só em `js/core/config.js`; caminhos relativos (funciona no FastAPI e no GitHub Pages); `escapeHtml` em todo texto vindo do backend.
O legado `frontend/static/` foi removido. As páginas são só marcação, com CSS em `frontend/css/` e JS em `frontend/js/`.

## 9. Decisões técnicas (histórico)

- Madgwick local por requisição (evita estado sujo entre caminhadas).
- Madgwick roda **após** a reamostragem (corrigiu `IndexError`) e uma única vez (reuso dos quaternions para o yaw médio).
- Aceleração vertical via quaternion no lugar da magnitude total (limiares recalibrados: 10,3→9,95 e Δa mín 1,2→0,55).
- Anti-shake: média de giroscópio de 4,0 → 2,2 rad/s.
- Modo teste/simulação: a contagem de passos é **local** (`NavigationSession`); o backend só confirma o nó (porque o odômetro do matcher zera por nó e ignora passos fora do cone).

## 10. Convenções de código

- Python: PEP 8, type hints, `HTTPException` (400 payload, 404 ausente).
- Banco: `snake_case`.
- Git: `dev` (CI de sintaxe) e `main` (deploy). Mensagens `feat|fix(escopo): resumo`.
- Auditorias: `auditorias/auditoria-NNN.md`; toda micro-tarefa lista **/add** e **/read** por arquivo.
- Anotações do orquestrador: sufixo POV + número (ex.: `progresso-POV002.md`).

## 11. Como rodar

```bash
cd Backend && uvicorn api.app:app --reload        # http://127.0.0.1:8000  (precisa do MySQL/XAMPP ligado)
cloudflared tunnel --config cloudflared-config.yml run   # HTTPS para celular (iOS exige HTTPS)
python -m compileall Backend                              # checagem de sintaxe (CI)
```
Banco `POV`, usuário `root` sem senha (dev). Tabelas via `Backend/datasets/create_tables.py`; seed via `Backend/others/seed_map.py`.

## 12. Estado atual

| Auditoria | Tema | Status |
|---|---|---|
| 001 | Bússola + `/api/compass_route` | feito (a bússola será refeita na 003) |
| 002 | Aba Rotas, `saved_routes`, modo teste | feito (bugs: passos sempre 0, `/api/reset` duplicado) |
| **003** | **Refatoração do front (css/js), bússola nova, contagem de passos, "Simular rota"** | **feito (T0–T10)** |

Débito que permanece: o heading do grafo é relativo à pose da gravação, não é Norte magnético. Ícone PWA é o SVG em `frontend/assets/icon.svg`.

## 13. Próximos passos

1. Calibração dinâmica de `k` (Weinberg) por altura/histórico do usuário.
2. Yaw absoluto (magnetômetro) também na gravação, para alinhar grafo e bússola.
3. Visão do usuário final (navegação guiada) após fechar a visão admin.
4. Script offline que baixa `/api/sensors_log/{id}/csv` e plota bruto × Butterworth × picos.
