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

## Ações (`/api/v1/actions`, implementado — fase 7)

Tudo o que altera dados passa pela camada de ações (a interface e, mais tarde, a IA chamam as mesmas):

```text
GET  /api/v1/actions                 -> catálogo [{nome, modulo, nivel, descricao}]
POST /api/v1/actions/{nome}          {params: {...}, confirmado?: bool} -> {resultado: <resposta do módulo>}
```

| Ação | Parâmetros | Escreve em |
|---|---|---|
| `tarefas.concluir` / `tarefas.reabrir` | `instancia` (`I…`) | `PUT /tarefas/instancias/{id}` (`estado`, `dataConclusao`) |
| `tarefas.adiar` | `instancia`, `data?` (por omissão amanhã; nunca no passado) | `PUT /tarefas/instancias/{id}` (`data`); 409 `conflito` se a tarefa já existir nesse dia |
| `peso.registar` | `peso` (1–1000), `nota?`, `cid?` | `POST /peso/registos` (idempotente com `cid`) |
| `rto.marcar_dia` | `data`, `marca` (`T`, `C` ou `""` para limpar) | `PUT /rto/dias/{data}` |
| `financas.pagar` / `financas.anular_pagamento` | `lancamento`, `data?` | `PUT /financas/lancamentos/{id}` (`data_pagamento`) |

Regras: parâmetros validados antes de tocar em nada (400 `parametros_invalidos`; campos a mais recusados); os erros do módulo passam
tal e qual (409 `conflito`, 404 `nao_encontrado`…); módulo em baixo = 503 `modulo_indisponivel`; ações `sensitive_action` exigem
`confirmado: true` (409 `confirmacao_necessaria`); cada execução fica em `pulse_activity` com a origem (`ui`/`ia`), o resultado e só
ids/datas (nunca valores pessoais como o peso). Todas as ações atuais são `safe_action` e têm ação inversa (`reabrir`,
`anular_pagamento`, marca vazia) para o «Desfazer» da interface.

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
