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

## ADR-047 — Compras (29/09/2026)
Módulo exclusivo do Pulse (ADR-016): os seus dados são os únicos que vivem no `pulse.db` (migração `004_compras.sql`; já coberto pelo backup diário). Decisões: **(1) Listas:** a lista **«Casa»**
é partilhada por todas as contas e não se renomeia nem apaga; cada conta pode criar listas **pessoais** (só o dono as vê; para os outros são «inexistentes», 404) e qualquer conta pode criar
listas **partilhadas** extra (máx. 10 de cada tipo por conta). Um item passa de uma lista para outra (`compras.mover`). **(2) Produto único por lista; quantidade nunca direta:** tocar num produto do catálogo
põe-no na lista e tocar outra vez tira-o; a quantidade é opcional e só se define nos detalhes do item (vazio = sem quantidade). Adicionar nunca soma. Um item comprado volta a ficar por comprar (sem quantidade
nem nota) ao tocar de novo. Preços e orçamento ficam fora (uma ligação às Finanças, se alguma vez houver, é outra decisão). **(3) Idempotência:** as ações **definem** estados
(`comprado`, `quantidade`) em vez de os alternar, e `adicionar` aceita `cid`, para a fila offline do Android poder repetir sem efeito. **(4) Catálogo de série:** 338 produtos em 13 corredores
(`pulse/server/pulse/compras_catalogo.py`), sincronizados a cada arranque por `slug` estável: inserem-se os novos, atualizam-se nome/categoria/ícone dos de série, e **nunca** se tocam favoritos, escondidos ou produtos próprios
(um produto próprio com o mesmo nome de um de série novo ganha). Produtos próprios: criar, editar (só quem os criou ou o administrador) e apagar (sensível); os de série só se escondem ou marcam como favoritos. Favoritos e
escondidos são **por conta**; o catálogo é comum. **(5) Ícones:** 73 SVG lineares em `web/src/assets/shop-icons.json` (a fonte que o Android converterá em VectorDrawable); um teste garante que o servidor e a Web têm os mesmos.
**(6) Ações** (`compras.*`, 15): tudo passa pela camada de ações, incluindo o que a IA fará («adiciona leite à lista» = `compras.adicionar` por nome, que usa o produto existente ou cria um próprio);
`limpar_comprados`, `produto_apagar` e `lista_apagar` são sensíveis; o «Desfazer» de remover e limpar usa `compras.restaurar`. **(7) Partilha entre contas:** a Web volta a pedir a lista de 30 em 30 segundos
e ao voltar ao separador (o que a Camila acrescenta vê-se no supermercado); notificações «X acrescentou itens» ficam para uma decisão futura (a infraestrutura de eventos do ADR-045 já as permite).

## ADR-048 — Compras: esconder categorias e sugestões (29/09/2026)
**Esconder uma categoria inteira** (por conta, `shop_user_categories`): a categoria sai do catálogo e dos filtros, mas (1) o que já está numa lista continua a ver-se lá, (2) a pesquisa ainda encontra os seus produtos
(senão criar «fraldas» daria «já existe») e (3) em «Gerir» aparece a lista das categorias escondidas para as voltar a mostrar. O servidor não corta o catálogo: devolve `oculta` em cada categoria e a interface filtra.
**Sugestões** (só leitura, nunca adicionam nada sozinhas; alinhado com «lembretes ajudam, não impõem»): vêm do **histórico de compras** (`shop_history`), um registo por produto, âmbito e dia em que foi marcado como comprado
— desmarcar no mesmo dia retira-o (um toque enganado não conta) e sobrevive a «Limpar comprados», a remover itens e a apagar listas. O âmbito é `partilhada` (a casa toda vê) ou `pessoal:<conta>`. Duas sugestões:
**«Talvez esteja a acabar»** — produtos com pelo menos 3 dias de compra, ritmo (mediana dos intervalos) de 5 dias ou mais, e que já passaram ~80% desse ritmo desde a última compra (até 3× o ritmo: se deixou de comprar, deixa de sugerir);
**«Costumas comprar»** — 2 ou mais dias de compra nos últimos 90 dias. Um produto nunca está nas duas. Ficam de fora os produtos escondidos (ou de categoria escondida), os marcados «Não sugerir» (por conta, com desfazer) e os que já estão
por comprar na lista escolhida. Sem inteligência remota: é aritmética sobre o histórico, calculada no servidor (`services/compras.sugestoes`) para Web e Android mostrarem o mesmo.


## ADR-049 — Google: Calendário e Email (29/09/2026)
Os módulos **Calendário** e **Email** passam a existir, sobre contas Google que o utilizador liga em Definições (o login do Pulse continua a ser o do ADR-037, sem Google).
**(1) Ligação.** OAuth 2.0 de servidor com PKCE: `POST /google/connect` devolve o endereço de consentimento, o Google regressa a `GET /google/callback` (sem sessão: o `state`, de um só uso e 10 min, diz quem pediu; tabela `google_oauth_states`) e a Web volta a Definições com `?google=ok|erro`.
Um utilizador pode ligar várias contas e escolher, por conta, **Gmail**, **Calendar** ou ambos. **(2) Segredos.** O refresh token vive só em `google_accounts` (`006_google.sql`), cifrado com Fernet (`PULSE_GOOGLE_KEY`); nunca sai para a Web nem para o Android.
Sem `PULSE_GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI/KEY` (ou sem `cryptography`, em `requirements-google.txt`) a integração fica desligada: `google_desligado` (503) e os cartões dizem «não ligado». **(3) Scopes mínimos.** Gmail só `gmail.modify` (ler, lida, arquivar, estrela; **nunca enviar nem apagar**);
Calendar `calendar.events` + `calendar.readonly`. **(4) Escritas só por ações** (`calendario.criar|editar|apagar`, `email.lida|arquivar|estrela`; apagar evento é sensível). Ler uma mensagem **não** a marca como lida, e o corpo vem em texto simples, sem HTML nem anexos.
**(5) Autorização terminada.** Se o Google recusar o refresh token, a conta passa a `reautorizar` (409 na ação) e a Web mostra um aviso persistente enquanto durar, com o botão para voltar a ligar. Um erro noutra conta não estraga as restantes: a resposta traz o estado de cada conta.
**(6) Hoje.** O Hoje ganha os cartões de Calendário e Email (só os dados do dia; sem conta ligada convidam a ligar, `nao_ligado`). `GET /calendar` pede no máximo 62 dias, como o Calendário de Tarefas. Sem notificações de e-mail: alinhado com «lembretes ajudam, não impõem».

## ADR-050 — APK Android v1: shell, Hoje e Mais (29/09/2026)
Primeira versão da app nativa (`android/`, Kotlin + Compose + Material 3, `pt.pereirabmd.pulse`, minSdk 29, versão `0.1.0`, chave do ADR-034).
**(1) Âmbito v1:** início de sessão (e-mail + palavra-passe, `cliente: "android"`, token `Bearer` guardado cifrado no Keystore com `EncryptedSharedPreferences`), mudança obrigatória da palavra-passe, **PIN de 6 dígitos** (só o hash PBKDF2 fica no telemóvel; oferta após o 1.º início de sessão com «Agora não», que não se repete), **biometria** forte por cima do PIN, tema Sistema/Claro/Escuro, **Hoje** (mesmo `GET /dashboard/today`, mesmos cartões e textos da Web) e **Mais**. Fora da v1: fila offline/Room/WorkManager (fase 5), notificações FCM (nunca testadas com o Firebase real).
**(2) Hoje é só de leitura no Android**; concluir/adiar/registar continuam na Web até haver ecrãs nativos. **Mais** lista os módulos ativos (`GET /modules`; o que o administrador desativou não aparece) e cada um **abre a Web do Pulse** no navegador, marcado «Na Web»; o mesmo para ligar contas Google (o OAuth do ADR-049 fica na Web).
**(3) Bloqueio:** a app pede PIN/biometria ao abrir e depois de 1 minuto em segundo plano; à 5.ª tentativa errada a sessão termina localmente (token e PIN apagados). PIN e biometria são só do Android (CLAUDE.md).
**(4) Ícones e marca:** os ícones lineares da Web foram portados com os mesmos caminhos SVG (`Icones.kt`); os WebP animados de `assets/branding` (splash no arranque, loading, erro; `pulse_success` e `onda_semfim` copiados para uso nas ações e fundos das próximas versões) são carregados com Coil.
**(5) Distribuição e atualização interna (ADR-026):** `scripts/deploy/publicar_apk.sh` corre os testes, compila o `assembleRelease` assinado, confere a assinatura e publica em `/opt/pulse/apk/` (fora das releases do servidor): `pulse-<versão>.apk`, `pulse.apk` (endereço fixo, é o link do `index.html` da raiz e de Definições na Web) e `version.json` (`versionCode`, `versionName`, `url`, `sha256`, `notas`). O nginx serve-o em `/pulse/apk/` (`pulse-web.conf`). A app lê o `version.json` ao abrir; se o `versionCode` for maior mostra um **aviso persistente** (no Hoje e em Definições), descarrega só do próprio servidor do Pulse, confere o SHA-256 e entrega ao instalador do Android (que exige a mesma assinatura). O `versionCode` só pode subir.
**(6) Regra nova de trabalho:** cada funcionalidade nova passa a ser entregue **no APK e na Web** e é discutida antes de implementar (`PARITY_ANDROID.md` regista o estado de cada lado).

## ADR-051 — APK Android completo: todos os módulos nativos (29/09/2026)
Corrige o ADR-050 (2): **nada abre a Web do Pulse no navegador**; a app Android (versão `0.2.0`) tem todos os módulos como ecrãs nativos, com a paridade da Web: Hoje (com ações: concluir/adiar tarefas, marcar RTO por toque, registar peso, pagar contas, marcar compras), Tarefas (Hoje, Calendário, Tarefas, Horário, Piscina, Config e administração), Peso, RTO (com modo administrador), Finanças, Bilhetes CP (editor da semana), Compras (listas, catálogo, 73 ícones, sugestões), Calendário e Email (Google), Contas Google, Sessões e Administração de módulos.
**(1) Mesma API e as mesmas regras:** os ecrãs só apresentam o que o servidor calcula (`GET /tasks`, `/weight`, `/rto`, `/finance`, `/tickets`, `/shopping`, `/calendar`, `/mail`) e escrevem pelas ações (`POST /actions/<nome>`), com «Desfazer» nas mesmas ações inversas da Web. As pequenas regras de apresentação (formatos pt-PT, calendários, validação do editor da semana, marcas do RTO) foram portadas de `web/src/lib` para `android/.../util` e têm testes.
**(2) Ligar uma conta Google (o único passo que sai da app):** por regra da Google o consentimento não pode correr numa WebView, por isso abre num Custom Tab e **regressa à app** por `pulse://google?resultado=ok|erro&motivo=…`. `POST /google/connect` aceita `cliente: "web"|"android"` (guardado no pedido, migração `007_google_cliente.sql`); no regresso a Web continua a ser redirecionada para as Definições e o Android recebe uma página-ponte sem scripts com esse link. Depois de o utilizador dar a permissão, mesmo que a app se tenha bloqueado entretanto, o ecrã das contas abre sozinho.
**(3) Alguns pormenores nativos:** «Calendário» numa tarefa abre o calendário do telemóvel com o evento preenchido (`ACTION_INSERT`); o histórico de Tarefas exporta-se em CSV pelo menu de partilha; os gráficos (Peso) e o mapa de calor (RTO Ano) são desenhados em Canvas; o corpo de um email é sempre texto simples, nunca HTML.
**(4) Fora desta versão** (mantém-se em `PARITY_ANDROID.md`): notificações FCM, cache/fila offline (Room, WorkManager) e puxar para atualizar.

## ADR-052 — Afinações de uso: RTO instantâneo, logo no «Hoje», Peso com uma só caixa, categorias recolhíveis (30/09/2026)
**(1) RTO instantâneo:** tocar num dia mostra logo a marca (Web e Android, calendário e cartão do Hoje); a ação segue em segundo plano e os dados recarregam quando o último pedido termina. Se falhar, a marca volta atrás e diz porquê. **(2)** O ícone «Hoje» (sol) foi substituído pelo **logo do Pulse** na navegação; no Android a barra «Hoje / Mais» fica visível em todos os ecrãs. **(3) Peso no Hoje:** uma só caixa; editável enquanto falta o registo de hoje (vem com o último peso), e depois passa a mostrar o peso de hoje sem se poder editar. **(4) Compras:** as categorias da lista e do catálogo expandem e encolhem (há «Encolher/Expandir todas»); o que ficou encolhido lembra-se no aparelho e a pesquisa mostra sempre os resultados. **(5) Espaçamentos (Android):** as semanas dos calendários tinham 10 dp entre linhas (o espaçamento do bloco) e passaram a 4 dp; os chips deixaram de ocupar 48 dp de altura; os blocos ficaram mais compactos.

## ADR-053 — Piscina e saída do Bruno no cartão das Tarefas (30/09/2026)
**(1)** No separador Piscina, a manutenção **sugerida para hoje ou já passada da data** (`destacar` ou `atrasada`, calculado no servidor) sobe para o topo e fica destacada (fundo, traço lateral e nome a negrito), na Web e no Android. **(2)** O cartão «Tarefas de hoje» do Hoje ganha, dentro dele, uma secção **Piscina** com essas mesmas tarefas e o botão para as marcar feitas (`tarefas.piscina_registar`, com «Desfazer» por `tarefas.piscina_repor`); sem nenhuma, a secção não aparece. Vem de `GET /dashboard/today` → `tarefas.piscina[]` (`id, nome, nota, estado, ultima, proxima, diasDesde`). **(3)** O cartão mostra também «**Bruno sai às HH:MM · aviso às HH:MM**», da hora de saída de hoje no Horário escolar (`tarefas.horario`: `aluno, entra, sai, aviso`). O aluno é o do horário cujo nome contém «bruno» (`ALUNO_DO_CARTAO` em `services/dashboard.py`); sem aulas hoje, sem esse aluno ou com o Horário indisponível, a linha não aparece e o resto do cartão não é afetado.

## ADR-054 — Ordem dos cartões do Hoje, teclado e RTO (30/09/2026)
**(1) Ordem dos cartões do Hoje:** escolhe-se em **Definições › Ordem do Hoje** (não no próprio Hoje, que mostra só os cartões pela ordem escolhida): lista com **pega de arrastar** por cartão (Web: rato/dedo, ou setas ↑ ↓ com a pega em foco; Android: arrastar, ou ações de acessibilidade «Mover para cima/baixo»). A ordem é **por utilizador, guardada no servidor** (`pulse_hoje_ordem`, migração 008; `GET` e `PUT /dashboard/order`), logo igual no APK e na Web; `GET /dashboard/today` devolve `ordem`, sempre completa (cartões em falta entram no fim, pela ordem de origem). **(2) Teclado:** no Android o ecrã encolhe com o teclado (`imePadding`) e a barra «Hoje / Mais» esconde-se enquanto ele está aberto; na Web o viewport redimensiona o conteúdo (`interactive-widget`), a barra de baixo esconde-se e o campo em foco vai para o centro. **(3) RTO:** a linha «Férias» passou para debaixo da grelha do calendário, junto à legenda, para acabar com o vazio entre o mês e o calendário.

## ADR-055 — Ações do Hoje rápidas: atualização parcial, alteração imediata e cache da Google (30/09/2026)
**Diagnóstico:** as ações em si eram rápidas (o `dados-api` responde em 15–45 ms); a lentidão vinha de, **depois de cada ação, o Hoje voltar a pedir tudo**, incluindo Calendário e Email da Google (chamadas de rede a cada pedido). **(1)** `GET /dashboard/today?modulos=tarefas,peso` devolve só esses módulos; depois de uma ação a Web e o Android pedem apenas o módulo dela (`tarefas.*` → `tarefas`, etc.) e fundem-no no ecrã; se esse pedido falhar, pedem tudo. **(2)** **Alteração imediata** (como no RTO, ADR-052) ao concluir uma tarefa (sai logo da lista) e ao registar o peso (passa a «registo de hoje feito»); se o servidor recusar, o Hoje volta a pedir tudo e o estado real regressa. **(3)** Os cartões Calendário e Email têm **cache de 60 s por utilizador** no servidor (só quando nenhuma conta tem problemas). **(4)** O servidor regista no log (`pulse.lento`) os pedidos com mais de 0,5 s, para diagnosticar a próxima lentidão sem adivinhar. Os outros ecrãs de módulo já recarregavam só o seu módulo.

## ADR-056 — Escritas lentas no Pi: ligação SQLite sempre aberta (30/09/2026)
**Diagnóstico (continuação do ADR-055):** com o log `pulse.lento` viu-se que as **ações** demoravam 1,5–3,8 s no servidor. A causa era o `dados-api` (e o `pulse.db`): cada pedido abre e fecha a sua ligação SQLite e, **em WAL, a última ligação a fechar faz um checkpoint e apaga o `-wal`, com `fsync` no cartão SD** — pago a cada escrita. Medido no Pi: mediana 70 ms, 10 % acima de 1,4 s, máximo 2,8 s; com uma ligação sempre aberta: mediana 7 ms, máximo 32 ms. (O cartão SD tem escritas lentas — cerca de 220 ms em média desde o arranque — e o Pi já registou subtensão: vale a pena trocar o cartão/fonte, mas o software já não depende disso a cada escrita.) **Correção:** `db.manter_aberta()` no `dados-api` (todas as bases, no arranque) e no Pulse (no `lifespan`); o `pulse.db` passa também a `synchronous=NORMAL` (como o `dados.db`: seguro em WAL, só a última escrita pode perder-se num corte de luz). Depois: 25 escritas seguidas em 13 ms cada. **Regressão corrigida:** a primeira versão do log de pedidos lentos era um `BaseHTTPMiddleware`, que corre o endpoint noutra thread e fazia rebentar o fecho das ligações SQLite (500 em `/auth/sessions`); agora é ASGI puro (`PedidosLentos`), com teste. **Por resolver (fora do âmbito):** `POST /recalcularAgora` no `tarefas-api` responde 401 ao Pulse, por isso o recálculo imediato dos avisos ntfy não corre (o timer de 5 min reconcilia na mesma).

## ADR-057 — Notificações FCM no Android: registo, canais e teste (30/09/2026)
Primeiro passo da passagem do ntfy para o FCM (ADR-032/045), sem ligar ainda nenhum módulo. **(1) Servidor:** FCM ligado no Pi (service account do projeto `bmdpereira-5a8f4` em `/etc/pulse-app/fcm-service-account.json`, dono do serviço, modo 600; a pasta `/etc/pulse-app` passou a 711 só para o serviço a atravessar; `cryptography` instalada no venv). Novo `POST /notifications/test` (409 `sem_dispositivo` / `fcm_desligado`; senão envia «Notificação de teste» aos telemóveis do utilizador). **(2) Android 0.2.5:** `firebase-messaging` (sem Analytics) e plugin `google-services` (o `app/google-services.json` fica fora do Git, como o do `pulse/`); pede a permissão `POST_NOTIFICATIONS` **uma só vez** (depois só em Definições › Notificações); cria um canal de importância alta por módulo (`pulse_<módulo>`, mais `pulse_geral`); regista o telemóvel em `POST /devices` ao arrancar e quando o Google renova o token; ao terminar a sessão remove-o (`DELETE /devices/<id>`); com a app aberta mostra o aviso ele próprio, em segundo plano o Android mostra-o no canal indicado. **(3) Definições › Notificações:** estado da permissão e «Enviar notificação de teste». **(4) Ícone do lançador** com fundo transparente. **Falta:** ligar cada módulo (Bilhetes CP primeiro, depois Tarefas com agendador e Finanças) e deixar o ntfy em paralelo até confirmar.

## ADR-058 — Avisos dos Bilhetes CP também por FCM (30/09/2026)
Decidido com o utilizador: durante a transição **cada aviso dos Bilhetes CP sai pelo ntfy e pelo Pulse (FCM)**, ambos com prioridade alta (popup), até ele confirmar que o FCM chega para deixar o ntfy. No Pi: `bilhetes_cp/scripts/common.py` atualizado (antes só tinha o ntfy; o resto do código era igual) e `PULSE_EVENTS_URL` (`http://127.0.0.1:8897/api/v1/internal/events`), `PULSE_SERVICE_KEY` (a mesma do Pulse) e `PULSE_EVENTS_USER` no `.env` do `bilhetes_cp` (600); `cp-scheduler` reiniciado num momento sem compras agendadas. Um aviso de teste chegou ao estado `enviado`. A cópia é de melhor esforço (nunca atrasa o ntfy nem as compras) e idempotente por `chave`. Ficheiros de segurança no Pi: `common.py.bak-antes-pulse-event`, `.env.bak-antes-pulse-event`. **Falta:** Finanças e Tarefas (agendador próprio).

## ADR-059 — Avisos das Finanças também por FCM (30/09/2026)
Como os Bilhetes CP (ADR-058): o `dados/financas_notificar.py` (timer de 30 min no Pi) envia cada aviso («Vence hoje», «Rendimento previsto hoje», lembretes) pelo ntfy, que decide se conta como enviado, e **copia-o para o Pulse** (`pulse_eventos`, stdlib, melhor esforço) para cada utilizador de `PULSE_FINANCAS_USERS` (por omissão `ACL_FINANCAS`). A `chave` (`fin-l<id>-<dia>` / `fin-r<id>-<dia>` + utilizador) torna repetir inofensivo. Pi: `financas_notificar.py` e `PULSE_EVENTS_URL` no `.env` do `dados` (cópias `*.bak-antes-pulse*`).

## ADR-060 — Avisos das Tarefas também por FCM, agendados no Pulse (30/09/2026)
O motor `tarefas/pi/recalcular.py` continua a decidir quando e a quem avisar (ntfy, sem mudanças). Para cada aviso o `pulse_eventos.py` mantém, **em paralelo e à parte** (`pulse_agendados.json`), um evento **agendado** no Pulse para a mesma hora (`entregarEm`); o agendador do Pulse entrega-o por FCM. Quando o motor cancela ou reagenda (tarefa feita, adiada, hora mudada, «Daqui a 1 h») o evento é cancelado por `DELETE /internal/events/<chave>` (novo: só apaga o que ainda está `agendado`). Destinatários: a pessoa da instância (`Pessoa<N>_Email`), ou todas se não tem responsável; piscina e horário seguem os destinatários do painel (tópico ntfy → pessoa). Mesmo horizonte do ntfy (3 dias); chave estável por (chave, hora, e-mail), por isso repetir não duplica; se o Pulse falhar, repete-se no ciclo seguinte e o ntfy nunca é afetado. **Corrigido de passagem:** o `servidor.py` do Pi (`tarefas-api`) não tinha a autenticação por chave de serviço do Pulse, por isso o recálculo imediato respondia 401; foi atualizado (`POST /recalcularAgora` 200). **Fica para depois:** botões «Marcar feita»/«Daqui a 1 h» dentro da notificação do Pulse (hoje só o toque, que abre a app) e o toque a abrir o cartão certo.

## ADR-061 — Botões na notificação e toque que abre o sítio certo (30/09/2026)
**(1) Botões «Marcar feita» e «Daqui a 1 h»** nas notificações das tarefas (Android 0.2.7): agem sem abrir a app, pelas mesmas ações do Pulse (`tarefas.concluir` e a nova `tarefas.lembrar_mais_tarde`, 5–720 min, por omissão 60) com a sessão guardada no telemóvel; se falharem, a notificação troca-se por outra a dizer porquê. **«Daqui a 1 h» não cria um aviso novo:** pede ao `tarefas-api` (`POST /snoozeServico`, chave de serviço ou token Google, sem a assinatura HMAC dos botões do ntfy) que registe o snooze, e o motor de avisos reagenda o ntfy **e** o evento do Pulse (um só caminho); concluir cancela ambos no ciclo seguinte. **(2) Toque:** cada evento leva `link` (`pulse://<módulo>[/<aba>]`, ex.: `pulse://tarefas/piscina`) e, nas tarefas, `instancia`; o toque abre o módulo (e a aba Hoje/Horário/Piscina). **(3) Só dados:** para a app poder desenhar botões, o servidor passa a mandar as mensagens FCM **sem** bloco `notification` (a app recebe-as sempre, aberta ou não). Isto só se liga com `PULSE_FCM_SO_DADOS=1` no `pulse.env`, **depois** de as apps instaladas terem a 0.2.7 (uma 0.2.6 ignoraria mensagens só de dados). Até lá os avisos saem como antes (aparecem, sem botões). Pi: `servidor.py` e `pulse_eventos.py` das Tarefas atualizados (cópias `*.bak-antes-*`); os 6 avisos agendados foram cancelados e recriados já com `link` e `instancia`.

## ADR-062 — ntfy em pausa para os módulos; verificação de versão ao voltar à app (30/09/2026)
**(1) ntfy em pausa, por omissão só onde há Pulse:** Finanças (`NTFY_PAUSADO=1` no `.env` do `dados`; só o utilizador tem acesso às Finanças) passa a avisar **só pelo Pulse** e o `notificado_em` marca-se quando o Pulse aceita; Tarefas: `NTFY_PAUSADO_TOPICOS=tarefas_bruno` no `.env` das Tarefas (o motor cancela o que o ntfy tinha agendado para esse tópico e deixa de agendar; o Pulse agenda sozinho). **A Camila continua no ntfy** até ter conta no Pulse (hoje só há uma conta). **Continuam por ntfy:** os avisos dos Bilhetes CP (operacionais e de compra, críticos no tempo: ficam em paralelo com o Pulse até haver uma separação «sistema» vs «resultado») e os alertas de sistema (backup, heartbeat). Reverter: apagar a linha do `.env` (e, nas Tarefas, o recálculo de 5 min volta a agendar o ntfy). **(2) Android 0.2.8:** ao voltar à frente a app volta a perguntar por uma versão nova, no máximo de 10 em 10 minutos, e uma falha de rede já não esconde uma atualização conhecida.

## ADR-063 — Multiutilizador: isolamento, acesso por pessoa e «O meu Hoje» (30/09/2026)
Primeira fase para cada pessoa (ex.: a Camila) ter o seu Pulse. **(1) Isolamento no `dados-api`:** Peso (`peso_registos`, `peso_config`) e RTO (`rto_dias`, `rto_notas`) ganharam `dono` (o e-mail da conta; migração `dados` 009, com `peso_config` e `rto_dias` reconstruídas com o dono na chave). Cada pedido só lê e escreve o que é do dono; um id alheio responde 404 (na nota RTO o «upsert» por id também, para não recriar nem sobrepor a de outra pessoa). O que já existia (351 linhas) passou para `DONO_DADOS_INICIAL` no arranque (`db.adotar_orfaos`; sem a variável só se atribui se uma única pessoa tiver acesso a Peso/RTO). Finanças continuam **da casa** (um só livro, sem dono); as Tarefas já separam por pessoa. **(2) Acesso por pessoa:** `pulse_user_modulos` (migração Pulse 009): cada conta só tem os módulos que o administrador lhe der (as existentes ficam com todos; contas da linha de comandos também; contas criadas pela administração começam só com Compras). `modulos.exigir` recusa com 403 `sem_acesso`; `GET /modules` devolve por conta `ativo` (ligado para todos **e** com acesso), `ativoGlobal` e `permitido`. Administração: `GET/POST /admin/users`, `PUT /admin/users/<id>/modules`, `PUT …/active` (termina as sessões; não se desativa a própria conta) e `POST …/password` (provisória), tudo auditado. No `dados-api`, `PULSE_ACL_DELEGADA=1` faz os pedidos do backend do Pulse (chave de serviço, loopback) não passarem pelas listas `ACL_<APP>` — quem decide é o Pulse; os pedidos com token Google (apps dedicadas) continuam sujeitos às listas. **(3) «O meu Hoje» por pessoa:** a ordem (ADR-054) e agora também os cartões **escondidos** (`pulse_hoje_ordem.ocultos`; `GET/PUT /dashboard/order` com `ordem`, `ocultos` e `disponiveis`). Um cartão escondido, ou de um módulo sem acesso, nem é pedido ao módulo (mais rápido) e sai como `desativado`. Web e Android: Definições › «O meu Hoje» (arrastar + Visível/Escondido) e, para administradores, Definições › «Pessoas». **Fica para depois:** avisos das Finanças por pessoa (hoje vão para `ACL_FINANCAS`), Bilhetes CP por pessoa (fase 2: os scripts de compra ainda usam as credenciais de um utilizador) e testes de ponta a ponta com uma segunda conta real. **No Pi:** cópias `dados.db.bak-antes-dono`, `pulse.db.bak-antes-pessoas` e `~/dados/_antes_dono/`.

## ADR-064 — Ícone do lançador sem ícone adaptativo (30/09/2026)
Na Xiaomi (MIUI/HyperOS) o ícone adaptativo com fundo transparente (ADR-057) aparecia sobre **preto**: o launcher compõe as camadas transparentes sobre preto. A 0.3.1 deixa de ter ícone adaptativo: `mipmap-*/ic_launcher.png` é só o logo do Pulse (`assets/branding/pulse-icon.png`) com fundo transparente, com margem de 6 %. Noutros launchers (ex.: Pixel) um ícone não adaptativo pode aparecer sobre um fundo claro do próprio launcher; o logo é legível nos dois. Se alguma vez se quiser o ícone adaptativo e o tema de ícones do Android 13, é preciso um fundo opaco e uma camada monocromática.

## ADR-065 — Google: sem login com Google; ligação de contas por configurar no Pi (30/09/2026)
Decidido: o login do Pulse **fica** e-mail + palavra-passe; o Google serve só para ligar Calendário e Gmail por pessoa (ADR-049/051). Descobriu-se que essa integração **não estava configurada no Pi** (falta `PULSE_GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI/KEY` no `pulse.env`), apesar de o código estar publicado: o passo a passo (consola do Google Cloud, variáveis e ligação na app) fica em `docs/GOOGLE_SETUP.md`. Pendente de o utilizador criar o cliente OAuth e entregar o JSON.

## ADR-066 — Pausa automática do ntfy quando a pessoa tem telemóvel no Pulse (30/09/2026)
Para ativar as notificações da Camila (e de quem vier) sem a deixar sem avisos: `NTFY_PAUSA_AUTOMATICA=1` no `.env` das Tarefas. Em cada ciclo (5 min) o motor pergunta ao Pulse (`GET /internal/devices/count`, chave de serviço) quantos telemóveis **ativos** tem a pessoa dona do tópico ntfy; com pelo menos um, o ntfy dela pausa-se (cancela o que tinha agendado e não agenda mais) e o Pulse avisa sozinho; se perder o telemóvel (sair da app, token inválido) o ntfy volta no ciclo seguinte. Só para tópicos de **uma** pessoa; se o Pulse não responder, nada se pausa. Junta-se à lista fixa `NTFY_PAUSADO_TOPICOS` (Bruno). Os avisos da Camila já estão agendados no Pulse desde que a conta existe (hoje 5); faltam-lhe instalar a app e entrar, e o registo do telemóvel acontece no arranque. Finanças e Bilhetes CP não têm a Camila (só o Bruno tem acesso). Limitação: o teste automático cobre a pergunta ao Pulse, mas a decisão de pausar (função interna do motor) só se viu a funcionar em produção com o Bruno.

## ADR-067 — Barra de baixo: «Hoje» ao centro, «Mais» discreto (30/09/2026)
Android 0.3.2 e Web (ecrãs estreitos): o «Hoje» (logo do Pulse e nome) fica **centrado** na barra inferior e o «Mais» passa a um botão pequeno e apagado (ícone de 16 dp, 65 % de opacidade) à direita, com cor de destaque só quando é o ecrã atual. O Android deixa de usar a `NavigationBar` do Material (duas metades iguais) por uma barra própria com o mesmo comportamento de esconder com o teclado aberto e papéis de acessibilidade de separador. Ecrã largo (Web): a barra lateral mantém-se.

## ADR-068 — Verificação do horário na CP no editor dos Bilhetes (30/09/2026)
Fecha o pendente «Verificação do horário na CP» da PWA. **(1) No servidor do Pulse** (decidido com o utilizador): `GET /tickets/timetable?comboio&data&origem&destino[&hora]` consulta `travel-api/trains/<n>/timetable/<data>` e, para viagens com transbordo, `travel-api/journeys`, com as chaves públicas da app da CP em `PULSE_CP_CONNECT_ID`, `PULSE_CP_CONNECT_SECRET` e `PULSE_CP_API_KEY_TRAVEL` (copiadas do `.env` dos Bilhetes CP; **nunca vão para o telemóvel**). Estações: Aveiro e Lisboa Oriente; outras com `PULSE_CP_ESTACOES` (JSON). Cache de 6 h; falhas de rede nunca ficam em cache. **(2) Consultiva, bem visível:** `estado` ∈ confirmado | preenchido | aviso | sem_informacao | desligado; um **aviso** (comboio inexistente nessa data, não para na origem, não segue para o destino, hora diferente) aparece como alerta «Verifica na CP» com o botão «Usar HH:MM» (a hora da 1.ª estação, a que abre a venda) e **nunca impede de guardar**; hora em falta preenche-se com a da CP. Web e Android 0.3.3. **(3) Validado em produção, só leitura:** o comboio 731 de 01/10 dá «Lisboa Santa Apolónia 17:30 → Lisboa Oriente 17:39 → Aveiro 20:02», igual ao que o scheduler usa para o disparo. Lógica espelhada de `bilhetes_cp/scripts/timetable.py` e da PWA.

## ADR-069 — Bilhetes CP: o Bruno marca para outras pessoas, a compra faz-se com as credenciais de quem viaja (30/09/2026)
Decidido com o utilizador: **quem marca é o Bruno (no Pulse); a compra usa a conta CP, o NIF, o cartão de cidadão e o Passe Verde de quem viaja; os avisos vão para o Bruno e para a própria pessoa** (se tiver conta Pulse com telemóvel). **(1) Compra por pessoa (`bilhetes_cp/scripts`):** `credenciais.py` (novo) carrega as credenciais de `bilhetes_utilizadores`; a password da CP decifra-se com `BILHETES_FERNET_KEY` (que passa a estar também no `.env` dos Bilhetes) e **nunca se regista** (nem o `repr`); o **utilizador 1 continua a usar o `.env`, como sempre** (o caminho que compra não muda). `Leg.utilizador_id` vem das colunas extra da base; `CPClient(cred=…)` e `login(cred)` usam só os dados dela (a morada fiscal `CP_FISCAL_ADDRESS` é do Bruno e **nunca** vai na compra de outra pessoa); sessão da CP por pessoa (`tokens/<id>.json`, o do Bruno continua `token.json`); «já comprado» conta por pessoa (o bilhete de uma não impede a compra da outra no mesmo comboio); compras e registos gravam o dono. Com dados em falta (ou sem a chave) **não se compra**: aviso «Não consigo comprar — <pessoa>» com os nomes dos campos em falta, nunca valores, e nunca com os dados de outra. Pre-flight com a verificação das credenciais da pessoa. **(2) Avisos:** `notify(..., utilizador_id=…)`: o ntfy continua a ser só do Bruno (não há ntfy por pessoa); o Pulse avisa o Bruno **e** o e-mail Pulse da pessoa (uma chave por destinatário); a vigilância de atrasos junta duas pessoas no mesmo comboio numa só e avisa as duas. **(3) `dados-api`:** `GET /bilhetes/dados?utilizador=`, `PUT /bilhetes/semana` e `/passe` (`utilizadorId`) filtram e gravam por dono; só o administrador (Bruno) usa outro utilizador (e só de pessoas ativas); **uma conta não registada nos Bilhetes não vê nada** (403 `sem_utilizador`, nunca assume ser o Bruno); pedidos só do dono (ou do administrador); `proximo` (o cartão do Hoje) é sempre da própria conta; passe por pessoa. **(4) Pulse (Web e Android 0.3.4):** nos Bilhetes, o administrador vê um seletor «Bruno (eu) · Camila · …» e, ao escolher outra pessoa, vê e marca a semana e o passe dela («A marcar para Camila…»); o «Desfazer» repõe a dela. **Publicado a 30/09/2026 às 17:48–18:00** (depois de a compra do 731 acabar esgotada): scripts do Pi (cópia `scripts.bak-antes-multiutilizador`, `.env.bak-antes-multiutilizador`, `BILHETES_FERNET_KEY` copiada do `dados/.env`), `dados-api`, Pulse e APK 0.3.4. Verificado em produção, só em leitura: o Bruno vê as suas 6 viagens e `pessoas=[Bruno]`; `?utilizador=2` (inexistente) dá 404; uma conta não registada dá `sem_utilizador`. Ensaio isolado no Pi (clone da base, chave de cifra real, sem ntfy nem Pulse): 3 pernas com os donos certos (1, 2, 3), a password da Camila decifra-se, o pre-flight dela passa e o do Davi (sem dados) falha a dizer que campos faltam. **Por fazer:** preencher na página de administração (rede de casa) os dados CP da Camila e correr `ensaio_compra.py --utilizador 2` (login, retenção e desconto com os dados dela, sem comprar) antes da primeira compra a sério; `config_reminder`, `pass_expiry_check` e o ensaio de simultaneidade continuam só para o Bruno.

## ADR-070 — Bilhetes CP: avisos de «lugar reservado» e de «sem lugar a T-1 min» (30/09/2026)
Pedido depois de o 731 de 01/10 acabar esgotado: a app só dizia que não havia lugares às 17:30, e só nos registos. **(1) «Lugar reservado — <viagem>»** quando a retenção antes de T consegue o lugar (diz a carruagem e o lugar, se a CP os deu, e quando fecha a compra: à abertura do desconto). **(2) «Sem lugar retido — <viagem>» a T-1 min** se ainda não há lugar retido: uma só vez, com o motivo da CP («não há lugares») e o conselho de ver alternativas na App CP; a app continua a tentar a T (e, se o lugar aparecer depois, vem o aviso de «Lugar reservado»). Ambos saem pelo ntfy e pelo Pulse e, nas viagens de outras pessoas, também para a própria pessoa (ADR-069). **(3) Scheduler:** deixou de avisar «Compra atrasada — a iniciar já» quando o processo quente está vivo (o de 30/09 disparou à hora certa e insistia por «esgotado»; o aviso era falso). **(4) `ensaio_compra.py --utilizador N`** ensaia a compra com as credenciais de outra pessoa (o cliente do ensaio também leva os dados dela), sem comprar.

## ADR-071 — Tipo de documento do passageiro: CC ou AR (30/09/2026)
O perfil da Camila na CP (lido do `Camila.har`, só o campo do documento) mostra o documento como **`AR` «Autorização de Residência»**; o do Bruno é Cartão de Cidadão (`CC`). Até aqui a compra enviava sempre `CC` no passo do passageiro. **(1) Dados:** migração `dados/migrations_bilhetes/004_tipo_documento.sql` (`bilhetes_utilizadores.passageiro_tipo_doc`, `CC` ou `AR`, por omissão `CC`: o Bruno e quem já existia ficam CC). A página de administração dos Bilhetes ganhou «Tipo de documento» e o número passa a ser «Número do documento» (6 a 15 letras/dígitos; o Cartão de Cidadão continua a exigir 8 a 12); a etiqueta do cartão da pessoa mostra o tipo. `importar-env` aceita `CP_PASSENGER_DOC_TYPE`. **(2) Compra:** `Credenciais.passageiro_tipo_doc` e `CPClient.tipo_doc` (o Bruno: `CP_PASSENGER_DOC_TYPE` do `.env`, por omissão `CC`); o passo do passageiro envia `{"code": <tipo>, "designation": <nome do tipo>}` (`AR` → «Autorização de Residência»); um tipo desconhecido levanta erro em vez de enviar um código inventado; uma base antiga sem a coluna conta como CC. **(3) Produção (30/09/2026):** backup `bilhetes.db.bak-antes-tipo-doc` e `~/dados/_antes_tipo_doc/`; migração aplicada (`user_version` 4); a Camila (já criada na administração) passou a `AR`. **Confirmado a 30/09/2026 às 18:50 com o ensaio (`ensaio_compra.py --utilizador 2`, que cancela a venda em vez de comprar):** com as credenciais da Camila e `AR` «Autorização de Residência» a CP aceitou o login, a venda (comboio 520 de 01/10, carruagem 22, lugar 77), os passos do passageiro, cliente e fiscal e o desconto do Passe Verde dela (pedido #1, 0 recusas); a venda 125941749 foi cancelada (HTTP 200) e nada foi comprado nem gravado nas compras. Uma primeira tentativa, 2 minutos antes, falhou no login (status 200 ×14, credenciais recusadas pela CP): depois de a Camila corrigir o login e a password na administração, 1 login isolado e o ensaio completo passaram.

## ADR-072 — Google ligado no Pi e política de privacidade (30/09/2026)
Para o Google aceitar publicar a app «em produção» (as autorizações deixam de expirar aos 7 dias) foi preciso uma **página inicial** e uma **política de privacidade**: `https://bmdpereira.duckdns.org/pulse/privacidade.html` (+ `privacidade.css`, sem estilos inline por causa da CSP do nginx), em português com resumo em inglês; diz o que o Pulse lê (Gmail só ler/marcar/arquivar/estrela, nunca enviar nem apagar; Calendário ler/criar/alterar/apagar a pedido), que nada é copiado para bases de dados (só memória do servidor e uma cache de minutos), que só o token cifrado fica no servidor pessoal e que não há venda, publicidade nem treino de IA, com a declaração de utilização limitada. O domínio autorizado é `bmdpereira.duckdns.org`. **No Pi:** `PULSE_GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI/KEY` no `pulse.env` (chave Fernet gerada no Pi; o JSON do cliente só serviu para as copiar e deve apagar-se do computador); o Pulse arranca com «Google ligado». Verificação: o pedido de consentimento gerado pelo Pulse dá 302 para o início de sessão do Google. **Falta:** cada pessoa ligar a sua conta em Definições › Contas Google.

## ADR-073 — Ligar uma segunda conta Google (30/09/2026)
Ao ligar uma segunda conta, o Google mostrava só a que já estava ligada: o Pulse mandava o e-mail da conta do Pulse como `login_hint` (o Google pré-selecionava essa conta e não deixava escolher outra) e o pedido só tinha `prompt=consent`. Agora o pedido não leva `login_hint` e usa `prompt=select_account consent`: o Google mostra sempre a lista de contas («Usar outra conta»). Testes: o URL de autorização já não tem `login_hint` e tem o novo `prompt`.

## ADR-074 — Emails clicáveis e próximos eventos no Hoje (30/09/2026)
O cartão do Calendário no Hoje deixa de mostrar só os eventos de hoje e passa a mostrar os **próximos 5 eventos, de qualquer dia, com a data** («Hoje», «Amanhã», «sex, 2 out»). O servidor procura nas próximas 2 semanas e só alarga (até 62 dias) se faltarem eventos; os eventos de hoje que já acabaram não contam e um evento de vários dias aparece só uma vez. Cada mensagem passa a trazer `link` (`https://mail.google.com/mail/u/<conta>/#all/<id>`, abre a mensagem certa na conta certa): no Hoje a linha do email é um link e na folha/detalhe há «Abrir no Gmail» (Web e Android; no Android o Gmail abre o link na própria app). Testes: servidor (próximos sem os que já acabaram, com a data, link do email), Web (link no cartão, `fmtDiaCurto`) e Android (`diaCurto`). APK 0.3.5.
