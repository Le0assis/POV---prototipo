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

As gravações reais do Poco 6 Pro (Chrome para Android), celular na mão, ritmo normal, ainda não estão nesta pasta. Quando chegarem, registrar aqui o cenário, o N_real, a taxa efetiva, quem contou e como contou. Escada e bolso ficam fora desta missão.
