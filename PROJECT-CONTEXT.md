# PROJECT-CONTEXT.md

Contexto de projeto para o repositório `escritorio-casa`. Atualizado após duas sessões de trabalho de 29 de agosto de 2026: a primeira auditou e melhorou 5 das apps do repositório; a segunda (mais tarde, no mesmo dia) não alterou código deste repositório — só documenta aqui, na secção `ciclismo/`, uma integração externa nova que passou a produzir ficheiros no formato que essa app lê.

## Visão geral

Este repositório não é uma aplicação única — é uma coleção de **PWAs pessoais independentes**, uma por pasta, cada uma um único `index.html` autossuficiente (mais um punhado de ficheiros irmãos: CSS, service worker, manifest, ícones). Não há build, bundler nem framework: cada app é HTML/CSS/JS servido tal e qual. Deploy é feito via **GitHub Pages** (build "legacy", serve diretamente da branch `main`, sem GitHub Actions), em `https://pereirabmd.github.io/escritorio-casa/<pasta>/`.

Pastas com apps ativas: `peso/`, `tarefas/`, `RTO/`, `receitas/`, `ciclismo/`. Há ainda `enfermagem/`, `receitas` (duplicado histórico em `enfermagemCamila.html`), `convidados/`, `xadrez/` que não fizeram parte desta sessão.

## Convenções partilhadas entre apps

- **Autenticação Google**: `peso`, `tarefas`, `RTO`, `receitas` e `ciclismo` usam o mesmo `CLIENT_ID` OAuth (`108256538530-fgunbb52s7f3s9aurfpjtaf01v8fjbph.apps.googleusercontent.com`), via Google Identity Services (token client), sessão persistida em `localStorage`.
- **Versionamento**: cada app tem a sua própria convenção, propositadamente não unificada — `peso` e `RTO` usam versão semântica (ex.: `v5.1.0`); `tarefas`, `receitas` e `ciclismo` usam "Beta N". O número aparece sempre no rodapé.
- **Service workers**: padrão estabelecido nesta sessão em todas as apps — só intercetam pedidos GET da **mesma origem** (nunca Drive/Sheets/APIs externas, que têm de ir sempre à rede), estratégia cache-first com atualização em segundo plano, e um banner "nova versão disponível" ligado ao evento `controllerchange`.
- **`localStorage`**: sempre protegido com `try/catch`, tanto leituras como escritas (helpers `lsGet`/`lsSet`/`lsRemove` ou equivalente, consoante a app).
- **Conteúdo importado pelo utilizador** (notas de treino, receitas em `.txt`, nomes de tarefas/pessoas) é sempre tratado como não confiável antes de ir para `innerHTML` — cada app tem a sua função `esc()`/`escapeHtml()`.
- **`.gs` (Google Apps Script)**: só existem para `tarefas/` (`Code.gs`, `InstanciasGenerator.gs`, `Manutencao.gs`, `NotificationSender.gs`, `Triggers.gs`, `WebApp.gs`). **O repositório é só uma cópia de referência — alterações a ficheiros `.gs` não têm efeito nenhum até serem copiadas manualmente para o projeto em script.google.com e reimplementadas.**

## Lição já registada em memória (sessões futuras)

O utilizador por vezes cola um pedido escrito para o domínio de uma app enquanto nomeia outra pasta na primeira linha (aconteceu logo no início desta sessão: um pedido inteiramente sobre controlo de peso apontava para `tarefas/index.html`). Confirmar sempre que o conteúdo real da pasta nomeada corresponde ao que o resto do pedido descreve antes de começar trabalho grande — ver `repo-structure-multi-app.md` na memória.

---

## `peso/` — Controlo de peso

Registo diário de peso sincronizado com Google Sheets (API direta, sem Apps Script). `SPREADSHEET_ID: 1UzEXtl7w6jMsk-c7Pkt3kq97AXL6XIiwTrjOYUaYFLs`. Versão semântica, atualmente `v4.0.0 R1`.

Já implementado (auditado, não alterado nesta sessão): tendência por regressão linear (não só os dois últimos pesos), evolução mensal, melhor/pior semana, previsão de data ao objetivo, TDEE (Mifflin-St Jeor) e IMC classificados, sequência de dias, desfazer eliminação com undo otimista, PWA completa com changelog extenso.

**Esta sessão**: só auditoria de leitura — nenhum código alterado.

## `tarefas/` — Tarefas de Casa

Gestão de tarefas domésticas partilhada entre várias pessoas. CRUD direto à API do Google Sheets (`SHEET_ID: 1ZwA9RqwCbOlfWLmYZWFsE5iq2oUqr-XZru_HDy6NjjI`) + backend em Google Apps Script para geração agendada de instâncias recorrentes e notificações push (Firebase Cloud Messaging, projeto `bmdpereira-5a8f4`). Único service worker (`firebase-messaging-sw.js`) faz cache **e** push — nunca criar um segundo `service-worker.js` (concorreriam pelo mesmo scope). Versão "Beta N", atualmente **Beta 31**.

**Alterações desta sessão** (commits `a2d6cbe`, `52453e8`, `82d9a0e`):
- Correção de um bloqueio real: `#login-screen` era referenciado no JS mas não existia no HTML — login silencioso falhado deixava a app presa.
- Escaping de XSS aplicado sistematicamente a conteúdo interpolado em `innerHTML`.
- `sheetsAppend`/`sheetsUpdate` deixaram de fingir sucesso quando a rede falha; ações otimistas (marcar feita, saltar, reagendar) revertem se a gravação falhar.
- `LockService` à volta de `gerarInstancias()` em `InstanciasGenerator.gs`, para impedir duplicação de tarefas quando o trigger horário e o botão manual corressem em simultâneo. **⚠️ Pendente de redeploy manual no Apps Script.**
- Filtro Todas/Minhas/pessoa e secção "Amanhã" na tab Hoje; progresso do dia; atribuição de conclusão visível.
- Modal de reagendar substitui `prompt()` nativo; validação de recorrência incompleta.
- Banners de "sem ligação" e "nova versão disponível"; acessibilidade (ARIA tabs, `role="dialog"`, skip-link); `localStorage` protegido.
- **Bug de notificações resolvido**: o token FCM só era pedido ao servidor quando se clicava manualmente em "Ativar notificações" — se o Android matasse a app em segundo plano e o Chrome gerasse um token novo, a app nunca reparava sozinha, e o servidor desativava a subscrição na primeira falha de envio. Agora `sincronizarTokenNotifSilenciosamente()` corre a cada `carregarTudo()` e sempre que a app volta a primeiro plano (`visibilitychange`), renovando o token sozinha sem intervenção.
- `NotificationSender.gs`: `registarResultadoEnvio()` só desativa uma subscrição ao fim de **2 falhas seguidas** (antes: 1), usando `PropertiesService` por endpoint. **⚠️ Pendente de redeploy manual no Apps Script.**

## `RTO/` — KLx RTO (dias de escritório/casa)

Calendário de dias no escritório/em casa, quota anual e saldo. API direta ao Google Sheets, sem Apps Script (`SPREADSHEET_ID: 1u4QOqKMEOe8qq_kU_Cw5c8Vj4qQ0AHE5gXj9hPood9c`). Feriados portugueses calculados dinamicamente (algoritmo da Páscoa), saldo condicional (astreinte, suspensão RTO), exportação Excel, atalhos de PWA para marcar hoje T/C diretamente do ícone instalado. Versão semântica, atualmente **v5.1.0**.

**Alterações desta sessão** (commits `65fc349`, `8be8f8c`):
- Faixa "Hoje" (estado atual + próxima mudança conhecida — feriado ou início de férias) no topo do calendário.
- Comparação do mês em vista com o mês anterior.
- Calendário navegável por teclado; `localStorage` do modo noturno protegido.
- **Bug de layout corrigido**: a classe partilhada `.stat` define `width:100%`, e tanto `#todayStrip` como `.stat.saldoHero` têm margem lateral própria (16px) — a combinação fazia essas duas caixas ultrapassarem a grelha de estatísticas por baixo delas em ecrãs de telemóvel. Corrigido com `width:calc(100% - 32px)` só nesses dois seletores. Verificado numericamente (não só visualmente) com uma página de teste renderizada em Chromium headless.

## `receitas/` — Receitas

Livro de receitas pessoal. Cada receita é um ficheiro `.txt` (formato próprio `CHAVE: valor` + blocos `INGREDIENTES:`/`PASSOS:`/`NOTAS:`/`TAGS:`) guardado numa pasta "Receitas" no **Google Drive** (não Sheets). `SCOPES: drive.file`. Ficheiro grande (~640 KB) porque tem logótipos/ícones embutidos em base64. Versão "Beta N", atualmente **Beta 18**.

Já implementado (auditado, não alterado): escalamento de porções com frações e decimais, modo cozinhar passo a passo, temporizador que também dispara o Relógio nativo do Android, partilha nativa, favoritos.

**Alterações desta sessão** (commit `a2545a8`):
- **Editor de receitas dentro da app**: antes só era possível criar (upload de `.txt`) e eliminar — editar exigia alterar o ficheiro fora da app e voltar a carregá-lo, o que criava um **duplicado** no Drive (o upload nunca verificava nomes já existentes). Agora um `<textarea>` com o mesmo texto reutiliza o parser existente e faz `PATCH` ao ficheiro já existente no Drive.
- "Nova receita em branco" com o formato pré-preenchido como exemplo, no mesmo editor.
- Pesquisa passa a incluir nomes de ingredientes (antes só título/descrição/categoria/tags).
- Arranque offline-first: se a sessão falhar mas houver receitas guardadas no aparelho, mostra-as em vez de bloquear no login (cache local mudou de schema v1→v2 para guardar também o texto bruto, necessário para o editor — só limpa a cache local uma vez, o Drive é sempre a fonte de verdade).
- `service-worker.js`: passou de network-first para cache-first com atualização em segundo plano (arranque mais rápido dado o tamanho do ficheiro), `CACHE_NAME` v2.
- Acessibilidade: chips de categoria passam a `<button>`; cartões de receita mantidos como `<div role="button" tabindex="0">` (não podem ser `<button>` porque contêm botões de ação aninhados — inválido em HTML).

## `ciclismo/` — Plano de Treino

**Importante**: esta app mostra o **plano semanal escrito pelo treinador** (dia a dia, texto livre com "Sessão N:", `Total do dia:`, toggle feito/não-feito), sincronizado com uma pasta "ciclismo" no **Google Drive** — não é um histórico de treinos realizados com métricas de GPS/potência/FC, apesar de um pedido anterior ter assumido esse formato. Também lê o Sheet do `peso` (mesmo `SPREADSHEET_ID`) para mostrar o peso mais recente na aba "Atleta" — integração cruzada deliberada entre apps. Sem Apps Script. Versão "Beta N", atualmente **Beta 22**.

**Alterações desta sessão** (commit `999fd6f`):
- **Bug de segurança/correção corrigido**: o service worker intercetava e cacheava *todos* os pedidos GET, incluindo Drive, Sheets (peso) e a API do tempo — dados privados e sempre-mutáveis a serem servidos em cache desatualizada. Restringido à mesma origem, `CACHE_NAME` v23.
- Banner de "nova versão disponível"; `localStorage` protegido em leituras e escritas (antes só leituras); `esc()` reforçado a escapar aspas.
- Faixa "Hoje" (só quando o plano aberto cobre mesmo a data de hoje) e tabela "Evolução do Plano" entre semanas já sincronizadas do Drive — rotulada explicitamente como volume previsto, não dados reais de treino.
- Avisos de importação melhorados (ficheiro não reconhecível; vários ficheiros escolhidos sem Drive disponível).
- Acessibilidade: foco visível, ARIA tabs, skip-link.

**Integração externa decidida numa sessão posterior, 29 de agosto de 2026 (nenhum código deste repositório foi alterado)**:
- Um projeto separado, `~/garmin-dashboard` (repositório git próprio, fora de `escritorio-casa`, com o seu próprio `README.md`/systemd service), ganhou um separador "Plano Semanal" que **gera** o `.txt` que esta app lê e o **envia** para a mesma pasta "ciclismo" no Google Drive.
- Pedido inicial do utilizador era automatizar por completo (cron/systemd, todos os domingos); **decisão explícita do utilizador foi recusar essa automação** — a geração continua manual: o utilizador escolhe no dashboard os dias em que vai treinar nessa semana e só depois de rever o ficheiro (botão "Ver resumo") decide descarregar e/ou enviar para o Drive.
- O conteúdo de cada sessão (tipo de treino, intensidade, duração) é escrito pela API da Claude a partir do histórico real de carga/volume do Garmin — o utilizador escolheu esta opção em vez de um gerador por regras fixas, quando confrontado com as duas.
- O formato exato foi obtido por engenharia inversa do parser desta app (`parseTrainingFile`, `DAY_ORDER`, `splitByMarker`): marcadores `=====` pareados por secção, blocos de dia `--- COD DD-MM (Estado) ---` (COD = 3 letras: SEG/TER/QUA/QUI/SEX/SAB/DOM), `Sessão N:`, bullets `- `, `Total do dia:`. **Se este parser mudar no futuro, `~/garmin-dashboard/sync/plan_generator.py` tem de ser atualizado manualmente em sintonia — não há nenhuma ligação automática entre os dois repositórios.**
- Reutiliza deliberadamente o mesmo `CLIENT_ID` OAuth desta app (ver "Convenções partilhadas" acima) em vez de criar um cliente novo, para que a pasta "ciclismo" do Drive fique visível a ambos os projetos.

---

## Entregável desta sessão ainda por agir

**[Backlog das Apps](https://claude.ai/code/artifact/b9db4308-45f8-47e8-b48a-16587de08cd0)** — artifact publicado com 24 ideias de melhoria/funcionalidade organizadas pelas 5 apps, com prioridade sugerida. Nada daquilo foi implementado.

## Pendências que exigem ação manual do utilizador

1. **`tarefas/InstanciasGenerator.gs`** e **`tarefas/NotificationSender.gs`** — copiar o conteúdo atual para o projeto Apps Script em script.google.com e reimplementar. Sem isto, o lock contra duplicação de tarefas e a tolerância a falhas de notificação não têm efeito real, apesar de já estarem no repositório.
2. **Cliente OAuth partilhado** (`108256538530-...apps.googleusercontent.com`) — para o novo botão "Enviar para o Drive" do `~/garmin-dashboard` (ver secção `ciclismo/` acima) funcionar, é preciso adicionar `http://127.0.0.1:8787` a "Authorized JavaScript origins" desse cliente, na Google Cloud Console. Ainda não feito; até lá, esse botão específico falha (o resto do `garmin-dashboard`, incluindo o download do ficheiro, funciona sem este passo).
