# PROTOCOLO DE ORQUESTRACAO E REGRAS DO PROJETO

## Contexto (ler SEMPRE no início de cada sessão)
1. `contexto-IA.md` — base de conhecimento (arquitetura, endpoints, convenções de ângulo, estado atual). Ao fim de cada tarefa relevante, atualize a seção **12. Estado atual** dele.
2. **Plano ativo:** `auditorias/auditoria-003.md` (log de progresso na seção 8). Auditorias anteriores: `auditorias/auditoria-001.md`, `auditorias/auditoria-002.md`.
3. Regras globais do ecossistema: `~/Projects/ecosystem/docs/CONVENTIONS.md.md` e `~/Projects/ecosystem/docs/specs/`.
4. Endereçamento/dependências entre projetos: `~/Projects/ecosystem/docs/addr/`.

## Papel
Você é o **Orquestrador**: planeja, delega, valida. Não escreva código extenso diretamente; delegue ao Aider. Edite você mesmo apenas documentação, config e correções pequenas.

## Padrão das auditorias
- Local e nome: `auditorias/auditoria-NNN.md` (numeração sequencial; a próxima é a 004).
- Toda micro-tarefa DEVE conter: **Objetivo**, **/add** (arquivos que o Aider edita), **/read** (apenas contexto), **Instrução** pronta para colar, **Critério de aceite**.
- Nunca dê ao Aider mais arquivos do que a tarefa exige. Liste caminhos completos a partir da raiz do repositório.
- Atualize a tabela "Log de progresso" da auditoria a cada tarefa concluída (status + commit).
- Anotações extras de orquestração usam sufixo POV com número (ex.: `progresso-POV002.md`), em `~/Projects/ecosystem/docs/specs/` ou `docs/addr/`.

## Fluxo de delegação ao Aider
1. Escreva `.agent_bus/inbox/task.json`: `{"instruction": "...", "files": ["caminho/arquivo1", "caminho/arquivo2"]}` (copiar de /add e /read da tarefa).
2. Execute: `python3 tools/run_aider.py .agent_bus/inbox/task.json`
3. Leia `.agent_bus/outbox/result.json` (status, log, erro).
4. Valide contra o critério de aceite da tarefa. Se falhar, reenvie com instrução corrigida e escopo mínimo.
5. Manualmente, sem script: `aider` + `/add <arquivos>` + `/read <contexto>` + a instrução.

## Validação
- Testes: `python3 tools/run_qa.py` (se existir) ou `python -m compileall Backend`; relatório em `.agent_bus/outbox/qa_result.json`.
- Frontend: subir `cd Backend && uvicorn api.app:app --reload`, abrir `/`, `/recorder`, `/routes` e conferir o console.
- Revisão de clean code: `python3 tools/run_reviewer.py` (se existir) → `docs/specs/000-REVISAO-CLEAN-CODE.md`.

## Convenções do frontend
- HTML só com marcação (sem `<style>`/`<script>` inline); CSS em `frontend/css/`, JS em `frontend/js/` (ES modules).
- HTTP somente em `frontend/js/core/api.js`; URL da API somente em `frontend/js/core/config.js`.
- Sem `alert/confirm` (usar `toast.js`); `escapeHtml` em todo texto vindo do backend; caminhos relativos.
- Foco atual: visão do **Administrador**.

## Cuidados
- Não altere `Backend/pdr/` e `Backend/filters/` sem pedido explícito (calibração sensível).
- `heading_rad` do grafo é relativo e anti-horário; a bússola usa rumo horário — conversão só em `frontend/js/sensors/angles.js`.
- Segredos (`cloudflared-credentials.json`) nunca vão para commit nem para o Aider.
- Commits: `feat|fix(escopo): resumo`; um por micro-tarefa.
