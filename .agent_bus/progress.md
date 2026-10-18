# Progresso da orquestração — Auditoria 003

Fluxo: `.agent_bus/inbox/T<n>.json` → `python3 tools/run_aider.py <task>` → `.agent_bus/outbox/T<n>.json` → validação do orquestrador.

| Tarefa | Status | Commit | Validação |
|---|---|---|---|
| T0 | ok | c549934 | infra do aider (run_aider.py com files/read/task_id, .aider.conf.yml, metadata do modelo) |
| T1 | ok | 7cd16b4 | reset único c/ start_node, get_saved_route, path_sequence, mounts /css /js, rotas .html, steps_count; py_compile ok |

## Notas
- Aider precisa de `--edit-format diff` + `.aider.model.metadata.json` (sem isso usa `whole`, trunca a saída e não aplica).
