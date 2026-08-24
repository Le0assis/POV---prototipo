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
* **Python 3.10+**
* **XAMPP** (Apache e MySQL)
* **Cloudflare CLI (`cloudflared`)** *(Opcional: Apenas se for expor para rede externa)*

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
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000

```

> **Status de Sucesso:** API pronta em `[http://127.0.0.1:8000](http://127.0.0.1:8000)` e Swagger em `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`.

---

### Terminal 2: Exposição Externa via Cloudflare Tunnel (Opcional)

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