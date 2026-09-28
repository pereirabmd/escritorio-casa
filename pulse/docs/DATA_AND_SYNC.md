# Dados e sincronização

## Bases de dados

Existem bases de produção já existentes e separadas, conhecidas pelo Claude Code.

Adicionar:

- `pulse.db`;
- `teste-pulse.db`.

As bases existentes podem ser clonadas para variantes `teste-*`.

## pulse.db

Destina-se apenas a dados próprios do Pulse, por exemplo:

- utilizadores;
- sessões;
- contas Google ligadas;
- credenciais OAuth encriptadas;
- preferências;
- configurações de módulos;
- favoritos/fixados;
- activity log;
- tokens FCM;
- estado de sincronização;
- feature flags;
- versões;
- módulo Compras;
- permissões/ações IA;
- sessões Web.

Não duplicar dados de origem sem necessidade.

## Android offline

Ações offline são persistidas localmente.

Estrutura conceptual:

```text
offline_queue
- id
- module
- action
- payload
- idempotency_key
- created_at
- retry_count
- status
```

Fluxo:

```text
ação utilizador
 -> cache local
 -> queue
 -> ligação disponível
 -> API
 -> serviço oficial
 -> confirmação
 -> estado synced
```

## Conflitos

Não assumir `last-write-wins` para todos os módulos.

Cada integração deve declarar:

- campos conflitáveis;
- estratégia;
- necessidade de confirmação;
- resolução automática ou manual.

## Estado visível

A interface deve conseguir apresentar:

- sincronizado;
- pendente;
- a sincronizar;
- erro;
- offline;
- serviço indisponível.

## Testes

- desenvolvimento e testes nunca escrevem nas BDs reais;
- usar `teste-pulse.db` e clones `teste-*`;
- migrations devem produzir o mesmo schema em produção e teste.

## Retenção

Centro de atividade:
- 30 dias;
- limpeza automática.

## Backups

`pulse.db` deve ser incluída e validada no processo de backup existente no Raspberry Pi.
