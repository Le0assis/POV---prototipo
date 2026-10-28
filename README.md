# Documentação Técnica e Guia de Execução — Projeto POV (PDR Pipeline)

O **POV** é um sistema de Pedestrian Dead Reckoning (PDR) e mapeamento topológico. Ele processa dados inerciais brutos (acelerômetro e giroscópio), realiza fusão sensorial 3D via **Filtro de Madgwick**, isola a aceleração vertical real da Terra, aplica filtragem **Butterworth** e detecta passos por variação de amplitude (Modelo de Weinberg). O sistema grava os registros brutos em formato CSV no MySQL para análise de sinal e auditoria de erros.

---

## 1. Arquitetura do Pipeline PDR

```text
[Amostras Brutas] ──► [Reamostratagem Uniforme (TARGET_HZ)]
                              │
                              ▼
                 [Madgwick Attitude Estimator]
                              │
                              ▼
            [Isolamento de Aceleração Vertical Real]
                              │
                              ▼
            [Trava Global de Chacoalho (Giroscópio)] ──(Se Exceder)──► [Log: Inválido]
                              │ (Se Normal)
                              ▼
              [Filtro Passa-Baixas Butterworth]
                              │
                              ▼
            [Detecção de Picos / Comprimento do Passo]
                              │
                              ▼
        [Persistência do Grafo + Gravação de LOG CSV]

```

---

## 2. Estrutura do Projeto

```text
POV---prototipo/
├── Backend/
│   ├── api/
│   │   └── app.py                     # API FastAPI (Endpoints REST e envio de CSV)
│   ├── datasets/
│   │   ├── create_tables.py           # Criação de tabelas no MySQL (Inc. sensors_log)
│   │   ├── generate_sample_dataset.py # Gerador de massa de testes PDR
│   │   ├── ManagerDatabase.py         # Gerenciador de conexões SQL
│   │   └── sample_walk.csv            # Amostras para simulação
│   ├── filters/
│   │   ├── attitude_estimator.py     # Wrapper de altitude/orientação
│   │   ├── butterworth.py            # Filtro Butterworth Passa-Baixas 2ª Ordem
│   │   ├── madgwick.py               # Algoritmo de Fusão Sensorial Madgwick
│   │   ├── quaternion.py             # Vetores 3D e isolamento de Aceleração Vertical
│   │   └── signal_filter.py          # Utilitários de sinal
│   ├── map/
│   │   ├── MapDatabaseManager.py     # Persistência de grafos, arestas e logs de sensores
│   │   ├── router.py                 # Algoritmos de roteamento topológico
│   │   ├── topological_map.py        # Grafo de checkpoints
│   │   └── topological_matcher.py    # Casamento de posições em mapa
│   ├── others/
│   │   ├── evaluate_steps.py         # Conta passos de um CSV contra o rótulo
│   │   └── seed_map.py               # Alimentador de posições iniciais do mapa
│   ├── pdr/
│   │   ├── processor.py              # Pipeline principal de PDR e validação
│   │   └── steps.py                  # Detector de picos de passos (Weinberg)
│   └── requirements.txt
├── frontend/
├── cloudflared-config.yml
└── README.md

```

---

## 3. Pré-requisitos

* **Git**
* **Python 3.11+**
* **XAMPP** (Apache e MySQL)
* **Cloudflare CLI (`cloudflared`)** *(Opcional: Apenas se for expor para rede externa)*

A detecção corta a gravação onde o intervalo entre timestamps passa de `StepDetectorConfig.max_gap_s` (padrão **0,25 s**) e não interpola esse vão. O valor é da config, não uma constante solta: `StepDetectorConfig(max_gap_s=0.5)` ou `python others/evaluate_steps.py arquivo.csv --max-gap-s 0.5` (a partir de `Backend/`). Se o Chrome no MIUI engasgar e o `devicemotion` furar cerca de **0,5 s**, o padrão de 0,25 s parte uma passada contínua em dois trechos; nesse caso suba o limite para ~0,5 s.

---

## 4. Passo a Passo de Instalação e Configuração

### Passo 1: Clonar o Repositório e Criar Ambiente Virtual

```bash
# 1. Clonar o projeto
git clone https://github.com/Le0assis/POV---prototipo
cd POV---prototipo/Backend

# 2. Criar ambiente virtual
python -m venv venv

# 3. Ativar o ambiente virtual
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# 4. Instalar dependências
pip install -r requirements.txt


## Instalar plugin do sql
pip install mysql-connector-python

## instalar cloudflare tunnel (scripts devem estar habilitados)
winget install --id Cloudflare.cloudflared

```
### Passo 2: Configurar o Banco de Dados (MySQL)

1. Inicie o serviço **MySQL** pelo painel do **XAMPP**.
2. Abra o browser em `http://localhost/phpmyadmin`.
3. Crie um banco de dados chamado **`POV`** (UTF-8 General CI).

### Passo 3: Inicializar a Estrutura e Povoar o Banco

Com o ambiente virtual ativado no diretório `Backend/`, execute a sequência obrigatória de inicialização:

```bash
# 1. Criar tabelas no banco (Incluindo a tabela sensors_log para auditoria)
python -m datasets.create_tables

# 2. Gerar dataset base de passos
python -m datasets.generate_sample_dataset

# 3. Povoar o mapa topológico base com checkpoints
python -m others.seed_map

```

---

## 5. Ordem Correta de Execução do Sistema

Para rodar a aplicação completa com testes e logs de sensores, abra 3 terminais separados.

### Terminal 1: Servidor Principal FastAPI (Backend PDR)

Acesse o diretório `Backend` com o `venv` ativado:

```bash
cd Backend
# Senha do editor: só o hash argon2id. Gere com python scripts/hash_password.py
# e cole em .env na raiz (EDITOR_PASSWORD_HASH). Não exporte a senha em claro.
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers

```

> **Status de Sucesso:** API pronta em `[http://127.0.0.1:8000](http://127.0.0.1:8000)` e Swagger em `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`.

`python -m datasets.create_tables` cria o schema de `DB_NAME` se ele não existir (`CREATE DATABASE IF NOT EXISTS`, utf8mb4) e aplica as migrações. Não apaga tabela nem linha. Ver a seção **Aplicar o banco** abaixo. `GET /api/map-config` responde **500** com a mensagem pedindo essa migração quando a tabela ainda não existe.

### Senha do editor do mapa

O arquivo `.env` está no `.gitignore`. O exemplo versionado é `.env.example`, sem senha e sem hash. Há uma senha só. No `.env` fica `EDITOR_PASSWORD_HASH`, um hash argon2id. Gere com `python scripts/hash_password.py` a partir de `Backend/` (a senha é pedida no terminal, não vai para o histórico). A API carrega o `.env` da raiz na subida; uma variável já exportada no shell não é substituída. O header continua `X-Editor-Password`. A comparação é `PasswordHasher.verify` (argon2id). Oito senhas erradas no mesmo cliente, em cinco minutos, respondem **429**. A contagem reserva a tentativa no mesmo lock antes do argon2: as que estão em curso mais as que já falharam. No limite a resposta é **429**, sem conferir. Senha certa ou **503** devolve a reserva; senha errada fica contada. No máximo quatro conferências argon2 ao mesmo tempo. Quem não pega vaga em cerca de 2s responde **503** com `Retry-After`. Uma senha que acabou de conferir fica em cache por cerca de 60s, na chave do HMAC dela: só a mesma senha confere, e header ausente ou vazio nunca passa pelo cache. `CF-Connecting-IP` e `X-Forwarded-For` só entram se o par do socket estiver em `TRUSTED_PROXIES` (lista separada por vírgula de IPs ou CIDRs; `*` e `/0` são ignorados). No `X-Forwarded-For` vale o endereço mais à direita que não está nessa lista: o da esquerda pode ser forjado. Sem essa variável, os headers não mudam o cliente. O uvicorn, no padrão, trata `127.0.0.1` como proxy e reescreve o par a partir de `X-Forwarded-For`. O comando acima usa `--no-proxy-headers` para o par continuar sendo o socket. Não use `*`.

| Situação | Resposta |
| --- | --- |
| `EDITOR_PASSWORD_HASH` ausente, vazia ou inválida | **503** em toda escrita protegida |
| Header ausente ou senha diferente | **401** |
| Tentativas demais (senha errada) | **429** |
| Sem vaga de argon2 depois da espera | **503** com `Retry-After` |
| Senha correta | a escrita segue |

Escritas protegidas: `POST /api/checkpoints`, `PATCH /api/checkpoints/{name}/position`, `POST /api/edges`, `POST /api/edges/process-raw`, `PUT /api/map-config`, `POST /api/routes`, `DELETE /api/routes/{id}`. `POST /api/reset` também, e só responde se `POV_ENABLE_TEST_ROUTES` estiver ligada; sem a flag é **404**. `GET /api/sensors_log/{id}/csv` exige a mesma senha.

Leituras públicas, entre elas `GET /api/health`, `GET /api/map`, `GET /api/map-config`, `GET /api/connections`, `GET /api/connections/{id}` e `GET /api/pdr/config`. `GET /health` e `GET /api/health` não abrem MySQL: **200** `{"status":"ok"}` se o grafo subiu com nó e aresta. Grafo vazio ou erro na carga responde **503** (`status` `empty` ou `error`, motivo em `detail`). Em `POV_ENV=production` o processo não sobe nesses casos. O nome do checkpoint compara com `strip`, espaços internos colapsados e `casefold`. O acento continua distinto (`Recepção` não é `Recepcao`). O rótulo exibido é o da primeira gravação: `quarto` e ` QUARTO ` acham `Quarto` e a rota usa esse texto. A aresta no SQL continua no rótulo gravado (`CAST AS BINARY`). Sem o nó, a rota responde **404**. `POST /api/localize` e `GET /api/current_location` ficam atrás da mesma flag de teste (padrão desligada). Sem checkpoint, essas rotas nascem sem posição (`current_node` nulo). `POST /api/reset?start_node=` define o ponto; sem o nome a origem fica vazia; nome inexistente responde **404**. O matcher e o caminho visitado são por aparelho: o cliente manda `X-Pov-Session` (8 a 64 caracteres: letras, números, `_` e `-`). Sem o header, ou com um id inválido, a resposta é **400**. Uma sessão não vê a outra. O aplicativo Vite não chama essas rotas.

### API pública, CORS e banco

A API de produção é `https://api.pov-unimar.com`. Com `POV_ENV=production`, o CORS aceita só `https://pov-unimar.com` e `https://www.pov-unimar.com`. Sem `POV_ENV`, o padrão é desenvolvimento: `localhost` e `127.0.0.1` nas portas do uvicorn (8000), do Live Server (5500) e da 3000. `CORS_ORIGINS` (vírgulas) substitui essa lista. A resposta não manda `Access-Control-Allow-Credentials`. Os registros DNS estão em `docs/dns.md`.

O MySQL continua o do XAMPP. A API lê `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`. Sem usuário ou senha no ambiente, a conta não é preenchida: não vira `root` nem uma senha vazia inventada. Host, porta e schema, se faltarem, ficam `localhost`, `3306` e `POV`. Com `POV_ENV=production` as cinco variáveis são obrigatórias, `DB_USER` não pode ser `root` e a senha não pode ser vazia. Se alguma dessas regras falha, o processo para na subida e a mensagem não contém a senha. A API não lê `DB_ADMIN_USER` nem `DB_ADMIN_PASSWORD`. Há um pool só, em `ManagerDatabase` (no máximo 8 sessões ociosas e 32 abertas). Antes de reusar, faz ping; se a sessão caiu, reconecta uma vez. Pool esgotado continua **503** com `Retry-After`. Erro de SQL continua **500** genérico. `localhost` na conexão vira `127.0.0.1`. O nome do schema é exatamente `POV`: no Linux, `pov` é outro banco. A API com `DB_NAME=POV` responde `1049 Unknown database` enquanto esse schema não foi criado. O matcher de `/api/localize` não é global: cada `X-Pov-Session` tem o seu.

### Aplicar o banco

Na raiz do repositório, com o `.env` (ou o shell) definindo `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD`. Os scripts não herdam o default da API e não entram como root se a variável faltar: param com o nome do que falta.

`create_tables` ainda precisa de `DB_ADMIN_USER` e `DB_ADMIN_PASSWORD` para `CREATE DATABASE`, `CREATE USER` e `GRANT`. No XAMPP local essa conta é `root` sem senha, escrita no ambiente. O seed roda depois, só com `DB_USER=pov`, e só lê e insere.

```bash
cd Backend
# No XAMPP local, no .env: DB_ADMIN_USER=root e DB_ADMIN_PASSWORD vazio.
# DB_USER=pov e DB_PASSWORD com a senha dessa conta.
# export DB_POV_PASSWORD='senha-do-pov'   # só se a conta pov ainda não existe
python -m datasets.create_tables
python others/seed_map.py
```

O que isso faz, e o que não faz:

- `CREATE DATABASE IF NOT EXISTS POV` com `utf8mb4` / `utf8mb4_unicode_ci`. Schema que já existe não é recriado nem esvaziado.
- `GRANT` de `POV.*` para `pov@localhost` e `pov@127.0.0.1` (a API liga em `127.0.0.1`). Conta que já existe não troca de senha. Sem `DB_POV_PASSWORD` (e sem `DB_USER=pov`), a conta nova não é criada; o GRANT avisa e segue.
- Tabelas com `CREATE TABLE IF NOT EXISTS`. Coluna e índice novos só entram depois de olhar o `information_schema`.
- Migração 002 não dá `DELETE` em `edges`. Cópias do mesmo sentido (inclusive `Sala` e `sala`, que o unique trata como iguais) ficam na tabela. `dup_rank` 0 é a aresta cujo `source_node` e `target_node` batem com `checkpoints.name` em comparação `BINARY`; empate, o maior `id`. Se nenhuma bater, o maior `id` continua canônico e o script avisa. As outras ficam com 1, 2, … Rodar de novo recalcula o rank (passa por um valor negativo para não colidir no unique) e não apaga linha. O mapa e o upsert usam só `dup_rank` 0.
- Rode `create_tables` antes de subir esta versão da API. A leitura filtra `dup_rank`. A coluna nasce na migração, com default 0. Sem ela o SELECT do mapa falha; com ela, a linha antiga continua no mapa.
- Seed (`others/seed_map.py`) usa o mesmo `DB_NAME` e entra como `pov`. Não abre sessão com `DB_ADMIN_USER`. `INSERT ... ON DUPLICATE KEY UPDATE` não muda checkpoint nem distância que já existam.
- Rodar o comando de novo é seguro. Não há `DROP`, `TRUNCATE` nem `DELETE` de dado de mapa.

`pov_save_repro` e qualquer outro schema que não seja o `DB_NAME` ficam intocados. Se o mapa real estiver num nome diferente de `POV`, ajuste `DB_NAME` para esse nome antes de rodar. Não copie à mão e não apague o antigo.

### Mapa, arestas e trajetória

- `edges` é a única fonte do grafo: uma linha canônica por sentido (`dup_rank` 0; o unique é `(source_node, target_node)` ou, se já havia cópia, `(source_node, target_node, dup_rank)`). `saved_routes` é histórico e não entra no mapa.
- `origin` no banco e na API é `manual` ou `recorded` (o exemplo do contrato do front usa a palavra `recording`; o valor gravado é `recorded`).
- Aresta antiga: ao criar a coluna, `origin='recorded'` se existir qualquer `sensors_log` do par source/target, mesmo com `is_valid=0` (logs antigos não preenchiam o campo). Sem log, fica `manual`. A classificação não roda de novo. `is_valid` vale só para gravações novas: mediana, `samples_count` e `active_trace_id`.
- `origin='manual'` conserva distância e heading. Sem manual, a distância é a mediana das `walk_traces` válidas daquele sentido e o heading é a média circular. `active_trace_id` aponta a válida mais recente. `samples_count` é quantas trajetórias válidas aquele sentido tem, e sobe mesmo quando a distância manual permanece.
- `started_at` e `ended_at` são `DATETIME(3)` sem fuso, gravados em UTC. Quem lê trata o valor naive como UTC.
- `GET /api/map` devolve `pos_x_px` e `pos_y_px` em cada checkpoint (planta, origem no canto superior esquerdo, y para baixo) e as arestas do grafo carregado só de `edges`.
- `GET /api/connections` agrupa o par físico: uma entrada, com `reverse_edge_id` para o front não desenhar duas vezes. O sentido listado é o que tem `active_trace_id`; se nenhum tiver, o de menor id. `include_path` default é true; `false` omite `path`. Aresta sem trajetória devolve um segmento reto `[{x:0,y:0,t:null},{x:d·cos(h),y:d·sin(h),t:null}]`. `GET /api/connections/{id}` devolve aquele sentido (não troca pelo par) e `traces`.
- `POST /api/edges/process-raw` grava `sensors_log` (`steps_detected`, `distance_m`, `is_valid`) e a trajetória (`walk_traces` + `walk_steps`) do sentido andado, numa transação. A conexão abre só em volta do SQL, no thread do endpoint, e volta ao pool no fim. A detecção de passos não segura sessão. Se o connect falha, a rota responde 503 e não usa uma conexão de boot. `connect` tem prazo de 5 s e não usa named pipe (`localhost` vira `127.0.0.1`). Arquivo estático não abre banco. O lock da gravação é o par ordenado `(source, target)`, nunca um lock global: primeiro o mutex, depois BEGIN, os checkpoints em `FOR UPDATE` por nome e a aresta em ordem. Os dois sentidos de `POST /api/edges` entram na mesma transação. O corpo antigo (`steps`, `distance_m`, `mean_yaw_rad`, …) permanece. `path` é um array `[{x, y, t}]` com o ponto de origem; `t` é epoch (`started_at + t_ms/1000`). `trace_id` vem no topo. Cada step traz `step_index`, `x`, `y`, `heading_rad` e `length_m` (e os campos antigos `t`, `t_rel`, `cadence_spm`). `displacement_m` é o módulo do último ponto. Caminhada inválida grava o trace com `is_valid=0`, devolve `path` e `trace_id`, e não altera a aresta. Se a transação da trajetória falhar, a resposta é **500** e nada do trace fica commitado. O heading zera uma vez, na pose do checkpoint, não a cada buraco da amostragem.
- `PUT /api/map-config` exige `px_per_m` maior que zero (422 se faltar ou for inválido). `GET` e `PUT` devolvem `{"status","map_config":{plan_image,px_per_m,rotation_rad}}`. `plan_image` é caminho relativo do front, `VARCHAR(512)` porque o MySQL exige tamanho. A linha é `id=1`.
- `PATCH /api/checkpoints/{name}/position` exige `pos_x_px` e `pos_y_px` numéricos (422). A resposta traz `checkpoint`.

Meta futura de localização (não há tabela nesta entrega): checkpoint correto em pelo menos 90% dos testes e erro de até 1,5 m.

---

### Terminal 2: Exposição Externa via Cloudflare Tunnel (Opcional)

---

#### Primeira vez rodando execute:

cloudflare login

E envie o link que aparece no terminal para o administrador

Execute na raiz do projeto (`POV---prototipo/`):

```bash
cloudflared tunnel --config cloudflared-config.yml run

```

> **IP real atrás do túnel:** o `cloudflared` conecta em `127.0.0.1`, então sem configuração todo visitante divide o mesmo IP e o 9º recebe 429 (limite de 8 sessões por IP). No `.env`, defina `TRUSTED_PROXIES=127.0.0.1,::1`. Detalhes em [docs/proxy-confiavel.md](docs/proxy-confiavel.md).

> **Status de Sucesso:** A API em `[https://api.pov-unimar.com/docs](https://api.pov-unimar.com/docs)`. O túnel não publica o site: `pov-unimar.com` é o GitHub Pages.

---

### Conferir um CSV de caminhada

A partir de `Backend/`, o script conta os passos do arquivo (e compara com o rótulo, se você passar `--steps-real`):

```bash
cd Backend
python others/evaluate_steps.py datasets/sample_walk.csv --steps-real 20

```

---

## 6. Auditoria de Sensores e Download de CSVs Brutos

O sistema grava o sinal bruto de cada tentativa de caminhada na tabela `sensors_log` para diagnóstico de sinal e ajuste de limiares.

### Schema da Tabela `sensors_log`

```sql
CREATE TABLE sensors_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(50),
    target VARCHAR(50),
    steps_detected INT DEFAULT 0,
    distance_m FLOAT DEFAULT 0.0,
    is_valid BOOLEAN DEFAULT FALSE,
    message VARCHAR(255),
    raw_csv LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

```

### Endpoints para Download e Inspeção de Sinal

| Método | Endpoint | Descrição |
| --- | --- | --- |
| `GET` | `/api/sensors_log/{log_id}/csv` | Baixa o arquivo `.csv` bruto da gravação |
| `GET` | `/docs` | Interface Swagger interativa para execução |

Para analisar a curva de aceleração de um teste no Excel ou Python Pandas:

1. Acesse o MySQL via phpMyAdmin e pegue o `id` da gravação desejada na tabela `sensors_log`.
2. Acesse a URL no seu navegador: `[http://127.0.0.1:8000/api/sensors_log/](http://127.0.0.1:8000/api/sensors_log/){id}/csv`.

---

## 7. Estratégia de Branches (Git) e Automação (CI/CD)

### Branches Principais

* **`main` (Produção):** Contém exclusivamente o código estável e validado.
* **`dev` (Desenvolvimento):** Branch principal de trabalho, onde novas alterações de filtros e endpoints são integradas e testadas.

### Fluxo de Trabalho Git Recomendado

```bash
# 1. Garantir que está na branch de desenvolvimento
git checkout dev

# 2. Registrar alterações locais
git add .
git commit -m "feat: ajuste na taxa de amostragem e log de csv no banco"

# 3. Enviar para a branch dev remota
git push origin dev

# 4. Promover código para produção (Merge) quando estável
git checkout main
git merge dev
git push origin main
git checkout dev

```

### CI/CD via GitHub Actions

* **Disparo em `dev`:** Roda testes estáticos de compilação Python e validações de rotas para impedir erros de sintaxe ou bibliotecas ausentes.
* **Disparo em `main`:** Roda a verificação do backend e, no workflow `pages.yml`, publica o build do Vite (`frontend/dist`) no GitHub Pages. A origem em Settings → Pages precisa ser **GitHub Actions**. Os registros DNS estão em `docs/dns.md` e os passos manuais em `docs/frontend/fase-6-pages.md`.

---

## 8. Frontend

O visitante abre `frontend/index.html`. A administração fica em `frontend/admin/` (editor, gravador, planta e QR). Rotas salvas, simulação, dashboard e as páginas da raiz que só redirecionavam saíram.

**Calibração da bússola:** o heading do grafo é anti-horário e a bússola é horária. A conversão está só em `frontend/src/sensors/angles.ts`.

## 9. Frontend — fase 0

As travadas ao salvar e no mapa 2D estão diagnosticadas em `docs/frontend/fase-0-travadas.md`. Ainda não há número de FPS do Poco 6 Pro: a medição de campo continua no checklist `docs/qa/checklist-poco6pro.md`. Os testes do frontend, a partir da raiz:

```bash
npm ci
npm test
```

## 10. Frontend — fase 4

O visitante e o admin compilam com Vite a partir de `frontend/src` (TypeScript). Preact e `@preact/signals` desenham o estado do visitante; o Leaflet continua no script `frontend/vendor/leaflet` e entra pelo `MapController`, fora da árvore do Preact.

A URL da API é uma só, em `frontend/src/core/config.ts`. O Vite lê `VITE_API_URL`. Se ela faltar, vale `VITE_API_BASE_URL` (o workflow do Pages define as duas como `https://api.pov-unimar.com`). Sem as duas, o build de produção usa `https://api.pov-unimar.com` e o `npm run dev` usa `http://127.0.0.1:8000`. Os arquivos versionados são `frontend/.env.development` e `frontend/.env.production`. Um override local fica em `frontend/.env.local` (não entra no git). O exemplo está no `.env.example` da raiz.

`/api/localize`, `/api/current_location` e `/api/reset` não fazem parte do aplicativo. O corpo desses pedidos de teste está só em `frontend/tests/fixtures/server-location.js`. `VITE_ENABLE_TEST_ROUTES=1` não liga essas chamadas no build de produção: a flag em `testRoutesEnabled` exige desenvolvimento e exige que não seja produção. O bundle de `npm run build` não contém esses caminhos.

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

## 11. Frontend — fase 5

Rótulos permanentes só a partir do zoom 1; origem e destino ficam sempre. A caixa Camadas (planta, gravados, manuais, rótulos, rota) grava em `pov.map.layers`. Modo escuro é `html.dark`, no mesmo painel do alto contraste. Detalhe em `docs/frontend/fase-5-mapa-visual.md`.

