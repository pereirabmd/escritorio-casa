# IA do Pulse

## Objetivo

A IA do Pulse deve:

1. compreender contexto consolidado;
2. pesquisar;
3. resumir;
4. recomendar ações contextuais;
5. executar ações autorizadas.

## Infraestrutura nesta fase

Mesmo que o agente final seja implementado no fim, a arquitetura deve incluir desde início:

- Action/Tool registry;
- permissões;
- validação;
- confirmações;
- idempotência;
- audit log;
- contratos de ação;
- APIs oficiais dos módulos.

## Níveis

### read
Consulta apenas.

Exemplos:
- eventos de amanhã;
- tarefas pendentes;
- próximo comboio;
- histórico de peso.

### safe_action
Ações reversíveis ou de baixo risco.

Exemplos:
- concluir tarefa;
- adiar tarefa;
- adicionar item à lista de compras;
- marcar dia RTO quando permitido.

### sensitive_action
Ações destrutivas, financeiras, externas ou com impacto relevante.

Exemplos:
- apagar;
- enviar email;
- operações sensíveis;
- alterações que não sejam facilmente reversíveis.

Devem exigir confirmação.

## Regra absoluta

A IA não executa SQL direto.

```text
IA
 -> Action Layer
 -> autorização/validação
 -> API/Core oficial
 -> dado
```

## Auditoria

Registar:
- ação;
- módulo;
- origem IA;
- utilizador;
- timestamp;
- resultado;
- confirmação quando aplicável.

## Detalhes posteriores

Prompts, modelo, contexto ideal, UX conversacional e regras específicas por ação podem ser afinados na fase final.
