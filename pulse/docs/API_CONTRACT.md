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

## Autenticação (ADR-037)

```text
POST   /api/v1/auth/login          {email, password, cliente: web|android} -> cookie (web) | token (android)
GET    /api/v1/auth/me             -> {utilizador{..., mudarPassword}}
POST   /api/v1/auth/password       {atual, nova}
POST   /api/v1/auth/logout
GET    /api/v1/auth/sessions       DELETE /api/v1/auth/sessions/{id}
```

Web: cookie httpOnly + cabeçalho `X-Pulse-Client` nos pedidos que alteram. Android: `Authorization: Bearer`. Com
`mudarPassword` verdadeiro só `/auth/me`, `/auth/password` e `/auth/logout` respondem; o resto dá 403 `mudar_password`.

## Dashboard

Deve agregar apenas dados necessários ao Hoje.

### `GET /api/v1/dashboard/today` (implementado)
Um só pedido para o «Hoje». Exige sessão com a palavra-passe já mudada. O backend chama, em paralelo e em nome do utilizador,
as APIs dos módulos (ADR-031) e devolve:

```text
{ estado: "ok" | "degradado", geradoEm, data, resumo: null,   # `resumo` reservado ao insight do Pulse (IA, mais tarde)
  modulos: {
    tarefas:   { hoje[], atrasadas, feitasHoje, totalHoje, pessoa },   # só as do utilizador (Pessoa<N>_Email) e as sem responsável
    bilhetes:  { proximo{..., compra|null}, passe{diasRestantes,...} },
    rto:       { semana{inicio,fim}, dias[7]{data,diaSemana,marca:"T"|"C"|"",hoje}, contagem{T,C} },
    peso:      { ultimo{quando,peso}|null, registadoHoje, sugestao },   # `sugestao` pré-preenche o registo de hoje
    financas:  { proximas[≤5], vencidas, total, valorTotal },           # despesas pendentes até 30 dias, mais as vencidas
    calendario, email: { estado: "nao_ligado" }                          # fase 10
  } }
cada módulo: { estado: "ok" | "indisponivel" | "sem_acesso" | "erro", dados | erro{codigo,mensagem} }
```

Modo degradado: um módulo que falha aparece com o seu `estado` e os restantes continuam (o agregado passa a `degradado`);
`sem_acesso` (o utilizador não está na ACL desse módulo) e `nao_ligado` não contam como falha. As ações do cartão (concluir/
adiar tarefa, editar semana de RTO, registar peso, pagar conta) usam as rotas de escrita de cada módulo, a definir na fase 7.

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
