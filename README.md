# Documentação de Instalação e Execução - Projeto POV

## 1. Estrutura do Projeto

```text
POV---prototipo/
├── api/
│   └── app.py
├── datasets/
│   ├── create_tables.py
│   ├── generate_sample_dataset.py
│   ├── ManagerDatabase.py
│   └── sample_walk.csv
├── filters/
│   ├── attitude_estimator.py
│   ├── butterworth.py
│   ├── madgwick.py
│   ├── moving_average.py
│   ├── quaternion.py
│   └── signal_filter.py
├── map/
│   ├── MapDatabaseManager.py
│   ├── router.py
│   ├── topological_map.py
│   └── topological_matcher.py
├── others/
│   ├── example_sensors.py
│   ├── run_csv_client.py
│   └── seed_map.py
├── pdr/
│   ├── altitude.py
│   ├── magnitude.py
│   ├── steps.py
│   └── tracker.py
├── sensors/
│   ├── accelerometer.py
│   ├── barometer.py
│   ├── gyroscope.py
│   ├── magnetometer.py
│   ├── repository.py
│   └── sensor_sample.py
├── static/
│   ├── index.html
│   ├── mapa-2d.html
│   ├── recorder.html
│   └── sensors_upload.html
└── tests/

```

---

## 2. Pré-requisitos

* Git
* Python 3.10 ou superior
* XAMPP (Apache e MySQL)

---

## 3. Clonagem do Repositório e Ambiente Virtual

1. Clone o repositório e acesse a pasta raiz:

```bash
git clone https://github.com/Le0assis/POV---prototipo
cd POV---prototipo

```

2. Crie e ative o ambiente virtual Python:

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar no Windows (PowerShell)
.\venv\Scripts\Activate.ps1

```

3. Instale as dependências do projeto:

```bash
pip install -r requirements.txt

```

---

## 4. Configuração do Banco de Dados (MySQL via XAMPP)

1. Abra o painel do XAMPP e inicie os serviços **Apache** e **MySQL**.
2. Acesse o gerenciador de banco de dados no navegador: `http://localhost/phpmyadmin`.
3. Crie um novo banco de dados com o nome exato: `POV`.

---

## 5. Inicialização e Povoamento do Banco de Dados

Execute os scripts a partir da raiz do projeto (`POV---prototipo`) na seguinte ordem:

1. Criar as tabelas no banco de dados:

```bash
python -m datasets.create_tables

```

2. Gerar o conjunto de dados de amostra:

```bash
python -m datasets.generate_sample_dataset

```

3. Alimentar o banco com os dados de teste do mapa:

```bash
python -m others.seed_map

```

---

## 6. Execução do Servidor Web (API)

Inicie o servidor backend FastAPI com Uvicorn:

```bash
uvicorn api.app:app --reload

```

O servidor estará disponível em: `[http://127.0.0.1:8000](http://127.0.0.1:8000)`

---

## 7. Simulação de Passos (Cliente PDR)

Com o servidor rodando, abra um segundo terminal, ative o ambiente virtual e execute o cliente de simulação:

```bash
python -m others.run_csv_client

```

---

## 8. Checkpoints de Validação

* **Checkpoint 1 (Banco de Dados):** Acesse `http://localhost/phpmyadmin`, selecione o banco `POV` e certifique-se de que as tabelas foram criadas e populadas com os dados inseridos pelos scripts.
* **Checkpoint 2 (Servidor API):** Acesse `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)` no navegador para verificar se a interface Swagger do FastAPI está ativa.
* **Checkpoint 3 (Cliente PDR):** Verifique se o terminal do script `run_csv_client.py` exibe o envio sequencial dos passos e recebe respostas HTTP de sucesso (`200 OK`) da API. 