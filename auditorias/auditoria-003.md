# Auditoria 003 — Refatoração completa do Frontend (visão Administrador)

> **Status:** PLANEJADA (nenhuma micro-tarefa executada ainda)
> **Executor:** Aider (via `tools/run_aider.py` ou manualmente com `/add` e `/read`)
> **Orquestrador:** Claude Code — valida cada tarefa antes de liberar a próxima
> **Antecessoras:** `auditoria-001.md` (bússola/endpoint), `auditoria-002.md` (aba Rotas/modo teste)

## 1. Objetivo

1. Separar CSS e JS dos HTML em `frontend/css/` e `frontend/js/`.
2. Refatorar todo o frontend com visual tecnológico e fluido, priorizando a **visão do administrador**.
3. Refazer a bússola de `routes.html`: melhor visual e mais precisa.
4. Corrigir a contagem de passos do modo teste, que fica sempre em 0.
5. Adicionar o botão **"Simular rota"**.
6. Melhorar `CLAUDE.md` e `contexto-IA.md` para as próximas sessões.

## 2. Regras para o Aider (valem para TODAS as tarefas)

- Faça **somente** o que a tarefa pede; use apenas os arquivos listados em `/add`.
- Arquivos em `/read` são só contexto: **não edite**.
- Frontend: HTML contém apenas marcação (sem `<style>` e sem `<script>` inline, só `<script type="module" src="...">`).
- JS em ES modules, sem frameworks, sem `alert()`/`confirm()` (usar `js/core/toast.js`).
- Toda chamada HTTP passa por `js/core/api.js`; a URL da API só existe em `js/core/config.js`.
- Caminhos de CSS/JS/links **relativos** (`css/base.css`, `js/pages/routes.js`, `routes.html`), para funcionar no FastAPI e no GitHub Pages.
- Todo texto vindo do backend inserido via `innerHTML` passa por `escapeHtml()`.
- Não alterar nada em `Backend/pdr/`, `Backend/filters/` ou na lógica de `Backend/map/`.
- Após cada tarefa: um commit (`auto-commits` do Aider) com mensagem `feat|fix(frontend): T<n> <resumo>`.

## 3. Diagnóstico (bugs confirmados no código atual)

| # | Arquivo | Problema | Tarefa |
|---|---|---|---|
| B1 | `frontend/static/js/routes.js` | Passos = `accumulated_distance_m / 0.75`, mas nenhum passo chega ao backend (`/api/localize` nunca é chamado) → sempre 0. A distância ainda zera a cada nó (`Backend/map/topological_matcher.py`). | T4, T6, T7 |
| B2 | `Backend/api/app.py` | `/api/reset` definido 2x (≈ linhas 77 e 231). O primeiro vence e ignora `start_node`. O front manda `start_node` no body JSON, mas o endpoint lê da Query. | T1, T3 |
| B3 | `frontend/static/js/compass.js` | Usa `alpha` cru (anti-horário e relativo no Android); sem `webkitCompassHeading`/`deviceorientationabsolute`; sem compensar `screen.orientation`; sem suavização; salto 359→0; `transform-origin: center bottom` + `translate(-50%,-50%)` gira fora do centro. | T4, T5 |
| B4 | `compass.js` | `render()` injeta `.compass-wrapper` dentro de `#test-compass` (que já é o círculo) → DOM aninhado, IDs duplicados. | T5 |
| B5 | `compass.js` | Listeners em `window` nunca removidos (vazam a cada teste). | T5 |
| B6 | `frontend/index.html` | Lê `data.path_sequence` de `/api/compass_route`, campo que o endpoint não retorna → rota nunca desenhada. | T1, T8 |
| B7 | `frontend/index.html` | Canvas 900×480 esticado por CSS, sem `devicePixelRatio` → borrado; painel admin `#panel-map` escondido (`display:none`). | T8 |
| B8 | todos os HTML | Importam `/static/js/*`, mas o FastAPI serve o front em `/frontend_static` (`/static` é `Backend/static`). Links `/routes` e `/recorder` quebram no GitHub Pages. | T1, T3, T7–T9 |
| B9 | `frontend/recorder.html` | URL da API fixa em produção; cards de histórico com cores claras no tema escuro; contadores duplicados. | T9 |
| B10 | todos | `innerHTML` sem escape; `alert/confirm`; fetch sem timeout nem tratamento de HTTP error. | T3, T7–T9 |
| B11 | `tools/run_aider.py`, `.aider.conf.yml` | Ignora `files` do `task.json`; `--read auditoria-001.md` fixo (arquivo nem está na raiz). | T0 |

### Fatos do backend que o front precisa respeitar (verificados)

- `TARGET_HZ = 30` em `Backend/pdr/processor.py` (o `contexto-IA.md` antigo dizia 50). `weinberg_k=0.45` no processor (default 0.48 em `steps.py`); passo limitado a `[0.40, 0.95]` m.
- `heading_rad` das arestas = yaw do Madgwick (`Quaternion.yaw`, ZYX, **anti-horário**, relativo à pose inicial; não é Norte magnético). O layout 2D do mapa usa `x = d·cos(h)`, `y = d·sin(h)` (convenção matemática).
- O matcher aceita o passo se `|yaw - heading| ≤ 30°` e troca de nó quando `accumulated_distance ≥ distance_m` (zera o odômetro).
- `POST /api/localize` recebe `{step_length_m, yaw_rad}` e retorna `{current_node, accumulated_distance_m}`.
- Consequência para a bússola: o rumo do aparelho (Norte, horário) e o heading do grafo (relativo, anti-horário) são referenciais diferentes → obrigatório ter **calibração** (botão "estou de frente para o corredor") e a constante `HEADING_CONVENTION` isolada em `js/sensors/angles.js`.

## 4. Estrutura final do frontend

```
frontend/
├── index.html  recorder.html  routes.html  manifest.json
├── css/        base.css  dashboard.css  recorder.css  routes.css  compass.css
└── js/
    ├── core/        config.js  api.js  dom.js  toast.js
    ├── components/  nav.js  compass.js
    ├── sensors/     angles.js  heading.js  step-detector.js
    ├── routes/      navigation-session.js  route-simulator.js
    └── pages/       dashboard.js  recorder.js  routes.js
```
`frontend/static/` é removida na T10.

## 5. Micro-tarefas

Ordem obrigatória: T0 → T10. Cada tarefa só começa após o critério de aceite da anterior.

---

### T0 — Infra do Aider e organização das auditorias
**Objetivo:** o Aider receber os arquivos certos; `auditorias/` concentrar todas as auditorias.

- **/add** `tools/run_aider.py` `.aider.conf.yml`
- **/read** `CLAUDE.md` `auditorias/auditoria-003.md`
- **Nota:** `auditoria-002.md` já está em `auditorias/` (nada a mover).

**Instrução (colar no Aider):**
> Em `tools/run_aider.py`: leia `task["files"]` (lista opcional) e passe cada arquivo ao comando como argumento posicional; adicione `--read` para `auditorias/auditoria-003.md` e `contexto-IA.md` (apenas se existirem); crie a pasta `.agent_bus/outbox` se não existir; devolva em `result.json` também `returncode` e `files`. Em `.aider.conf.yml`: troque `read:` por `auditorias/auditoria-003.md` e `contexto-IA.md`. Não mude o modelo.

**Aceite:** `python3 tools/run_aider.py .agent_bus/inbox/task.json` monta o comando com os `files` da task (conferir `result.json`).

---

### T1 — Backend mínimo para o front
**Objetivo:** corrigir B2, B6, B8 e a rota duplicada, sem tocar no PDR.

- **/add** `Backend/api/app.py`
- **/read** `Backend/map/router.py` `Backend/api/schema.py` `Backend/map/topological_matcher.py`

**Instrução:**
> Em `Backend/api/app.py`: (1) remova o **primeiro** `@app.post("/api/reset")` (função `reset_session` sem parâmetro) e mantenha o que aceita `start_node: str = Query(default="Recepcao")`; se o `start_node` não existir em `topo_map.nodes`, use o primeiro nó do mapa em vez de "Recepcao" fixo. (2) Renomeie a função do `GET /api/routes/{route_id}` de `get_route` para `get_saved_route` (evita sobrescrever `get_route` de `/api/route`). (3) Em `get_compass_route`, retorne também `"path_sequence": [origem] + [s["target"] for s in segments]`. (4) Troque os mounts por `app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"))` e `app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"))`, mantendo `/static` do Backend; resolva `FRONTEND_DIR` com `.resolve()`. (5) Mantenha `/`, `/recorder`, `/routes` e adicione `/index.html`, `/recorder.html`, `/routes.html` apontando para os mesmos arquivos. (6) Em `/api/current_location`, inclua `"steps_count"` (inteiro; use `getattr(matcher, "steps_count", 0)`). Não altere nenhum outro endpoint.

**Aceite:** `curl -X POST "http://127.0.0.1:8000/api/reset?start_node=<nó>"` devolve o nó pedido; `/api/compass_route` traz `path_sequence`; `python -m compileall Backend` passa; as pastas `css/` e `js/` precisam existir (a T2 cria `css/`; criar `js/` vazia com `.gitkeep` se rodar antes).

---

### T2 — CSS base (design system)
**Objetivo:** tema tecnológico único reutilizado por todas as páginas.

- **/add** `frontend/css/base.css`
- **/read** `frontend/index.html` `frontend/routes.html` `frontend/recorder.html`

**Instrução:**
> Crie `frontend/css/base.css` com: variáveis `:root` (`--bg:#060a14; --surface; --glass: rgba(15,23,42,.6); --border; --cyan:#22d3ee; --violet:#8b5cf6; --ok:#22c55e; --warn:#f59e0b; --danger:#ef4444; --text; --muted; --radius; --shadow-glow; --font-mono`); reset; `body` com fundo em gradiente radial + grid sutil (`background-image` de linhas a 1px); cards glass (`backdrop-filter: blur`), borda com brilho no hover; `.top-nav` fixa com `.nav-btn`, `.nav-btn.active` com glow e `.badge-admin`; `.status-dot` (online/offline com pulso); botões `.btn`, `.btn-primary` (gradiente cyan→violet), `.btn-ghost`, `.btn-danger`, `.btn-success` com estados hover/active/disabled/focus-visible; inputs/selects; `.form-group`; `.badge`; `.kpi`; `.skeleton` (shimmer); `.modal` + `.modal-content`; `.toast-stack` + `.toast` (ok/erro/info); `.hidden`; utilitário `.mono`. Transições 150–250ms; `@media (prefers-reduced-motion: reduce)` desliga animações; mobile-first (nav rolável horizontal em telas ≤ 480px). Sem JS.

**Aceite:** arquivo único, sem dependências externas (sem CDN/fonts remotas); nenhum seletor por ID.

---

### T3 — Núcleo JS (config, api, dom, toast, nav)
**Objetivo:** base compartilhada; corrige B2 (lado front), B8, B10.

- **/add** `frontend/js/core/config.js` `frontend/js/core/api.js` `frontend/js/core/dom.js` `frontend/js/core/toast.js` `frontend/js/components/nav.js`
- **/read** `Backend/api/app.py` `Backend/api/schema.py` `frontend/static/js/nav.js`

**Instrução:**
> Crie os 5 arquivos (ES modules). **config.js:** exporte `API_BASE_URL` (localhost/127.0.0.1/[::1] → `http://127.0.0.1:8000`; senão `https://api.pov-unimar.com`; permitir override por `localStorage.pov_api_url`), `STEP_LENGTH_DEFAULT = 0.70`, `WEINBERG_K = 0.45`, `STEP_MIN_M = 0.40`, `STEP_MAX_M = 0.95`, `POLL_MS = 500`, `ANGLE_TOLERANCE_DEG = 30`, `STORAGE_KEYS` (`stepLength`, `headingOffset`, `startPoint`). **api.js:** função interna `request(path, {method, body, query, timeout=8000})` com `AbortController`, `Content-Type` JSON, e, se `!res.ok`, `throw new ApiError(detail, status)` usando `detail` do JSON; exporte `getMap`, `getRoutes`, `getRoute(id)`, `createRoute({start_node,end_node,name})`, `deleteRoute(id)`, `getCompassRoute(start,end)`, `reset(startNode)` (POST `/api/reset` com **query** `start_node`), `localize(stepLengthM, yawRad)` (POST `/api/localize` `{step_length_m, yaw_rad}`), `currentLocation()`, `saveCheckpoint(name)`, `saveEdge({source,target,distance_m,heading_rad})`, `processRaw({source,target,samples})`, `ping()`. **dom.js:** `$`, `$$`, `escapeHtml`, `fillSelect(select, nodes, placeholder)` (usa `textContent`/`option` via DOM, não concatenação de HTML), `formatNum(n, d)`. **toast.js:** `toast(msg, type='info', ms=3500)` criando `.toast-stack` sob demanda e `confirmDialog(msg, {okLabel, danger})` retornando `Promise<boolean>` com modal acessível (Esc cancela, foco no botão). **nav.js:** `insertTopNav(active)` com links **relativos** `index.html`, `recorder.html`, `routes.html`, badge "ADMIN", `.status-dot` atualizado por `ping()` a cada 10s (limpar intervalo no `pagehide`).

**Aceite:** nenhum `fetch` fora de `api.js`; nenhum `alert`; `node --check` em cada arquivo passa.

---

### T4 — Sensores (ângulos, rumo, detector de passos)
**Objetivo:** base da precisão da bússola e da contagem de passos (B1, B3).

- **/add** `frontend/js/sensors/angles.js` `frontend/js/sensors/heading.js` `frontend/js/sensors/step-detector.js`
- **/read** `Backend/pdr/steps.py` `Backend/map/topological_matcher.py` `Backend/filters/quaternion.py` `frontend/recorder.html` `frontend/js/core/config.js`

**Instrução:**
> **angles.js:** `normalizeDeg(a)` → [0,360); `signedDelta(from,to)` → (-180,180]; `degToRad/radToDeg`; `circularEma(prev, next, alpha)` (média via sin/cos); `unwrap(prevContinuous, newDeg)` devolve ângulo contínuo sem saltos de 360°; `cardinal(deg)` → N/NE/L/SE/S/SO/O/NO; `export const HEADING_CONVENTION = 'ccw'` (`'ccw'` = o heading do grafo cresce no sentido anti-horário, como o yaw do Madgwick; `'cw'` = rumo de bússola); `backendHeadingToBearing(rad, offsetDeg=0)` converte para rumo horário de bússola conforme `HEADING_CONVENTION`; `bearingToBackendYaw(deg, offsetDeg=0)` faz o inverso. Documente em comentário que o heading do grafo é relativo à pose inicial (não é Norte magnético) e por isso existe `offsetDeg`. **heading.js:** classe `HeadingProvider` com `start()` (pede `DeviceOrientationEvent.requestPermission` no iOS; deve ser chamado dentro de gesto do usuário), `stop()`, `onHeading(cb)`, `get offsetDeg`, `calibrate(targetBearingDeg)` (offset = target − rumo bruto, salvo em localStorage), `getYawRadForBackend()`. Fonte de rumo por prioridade: `event.webkitCompassHeading` (iOS) → `deviceorientationabsolute` com `(360 - alpha)` → `deviceorientation` com `(360 - alpha)` marcado `source:'relative'`. Compense `screen.orientation.angle`. Emita `{headingDeg, source, accuracy}` e aplique `circularEma` (alpha 0.15) antes de emitir. Também suporte `injectHeading(deg)` (usado pelo simulador e por teclado ← → no desktop). **step-detector.js:** classe `StepDetector` com `start()`, `stop()`, `onStep(cb)` usando `devicemotion` (`accelerationIncludingGravity`); magnitude com low-pass (EMA 0.2); média móvel de 1,5 s; pico quando `mag > max(9.95, média + 0.12)` e subida seguida de descida; período refratário 330 ms; aceite apenas se `0.55 ≤ Δa ≤ 4.5` (Δa = pico − vale da janela); comprimento `k·Δa^0.25` com `k = WEINBERG_K`, limitado a `[STEP_MIN_M, STEP_MAX_M]`; callback `{length, ts, deltaA}`; método `feed(sample)` para teste sem sensor; `reset()`.

**Aceite:** `normalizeDeg(-10)=350`; `signedDelta(350,10)=20`; `signedDelta(10,350)=-20`; `unwrap` nunca devolve salto > 180° entre amostras consecutivas; `StepDetector.feed` com senóide 1,8 Hz de amplitude 1,5 m/s² detecta ≈ 1,8 passos/s.

---

### T5 — Componente Bússola (visual + precisão)
**Objetivo:** substituir `frontend/static/js/compass.js` (B3, B4, B5).

- **/add** `frontend/js/components/compass.js` `frontend/css/compass.css`
- **/read** `frontend/js/sensors/angles.js` `frontend/js/sensors/heading.js` `frontend/static/js/compass.js` `frontend/css/base.css`

**Instrução:**
> Crie o componente `Compass` (ES module) que desenha um **SVG** dentro do elemento recebido (sem criar wrappers aninhados e sem IDs fixos, use classes): anel externo com 72 marcações (a cada 5°; maiores a cada 15° e 30°), rótulos N (destaque cyan), L, S, O e graus a cada 30°; **rosa gira** em `-heading`; **seta-alvo** neon (grupo SVG separado) em `bearingAlvo - heading`; marcador fixo de "frente" no topo; **cone de tolerância ±30°** (usar `ANGLE_TOLERANCE_DEG`) em torno da frente, que fica verde quando `|delta| ≤ 30°`, âmbar até 90°, vermelho acima; ponto central e anéis concêntricos com glow. API: `constructor(el)`, `setHeading(deg)`, `setTarget(bearingDeg|null)`, `setReadout({target, distanceM})`, `destroy()`. Animação com `requestAnimationFrame` interpolando o ângulo exibido até o alvo (fator 0.2) usando `unwrap` (sem `transition` CSS na rotação e sem salto 359→0); parar o rAF quando `destroy()` ou aba oculta (`visibilitychange`). Leituras abaixo da bússola: rumo atual `123° SE`, delta assinado em texto ("Vire 35° à direita", "Siga em frente", "Vire à esquerda 120°", "Meia-volta"), fonte do rumo (`absolute|webkit|relative`) com aviso "rumo relativo, calibre" quando relativo, e botão **"Calibrar (estou de frente para o corredor)"** que dispara o evento `compass:calibrate`. Acessibilidade: `role="img"` + `aria-label` atualizado a cada 500 ms. `compass.css`: tamanhos responsivos com `clamp()`, glow, estados de cor via classes `.is-aligned/.is-close/.is-off`, `prefers-reduced-motion`. Nenhum `addEventListener` em `window` dentro do componente (o rumo chega via `setHeading`).

**Aceite:** instanciar e destruir 20× não deixa listeners nem rAF ativos; girar de 359° para 1° anima +2° e não -358°; DOM do componente tem 1 único `<svg>` raiz.

---

### T6 — Sessão de navegação e simulador
**Objetivo:** fonte única de contagem para teste real e simulação (B1).

- **/add** `frontend/js/routes/navigation-session.js` `frontend/js/routes/route-simulator.js`
- **/read** `frontend/js/core/api.js` `frontend/js/core/config.js` `frontend/js/sensors/step-detector.js` `frontend/js/sensors/angles.js` `Backend/map/topological_matcher.py`

**Instrução:**
> **navigation-session.js:** classe `NavigationSession(route, {stepLength})` com `EventTarget`: estado `segmentIndex`, `steps`, `distTotal`, `distSegment`, `visited[]`, `startedAt`, `finished`. `registerStep(lengthM)`: soma passo e distância, `distSegment += length`; quando `distSegment ≥ segment.distance_m` avança o segmento (carrega o excedente para o próximo), emite `segment` e, no último, `finish`. `syncBackendNode(nodeName)`: se o nó do backend for o `target` do segmento atual (ou de um posterior), avança o segmento imediatamente (backend vence em divergência). Getters: `expectedSteps = Math.round(route.total_distance_m / stepLength)`, `progress` (0–1 por distância), `remainingSegmentM`, `currentSegment`, `bearingTarget(offsetDeg)` via `backendHeadingToBearing`. Eventos: `step`, `segment`, `finish`, `update`. **route-simulator.js:** classe `RouteSimulator(session, {onHeading, sync=false, stepLength})`: `start()`, `pause()`, `resume()`, `stop()`, `setSpeed(1|2|4)`. Cadência 1,8 passos/s × velocidade (timer por passo), comprimento do passo = `stepLength` ±5% (aleatório), chama `session.registerStep`. O rumo simulado = bearing do segmento atual: ao trocar de segmento faz curva interpolada em ~600 ms (caminho mais curto via `signedDelta`) e jitter ±3°, emitindo por `onHeading(deg)`. Se `sync=true`: no início `api.reset(route.start_node)` e, por passo, `api.localize(length, bearingToBackendYaw(deg))`, aplicando `session.syncBackendNode(resp.current_node)`; erros de rede viram evento `error` sem parar a simulação. Ao finalizar, expõe `summary()` → `{steps, distance, durationS, visited}`. Usar `performance.now()` e limpar todos os timers em `stop()`.

**Aceite:** simulando uma rota de 3 segmentos (10 m, 5 m, 8 m) com passo 0,70 m e sem ruído, termina com `distTotal ≈ 23,0 m (±0,7)` e `steps ≈ 33 (±2)`; `segmentIndex` avança 0→1→2; `progress` chega a 1; `stop()` não deixa timers.

---

### T7 — Página Rotas (lista, Testar, Simular)
**Objetivo:** reconstruir `routes.html` com a bússola nova e o botão "Simular rota" (B1, B8, B10).

- **/add** `frontend/routes.html` `frontend/css/routes.css` `frontend/js/pages/routes.js`
- **/read** `frontend/js/components/compass.js` `frontend/js/components/nav.js` `frontend/js/routes/navigation-session.js` `frontend/js/routes/route-simulator.js` `frontend/js/sensors/heading.js` `frontend/js/sensors/step-detector.js` `frontend/js/core/api.js` `frontend/js/core/dom.js` `frontend/js/core/toast.js` `frontend/js/core/config.js` `frontend/css/base.css` `frontend/css/compass.css` `frontend/static/js/routes.js`

**Instrução:**
> `routes.html`: somente marcação, `<link>` para `css/base.css`, `css/compass.css`, `css/routes.css`, `<script type="module" src="js/pages/routes.js">`; header com título e **"+ Nova rota"**; lista de rotas (skeleton enquanto carrega, estado vazio com CTA); modal de nova rota (origem, destino, nome); overlay tela cheia de execução. `routes.js` (sem `window.xxx` globais, usar `addEventListener` e delegação de eventos): carregar nós e rotas via `api.js`; card da rota com nome, origem → destino, distância, passos esperados (`Math.round(dist / stepLength)`) e botões **🧪 Testar**, **▶ Simular rota**, **🗑 Excluir** (com `confirmDialog`). Campo "Comprimento do passo (m)" (padrão 0,70; salvo em localStorage; recalcula esperados). **Testar** (real): `HeadingProvider.start()` e `StepDetector.start()` dentro do clique; `api.reset(route.start_node)`; cada passo → `session.registerStep(length)` + `api.localize(length, heading.getYawRadForBackend())`; polling `currentLocation()` a cada `POLL_MS` chamando `session.syncBackendNode`. **Simular rota:** cria `NavigationSession` + `RouteSimulator`, ligando `onHeading` → `compass.setHeading`. Overlay: bússola grande (componente), nome da rota, segmento atual `A → B`, distância restante do segmento, **passos `X / Y`** (X vem de `session.steps`, nunca de `accumulated_distance`), distância `X m / Y m`, barra de progresso segmentada (um trecho por segmento, proporcional à distância), lista de nós (visitado/atual/pendente), controles ▶/⏸, velocidade 1×/2×/4×, checkbox "Sincronizar com backend" (só simulação), **Finalizar**. Ao concluir: painel de resumo (passos, distância, tempo, nós) com **Repetir** e **Fechar**. O evento `compass:calibrate` chama `heading.calibrate(bearingDoSegmentoAtual)`. Ao fechar o overlay: `compass.destroy()`, `heading.stop()`, `detector.stop()`, `simulator.stop()`, limpar polling e `api.reset()`. Sem `alert/confirm/prompt`.

**Aceite:** clicar em "Simular rota" faz passos subirem continuamente (nunca fica em 0), bússola gira suave, segmento muda, resumo aparece; abrir/fechar 10× o overlay não acumula timers/listeners; links do nav funcionam abrindo o arquivo direto (sem servidor).

---

### T8 — Dashboard do administrador (`index.html`)
**Objetivo:** painel admin tecnológico com mapa nítido e rota correta (B6, B7).

- **/add** `frontend/index.html` `frontend/css/dashboard.css` `frontend/js/pages/dashboard.js`
- **/read** `frontend/js/core/api.js` `frontend/js/core/dom.js` `frontend/js/core/toast.js` `frontend/js/core/config.js` `frontend/js/components/nav.js` `frontend/css/base.css` `Backend/map/topological_map.py`

**Instrução:**
> `index.html` apenas marcação (links `css/base.css`, `css/dashboard.css`, `<script type="module" src="js/pages/dashboard.js">`). Layout: faixa de **KPIs** (nós, arestas, rotas salvas, status da API, nó atual); coluna do mapa (canvas) e coluna **Admin** sempre visível com: (a) novo checkpoint, (b) nova conexão (origem, destino, distância m, **heading em graus** convertido para rad antes do envio; mostrar o valor em rad ao lado), (c) "Resetar sessão PDR" com seletor de nó inicial (`api.reset`), (d) seletor de destino que calcula a rota planejada. `dashboard.js`: canvas com `devicePixelRatio` (ajustar `width/height` reais ao tamanho CSS e a `ResizeObserver`), auto-fit com margem, **zoom (roda/pinça) e pan (arrastar)**, duplo clique reajusta; desenhar arestas (com distância ao meio), rota planejada derivada de `segments`/`path_sequence` de `getCompassRoute` (linha verde com fluxo animado), trilha visitada (tracejada ciano), nós com rótulo escapado, posição atual pulsante (anel animado via rAF, parado se `prefers-reduced-motion`); tooltip ao passar o mouse no nó (nome + vizinhos). Polling `currentLocation()` a cada `POLL_MS` pausando com `visibilitychange`. Rota recalculada quando o nó atual muda e há destino selecionado. Erros via `toast`; sem `alert`.

**Aceite:** ao escolher um destino a linha verde aparece; canvas nítido em telas de alta densidade; formulário de conexão grava `heading_rad = graus·π/180`; nenhum `<style>`/`<script>` inline em `index.html`.

---

### T9 — Recorder (`recorder.html`)
**Objetivo:** modernizar a telemetria e unificar o contador de passos (B9, B10).

- **/add** `frontend/recorder.html` `frontend/css/recorder.css` `frontend/js/pages/recorder.js`
- **/read** `frontend/js/core/api.js` `frontend/js/core/dom.js` `frontend/js/core/toast.js` `frontend/js/core/config.js` `frontend/js/components/nav.js` `frontend/js/sensors/step-detector.js` `frontend/js/sensors/heading.js` `frontend/css/base.css` `Backend/api/schema.py`

**Instrução:**
> Migrar para marcação pura + `css/recorder.css` + `js/pages/recorder.js` preservando o contrato do payload (`timestamp` em segundos, `accel_x/y/z`, `gyro_x/y/z` em rad/s, `mag_x/y/z` = alpha/beta/gamma) enviado por `api.processRaw`. Usar `HeadingProvider` para alpha/beta/gamma e `StepDetector` para o contador ao vivo (substitui o limiar fixo 11,8). UI: origem/destino, botão grande de gravar com estado "gravando" pulsante e cronômetro, grid de telemetria (aceleração, giroscópio, orientação) com **mini-sparkline de |acc|** em `<canvas>` (últimos ~200 pontos), badge do giroscópio, **um único** contador de amostras, passos ao vivo, histórico em cards **escuros** (válido/descartado, passos processados × ao vivo, distância, hora, mensagem). Resultado da gravação em `toast`, sem `alert`. Pedir permissões de sensor dentro do clique de gravar. Remover listeners de sensor ao parar e ao `pagehide`. Usar `escapeHtml` no histórico.

**Aceite:** payload idêntico ao anterior (validar com `Backend/api/schema.py::RawSampleSchema`); histórico legível no tema escuro; sem `<style>`/`<script>` inline.

---

### T10 — Limpeza e documentação
**Objetivo:** remover legado e fechar a auditoria.

- **/add** `frontend/manifest.json` `README.md` `.gitignore`
- **/read** `auditorias/auditoria-003.md` `contexto-IA.md` `.github/workflows/frontend-deploy.yml`
- **Antes (manual):** `git rm -r frontend/static`

**Instrução:**
> `frontend/manifest.json`: `start_url` `./index.html`, `scope` `./`, `theme_color` `#22d3ee`, `background_color` `#060a14`; remova as referências a `/static/icon-192.png` e `/static/icon-512.png` (não existem) ou aponte para um SVG em `frontend/assets/icon.svg` (criar se usar). `README.md`: atualize a seção do frontend (estrutura `css/` + `js/`, como abrir as páginas, "Simular rota", calibração da bússola). `.gitignore`: garanta `.aider*`, `.agent_bus/outbox/` e `venv/`.

**Aceite:** `grep -rn "static/js" frontend` não retorna nada; `grep -rnE "<style|<script>" frontend/*.html` não retorna nada.

## 6. Verificação final (orquestrador)

1. `cd Backend && uvicorn api.app:app --reload` → abrir `/`, `/recorder`, `/routes`: console sem 404/erros.
2. `POST /api/reset?start_node=X` devolve `X`; `/api/compass_route` traz `path_sequence`.
3. Dashboard: rota verde visível ao escolher destino; canvas nítido; zoom/pan funcionam.
4. Rotas → **Simular rota**: passos sobem sem ficar em 0, distância final ≈ soma dos segmentos, bússola sem salto em 0°/360°, resumo ao final; com "Sincronizar com backend", `/api/current_location` acompanha os nós.
5. Celular via túnel HTTPS: permissões iOS pedidas no clique, fonte do rumo exibida, passos reais incrementam; calibrar alinha a seta ao corredor.
6. `python -m compileall Backend` passa; nenhum bloco inline nos HTML; `node --check frontend/js/**/*.js`.

## 7. Riscos e pontos em aberto

- **Referencial do heading:** o yaw do grafo é relativo à pose inicial da gravação do corredor; se corredores foram gravados com orientações diferentes do aparelho, a seta pode errar mesmo calibrada. Mitigação: calibração por segmento; solução definitiva fica para a próxima auditoria (usar magnetômetro/rumo absoluto também na gravação).
- `matcher` só avança com `|yaw − heading| ≤ 30°`; passos fora do cone não somam distância no backend (por isso a sessão local usa a própria contagem e deixa o backend só sincronizar o nó).
- iOS exige HTTPS e gesto do usuário para sensores (usar o túnel Cloudflare).
- Ícones PWA inexistentes (tratados na T10).

## 8. Log de progresso

| Tarefa | Status | Commit | Observações |
|---|---|---|---|
| T0 | pendente | – | – |
| T1 | pendente | – | – |
| T2 | pendente | – | – |
| T3 | pendente | – | – |
| T4 | pendente | – | – |
| T5 | pendente | – | – |
| T6 | pendente | – | – |
| T7 | pendente | – | – |
| T8 | pendente | – | – |
| T9 | pendente | – | – |
| T10 | pendente | – | – |
