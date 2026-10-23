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
│   │   ├── run_csv_client.py         # Cliente de simulação PDR via cliente HTTP
│   │   └── seed_map.py               # Alimentador de posições iniciais do mapa
│   ├── pdr/
│   │   ├── processor.py              # Pipeline principal de PDR e validação
│   │   ├── steps.py                  # Detector de picos de passos (Weinberg)
│   │   └── tracker.py                # Rastreamento de deslocamento acumulado
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
# Senha do editor: só o ambiente do processo. Não usamos python-dotenv.
export EDITOR_PASSWORD='defina-uma-senha'
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000

```

> **Status de Sucesso:** API pronta em `[http://127.0.0.1:8000](http://127.0.0.1:8000)` e Swagger em `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`.

`python -m datasets.create_tables` também aplica a migração idempotente `datasets/migrations/002_walk_traces.py` (dedupe de `edges`, trajetória e planta). Se `edges_backup_m02` já existe, ela não é recriada. `GET /api/map-config` responde **500** com a mensagem pedindo essa migração quando a tabela ainda não existe.

### Senha do editor do mapa

O arquivo `.env` está no `.gitignore`. O exemplo versionado é `.env.example`, sem senha. A API lê `EDITOR_PASSWORD` com `os.environ` e compara o header `X-Editor-Password` em tempo constante (SHA-256 + `hmac.compare_digest`).

| Situação | Resposta |
| --- | --- |
| `EDITOR_PASSWORD` ausente ou vazia | **503** em toda escrita protegida |
| Header ausente ou senha diferente | **401** |
| Senha correta | a escrita segue |

Escritas protegidas: `POST /api/checkpoints`, `PATCH /api/checkpoints/{name}/position`, `POST /api/edges`, `POST /api/edges/process-raw`, `PUT /api/map-config`, `POST /api/routes`, `DELETE /api/routes/{id}`, `POST /api/reset`.

Leituras públicas, entre elas `GET /api/map`, `GET /api/map-config`, `GET /api/connections`, `GET /api/connections/{id}`, `GET /api/pdr/config` e o restante dos GET já existentes. `POST /api/localize` continua aberto.

### Mapa, arestas e trajetória

- `edges` é a única fonte do grafo: uma linha por sentido (`UNIQUE (source_node, target_node)`). `saved_routes` é histórico e não entra no mapa.
- `origin` no banco e na API é `manual` ou `recorded` (o exemplo do contrato do front usa a palavra `recording`; o valor gravado é `recorded`).
- Aresta antiga: ao criar a coluna, `origin='recorded'` se existir qualquer `sensors_log` do par source/target, mesmo com `is_valid=0` (logs antigos não preenchiam o campo). Sem log, fica `manual`. A classificação não roda de novo. `is_valid` vale só para gravações novas: mediana, `samples_count` e `active_trace_id`.
- `origin='manual'` conserva distância e heading. Sem manual, a distância é a mediana das `walk_traces` válidas daquele sentido e o heading é a média circular. `active_trace_id` aponta a válida mais recente. `samples_count` é quantas trajetórias válidas aquele sentido tem, e sobe mesmo quando a distância manual permanece.
- `started_at` e `ended_at` são `DATETIME(3)` sem fuso, gravados em UTC. Quem lê trata o valor naive como UTC.
- `GET /api/map` devolve `pos_x_px` e `pos_y_px` em cada checkpoint (planta, origem no canto superior esquerdo, y para baixo) e as arestas do grafo carregado só de `edges`.
- `GET /api/connections` agrupa o par físico: uma entrada, com `reverse_edge_id` para o front não desenhar duas vezes. O sentido listado é o que tem `active_trace_id`; se nenhum tiver, o de menor id. `include_path` default é true; `false` omite `path`. Aresta sem trajetória devolve um segmento reto `[{x:0,y:0,t:null},{x:d·cos(h),y:d·sin(h),t:null}]`. `GET /api/connections/{id}` devolve aquele sentido (não troca pelo par) e `traces`.
- `POST /api/edges/process-raw` grava `sensors_log` (`steps_detected`, `distance_m`, `is_valid`) e a trajetória (`walk_traces` + `walk_steps`) do sentido andado, numa transação. Cada requisição abre a própria conexão MySQL, para um GET não deixar transação implícita no cursor da gravação. O corpo antigo (`steps`, `distance_m`, `mean_yaw_rad`, …) permanece. `path` é um array `[{x, y, t}]` com o ponto de origem; `t` é epoch (`started_at + t_ms/1000`). `trace_id` vem no topo. Cada step traz `step_index`, `x`, `y`, `heading_rad` e `length_m` (e os campos antigos `t`, `t_rel`, `cadence_spm`). `displacement_m` é o módulo do último ponto. Caminhada inválida grava o trace com `is_valid=0`, devolve `path` e `trace_id`, e não altera a aresta. Se a transação da trajetória falhar, a resposta é **500** e nada do trace fica commitado. O heading zera uma vez, na pose do checkpoint, não a cada buraco da amostragem.
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

> **Status de Sucesso:** Rotas mapeadas para HTTPS remoto (ex: `[https://api.pov-unimar.com/docs](https://api.pov-unimar.com/docs)`).

---

### Terminal 3: Cliente de Simulação e Validação PDR

Acesse a pasta `Backend`, ative o `venv` e execute o cliente de envio de dados inerciais:

```bash
cd Backend
python -m others.run_csv_client

```

> **Status de Sucesso:** Envio em lote dos sensores brutos, retornos de validação HTTP `200 OK` e persistência dos CSVs na tabela `sensors_log`.

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
* **Disparo em `main`:** Executa o pipeline completo de verificação e dispara a atualização direta no servidor de produção final.

---

## 8. Frontend

O visitante abre `frontend/index.html`. A administração fica em `frontend/admin/` (editor, gravador, planta e QR). Rotas salvas, simulação, dashboard e as páginas da raiz que só redirecionavam saíram.

**Calibração da bússola:** o heading do grafo é anti-horário e a bússola é horária. A conversão está só em `frontend/js/sensors/angles.js`.

## 9. Frontend — fase 0

As travadas ao salvar e no mapa 2D estão diagnosticadas em `docs/frontend/fase-0-travadas.md`. Ainda não há número de FPS do Poco 6 Pro: a medição de campo continua no checklist `docs/qa/checklist-poco6pro.md`. Os testes do frontend, a partir da raiz:

```bash
npm ci
npm test
```

