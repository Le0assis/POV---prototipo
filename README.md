# Documentação de Instalação e Execução — Projeto POV

## 1. Estrutura do Projeto

```text
POV---prototipo/
├── Backend/
│   ├── api/
│   │   └── app.py
│   ├── datasets/
│   │   ├── create_tables.py
│   │   ├── generate_sample_dataset.py
│   │   ├── ManagerDatabase.py
│   │   └── sample_walk.csv
│   ├── filters/
│   │   ├── attitude_estimator.py
│   │   ├── butterworth.py
│   │   ├── madgwick.py
│   │   ├── moving_average.py
│   │   ├── quaternion.py
│   │   └── signal_filter.py
│   ├── map/
│   │   ├── MapDatabaseManager.py
│   │   ├── router.py
│   │   ├── topological_map.py
│   │   └── topological_matcher.py
│   ├── others/
│   │   ├── example_sensors.py
│   │   ├── run_csv_client.py
│   │   └── seed_map.py
│   ├── pdr/
│   │   ├── altitude.py
│   │   ├── magnitude.py
│   │   ├── steps.py
│   │   └── tracker.py
│   ├── sensors/
│   │   ├── accelerometer.py
│   │   ├── barometer.py
│   │   ├── gyroscope.py
│   │   ├── magnetometer.py
│   │   ├── repository.py
│   │   └── sensor_sample.py
│   ├── static/
│   │   ├── index.html
│   │   ├── mapa-2d.html
│   │   ├── recorder.html
│   │   └── sensors_upload.html
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── index.html
│   └── package.json
├── .gitignore
├── cloudflared-config.yml
└── CNAME
```

---

## 2. Pré-requisitos

Antes de iniciar, certifique-se de que os seguintes programas estão instalados:

- Git
- Python 3.10 ou superior
- XAMPP (Apache e MySQL)
- Cloudflare CLI (`cloudflared`)

---

## 3. Clonagem do Repositório, Instalação do Cloudflare CLI e Ambiente Virtual

### 3.1. Clonar o repositório

Clone o repositório e acesse a pasta raiz:

```bash
git clone https://github.com/Le0assis/POV---prototipo
cd POV---prototipo
```

### 3.2. Instalar o Cloudflare CLI

Execute o PowerShell como **Administrador** e instale o `cloudflared`:

```powershell
winget install --id Cloudflare.cloudflared
```

### 3.3. Criar o ambiente virtual Python

Acesse o diretório do backend:

```bash
cd Backend
```

Crie o ambiente virtual:

```bash
python -m venv venv
```

### 3.4. Ativar o ambiente virtual

#### Windows — PowerShell

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux/macOS

```bash
source venv/bin/activate
```

### 3.5. Instalar as dependências

Com o ambiente virtual ativado:

```bash
pip install -r requirements.txt
```

---

## 4. Configuração do Banco de Dados (MySQL via XAMPP)

### 4.1. Iniciar o XAMPP

Abra o painel de controle do **XAMPP**.

Inicie os seguintes serviços:

- Apache
- MySQL

### 4.2. Acessar o phpMyAdmin

Abra o navegador e acesse:

[http://localhost/phpmyadmin](http://localhost/phpmyadmin)

### 4.3. Criar o banco de dados

Crie um novo banco de dados com o nome exato:

```text
POV
```

> **Observação:** caso o nome do banco esteja configurado de forma diferente no arquivo `Backend/datasets/ManagerDatabase.py`, utilize o nome definido nesse arquivo.

---

## 5. Inicialização e Povoamento do Banco de Dados

Dentro do diretório `Backend/`, com o ambiente virtual ativo, execute os scripts na seguinte ordem.

### 5.1. Criar as tabelas no banco de dados

```bash
python -m datasets.create_tables
```

### 5.2. Gerar o conjunto de dados de amostra

```bash
python -m datasets.generate_sample_dataset
```

### 5.3. Alimentar o banco com os dados de teste do mapa

```bash
python -m others.seed_map
```

---

## 6. Execução do Servidor Web (API)

Ainda dentro da pasta `Backend/`, inicie o servidor FastAPI utilizando o Uvicorn:

```bash
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

O servidor local estará disponível em:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

### 6.1. Documentação Swagger

A documentação interativa da API estará disponível em:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

> **Importante:** mantenha este terminal aberto enquanto estiver utilizando a API.

---

## 7. Execução do Cloudflare Tunnel (HTTPS)

O Cloudflare Tunnel permite expor a API local para a internet utilizando HTTPS.

Isso possibilita o consumo da API por um frontend hospedado, por exemplo, no GitHub Pages ou Vercel.

### 7.1. Abrir um novo terminal

Abra um novo terminal na **raiz do repositório**:

```text
POV---prototipo/
```

### 7.2. Realizar o login no Cloudflare

Caso seja a primeira execução nessa máquina, faça o login:

```bash
cloudflared tunnel login
```

### 7.3. Configurar a rota DNS

Configure a rota DNS do túnel:

```bash
cloudflared tunnel route dns pov-backend api.pov-unimar.com
```

### 7.4. Iniciar o túnel

Ainda na raiz do projeto, execute:

```bash
cloudflared tunnel --config cloudflared-config.yml run
```

Após a inicialização, a API deverá estar acessível publicamente pelo domínio configurado.

---

## 8. Simulação de Passos (Cliente PDR)

Com a **API** e o **Cloudflare Tunnel** em execução, abra um terceiro terminal.

### 8.1. Acessar o diretório Backend

```bash
cd POV---prototipo/Backend
```

### 8.2. Ativar o ambiente virtual

No Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

No Linux/macOS:

```bash
source venv/bin/activate
```

### 8.3. Executar o cliente PDR

```bash
python -m others.run_csv_client
```

O script utilizará os dados do arquivo de amostra para simular o envio de informações do sistema PDR para a API.

---

## 9. Checkpoints de Validação

### 9.1. Checkpoint 1 — Banco de Dados

Acesse:

[http://localhost/phpmyadmin](http://localhost/phpmyadmin)

Selecione o banco de dados `POV` e confirme que:

- O banco existe.
- As tabelas foram criadas.
- Os dados de teste foram inseridos corretamente.

---

### 9.2. Checkpoint 2 — Servidor API Local

Acesse:

[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

A página do Swagger do FastAPI deve ser exibida.

Verifique se os endpoints da API estão disponíveis e funcionando.

---

### 9.3. Checkpoint 3 — API Pública via Cloudflare Tunnel

Acesse:

[https://api.pov-unimar.com/docs](https://api.pov-unimar.com/docs)

A documentação Swagger da API deverá ser carregada através do domínio público.

Isso confirma que o Cloudflare Tunnel está conectado corretamente ao servidor local.

---

### 9.4. Checkpoint 4 — Cliente PDR

Observe o terminal onde o seguinte comando foi executado:

```bash
python -m others.run_csv_client
```

O resultado esperado é:

- Envio sequencial das coordenadas/dados da simulação.
- Respostas HTTP `200 OK` da API.
- Processamento contínuo dos dados pelo backend.

---

## 10. Resumo da Execução

A ordem geral para executar o projeto é:

### Terminal 1 — Backend/API

```bash
cd POV---prototipo/Backend
```

Ative o ambiente virtual.

#### Windows PowerShell

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux/macOS

```bash
source venv/bin/activate
```

Inicie a API:

```bash
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

---

### Terminal 2 — Cloudflare Tunnel

Na raiz do projeto:

```bash
cd POV---prototipo
```

Execute:

```bash
cloudflared tunnel --config cloudflared-config.yml run
```

---

### Terminal 3 — Cliente PDR

Acesse o diretório do backend:

```bash
cd POV---prototipo/Backend
```

Ative o ambiente virtual.

#### Windows PowerShell

```powershell
.\venv\Scripts\Activate.ps1
```

#### Linux/macOS

```bash
source venv/bin/activate
```

Execute o cliente:

```bash
python -m others.run_csv_client
```

---

## 11. URLs de Validação

| Serviço | URL |
|---|---|
| phpMyAdmin | [http://localhost/phpmyadmin](http://localhost/phpmyadmin) |
| API local | [http://127.0.0.1:8000](http://127.0.0.1:8000) |
| Swagger local | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| Swagger público | [https://api.pov-unimar.com/docs](https://api.pov-unimar.com/docs) |

---

## 12. Observações

- O MySQL deve estar em execução antes dos scripts de criação e povoamento do banco.
- O ambiente virtual Python deve estar ativado ao executar os comandos do backend.
- A API precisa estar em execução antes de iniciar o Cloudflare Tunnel.
- O Cloudflare Tunnel precisa estar ativo antes de executar o cliente PDR caso o cliente utilize a API pública.
- Para uma execução completa, mantenha os terminais da API e do Cloudflare Tunnel abertos durante toda a simulação.
- Certifique-se de que o arquivo `cloudflared-config.yml` está corretamente configurado antes de iniciar o túnel.
- Certifique-se de que o banco de dados `POV` corresponde às configurações utilizadas pelo backend.