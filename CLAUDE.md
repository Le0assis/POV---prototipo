# PROTOCOLO DE ORQUESTRACAO E REGRAS DO PROJETO

## Contexto e Regras Gerais:
- **Plano de Execução Ativo:** Consulte sempre `auditoria-001.md` para acompanhar os passos atuais da tarefa.
- **Comunicação por Arquivos (.agent_bus):** Utilize a pasta `.agent_bus/` para registrar o histórico de progresso, pendências e o estado atual entre as execuções.

## Protocolo de Execução com o Aider (Sem Scripts Automáticos):
Você é o Orquestrador Principal do ecossistema. Como não utilizamos automações por scripts Python intermediários, siga este fluxo direto:

1. **Planejamento da Tarefa:**
   - Leia o plano atual em `auditoria-001.md`.
   - Defina claramente quais arquivos do repositório precisam ser alterados ou criados.

2. **Delegação para o Aider:**

   - Escreva a instrução da micro-tarefa de forma direta para ser executada no terminal com o Aider.
   - Instrua o usuário (ou execute via comando direto) limitando o contexto estritamente aos arquivos necessários usando o comando `/add` do Aider.
   - Exemplo de comando no Aider: `/add caminho/do/arquivo.py` seguido do comando descritivo da alteração.
   - Voce pode usar tools/run_aider.py para fazer chamadas para o aider tambem

3. **Validação Humana e Registro:**
   - Após o Aider concluir a modificação, valide se o código atende aos requisitos de `auditoria-001.md`.
   - Atualize o status da tarefa no projeto para manter o histórico limpo e organizado.