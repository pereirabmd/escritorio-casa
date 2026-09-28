# Arquitetura

## Visão geral

```text
                 Android Pulse
                 Kotlin/Compose
                       |
                       |
                 Pulse Web
             React/Vite/TypeScript
                       |
                       v
              Pulse Backend API
                 FastAPI / RPi
                       |
      +----------------+----------------+
      |                |                |
 Google APIs      APIs existentes    pulse.db
      |           dos módulos          |
 Gmail            RTO                 |
 Calendar         Peso                |
 Tasks            Bilhetes CP         |
                  Finanças            |
                  Tarefas             |
```

Android e Web são duas interfaces do mesmo produto. Devem consumir o mesmo backend, contratos e regras de negócio.

## Shared Infrastructure First

Sempre que tecnicamente adequado, Pulse e aplicações dedicadas devem partilhar:

- APIs;
- regras de negócio;
- modelos;
- validações;
- autenticação/autorização;
- notificações;
- jobs;
- contratos OpenAPI;
- testes de contrato.

Não duplicar lógica de negócio no Pulse se essa lógica já puder ser centralizada.

## Backend

Backend no Raspberry Pi:

- FastAPI;
- endpoints versionados `/api/v1/`;
- SQLite;
- serviços por módulo;
- Action/Tool layer para UI e IA;
- jobs/sync;
- notificações;
- atualização da app;
- autenticação;
- integração Google;
- pesquisa global.

## Dados

Existem bases de dados já existentes e separadas. Claude Code conhece o conteúdo e responsabilidade de cada uma.

Adicionar:

- `pulse.db`: produção, dados próprios do Pulse.
- `teste-pulse.db`: desenvolvimento/testes.

As bases existentes podem ser clonadas para `teste-*` quando necessário.

## Escritas

Todas as operações de criação, edição e eliminação usam a via oficial do respetivo módulo.

Proibido:

```text
Android/Web/IA -> SQL direto na BD de origem
```

Correto:

```text
Android/Web/IA -> Pulse API -> API/Core oficial do módulo -> BD
```

## Android offline

```text
UI
 |
Room/cache
 |
offline queue
 |
WorkManager/retry
 |
Pulse API
```

As operações devem usar idempotency keys quando necessário.

## Web

A Web fica alojada no Raspberry Pi e disponível em:

`https://bmdpereira.duckdns.org/pulse/`

Stack:

- React;
- Vite;
- TypeScript.

## IA

A IA usa o mesmo Action Layer que a interface convencional.

Níveis:
- read;
- safe_action;
- sensitive_action.

Sensitive actions exigem confirmação.

## Degraded mode

Uma falha num serviço não deve derrubar a aplicação completa.

Exemplo:
- Gmail indisponível;
- RTO, Peso, CP e Compras continuam operacionais.

A UI deve indicar de forma discreta o módulo afetado.

## Notificações

FCM é o canal oficial de notificações do Pulse.

ntfy não é requisito funcional principal; pode permanecer como ferramenta técnica/administrativa separada se útil no Raspberry Pi.
