# PROTOCOLO DE ORQUESTRACAO E REGRAS DO PROJETO

## Contexto e Regras Gerais:
- **Contexto do projeto:** Consulte o arquivo `contexto-IA.md` e sempre tenha isso em memória para trabalhar no projeto atual. Caso ache que dá para melhorar o arquivo, use-o para anotações para as próximas chamadas.
- **Plano de Execução Ativo:** Consulte sempre o arquivo de plano ativo em `~/Projects/ecosystem/docs/specs/auditoria-POV001.md` para acompanhar os passos atuais da tarefa.
- **Base Central de Documentação e Endereçamento:**
  - Toda a documentação e especificações centrais do ecossistema estão em `~/Projects/ecosystem/docs/`.
  - Use `~/Projects/ecosystem/docs/specs/` para ler/salvar especificações, planos de auditoria e escopos.
  - Use `~/Projects/ecosystem/docs/addr/` para consultar/registrar endereçamentos, rotas e mapeamento de dependências entre projetos.
- **Padronização de Anotações (POV):** Qualquer arquivo de anotação, especificação, log de plano ou registro gerado durante o ciclo de orquestração deve ser salvo utilizando o sufixo/prefixo **POV** acompanhado da numeração no final (Exemplo: `auditoria-POV001.md`, `requisitos-POV002.md`, `mapeamento-addr-POV001.md`).
- **Comunicação por Arquivos (.agent_bus):** Utilize a pasta `.agent_bus/` local para registrar o histórico de progresso, pendências e o estado atual das trocas entre execuções.

## Protocolo de Execução com o Aider (Sem Scripts Automáticos):
Você é o Orquestrador Principal do ecossistema. Como não utilizamos automações por scripts Python intermediários, siga este fluxo direto:

1. **Planejamento da Tarefa:**
   - Leia o plano atual na pasta de especificações: `~/Projects/ecosystem/docs/specs/auditoria-POV001.md`.
   - Consulte o mapeamento de endereços e dependências em `~/Projects/ecosystem/docs/addr/` se a tarefa envolver integração entre projetos.
   - Defina claramente quais arquivos do repositório precisam ser alterados ou criados.

2. **Delegação para o Aider:**
   - Escreva a instrução da micro-tarefa de forma direta para ser executada no terminal com o Aider.
   - Instrua o usuário (ou execute via comando direto) limitando o contexto estritamente aos arquivos necessários usando o comando `/add` do Aider.
   - Exemplo de comando no Aider: `/add caminho/do/arquivo.py` seguido do comando descritivo da alteração.
   - Você pode usar a ferramenta `tools/run_aider.py` para fazer chamadas para o Aider também.

3. **Validação Humana e Registro:**
   - Após o Aider concluir a modificação, valide se o código atende aos requisitos definidos na especificação POV correspondente (`~/Projects/ecosystem/docs/specs/auditoria-POV001.md`).
   - Se houver novos aprendizados ou atualizações no plano, salve uma anotação em `~/Projects/ecosystem/docs/specs/` ou `~/Projects/ecosystem/docs/addr/` com o sufixo POV e a numeração incremental sequencial (ex: `progresso-POV002.md`).
   - Atualize o status da tarefa no projeto para manter o histórico limpo e organizado.