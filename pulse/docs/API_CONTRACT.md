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

### `GET /api/v1/tasks` (implementado)
Depois de qualquer ação do módulo Tarefas o Pulse pede ao `tarefas-api` o recálculo imediato dos avisos ntfy (`POST /recalcularAgora`, chave de serviço, em segundo plano e sem nunca falhar a ação: se não responder, o timer de 5 min reconcilia).

O módulo Tarefas (Hoje e catálogo): `hoje`, `feitas`, `atrasadas` (a mais recente de cada tarefa), `amanha`, `tarefas` (ativas, com `resumo` da repetição e `hora`),
`pessoas`, `categorias`, `horaPadrao` e `pessoa` (a do utilizador, pelo e-mail da Config). Regras em `services/tarefas.py`. O filtro por pessoa fica na interface;
nada da Config sensível (palavras-passe do ntfy…) sai.

Restantes secções do módulo (ADR-043), todas só de leitura e com as regras no servidor:
- `GET /api/v1/tasks/calendar?de=AAAA-MM-DD&ate=AAAA-MM-DD` — um dia por data (máx. 62 dias): `feriado` e `itens` (ocorrências de tarefas ativas, na ordem do «Hoje»); a Web pede o mês (grelha de domingo a sábado) ou a semana; 400 `intervalo_invalido` fora dos limites.
- `GET /api/v1/tasks/schedule` — horário escolar por aluno do ano letivo em curso: dias com `entra`, `sai`, `aviso` (saída menos os minutos da Config) e blocos (`dividida` = turma dividida, `ultima` = a que fecha o dia; as aulas que o aluno não frequenta não contam). `disponivel: false` se o módulo não responder (o resto do módulo continua).
- `GET /api/v1/tasks/pool` — piscina: estação, manutenção periódica (por ordem: nunca registadas primeiro, depois pela próxima data; `estado`: `nunca|ok|hoje|atrasada`) e ações condicionais (`registo`). Se faltar alguma tarefa do catálogo na base, acrescenta-a (`POST /tarefas/piscina/catalogo`, nunca toca nas existentes).
- `GET /api/v1/tasks/settings` — pessoas (nome, e-mail), pessoa do utilizador, preferências (não incomodar, avisos do horário), resumo dos últimos 7 dias por pessoa e `desequilibrio`, últimas 10 ações (auditoria), estado do Pi (`/saude` do `tarefas-api`, `null` se não responder) e, só para administradores, o painel `admin` (administradores e destinatários das notificações gerais).
- `GET /api/v1/tasks/history` — ocorrências feitas ou saltadas, para a interface exportar em CSV.

### Finanças (ADR-044, implementado)
- `GET /api/v1/finance?mes=AAAA-MM&janela=mes|30d` — o mês (`lancamentos` com `estado` derivado: `pago|vencido|hoje|pendente`; `totaisMes`), as despesas vencidas por pagar (`atrasadas`), a janela do resumo (`mes` = mês civil por vencimento; `30d` = hoje..+29) e o `resumo` «ativo − passivo» (`rendimento`, `porPagar`, `saldo`, `emAtraso` = vencidas antes da janela, `saldoComAtraso`, `porCategoria`), mais as `categorias`. Regras em `services/financas.py` (porta da app `financas/`). Ler não escreve: o mês só é preparado pela ação `financas.preparar_mes`.
- `GET /api/v1/finance/reports?de=AAAA-MM&ate=AAAA-MM` — totais por mês (`rendimento`, `despesas`, `saldo`) e por categoria (com o valor de cada mês); máx. 61 meses (400 `intervalo_invalido`).
- `GET /api/v1/finance/reminders` — lembretes agendados (avisos ntfy próprios da Finanças).

### Bilhetes CP (ADR-046, implementado)
- `GET /api/v1/tickets?semana=AAAA-MM-DD` — `proxima`/`proximas` (a viagem ativa em curso, até à chegada **estimada**, ou a seguinte), `semana` (a segunda-feira à volta da data pedida, por omissão a próxima; `dias` e `viagens` dessa semana), `semanaSeguinte` (`ativas` = 0 → falta configurar), `passe` (com `estado`: `sem_data|expirado|hoje|a_expirar|ok`), `bilhetes` (`proximos`, `anteriores`), `pedidos` (pendentes, com `retry`/`forcar` booleanos), `registo` (80 mais recentes, o mais novo primeiro), `estacoes` e `historico` (comboios já usados). Cada viagem traz `estado`: `comprado|por_comprar|inativa|em_curso|passada`, `fimEstimado` e a `compra` (carruagem, lugar, referência). Regras em `services/bilhetes.py`; a chegada estimada é partida + 180 min (não está guardada).
- Ações: `bilhetes.semana` (`inicio` = segunda-feira, `viagens[]` `{data, origem, destino, comboio, hora, ativo}`; substitui a semana e devolve `anteriores` para o «Desfazer»), `bilhetes.passe` (`dataUltimaCompra`, `validadeDias?`), `bilhetes.pedido_repetir` (`pedido`, `retry`, `intervaloMinutos?`), `bilhetes.pedido_forcar` (`pedido`).

### Compras (ADR-047, implementado)
- `GET /api/v1/shopping?lista=<id>` — `listas` (as visíveis: a «Casa», as pessoais próprias e as partilhadas; com `pendentes`/`total`), `lista` (a escolhida; por omissão a «Casa»; a lista pessoal de outra conta é 404), `grupos` (itens por comprar por corredor), `comprados`, `pendentes`, `categorias` (por ordem de corredor, com `oculta` para esta conta), `sugestoes` (`acabar` e `frequentes`: produto, nome, ícone, `ultima`, `diasDesde`, `compras`, `intervaloDias?`; ADR-048) e `produtos` (todo o catálogo com `favorito`/`oculto` da conta e, se estiver na lista escolhida, `item` e `estado`). Ler nunca escreve.
- Ações `compras.*` (dados do próprio `pulse.db`, nada vai ao `dados-api`): `adicionar` (`lista` + `produto` **ou** `nome` [+ `categoria`, `icone`], `cid?`; devolve o item e `novo`), `remover` (`item`; devolve o que era), `comprado` (`item`, `comprado`), `detalhes` (`item`, `quantidade?`, `nota`), `mover` (`item`, `lista`), `limpar_comprados` (sensível; `lista`), `restaurar` (`lista`, `itens[{produto, quantidade?, nota?, estado?}]`), `favorito`/`ocultar`/`sugestao_ignorar` (`produto`, `valor`), `categoria_ocultar` (`categoria`, `valor`), `produto_criar` (`nome`, `categoria`, `icone?`), `produto_editar` (`produto` + o que muda; só produtos próprios), `produto_apagar` (sensível), `lista_criar` (`nome`, `tipo?` = `pessoal|partilhada`), `lista_editar`, `lista_apagar` (sensível). Erros: 403 `lista_padrao`, `produto_de_serie`, `sem_permissao`; 409 `ja_existe`; 400 `demasiadas_listas`, `categoria_invalida`, `icone_invalido`, `quantidade_invalida`.

### Google: contas, Calendário e Email (ADR-049, implementado)
- `GET /api/v1/google/accounts` — `{configurado, servicos, contas: [{id, email, servicos, estado}]}` (sem tokens). `POST /google/connect` `{servicos: ["gmail"|"calendar"]}` → `{url}` do consentimento; `GET /google/callback` (sem sessão) regressa a Definições; `DELETE /google/accounts/{id}` revoga e apaga. 503 `google_desligado` sem configuração.
- `GET /api/v1/calendar?de=AAAA-MM-DD&ate=AAAA-MM-DD` — agenda de todas as contas com Calendar, por dia (máx. 62 dias); `ligado: false` sem contas. `GET /api/v1/mail?filtro=importantes|entrada|por_ler&conta?` — mensagens mais recentes primeiro e o estado de cada conta; `GET /mail/{conta}/{mensagem}` — texto simples, não marca como lida.
- Ações: `calendario.criar` (`conta`, `titulo`, `data`, `dataFim?`, `inicio?`/`fim?` HH:MM, `local?`, `descricao?`, `calendario?`), `calendario.editar`, `calendario.apagar` (sensível), `email.lida`, `email.arquivar`, `email.estrela` (`conta`, `mensagem` + booleano). Erros: 409 `reautorizar`, 403 `sem_permissao`, 502 `google_indisponivel`.

### Módulos e administração (ADR-046, implementado)
- `GET /api/v1/modules` — `{modulos: [{id, nome, disponivel, ativo}]}` (todos os módulos estão disponíveis desde o ADR-049).
- `PUT /api/v1/admin/modules` `{modulos: {<id>: bool}}` — só administradores (403 `sem_permissao`); ativa ou desativa módulos **para todos**. Um módulo desativado responde 403 `modulo_desativado` na sua API e nas suas ações, aparece como `{estado: "desativado"}` no Hoje e sai de Mais. Fica no centro de atividade (`modulo.ativar`/`modulo.desativar`).

### Notificações (ADR-045, implementado)
- `POST /api/v1/devices` `{token, nome?, plataforma?}` — regista (ou renova) o token FCM do dispositivo; devolve `{id}`. `DELETE /api/v1/devices/{id}` remove o do próprio utilizador.
- `GET /api/v1/notifications?desde=<id>&limite=50` — a caixa de eventos do utilizador (mais recentes primeiro; não mostra os `agendado`), com `naoLidas`. `POST /api/v1/notifications/read` `{ids?}` marca lidas (sem `ids`, todas).
- `POST /api/v1/internal/events` — **só na mesma máquina** (chave `X-Pulse-Key` ≥ 32 caracteres + `X-Pulse-User`; recusa qualquer pedido com `X-Real-IP`/`X-Forwarded-For`, isto é, vindo do nginx). Corpo: `{modulo, tipo, titulo, corpo?, dados?{str:str}, chave?, entregarEm?}`. `chave` torna o pedido idempotente; `entregarEm` (segundos Unix) no futuro agenda o envio (o FCM não agenda: o Pulse espera, ADR-032). Resposta 201 `{id, novo, estado}`; estados `agendado|novo|enviado|sem_canal|erro`.

## Ações (`/api/v1/actions`, implementado — fase 7)

Tudo o que altera dados passa pela camada de ações (a interface e, mais tarde, a IA chamam as mesmas):

```text
GET  /api/v1/actions                 -> catálogo [{nome, modulo, nivel, descricao}]
POST /api/v1/actions/{nome}          {params: {...}, confirmado?: bool} -> {resultado: <resposta do módulo>}
```

| Ação | Parâmetros | Escreve em |
|---|---|---|
| `tarefas.concluir` | `instancia` (`I…`) | `PUT /tarefas/instancias/{id}`; se estava Atrasada, `PUT /tarefas/instancias` (lote atómico) também para as atrasadas anteriores da mesma tarefa; devolve `tambem` |
| `tarefas.reabrir` | `instancia`, `tambem?` | `PUT` (uma) ou lote (várias) com `estado=Pendente` |
| `tarefas.saltar` | `instancia` | `PUT /tarefas/instancias/{id}` (`estado=Saltada`) |
| `tarefas.criar` / `tarefas.editar` | `nome`, `categoria`, `recorrencia`, `dias?`/`data?`/`diaMes?` conforme a repetição, `hora?`, `pessoa?`, `prioridade?`, `rotacao?`, `dependeDe?` (+ `tarefa` ao editar, `cid?` ao criar) | `POST` / `PUT /tarefas/tarefas` |
| `tarefas.apagar` (**sensitive**) | `tarefa` | `DELETE /tarefas/tarefas/{id}` (desativa e salta as pendentes) |
| `tarefas.adiar` | `instancia`, `data?` (por omissão amanhã; nunca no passado) | `PUT /tarefas/instancias/{id}` (`data`); 409 `conflito` se a tarefa já existir nesse dia |
| `tarefas.piscina_registar` / `tarefas.piscina_repor` | `item` (`P01`…); a segunda repõe `ultimaData`, `proximaData`, `usarIntervaloLongo`, `notificacaoEnviada` (o «Desfazer») | `PUT /tarefas/piscina/{id}` (próxima data e alternância de intervalo calculadas no servidor) e `POST /tarefas/auditoria` (`piscina_feita`, sem bloquear o registo); devolve `anterior` |
| `tarefas.avisos_horario` | `ativos` | `PUT /tarefas/config` (`HorarioAvisos`) |
| `tarefas.preferencias` | `naoIncomodarInicio`, `naoIncomodarFim` (`HH:MM` ou vazios) | `PUT /tarefas/config` |
| `tarefas.pessoa_adicionar` | `nome` (sem vírgulas), `email?` | `PUT /tarefas/config` (`Pessoa<N>_Nome/_Email`, N = próximo número); 409 `pessoa_existe` |
| `tarefas.pessoa_editar` | `nome`, `novoNome`, `email?` | renomear: `POST /tarefas/pessoas/reatribuir` (atómico, com `configChave`); e-mail: `PUT /tarefas/config` |
| `tarefas.pessoa_remover` (**sensitive**) | `nome`, `substituto?` (obrigatório se tiver tarefas por fazer) | `POST /tarefas/pessoas/reatribuir` (só pendentes) e `PUT /tarefas/config` (apaga as chaves `Pessoa<N>_*`); nunca a última pessoa |
| `tarefas.reatribuir` (**sensitive**) | `de`, `para` | `POST /tarefas/pessoas/reatribuir` (só pendentes) |
| `tarefas.admin` (**sensitive**) | `admins?`, `notificacoes?` (`piscina`/`horario` → nomes) | `PUT /tarefas/admin` (403 se não for administrador) |
| `tarefas.gerar` | — | `POST /gerar` no `tarefas-api` (cria já as ocorrências dos próximos dias); 503 se não responder |
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
| `financas.criar` / `financas.editar` | `tipo`, `descricao`, `valor`, `categoriaId`, `dataVencimento`, `dataPagamento?`, `recorrente?`, `mesReferencia?`, `cid?` (editar: `lancamento` + só o que muda; `dataPagamento: null` volta a pôr por pagar) | `POST`/`PUT /financas/lancamentos` |
| `financas.apagar` (sensível) | `lancamento` | `DELETE /financas/lancamentos/{id}` (devolve o lançamento, para o «Desfazer») |
| `financas.preparar_mes` | `mes` | `POST /financas/meses/{mes}/preparar` (idempotente; copia os recorrentes) |
| `financas.categoria_criar` / `_editar` / `_eliminar` (sensível) | `nome`, `cor?` / `categoria` | `/financas/categorias` (só apaga categorias sem lançamentos) |
| `financas.lembrete_criar` / `_editar` / `_eliminar` (sensível) | `titulo`, `nota?`, `data`, `hora`, `repeticao` (`unica|mensal`) / `lembrete`, `ativo?` | `/financas/lembretes` |

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
