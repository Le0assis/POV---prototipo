# IndoorIPS

Sistema de Posicionamento Indoor (IPS) baseado em Pedestrian Dead Reckoning
(PDR), utilizando apenas sensores de smartphone (acelerômetro, giroscópio,
magnetômetro, barômetro) — sem Wi-Fi, BLE, RFID, UWB, GPS ou visão
computacional.

## Status do desenvolvimento

Construído em etapas incrementais. Progresso atual:

- [x] Etapa 0 — Estrutura do projeto
- [x] Etapa 1 — Leitura dos sensores
- [ ] Etapa 2 — Magnitude da aceleração
- [ ] Etapa 3 — Filtragem
- [ ] Etapa 4 — Detecção de passos
- [ ] Etapa 5 — Cadência
- [ ] Etapa 6 — Comprimento do passo
- [ ] Etapa 7 — Fusão sensorial (Madgwick)
- [ ] Etapa 8 — Orientação (quaternion → Euler)
- [ ] Etapa 9 — Atualização da posição
- [ ] Etapa 10 — Barômetro (altitude / detecção de andar)
- [ ] Etapa 11 — Fingerprint magnético
- [ ] Etapa 12 — Map Matching
- [ ] Etapa 13 — Particle Filter (interfaces)
- [ ] Etapa 14 — Navegação (Dijkstra/A*/Theta*/JPS)
- [ ] Etapa 15 — Integração final (main.py)

## Estrutura

```
IndoorIPS/
├── sensors/     # Leitura dos sensores (Etapa 1) ✅
├── filters/     # Filtragem de sinal (Etapa 3)
├── pdr/         # Núcleo do PDR: magnitude, passos, cadência, fusão, posição
├── map/         # Map matching e grafo de navegação
├── datasets/    # Datasets de exemplo/teste
├── tests/       # Testes unitários por módulo
├── examples/    # Scripts de demonstração de cada módulo
└── main.py      # Ponto de entrada (integração final)
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
