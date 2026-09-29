# Decisões

## ADR-001 — Nome
Produto: Pulse.

## ADR-002 — Android
Kotlin + Jetpack Compose + Material 3.

## ADR-003 — Web
React + Vite + TypeScript.

## ADR-004 — Backend
FastAPI no Raspberry Pi.

## ADR-005 — Base Pulse
SQLite `pulse.db`.

## ADR-006 — Teste
`teste-pulse.db` e clones `teste-*` das duas BDs existentes.

## ADR-007 — Escritas
Sempre através da API/Core oficial.

## ADR-008 — Offline
Android offline-first com queue persistente.

## ADR-009 — Auth Android
Google para conta Pulse + PIN/biometria para desbloqueio da app.

## ADR-010 — Auth Web
Google apenas.

## ADR-011 — Google
Acesso Gmail/Calendar/Tasks gerido no servidor.

## ADR-012 — Notificações
FCM.

## ADR-013 — Centro de atividade
30 dias.

## ADR-014 — Favoritos
Configuráveis e reordenáveis por drag-and-drop/long press.

## ADR-015 — Pesquisa
Pesquisa global entra na V1.

## ADR-016 — Compras
Exclusiva do Pulse.

## ADR-017 — Migração primeira vaga
RTO, Peso, Tarefas e Bilhetes CP.

## ADR-018 — Descontinuação
O utilizador decide quando cada app migrada está pronta para ser descontinuada.

## ADR-019 — Tarefas
Pode continuar como app dedicada para outros utilizadores.

## ADR-020 — IA
Deve poder executar ações; arquitetura preparada desde início.

## ADR-021 — IA permissões
`read`, `safe_action`, `sensitive_action`.

## ADR-022 — Dados sensíveis
Visíveis por defeito após autenticação; ocultação é opcional.

## ADR-023 — Web URL
`https://bmdpereira.duckdns.org/pulse/`

## ADR-024 — Página pública
`https://pereirabmd.github.io/escritorio-casa/index.html`

## ADR-025 — Versionamento
`beta_YYYYMMDD_X`, com X global e nunca reiniciado.

## ADR-026 — APK
Fora da Play Store, com atualização interna e instalação pelo mecanismo normal do Android.

## ADR-027 — Backups
Claude Code valida explicitamente a inclusão de `pulse.db`.

## ADR-028 — Dashboard
Apenas main features; profundidade dos módulos fica em Mais.

## ADR-029 — Idioma
Português de Portugal (`pt-PT`).

## ADR-030 — Visual
Profissional, moderno, completo, clean e sem aparência genérica de IA.

## ADR-031 — Fronteira Pulse ↔ APIs existentes (28/09/2026)
O backend do Pulse não reimplementa nem lê diretamente as bases dos módulos: chama as APIs oficiais existentes
(`dados-api`, em `127.0.0.1:8898`, para Peso, RTO, Tarefas, Finanças e Bilhetes CP) em nome do utilizador.

- Autenticação serviço-a-serviço: `X-Pulse-Key` (segredo `PULSE_SERVICE_KEY`, ≥ 32 caracteres, só no `.env` do Pi) e
  `X-Pulse-User` (e-mail do utilizador Pulse). Só vale numa ligação direta em loopback: o nginx acrescenta sempre
  `X-Real-IP`, por isso nada vindo da Internet chega a esta via. O e-mail continua sujeito a `ACL_<APP>` e aos limites
  por utilizador. Implementado em `dados/api.py`, com testes (`ServicoPulseTest`). Em produção desde 28/09/2026.
- O Pulse tem sessões próprias (ADR-009/010); o token Google nunca é reencaminhado para as APIs dos módulos.
- Utilizadores: por agora só o dono. A estrutura (sessão → e-mail → ACL) já suporta mais pessoas, mas as APIs
  atuais só têm ACL por app (tudo ou nada); filtrar por pessoa é trabalho do Pulse quando houver mais utilizadores.
- Risco aceite: a chave de serviço personifica qualquer e-mail das ACL; um backend comprometido compromete as apps.
- `ctx.ip` das chamadas de serviço é `127.0.0.1`; o `naLan` da administração dos Bilhetes conta loopback como LAN.
  Irrelevante enquanto o Pulse não expuser essa administração; a rever antes disso.
- O `tarefas-api` (botões das notificações ntfy, recálculo, `configurarNtfy`) não é chamado pelo Pulse: as Tarefas
  do Pulse usam as rotas `/tarefas/*` do `dados-api`, tal como a PWA.

Contratos de leitura/escrita que o Pulse consome (dashboard «Hoje»):

| Cartão | Chamada |
|---|---|
| RTO da semana | `GET /rto/dias?desde&ate`, `PUT /rto/dias/{data}` |
| Peso de hoje | `GET /peso/registos?desde=…`, `POST /peso/registos` (com `cid`) |
| Próximas contas | `GET /financas/lancamentos?pendentes=1&de&ate`; pagar: `PUT /financas/lancamentos/{id}` |
| Tarefas de hoje | `GET /tarefas/dados`; concluir: `PUT /tarefas/instancias/{id}` (`estado=Feita`, `dataConclusao`) |
| Próximo bilhete | `GET /bilhetes/proximo` (novo: viagem ativa seguinte, compra se existir, passe) |

O agregado do «Hoje» faz-se no backend do Pulse (5-6 chamadas em loopback), para o cliente fazer um só pedido.
O limite por IP do `dados-api` (120/min) é partilhado por todas as chamadas do serviço.

Idempotência da fila offline (`idempotency_key` do Android → `cid`): Peso, RTO e Finanças já aceitavam `cid`; as
Tarefas passam a aceitá-lo em `POST /tarefas/tarefas` e `POST /tarefas/instancias` (migração `008_tarefas_cid.sql`,
coluna anulável, ninguém mais a nomeia). Um pedido repetido com o mesmo `cid` devolve o criado (200 em vez de 201).
Formato: 8-64 caracteres `[A-Za-z0-9-]` (um UUID serve).

## ADR-032 — Notificações: FCM no Pulse, ntfy nas outras apps (28/09/2026)
O Pulse usa FCM. As apps dedicadas mantêm o ntfy, sem alterações, até existir uma camada comum (fase posterior,
já prevista). Consequências assumidas:

- Enquanto convivem, o mesmo evento pode chegar por dois canais a quem usar as duas coisas; aceita-se e resolve-se
  quando a camada comum existir.
- O ntfy agenda mensagens no servidor; o FCM não. O Pulse precisa de um agendador próprio (timer que dispara à hora
  certa) para lembretes com hora (tarefas, horário escolar, contas a pagar). Não se reutiliza o agendamento do ntfy.
- Os botões das notificações (concluir, adiar) passam a ser ações de notificação do Android que chamam a API do Pulse.
- Prioridade: todas as notificações do Pulse com prioridade alta, como no ntfy (sempre visíveis no telemóvel).
- Envio: API HTTP v1 do FCM com a chave privada de uma service account, guardada só no Pi, fora do repositório.
- Tokens FCM dos dispositivos: tabela própria do `pulse.db` (já prevista em DATA_AND_SYNC).
- Projeto Firebase: `bmdpereira-5a8f4`. `google-services.json` e a chave da service account nunca entram no
  Git (repositório público): estão no `.gitignore` do Pulse e a guarda do `push.sh` cobre `firebase-adminsdk*.json`.

## ADR-033 — «Adiar» uma tarefa = mudar-lhe a data (28/09/2026)
No cartão de tarefas do «Hoje», «Adiar» passa a ocorrência para outra data (por defeito amanhã, com escolha de
data), com `PUT /tarefas/instancias/{id}` e o campo `data`. Não muda nenhuma API.
- Se já existir uma ocorrência dessa tarefa no dia de destino, o servidor responde 409 (`(tarefa, data)` é único):
  o Pulse avisa e oferece concluir ou saltar a de hoje; nunca funde duas.
- Adiar não conta como atraso nem escala avisos (princípio: lembretes ajudam, não impõem).
- «Lembrar daqui a 1 h» (o snooze das notificações ntfy) fica para depois do agendador do ADR-032.

## ADR-034 — Identidade Android e chave de assinatura (28/09/2026)
- `applicationId`: `pt.pereirabmd.pulse` (não muda: mudá-lo obriga a reinstalar e a refazer registos no Firebase/OAuth).
- Assinatura: keystore própria do Pulse (`~/.local/keystores/pulse.jks`, alias `pulse`, RSA 2048, validade até 2054),
  com a palavra-passe em `pulse-keystore.properties` (600), tudo fora do repositório e copiado para um gestor de
  passwords. Serve as builds de teste e as de publicação (ADR-026: a mesma chave em todas as versões).
  SHA-1: `8F:93:FC:29:59:4E:04:2B:D2:D1:DF:FC:F3:62:80:5C:59:76:B4:1F`.
- Independente da chave do `resumo_widget` (`resumo-debug.jks`), que continua a servir só esse widget.

## ADR-035 — Toolchain Android e teste de compilação (28/09/2026)
Compilar Kotlin + Compose cabe na máquina de desenvolvimento (3,2 GB de RAM, ~700 MB livres): projeto mínimo com
AGP 8.4.2, Kotlin 1.9.24, Compose BOM 2024.06 e JDK 17, `assembleDebug` em 2 min 13 s, APK de 7,9 MB. Definições que
o tornaram possível, a manter no `gradle.properties` do Pulse: `org.gradle.jvmargs=-Xmx1024m -XX:MaxMetaspaceSize=384m`,
`org.gradle.parallel=false`, `org.gradle.daemon=false`, `kotlin.compiler.execution.strategy=in-process`.
Por confirmar: o plugin `com.google.gms.google-services` 4.5.0 e o Firebase BoM 34.19.0 podem pedir AGP/Kotlin
mais recentes; testar o build com essas dependências antes de fixar versões. Um Pulse completo será mais pesado que o
teste (esperam-se builds limpos de 5-10 min).

## ADR-036 — Instalação do backend no Pi (28/09/2026)
Segue `FOLDER_STRUCTURE.md`/`OPERATIONS_AND_BACKUP.md`: releases `beta_YYYYMMDD_X` em `/opt/pulse/releases` com `current`
(symlink), dados em `/var/lib/pulse`, logs em `/var/log/pulse`, serviço `pulse-api` (uvicorn, `127.0.0.1:8897`, mesmo
sandbox do `dados-api`) e `location /pulse/api/` no nginx existente. Desvios do documento: (1) os segredos ficam em
`/etc/pulse-app/pulse.env` porque `/etc/pulse/` já é do PulseAudio; (2) o venv (`/opt/pulse/venv`) é partilhado entre
releases. O backup do `pulse.db` usa o mecanismo existente do `dados/` (`BACKUP_BASES_EXTRA`) em vez de um segundo
temporizador; restauro testado. Ver `pulse/infra/README.md`.

## ADR-037 — Contas próprias por e-mail e password (substitui ADR-009 e ADR-010) (28/09/2026)
O login do Pulse deixa de ser «Google apenas». Contas próprias, com **e-mail como identificador de registo** e password,
**criadas pelo administrador (convite); não há auto-registo.**

- Porquê: o Pulse pode ter mais utilizadores (também sem conta Google) e não depende de clientes OAuth para entrar.
  O e-mail da conta é o que o Pulse envia como `X-Pulse-User` (ADR-031) e é comparado com as `ACL_<APP>`; por isso o
  e-mail nunca pode ser reclamado por quem não é o dono: sem auto-registo, é o administrador quem o garante.
- Password: scrypt (`hashlib`), política mínima (≥ 10 caracteres, sem previsíveis); a inicial dada pelo administrador
  **obriga a mudar no primeiro acesso** (até lá só `/auth/me`, `/auth/password`, `/auth/logout` funcionam) e mudar
  termina as outras sessões. Sem SMTP, «esqueci-me da password» = o administrador repõe (`pulse.cli repor`).
- Sessão própria: token aleatório guardado só como SHA-256 em `pulse_sessions`, validade deslizante de 30 dias
  (`PULSE_SESSION_DAYS`), revogável e listável por dispositivo. Web: cookie httpOnly/Secure/SameSite=Lax de `Path=/pulse/`
  e cabeçalho `X-Pulse-Client` obrigatório nos pedidos que alteram (CSRF). Android: `cliente: "android"` devolve o token,
  enviado em `Authorization: Bearer`; o PIN/biometria continuam só no Android, por cima (ADR do AUTH_AND_SECURITY).
- Defesa: erro único para e-mail inexistente/password errada/conta desativada (com custo de tempo igual); 5 falhas seguidas
  bloqueiam a conta 10 min; 10 tentativas/min por IP (mais o `limit_req` do nginx); tudo auditado em `pulse_activity`
  (nunca passwords).
- Administração: `python -m pulse.cli criar|repor|desativar|ativar|listar` no servidor (password pelo stdin, nunca na linha de
  comandos). Sem endpoints de administração de utilizadores por agora.
- O Google continua necessário só para **ligar** Gmail/Calendar (fase 10), sem servir de login; «Entrar com Google»
  pode acrescentar-se depois ligado à mesma conta, sem refazer isto. Utilizadores extra só veem os módulos em cujas
  `ACL_<APP>` estiverem (o `dados-api` recusa o resto com 403); filtrar dados por pessoa dentro de cada app é trabalho futuro.

## ADR-038 — Web do Pulse (28/09/2026)
React + Vite + TypeScript em `pulse/web/`, servida como ficheiros estáticos pelo nginx a partir da release ativa
(`/opt/pulse/current/web`, e não `/var/www/pulse/` como previa o FOLDER_STRUCTURE: assim Web e API trocam juntas de versão e
o rollback do symlink cobre ambas). Mesma origem que a API (`/pulse/api/v1`) para o cookie de sessão httpOnly; CSP
restrita (`default-src 'none'`, sem estilos nem scripts inline). React Router com `basename=/pulse` e `try_files` no nginx.
Sem bibliotecas de UI nem de estado: Design System próprio (tokens Light/Dark, Inter incluída no build, ícones SVG).
Testes com Vitest + Testing Library. Publicação por `deploy_pi.sh`, que só envia se lint, testes e build passarem.

## ADR-039 — Camada de ações e ações do «Hoje» (28/09/2026)
Fase 7 começa pelas ações rápidas do «Hoje»: concluir/reabrir e adiar tarefa, registar peso, marcar dia de RTO, pagar/anular conta.
Em vez de um endpoint por operação, existe uma **camada de ações** (`server/pulse/actions.py`, `POST /api/v1/actions/{nome}`) que é
o Action/Tool layer do AI_SPEC: catálogo com módulo e nível, parâmetros validados (pydantic, campos extra recusados),
confirmação para `sensitive_action`, escrita só pela API oficial do módulo (ADR-031) e registo em `pulse_activity` com a origem.
A interface usa-a hoje; a IA usará a mesma (origem `ia`), sem SQL nem atalhos. Cada ação tem inversa para «Desfazer»; a interface
mostra uma confirmação curta (não um aviso de condição persistente). O `cid` do registo de peso é gerado na interface e mantém-se
até haver sucesso, por isso repetir um pedido que falhou não duplica. **Contrato:** `tests/test_contract_dados.py` corre o código
real do `dados-api` (como script, em bases `teste-*`) e exerce cada ação e o agregado; nada é testado contra bases reais.
Fora desta fatia (próximas): módulos completos em «Mais» (Tarefas, Peso, RTO, Finanças, Bilhetes CP) e a fila offline do Android.

## ADR-040 — Estatísticas de módulo no servidor; Peso completo (29/09/2026)
Primeiro módulo completo em «Mais»: Peso. A lógica de negócio que na app dedicada vivia no JavaScript (IMC, gasto diário, ritmo, progresso,
sequência, análise por regressão, previsão…) foi **portada para o servidor** (`services/peso.py`, funções puras, 28 testes) e o
`GET /api/v1/weight` devolve-a calculada: a Web e o Android mostram os mesmos números sem duplicar fórmulas (`ARCHITECTURE.md`: não
duplicar lógica de negócio). Padrão para os restantes módulos: `GET /api/v1/<módulo>` com dados + resumo calculado, escritas só por ações.
Apagar um registo é `sensitive_action` (a interface pergunta e envia `confirmado`); o «Desfazer» repõe o registo com a data original
(`peso.registar` aceita `quando`). O ecrã segue a estrutura da app dedicada (Resumo, Gráfico, Registos, Configuração) com o Design System
Pulse; a tabela de paridade fica em `PARITY_PESO.md` (o que falta está lá, marcado como pendente).

## ADR-041 — RTO completo (29/09/2026)
Segundo módulo completo. Seguindo o ADR-040, as regras de negócio que viviam no JavaScript da app dedicada (feriados e Páscoa, classificação das notas em
férias/astreinte/suspensão, totais, quota pro-rata, saldo e saldo condicional, estado de hoje e próxima mudança) foram portadas para o servidor
(`services/rto.py`, 28 testes) e `GET /api/v1/rto` devolve tudo calculado. As escritas são ações; a lógica de marcar férias (juntar, encolher, dividir) e o
gerador de validações vivem no servidor e são exercidos por testes de contrato contra o `dados-api` real. Decisões de interface: o ciclo de toque
T→C→vazio e os modos Férias/Administrador da app dedicada foram substituídos por um painel do dia com botões explícitos, e o «modo administrador» ficou
só como interruptor das notas em datas passadas (validado no servidor). Marcar o dia de férias e eliminar notas têm «Desfazer»; eliminar é ação sensível.
Paridade em `PARITY_RTO.md`.

**Correção (29/09/2026):** a primeira versão do RTO deixou marcar qualquer dia e reduziu o «modo administrador» às notas — não era paridade. Passou a seguir a app
dedicada: no modo normal só se marcam dias úteis de hoje em diante (fins de semana e dias passados bloqueados, na interface e no servidor: `dia_bloqueado`); o modo
administrador (com confirmação, aviso visível e parâmetro `admin` nas ações) liberta marcas, férias e notas sem restrições, incluindo fins de semana.

## ADR-042 — Tarefas: primeira fatia (29/09/2026)
A app Tarefas é a maior (Hoje, Calendário, Tarefas, Horário, Piscina, Config com pessoas, notificações e administração) e continua em paralelo para outros
utilizadores (ADR-019). O Pulse migra-a por fatias, sobre as mesmas rotas `/tarefas/*` do `dados-api` e a mesma BD (partilha de infraestrutura). **Fatia 1:** Hoje
(filtro por pessoa, concluir com fecho das atrasadas anteriores, saltar, adiar, ligação ao Google Calendar) e catálogo (criar, editar, duplicar, apagar). As regras
(atrasadas por tarefa, ordenação, resumo da repetição, pessoa do utilizador) vivem em `services/tarefas.py`; `GET /api/v1/tasks` devolve tudo calculado.
`tarefas.concluir` passou a ler o estado da instância para replicar o lote atómico da app dedicada. Limite conhecido: o Pulse ainda não pede ao `tarefas-api` o
recálculo imediato dos avisos ntfy (o timer de 5 min apanha-o); fica pendente e na tabela de paridade `PARITY_TAREFAS.md`, tal como Calendário, Horário, Piscina e
Config (as notificações por pessoa dependem da decisão sobre FCM/ntfy, ADR-032).

## ADR-043 — Tarefas completas e recálculo imediato dos avisos (29/09/2026)
As restantes secções da app Tarefas (Calendário, Horário, Piscina, Config) entram no Pulse seguindo o padrão dos ADR-040/041: `GET /api/v1/tasks/<secção>` com as regras
no servidor (`services/tarefas.py`, `horario.py`, `piscina.py`, funções puras) e escritas só por ações (catálogo em `API_CONTRACT.md`). Decisões: **(1)** o Calendário pede um
intervalo (o mês em grelha de domingo a sábado, ou a semana; máx. 62 dias), em vez de o cliente ter todas as ocorrências; os feriados são os da app dedicada (sem o municipal do RTO).
**(2)** O catálogo da Piscina é estático no servidor, como na app dedicada; a próxima data e a alternância 3/4 dias são calculadas no servidor e `piscina_registar` devolve o estado
anterior para o «Desfazer». **(3)** Pessoas: adicionar, renomear (atómico, leva tarefas e ocorrências), remover (só com substituto se houver tarefas por fazer; nunca a última) e
reatribuir em massa; remover, reatribuir e alterar a administração são ações sensíveis (confirmação). **(4)** A ligação a notificações ntfy por pessoa (utilizador/palavra-passe) **não** se
migra: o Pulse terá notificações próprias (FCM, ADR-032) e a app dedicada mantém o ntfy. **(5)** Recálculo imediato dos avisos: o `tarefas-api` (`servidor.py`) passou a aceitar a
chave de serviço do Pulse (`X-Pulse-Key`/`X-Pulse-User`, só em loopback direto, e-mail na `ACL_TAREFAS`; chave curta = desligado) e, depois de cada ação do módulo, o Pulse pede
`POST /recalcularAgora` **em segundo plano e sem nunca falhar a ação** — é uma otimização, o timer de 5 min continua a ser a rede de segurança. `tarefas.gerar` (criar já as
ocorrências) usa a mesma via. Consequência operacional: a `PULSE_SERVICE_KEY` tem de estar também no `.env` do `tarefas-api`.

## ADR-044 — Finanças no Pulse (29/09/2026)
A app `financas/` (v1.2.0) passa a módulo do Pulse, sobre as mesmas rotas `/financas/*` do `dados-api` e a mesma BD (a app dedicada **não** se descontinua: só quando o utilizador o declarar, ver `PARITY_FINANCAS.md`).
Decisões: **(1)** `GET /api/v1/finance` devolve o mês, o resumo «ativo − passivo» e as vencidas já calculados (`services/financas.py`); o estado (pago/vencido/hoje/pendente) continua a **derivar-se** de `data_pagamento` e `data_vencimento`, nunca a guardar-se.
**(2)** Ler nunca escreve: o ciclo mensal (copiar os recorrentes) é a ação `financas.preparar_mes`, que a Web chama ao abrir um mês até ao seguinte; é idempotente no `dados-api` (`financas_meses`). **(3)** Escrever é só por ações; apagar lançamentos, categorias e lembretes é sensível (confirmação) e o «Desfazer» de um lançamento volta a criá-lo (o id muda; a app dedicada faz o mesmo).
**(4)** O aviso de vencidas é persistente (não é um toast), como na app dedicada. **(5)** Os avisos ntfy da Finanças (vencimentos e lembretes) continuam a sair do `financas_notificar.py` do Pi; o Pulse só gere os lembretes. **(6)** Fila offline e cache de meses ficam para o Android (fase 5), como no Peso/RTO; a Web é só online.

## ADR-045 — Notificações: caixa de eventos e FCM, com o ntfy em uso (29/09/2026)
Concretiza o ADR-032 sem mexer no que funciona: **o `bilhetes_cp` continua a avisar por ntfy** e, em paralelo e de melhor esforço, copia cada aviso para o Pulse (`common.pulse_event`, desligado sem `PULSE_EVENTS_URL`, `PULSE_SERVICE_KEY` e `PULSE_EVENTS_USER`). Passar o Android de ntfy para FCM é, no dia em que a app Android existir, registar o token (`POST /devices`) e deixar de subscrever o tópico ntfy — sem alterar o `bilhetes_cp`.
- **Tabelas** (`003_notificacoes.sql`): `pulse_devices` (token FCM por utilizador) e `pulse_events` (caixa de saída). Um evento entra **uma vez** (idempotente por `chave`) e fica sempre guardado: sem canal FCM ligado, sem dispositivo ou com o Google em baixo, o Android vai buscá-lo a `GET /notifications?desde=<id>`.
- **Agendamento**: o FCM não agenda, por isso o Pulse guarda o evento com `entregarEm` e um agendador (tarefa de fundo do próprio servidor, `PULSE_SCHEDULER_S`, 30 s) entrega o que venceu e repete as falhas temporárias (até 5 tentativas; depois `erro`, sem novas tentativas sozinho). Dispositivo cujo token o Google diz não existir fica inativo.
- **FCM** (`notifications.FcmCanal`): API HTTP v1, prioridade alta, OAuth por JWT RS256 da service account (`PULSE_FCM_CREDENTIALS`, só no Pi, fora do Git; sem ficheiro ou inválido = desligado, o Pulse arranca na mesma). A assinatura precisa de `cryptography` (import tardio; **instalar no venv do Pi antes de ligar o FCM**). **Não foi testado contra o Firebase real** (só com transporte simulado): o primeiro envio a sério é o teste que falta.
- **Segurança**: `/internal/events` exige a chave de serviço, e-mail de conta ativa e ligação em loopback sem `X-Real-IP`/`X-Forwarded-For` (o nginx põe-nos sempre); o bloco `location /pulse/api/v1/internal/` do nginx devolve 404 como segunda barreira.
- **Prioridade alta em tudo** e um canal Android por módulo (`pulse_<módulo>`).

## ADR-046 — Bilhetes CP no Pulse e módulos ativáveis pelo administrador (29/09/2026)
**Bilhetes CP.** A app `bilhetes_cp/` passa a módulo do Pulse sobre o mesmo `dados-api` (`/bilhetes/*`, `bilhetes.db`): Semana (próximo comboio, passe, viagens da semana e editor), Bilhetes, Pedidos e Registo, com as regras em `services/bilhetes.py` (`GET /api/v1/tickets`) e escritas só por ações. Decisões: **(1)** o editor da semana tem os 7 dias fixos, cada um com 0..N viagens e um «Ativo» **por dia** (como na app dedicada); guarda-se a semana inteira e o `dados-api` preserva os ids das viagens que continuam (são a chave do lock de compra); dias passados não se alteram. O «Desfazer» volta a gravar as viagens que lá estavam. **(2)** A chegada de um comboio não está guardada: o cartão do Hoje e o ecrã mantêm a viagem «Em viagem» até partida + 180 min (estimativa). **(3)** As estações vêm de Aveiro e Lisboa Oriente mais as já usadas; quem as valida a sério continua a ser o Pi. **(4)** A verificação do horário contra a CP (a app dedicada consulta a API da CP do telemóvel, com chaves importadas) **não** vem para já: fica pendente (`PARITY_BILHETES.md`). **(5)** A página de administração dos utilizadores fica só na LAN (Pi), como está.
**Módulos.** Nova secção Definições → Administração (só administradores) para ativar/desativar módulos **para todos os utilizadores** (`pulse_settings.modulos_desativados`; um módulo novo nasce ativo). O servidor faz cumprir: 403 `modulo_desativado` na API e nas ações, e o Hoje nem pede dados ao módulo desativado. A Web esconde-o de Mais e do Hoje e explica no ecrã se se chegar lá por ligação. Calendário, Email e Compras («Em breve») não se alteram. Se o administrador quiser preferências por conta (cada um esconde o que não usa), é uma evolução separada; hoje é uma decisão do administrador.

