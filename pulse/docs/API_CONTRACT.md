# Contrato de API

## Base

Todas as APIs Pulse devem ser versionadas:

`/api/v1/`

## Convenções

- JSON;
- erros estruturados;
- IDs estáveis;
- timestamps ISO 8601;
- idempotency keys para operações aplicáveis;
- autenticação obrigatória salvo endpoints públicos;
- OpenAPI atualizado.

## Áreas previstas

```text
/api/v1/auth
/api/v1/dashboard
/api/v1/email
/api/v1/calendar
/api/v1/tasks
/api/v1/tickets
/api/v1/weight
/api/v1/rto
/api/v1/finance
/api/v1/shopping
/api/v1/search
/api/v1/activity
/api/v1/settings
/api/v1/notifications
/api/v1/actions
/api/v1/ai
/api/v1/version
/api/v1/health
```

## Dashboard

Deve agregar apenas dados necessários ao Hoje.

Evitar que o Android/Web faça dezenas de pedidos se um endpoint agregado puder entregar o estado essencial.

## Escritas

Todas as escritas passam pela camada oficial do módulo.

## Capabilities

Cada módulo deve declarar capacidades:

- read;
- create;
- update;
- delete;
- history;
- statistics;
- offline;
- notifications;
- ai_read;
- ai_actions.

## Compatibilidade

O backend deve evitar quebrar imediatamente APKs anteriores. Quando necessário, usar `minimum_supported_version`.
