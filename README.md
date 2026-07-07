# IndoorIPS (Indoor Positioning System via PDR)

Sistema de Posicionamento Indoor (IPS) baseado em **Pedestrian Dead Reckoning (PDR)**. Este projeto rastreia a trajetória de um usuário em ambientes fechados utilizando exclusivamente dados de sensores inerciais e ambientais de smartphones (Acelerômetro, Giroscópio, Magnetômetro e Barômetro), sem qualquer dependência de infraestruturas externas como Wi-Fi, BLE, RFID, UWB, GPS ou visão computacional.

## 🧠 Core Features (Pipeline PDR)
* **Sincronização de Sensores:** Leitura paralela e validação de timestamps.
* **Filtro Butterworth:** Atenuação de ruídos de alta frequência para destacar o padrão de caminhada humano.
* **Estimativa de Orientação (Madgwick):** Fusão sensorial (MARG) para rastreamento preciso do Yaw em 3D, minimizando deriva.
* **Modelo de Weinberg:** Estimativa dinâmica do comprimento do passo (Step Length) baseada na amplitude da aceleração.
* **Integração Trigonométrica:** Projeção de deslocamento iterativo em um mapa 2D.
* **Estimativa de Altitude:** Uso da fórmula barométrica para detecção de mudança de andares.

## 📂 Estrutura da Arquitetura (Padrão SOLID)

```text
IndoorIPS/
├── datasets/    # Conjuntos de dados (CSV) para testes e simulação
├── filters/     # Processamento de sinais contínuos
│   ├── butterworth.py       # Passa-baixa
│   ├── madgwick.py          # Fusão Sensorial MARG
│   └── quaternion.py        # Matemática espacial livre de Gimbal Lock
├── pdr/         # Núcleo da Lógica de Negócio Discreta
│   ├── altitude.py          # Cálculo barométrico
│   ├── steps.py             # Detecção de picos e Modelo de Weinberg
│   └── tracker.py           # Integração trigonométrica (Posição X, Y)
├── sensors/     # Camada de Infraestrutura e Domínio de Dados
│   ├── sensor_sample.py     # Entidade rica sincronizada
│   ├── repository.py        # Padrão Repository (Abstração de fonte de dados)
│   └── (leitores individuais por componente)
├── map/         # Map matching e grafo de navegação (Próximos passos)
├── tests/       # Testes unitários focados em TDD
└── main.py      # Entrypoint (Pipeline e Visualização Gráfica)
```

## Instalação

```bash
pip install -r requirements.txt
```

## Como rodar os testes

A partir da raiz do projeto:

```bash
python -m unittest discover -s tests -v
```

## Como rodar os exemplos

Os scripts em `examples/` importam pacotes da raiz do projeto (ex.:
`sensors`), então é necessário incluir a raiz no `PYTHONPATH`:

```bash
PYTHONPATH=. python examples/example_sensors.py
```

## Dependências permitidas

Apenas: `numpy`, `scipy`, `pandas`, `matplotlib`, `ahrs`, além dos módulos
padrão `typing`, `dataclasses`, `logging`, `pathlib`, `unittest`, `abc`.
