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

## Módulos (leitura)

### `GET /api/v1/weight` (implementado)
O módulo Peso completo: `{registos[], config, resumo}`. O `resumo` (peso atual e diferença, sequência, novo mínimo, controlo, progresso,
total perdido, ritmo, faltam, IMC, gasto diário, mínimo/máximo, análise e previsão) é calculado no servidor (`services/peso.py`, porta da
app dedicada) para a Web e o Android mostrarem exatamente o mesmo. Erros do módulo passam tal e qual (403 `sem_acesso`, 503 `modulo_indisponivel`).

### `GET /api/v1/rto?ano=AAAA` (implementado)
O módulo RTO de um ano (por omissão o atual): `dias` (marcas T/C do ano pedido e dos vizinhos), `notas`, `feriados` (3 anos), `ferias`/`astreinte`/`suspensao`
(datas), `marcasNotas` (a letra F/A de cada dia), `totais` (T, C, condicional, créditos de astreinte, quota pro-rata, saldo, saldo condicional),
`mensal` (T/C por mês), `hoje` (estado de hoje) e `proximaMudanca`. As regras vivem em `services/rto.py` (porta da app dedicada).

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
| `peso.registar` | `peso` (1–1000), `nota?`, `cid?`, `quando?` (repor um registo) | `POST /peso/registos` (idempotente com `cid`) |
| `peso.editar` | `registo`, `quando`, `peso`, `nota?` | `PUT /peso/registos/{id}` |
| `peso.eliminar` (**sensitive**, exige `confirmado`) | `registo` | `DELETE /peso/registos/{id}` (devolve o registo apagado, para «Desfazer») |
| `peso.configurar` | qualquer de `altura`, `nascimento`, `sexo`, `pesoAlvo`, `atividade`, `diaControlo`, `pesoMin`, `pesoMax` (`null` apaga) | `PUT /peso/config` |
| `rto.marcar_dia` | `data`, `marca` (`T`, `C` ou `""` para limpar), `admin?` | `PUT /rto/dias/{data}` |
| `rto.ferias_dia` | `data` (alterna), `admin?` | notas `POST`/`PUT`/`DELETE /rto/notas…` (junta, encolhe ou divide) e limpa a marca do dia |
| `rto.nota_criar` / `rto.nota_editar` | `inicio?`, `fim?`, `categoria`, `descricao`, `admin?` (+ `nota` ao editar, `cid?` ao criar) | `POST` / `PUT /rto/notas` |
| `rto.nota_eliminar` (**sensitive**) | `nota`, `admin?` | `DELETE /rto/notas/{id}` (devolve a nota, para «Desfazer») |
| `rto.nota_restaurar` | como editar (repõe com o mesmo id) | `PUT /rto/notas/{id}` (upsert) |
| `rto.gerar_validacoes` | `referencia`, `ate`, `tipo` | `POST /rto/notas/lote` em lotes de 100 |
| `financas.pagar` / `financas.anular_pagamento` | `lancamento`, `data?` | `PUT /financas/lancamentos/{id}` (`data_pagamento`) |

Regra do RTO: sem `admin: true` só se marcam (T/C/férias) dias úteis de hoje em diante (400 `dia_bloqueado`); `admin` também liberta as notas em datas passadas (400 `data_passada`).

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
