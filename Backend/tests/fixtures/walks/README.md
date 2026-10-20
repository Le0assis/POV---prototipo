# Caminhadas rotuladas

CSV de sensores exportado pelo recorder (`GET /api/sensors_log/{id}/csv` ou o mesmo formato de `datasets/sample_walk.csv`) mais o arquivo irmão `<nome>.labels.json`.

Nome: `AAAAMMDD_<cenario>_<posicao>_<NN>.csv`, por exemplo `20261020_normal_mao_01.csv`.

O rótulo mínimo:

```json
{
  "steps_real": 50,
  "scenario": "normal",
  "position": "mao",
  "device": "Poco 6 Pro",
  "date": "2026-10-20",
  "sample_rate_hz": 58.7,
  "dt_median_ms": 16.0,
  "dt_p95_ms": 24.0,
  "step_times_s": null,
  "time_base": null,
  "notes": "contagem em voz alta"
}
```

`sample_rate_hz`, `dt_median_ms` e `dt_p95_ms` não são digitados. A partir de `Backend/`:

```bash
python -m tests.utils.make_labels tests/fixtures/walks/20261020_normal_mao_01.csv \
  --steps-real 50 --scenario normal --position mao --date 2026-10-20 \
  --notes "contagem em voz alta"
```

`steps_real` é o total contado à mão. `step_times_s` é opcional; se existir, `time_base` é `epoch` ou `relative`. Uma coluna `step_mark` (0/1) no CSV vira `step_times_s` no loader. O processamento ignora essa coluna.

Sem `.labels.json` o CSV não entra na suíte. Fixture já aprovada não se altera; corrigir o rótulo é um PR separado.

## Aceite

| Meta | Limite |
|---|---|
| A1, cada caminhada com `steps_real` > 0 | erro ≤ 5% |
| A2, parado / manuseio (`steps_real` = 0, ~30 s) | ≤ 2 passos |
| A3, `datasets/sample_walk.csv` | 20 ± 1 |

O erro agregado de 3% é desejável e não bloqueia. A tabela sai com `python -m tests.utils.report`.

## O que falta

Escada e bolso ficam fora desta missão. A suíte reamostra cada CSV para 50 Hz, para o detector não ficar preso à taxa do app.

## Gravações de 2026-10-20 (Poco 6 Pro, Sensor Logger)

Gravadas com o app Sensor Logger 1.68 (Android nativo, ~100 Hz), não com o recorder do Chrome. Convertidas com `Backend/tools/convert_sensor_logger.py`: `TotalAcceleration` (com gravidade, eixos do Android = devicemotion) e `Gyroscope` (rad/s, interpolado na base do acelerômetro), timestamp relativo em s. Celular na mão, ritmo normal, passos contados à mão por Leonardo.

| fixture | origem | N_real |
|---|---|---:|
| 20261020_normal_mao_01 | primeira-30 | 30 |
| 20261020_normal_mao_02 | segunda-11 | 11 |
| 20261020_normal_mao_03 | terceira-8 | 8 |
| 20261020_normal_mao_04 | quarta-45 | 45 |
| 20261020_parado_mao_01 | parado (≈12 s, não 30 s) | 0 |
| 20261020_chacoalho_mao_01 | chacoalho (chacoalhando, sem andar) | 0 |

## Gravações de 2026-10-20 (Poco 6 Pro, recorder do Chrome)

Saíram do banco do próprio app (`timestamp` em epoch s, `mag_*` = orientação alpha/beta/gamma, aceleração com gravidade, giro em rad/s, ~59 Hz). O bruto continua em `tests/fixtures/chrome_raw/`. Aqui o CSV está no formato dos outros fixtures: timestamp relativo em s, só accel e giro. Contagem à mão por Leonardo. Em 4 ou 8 passos, 5% é menos de um passo, então o rótulo traz `tolerance_steps: 1`.

| fixture | trecho | duração | N_real |
|---|---|---:|---:|
| 20261020_chrome_quarto-sala | quarto-sala | 7,5 s | 4 |
| 20261020_chrome_sala-cozinha | sala-cozinha | 4,9 s | 4 |
| 20261020_chrome_cozinha-quarto | cozinha-quarto | 8,2 s | 8 |
