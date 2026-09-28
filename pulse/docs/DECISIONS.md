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
