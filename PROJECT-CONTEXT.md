# PROJECT-CONTEXT.md

Contexto de projeto para o repositório `escritorio-casa`. Descreve o **estado atual** de cada app e as decisões que não são óbvias a partir do código. Última alteração: 3 de setembro de 2026 — `convidados/` v1.3.0: clicar numa mesa no Resumo mostra quem lá está sentado, com opção de os retirar.

## Visão geral

Este repositório não é uma aplicação única — é uma coleção de **PWAs pessoais independentes**, uma por pasta, cada uma um único `index.html` autossuficiente (mais um punhado de ficheiros irmãos: service worker, manifest, ícones). Não há build, bundler nem framework: cada app é HTML/CSS/JS servido tal e qual. O deploy é feito via **GitHub Pages** (build "legacy", diretamente da branch `main`, sem GitHub Actions), em `https://pereirabmd.github.io/escritorio-casa/<pasta>/`.

Apps ativas: `peso/`, `tarefas/`, `RTO/`, `receitas/`, `ciclismo/`, `convidados/` (a lista de convidados do casamento real do utilizador — ver secção própria abaixo, é a exceção às apps "não mantidas"). Existem ainda `enfermagem/`, `xadrez/` e um duplicado histórico em `enfermagemCamila.html`, que continuam sem manutenção.

Na raiz existe também **`push.sh`** (não pertence a nenhuma app): adiciona, comita e faz push de todo o repositório para `main`, com uma guarda contra ficheiros que pareçam credenciais (`.env`, `.pem`, `.key`, `credentials.json`, etc.). Depois do push — e também no caminho em que não há nada para commitar, para permitir forçar um redeploy sem alterar ficheiros — pede explicitamente ao GitHub, via `gh api POST .../pages/builds`, que reconstrua o GitHub Pages, e espera até ~40s a reportar se ficou `built`/`errored`/ainda em curso. É um pedido explícito por cima do que já acontece sozinho (ver nota sobre o build "legacy" acima); exige a CLI `gh` instalada e autenticada, e falha em aviso (não em erro) se não estiver.

## Convenções partilhadas entre apps

- **Autenticação Google**: `peso`, `tarefas`, `RTO`, `receitas` e `ciclismo` usam o mesmo `CLIENT_ID` OAuth (`108256538530-fgunbb52s7f3s9aurfpjtaf01v8fjbph.apps.googleusercontent.com`), via Google Identity Services (token client), com a sessão persistida em `localStorage`.
- **Versionamento**: cada app tem a sua própria convenção, propositadamente não unificada — `peso` e `RTO` usam versão semântica (ex.: `v5.1.0`); `tarefas`, `receitas` e `ciclismo` usam "Beta N". O número aparece sempre no rodapé.
- **Service workers**: só intercetam pedidos GET da **mesma origem** — nunca Drive, Sheets ou APIs externas, que têm de ir sempre à rede. Estratégia cache-first com atualização em segundo plano, e um banner "nova versão disponível" ligado ao evento `controllerchange`. Sempre que o HTML muda, é preciso incrementar o `CACHE` do service worker dessa app.
- **`localStorage`**: sempre protegido com `try/catch`, tanto em leituras como em escritas (helpers `lsGet`/`lsSet`/`lsRemove` ou equivalente).
- **Conteúdo importado pelo utilizador** (planos de treino, receitas em `.txt`, nomes de tarefas e de pessoas) é tratado como **não confiável** antes de ir para `innerHTML` — cada app tem a sua função `esc()`/`escapeHtml()`.
- **`.gs` (Google Apps Script)**: só existem para `tarefas/`. **O repositório é apenas uma cópia de referência — alterações a ficheiros `.gs` não têm efeito nenhum até serem copiadas manualmente para o projeto em script.google.com e reimplementadas.**

## Lição registada em memória

O utilizador por vezes escreve um pedido para o domínio de uma app enquanto nomeia outra pasta na primeira linha. Confirmar sempre que o conteúdo real da pasta nomeada corresponde ao que o resto do pedido descreve antes de começar trabalho grande — ver `repo-structure-multi-app.md` na memória.

---

## `peso/` — Controlo de peso

Registo diário de peso sincronizado com Google Sheets (API direta, sem Apps Script). `SPREADSHEET_ID: 1UzEXtl7w6jMsk-c7Pkt3kq97AXL6XIiwTrjOYUaYFLs`. Versão `v4.0.0 R1`.

Funcionalidades: tendência por regressão linear (não apenas os dois últimos pesos), evolução mensal, melhor/pior semana, previsão de data ao objetivo, TDEE (Mifflin-St Jeor) e IMC classificados, sequência de dias, e desfazer eliminação com undo otimista.

## `tarefas/` — Tarefas de Casa

Gestão de tarefas domésticas partilhada entre várias pessoas. CRUD direto à API do Google Sheets (`SHEET_ID: 1ZwA9RqwCbOlfWLmYZWFsE5iq2oUqr-XZru_HDy6NjjI`) mais um backend em Google Apps Script para geração agendada de instâncias recorrentes e notificações push (Firebase Cloud Messaging, projeto `bmdpereira-5a8f4`). Versão **Beta 33**.

**Recorrências Trimestral/Semestral (Beta 33)**: pedido do utilizador — periodicidade a cada 3 ou 6 meses, ancorada numa **data de início à escolha**, sem criar nenhuma coluna nova em `Tarefas`. Reaproveita a coluna `DiasSemana` para guardar essa data de início (`YYYY-MM-DD`), exatamente o mesmo truque que `Pontual` já usava para guardar a sua data única; `DiaMes` fica vazio para estes dois tipos. O campo "Data" do formulário (antes só para Pontual) passa a mudar de label para "Data de início" quando o tipo é Trimestral/Semestral. A recorrência é calculada em `InstanciasGenerator.gs` → `ocorreNestaData()`: mesmo dia-do-mês da data de início, e diferença em meses múltipla de 3 ou 6 — por isso esta funcionalidade **não funciona só com o HTML**, depende do `case 'Trimestral'/'Semestral'` já copiado para o projeto Apps Script (ver aviso geral sobre `.gs` acima).

Pontos a não perder de vista:

- Existe **um único service worker** (`firebase-messaging-sw.js`) que faz cache **e** push. Nunca criar um segundo `service-worker.js` — competiriam pelo mesmo scope.
- As três funções de acesso ao Sheets partilham `sheetsFetch()`, que deteta o 401, **espera** pela renovação silenciosa do token e repete o pedido uma vez. Antes disto, só a leitura recuperava de um token expirado; as escritas falhavam para sempre em sessões cujo token expirasse noutro momento que não o do dono principal.
- O corpo das respostas de erro da API é guardado em `ultimoErroSheets` e aparece nos toasts — 401/403/400 não podem voltar a ser indistinguíveis.
- `sincronizarTokenNotifSilenciosamente()` corre a cada `carregarTudo()` e em `visibilitychange`, renovando sozinho o token FCM. Sem isto, se o Android matasse a app em segundo plano e o Chrome gerasse um token novo, as notificações paravam em silêncio.
- `NotificationSender.gs` só desativa uma subscrição ao fim de **2 falhas seguidas** (antes: 1), usando `PropertiesService` por endpoint.

## `RTO/` — KLx RTO (dias de escritório/casa)

Calendário de dias no escritório/em casa, quota anual e saldo. API direta ao Google Sheets, sem Apps Script (`SPREADSHEET_ID: 1u4QOqKMEOe8qq_kU_Cw5c8Vj4qQ0AHE5gXj9hPood9c`). Versão **v7.1.0**.

Feriados portugueses calculados dinamicamente (algoritmo da Páscoa), saldo condicional (astreinte, suspensão RTO), exportação Excel, faixa "Hoje" com a próxima mudança conhecida, comparação com o mês anterior, e atalhos de PWA para marcar hoje T/C diretamente do ícone instalado.

Navegação (desde v7.0.0, ordem alterada em v7.1.0): três separadores principais numa barra fixa no fundo do ecrã — **Calendário** (subseparadores Mês/Ano; é a **aba principal**, ecrã de entrada da app desde a v7.1.0), **Hoje** (estado do dia + saldo + estatísticas) e **Notas** (subseparadores Notas/Gerador de validações). Ver detalhe abaixo.

Detalhe de CSS a não repetir: a classe partilhada `.stat` define `width:100%`, e tanto `#todayStrip` como `.stat.saldoHero` têm margem lateral própria de 16px — a combinação fazia essas caixas ultrapassarem a grelha por baixo delas em telemóvel. Ambas usam `width:calc(100% - 32px)`.

### Reformulação visual completa (v6.0.0)

Pedido do utilizador: reformular o design por inteiro, à descrição da IA, mantendo apenas o objetivo/funcionalidades e o esquema de cores. Só `styles.css`, os `id`/classes estáticos manipulados pelo JavaScript no `index.html` (ícones adicionados, nenhum removido/renomeado) e o `CACHE_VERSION` do `sw.js` foram tocados — a lógica de negócio (autenticação, leitura/escrita no Sheets, cálculo de saldo, notas, undo, exportação) ficou intocada.

- **Paleta preservada ao byte**: todas as variáveis de cor (`--brand`, `--t/c/f/a/h-color` e os respetivos `-tint`, `--ok`/`--bad`) mantiveram exatamente os mesmos valores hex, claro e escuro — só os tokens estruturais (raio, sombra, espaçamento) foram redesenhados. Também se manteve a decisão histórica da v5.0.0 de **não usar gradientes** no cartão de Saldo nem no botão de exportar.
- Cabeçalho com efeito de vidro fosco (`backdrop-filter`), ícones SVG novos nos separadores, no seletor de modo (Normal/Férias/Administrador) e nos quatro cartões de estatística, legenda e visão do ano redesenhadas como etiquetas arredondadas, e a ficha de detalhe do dia / registo de alterações passaram a ter aspeto de folha (bottom sheet) com pega no topo.
- **Risco controlado**: como o JavaScript lê/escreve classes por `id` (ex.: `document.getElementById('statSaldoBox').className = 'stat saldoHero ' + saldoTier(...)`), o redesenho não podia renomear nenhum `id` nem nenhuma classe manipulada dinamicamente (`day`, `stat`, `saldoHero`, `saldo-ok/-warn/-bad`, `T/C/F/A/holiday`, `active`, `hidden`, `modeBtn`, `tabBtn`, etc.) — só CSS novo sobre o mesmo vocabulário, mais ícones estáticos em elementos que o JS nunca reescreve por inteiro.
- **Teste feito sem OAuth real** (a app exige login Google, que não está disponível neste ambiente): servida localmente (`python3 -m http.server`), pilotada por CDP (`chromium --headless=new --remote-debugging-port`) com dados sintéticos injetados diretamente nas variáveis globais do próprio script (`dayData`, `notasData`, chamando `renderMonth()`/`updateTotals()`/`renderNotes()`) para validar visualmente todos os ecrãs (calendário, ano, notas, modais, claro/escuro). JS e CSS também validados por sintaxe (balanceamento de chavetas/parênteses, `new Function()` sobre o script inline).
- Nota de ferramenta: capturar screenshots via `chromium --screenshot=...` com `--window-size` deu resultados inconsistentes neste ambiente (viewport não respeitado de forma fiável); a abordagem que funcionou de forma reprodutível foi abrir uma sessão CDP persistente e usar `Emulation.setDeviceMetricsOverride` + `Page.captureScreenshot`.

### Reformulação da navegação (v7.0.0)

Pedido do utilizador, explicitamente mais fundo que a v6.0.0: "a ideia é reformular mesmo", com liberdade dada para dividir por separadores/subseparadores. Desta vez mexeu-se também na arquitetura de informação, não só no CSS — mas a lógica de negócio (Sheets, saldo, notas, undo) continuou intocada; só a "casca" de navegação mudou.

- **Antes**: 3 separadores irmãos no topo — Calendário (que já continha o painel de estado/saldo/estatísticas em cima da grelha), Ano, Notas (com o gerador de validações num painel a abrir/fechar por baixo do formulário).
- **Agora**: 3 separadores — **Hoje** (painel de estado/saldo/estatísticas, isolado da grelha, é o ecrã de entrada), **Calendário** (a grelha + navegação de mês, agora com subseparador **Mês/Ano** — "Ano" deixou de ser separador de topo), **Notas** (subseparador **Notas/Gerador** — o gerador deixou de ser um painel escondido). A barra principal passou do topo para **fixa no fundo do ecrã**, ao alcance do polegar, padrão de app nativa. O botão de exportar (FAB) deixou de estar só na aba Calendário e passou a flutuar sobre qualquer separador.
- **Mapeamento de `id`s que mudaram** (para quem for mexer no JS depois): `tabAno`/`tabBtnAno` deixaram de existir — o conteúdo do ano vive agora em `calSubAno`, comutado por `calSubBtnAno` via `showCalSub('ano')`. `genToggleBtn` (botão que abria/fechava o painel do gerador) foi removido — o painel `genPanel` vive agora sempre visível dentro de `notasSubGerador`, comutado por `notasSubBtnGerador` via `showNotasSub('gerador')`. Todos os outros `id`s (`statSaldoBox`, `statT`, `grid`, `notasList`, `notaForm`, etc.) mantiveram-se exatamente iguais.
- `showTab()` ganhou dois irmãos, `showCalSub()` e `showNotasSub()`, com a mesma forma (`classList.toggle('hidden', ...)` + `aria-selected`); `showSkeleton()` foi ajustado para esconder as três abas de topo (incluindo a nova `tabHoje`) em vez de duas.
- **Validação estática antes de testar visualmente**: um script Node percorreu o HTML à procura de todo `getElementById('...')` chamado pelo JS e confirmou que cada um desses `id`s existe de facto no markup — apanhou, antes de qualquer teste manual, uma chamada esquecida a `getElementById('tabBtnAno')` (já removido) dentro do `onclick` das células da vista Ano, que teria rebentado em runtime assim que alguém tocasse num dia da vista Ano.
- **Teste visual**: mesma abordagem CDP da v6.0.0 (dados sintéticos injetados + `Emulation.setDeviceMetricsOverride` + `Page.captureScreenshot`), desta vez também a **clicar programaticamente** nos novos botões de subseparador e a confirmar via `getBoundingClientRect`/`classList` que o subseparador certo fica visível — incluindo o caso de regressão do clique num mini-dia da vista Ano (tinha de voltar ao subseparador Mês nesse mesmo mês, e ficou confirmado que fica).

**v7.0.1**: a legenda do calendário (`#legend` no Mês, `#anoLegend` no Ano) passou de etiquetas cinzentas com um pontinho colorido para etiquetas tingidas com a cor de cada categoria (fundo `-tint`, borda e texto na cor sólida), a pedido do utilizador. Cada `<span>` da legenda ganhou uma classe da categoria (`t`/`c`/`f`/`a`/`h`, o mesmo vocabulário já usado no `.dot`) só para estas duas listas estáticas — nunca escritas por JS, por isso sem risco de colisão com o resto da app.

**v7.1.0**: dois pedidos do utilizador — Calendário como aba principal, e corrigir o desfasamento do skeleton de carregamento.
- **Calendário como aba principal**: o botão `tabBtnCal`/painel `tabCalendario` passaram a vir primeiro na barra de separadores e no HTML (antes de `tabBtnHoje`/`tabHoje`), e `let currentTab` arranca em `'cal'` em vez de `'hoje'`. Os `id`s não mudaram — só a ordem no DOM e o estado inicial de `class="hidden"`/`active`/`aria-selected`. Nenhuma outra lógica dependia da ordem dos separadores (sem gestos de swipe, sem seletores `nth-child` sobre `.tabBtn`).
- **Skeleton desfasado do layout real**: o skeleton (`#skeletonOverlay`, mostrado por `showSkeleton(true)` enquanto `loadData()`/`loadNotes()` correm) tinha ficado da v6.0.0 — 3 abas falsas cheias de largura + grelha 2×3 de "cartões" — e nunca foi atualizado quando a v7.0.0 mudou a arquitetura de navegação; não batia certo nem com a antiga aba Hoje (4 cartões desiguais, não 6 uniformes) nem, agora, com a aba Calendário que passou a ser a primeira coisa que aparece. Foi reconstruído para espelhar exatamente a estrutura real da aba Calendário, pela mesma ordem: pílula de subseparadores Mês/Ano (`.skelSubBar`), navegação de mês com setas + rótulo + botão "Hoje" (`.skelMonthNav`), seletor de modo Normal/Férias/Administrador (`.skelModeRow`), cabeçalho de dias da semana + grelha 7×5 (`#skelCalendar`), e legenda de categorias (`.skelLegend`) — reutilizando os mesmos valores de margem/padding/altura das regras CSS reais (`#calSubBar`, `#monthNav`, `.navBtn`, `#todayBtn`, `#modeRow`, `#calendar`, `#legend`), para não haver salto de layout quando os dados chegam e o conteúdo verdadeiro substitui o skeleton. As classes antigas (`.skelTabs`/`.skelTab`/`.skelTotals`/`.skelCard`/`.skelNav`) foram removidas por inteiro — não eram usadas em mais lado nenhum.
- **Teste**: sem OAuth disponível neste ambiente, o skeleton foi validado isoladamente — uma página de teste local só com o `styles.css` real e o markup do `#skeletonOverlay`, servida por `python3 -m http.server` e capturada com `chromium --headless=new --screenshot=... --window-size=480,900` (mais simples que a via CDP das reformulações anteriores porque não há JavaScript de app nem autenticação a simular) — em claro e escuro, confirmando visualmente a ordem e o alinhamento dos blocos. Confirmado também por script Node que todo `getElementById('...')` chamado pelo JS continua a apontar para um `id` existente no HTML e que não ficaram `id`s duplicados após mover o painel Calendário para a frente do Hoje.

## `receitas/` — Receitas

Livro de receitas pessoal. Cada receita é um ficheiro `.txt` (formato próprio `CHAVE: valor` mais blocos `INGREDIENTES:`/`PASSOS:`/`NOTAS:`/`TAGS:`) guardado numa pasta "Receitas" no **Google Drive** — não em Sheets. `SCOPES: drive.file`. Ficheiro grande (~640 KB) por causa dos logótipos embutidos em base64. Versão **Beta 19**.

Funcionalidades: escalamento de porções com frações e decimais, modo cozinhar passo a passo, temporizador que dispara o Relógio nativo do Android, partilha nativa, favoritos, e um editor dentro da própria app que faz `PATCH` ao ficheiro existente no Drive (antes, editar fora da app e voltar a carregar criava um **duplicado**, porque o upload nunca verificava nomes já existentes).

Arranque offline-first: se a sessão falhar mas houver receitas guardadas no aparelho, mostra-as em vez de bloquear no login. O Drive é sempre a fonte de verdade.

Os cartões de receita são `<div role="button" tabindex="0">` e **não** `<button>`, porque contêm botões de ação aninhados — o que seria HTML inválido.

### Reformulação visual completa (Beta 19)

Pedido do utilizador: refazer o layout por inteiro para encaixar melhor no tema, com liberdade total sobre estrutura/abas, sujeito só a duas constraints — manter o mesmo ícone e o mesmo esquema de cores. Seguiu o mesmo princípio das reformulações da `RTO/`: só CSS e estrutura visual foram tocados; a lógica de negócio (Drive, parser `.txt`, favoritos, escalamento, temporizador, PATCH do editor) ficou intocada.

- **Cores e ícone preservados ao byte**: todas as variáveis de `:root`/`html.dark` (terracota, creme, oliva, carvão, etc.) mantiveram exatamente os mesmos valores; o PNG do ícone embutido em base64 (favicon, apple-touch-icon, marca de água de fundo, ecrã de login) não foi alterado.
- **Filtros passaram de uma única fila de chips para separador + subseparador**: "Todas"/"Favoritas" tornou-se um controlo segmentado (`.tabs-row`/`.tab-btn`) no topo, com as categorias como subseparador de chips por baixo (`#catSubRow`). `renderCategoryChips()` foi reescrita para emitir esta estrutura, mas manteve o mesmo mecanismo de filtragem (`data-cat`, `#favToggleChip`, `state.filterCategoria`/`state.showFavoritesOnly` compõem-se como antes).
- **Cartões e receita aberta ganharam ar de fichário de receitas**: tira de "fita" (`::before`) e canto dobrado (`::after`) nos cartões da grelha, a mesma tira e os furos de dossier (`.detail-holes`, já existente) na receita aberta, linha de meta separada por traço serrilhado.
- **Armadilha de CSS Grid encontrada e corrigida**: dar `white-space:nowrap` + `text-overflow:ellipsis` ao `.eyebrow` (para truncar categorias longas em vez de sobrepor os ícones de ação do cartão) alargava a coluna da grelha inteira, porque um item de CSS Grid sem `min-width:0` assume como largura mínima automática o `max-content` do texto por quebrar — mesmo com `overflow:hidden`. Corrigido com `min-width:0` no `.card` (o item de grid). Vale a pena lembrar sempre que texto com `nowrap`+ellipsis aparecer dentro de um item de grid/flex.
- **Teste sem OAuth** (a app exige login Google): grelha e receita aberta validadas via CDP (`chromium --headless=new --remote-debugging-port` com `--remote-allow-origins=*`, sessão `websocket-client` instalada com `pip install --break-system-packages`), com dados sintéticos semeados diretamente em `localStorage` (`receitas.cache.v1`/`receitas.favorites`) antes da navegação via `Page.addScriptToEvaluateOnNewDocument` — mais simples que injetar em variáveis JS globais porque o `boot()` desta app já lê a cache diretamente do `localStorage`. **Cuidado com o service worker**: depois da primeira navegação bem-sucedida, o `service-worker.js` (cache-first) passa a servir HTML antigo em recargas seguintes mesmo com o ficheiro em disco já alterado — só se resolveu com um perfil de browser novo (`--user-data-dir` limpo) a cada iteração de teste.

---

## `ciclismo/` — Plano de Treino

**Importante**: esta app mostra o **plano semanal escrito pelo treinador** — não é um histórico de treinos realizados com métricas de GPS/potência/FC, apesar de um pedido anterior ter assumido esse formato. Os ficheiros `.txt` são sincronizados a partir de uma pasta "ciclismo" no **Google Drive**. A app lê também o Sheet do `peso` (mesmo `SPREADSHEET_ID`) para mostrar o peso mais recente — integração cruzada deliberada entre apps. Sem Apps Script. Versão **Beta 23**, service worker `ciclismo-shell-v24`.

### Formato do ficheiro que o parser lê

Há **duas** origens de ficheiros, com formas diferentes, e o parser tem de aceitar as duas:

| | Ficheiros do treinador | Gerados pelo `~/garmin-dashboard` |
|---|---|---|
| Marcador de secção | 60 caracteres `=` | 5 caracteres `=` |
| Cabeçalho de dia | `--- SEGUNDA 2026-09-01 (Planeado) ---` | `--- SEG 01-09 (Planeado) ---` |
| Data | ISO completa | `DD-MM`, sem ano |
| Corpo do dia | campos `Tipo:`, `Duracao alvo:`, `Distancia estimada:` | bullets `- ` sob `Sessão 1:` |

Ambas as formas usam `Total do dia:` e podem ter várias sessões por dia. Datas `DD-MM` são normalizadas para ISO usando o ano deduzido de `Semana:`/`Ficheiro gerado em:`, com correção automática quando a semana atravessa a viragem do ano. **Internamente só circulam datas ISO** — é o formato usado para comparar com "hoje", indexar a previsão do tempo e ordenar semanas.

### Bug corrigido em Beta 23 (o motivo desta reescrita)

Um dia do plano aparecia cinzento, sem cartão, indistinguível de um dia marcado como `Indisponivel`, apesar de o `.txt` o descrever como treino Z2.

Causa: `splitByMarker` ancorava a expressão regular do cabeçalho de dia em `^---`, na **coluna 0**. Bastava um espaço à frente da linha `--- TERCA ... ---` para o dia deixar de ser reconhecido: desaparecia do mapa de dias **e** as suas linhas eram absorvidas pelo bloco do dia anterior. Como `renderSemana` desenhava um dia ausente com uma linha cinzenta igual à de um dia de descanso, uma falha de leitura do ficheiro era indistinguível de uma decisão do treinador.

Duas hipóteses que foram testadas e **descartadas**: não era o tratamento de `TERCA` sem acento (o matching usa `stripAccents`, e `TERCA`/`TERÇA`/`TER` resolvem todos para o mesmo dia), nem a quebra de linha dentro do campo `Estrutura:` da Quarta.

### O que mudou no parser

- Os cabeçalhos de dia passam a ser testados sobre a linha **trimada**, e o nome do dia, a data e o estado são identificados por posição relativa em vez de por uma ordem fixa. O estado é capturado com âncora no fim da linha, para não apanhar parênteses que apareçam no meio do texto.
- As secções deixaram de ser emparelhadas por índice (marcador 0-1, 2-3, ...), que desalinhava todas as secções seguintes quando houvesse um marcador a mais ou a menos. Agora um marcador seguido de um título abre sempre uma secção, com ou sem marcador de fecho.
- Um dia cujo nome não seja reconhecível mas que tenha data válida é atribuído ao dia da semana **deduzido da data**.
- Os campos `Campo: valor` passam a ser itens tipados (`kv`) no momento do parse, em vez de serem redescobertos por outra expressão regular na altura de desenhar — as duas podiam discordar.
- Continuações de linha só se juntam à linha anterior quando a própria linha não é um campo nem um bullet. Há ficheiros que indentam também os próprios campos (`  Tipo: Z2` dentro de `Sessão 1:`), por isso a indentação sozinha não chega.
- Distância e duração vêm primeiro dos campos das sessões e só depois, se nenhuma sessão os declarar, da linha `Total do dia:`. Antes eram procurados só em texto solto, e ficavam quase sempre a zero com os ficheiros reais.
- A classificação do dia passou a ter quatro níveis (descanso / base / moderado / intenso), com Z3 separado de Z4-Z5. Um dia só é de descanso se o ficheiro o disser — primeiro o estado do cabeçalho, depois `Total do dia:`, e só em último recurso o corpo. Menções como "sessão forte **cancelada**" já não classificam o dia como intenso.
- **Um dia em falta deixou de ser desenhado como um dia de descanso**: aparece agora a âmbar, tracejado, com "sem bloco no ficheiro", e é contado no diagnóstico. Os avisos do parser são mostrados na aba "Mais", em vez de desaparecerem em silêncio.

### O que mudou na segurança do parser

O `.txt` vem do Drive ou de um ficheiro escolhido à mão: é entrada não confiável.

- **Limites de tamanho** (`LIMIT`): 512 KB, 20 000 linhas, 4 000 caracteres por linha, 200 itens por sessão, 24 sessões por dia, 40 secções. O que for cortado é comunicado como aviso.
- **Caracteres de controlo e marcas bidireccionais** (U+202A-U+202E, U+2066-U+2069, zero-width, NUL) são removidos antes de tudo o resto — impedem um ficheiro de desenhar texto que se lê ao contrário do que diz (*Trojan Source*).
- **Poluição de protótipo**: o mapa de dias e os restantes mapas indexados por texto do ficheiro usam `Object.create(null)`, e a cache de sessões feitas rejeita as chaves `__proto__`/`constructor`/`prototype`.
- **`sanitizePlan()`**: o que vem de `localStorage` é revalidado campo a campo antes de chegar ao render — uma cache escrita por outra versão, truncada ou adulterada não pode rebentar a app. O `renderAll` tem ainda um `try/catch` que mostra uma saída em vez de deixar o ecrã em branco.
- **Injeção MIME no upload para o Drive**: a fronteira do corpo multipart era `'ciclismo-' + Date.now()`, perfeitamente adivinhável. Um `.txt` que a contivesse partia o pedido em partes extra. Agora é aleatória (`crypto.getRandomValues`) e verificada contra o conteúdo antes de ser usada.
- **Coordenadas da previsão do tempo** vindas da cache são validadas como números dentro do intervalo geográfico válido antes de entrarem numa URL.
- Sem `new RegExp` construído a partir de dados do ficheiro; a cache de textos do Drive é limitada a 24 ficheiros; só entram no parser ficheiros `.txt` de tamanho plausível.

Estas mudanças estão cobertas por um conjunto de testes (XSS, poluição de protótipo, Trojan Source, ficheiros gigantes, entrada degenerada, cache adulterada, datas inválidas) corridos em Node contra as funções puras do ficheiro. Os testes não estão no repositório — o padrão do repositório é não ter infraestrutura de build nem de teste.

### Redesenho visual (Beta 23)

O esquema de cores foi mantido exatamente (as mesmas variáveis CSS, claro e escuro); o layout foi todo refeito:

- Navegação passou de separadores no topo para uma **barra inferior** com quatro ícones, ao alcance do polegar.
- Barra de topo compacta, com as ações em botões de ícone e o seletor de semana numa linha própria.
- Um **cartão "Hoje"** com anel de progresso das sessões feitas, etiquetas de duração/distância/zona e o próximo treino.
- Grelha de quatro estatísticas, **barra empilhada de carga por zona**, e previsão a 7 dias num carrossel horizontal.
- Os dias passaram a uma **linha temporal** com carris e pontos coloridos pela intensidade; cada dia é um cartão colapsável (os dias já passados começam fechados).
- Estados visuais distintos para dia de treino, dia de descanso e dia em falta.

### Contrato com o `~/garmin-dashboard`

Um projeto separado, `~/garmin-dashboard` (repositório git próprio, fora de `escritorio-casa`), tem um separador "Plano Semanal" que **gera** um `.txt` no formato que esta app lê e o envia para a mesma pasta "ciclismo" do Drive. O conteúdo de cada sessão é escrito pela API da Claude a partir do histórico real de carga e volume do Garmin.

- A geração é **deliberadamente manual**. O pedido inicial era automatizá-la por cron/systemd todos os domingos; a decisão explícita do utilizador foi recusar essa automação — ele escolhe os dias em que vai treinar e só depois de rever o ficheiro decide enviá-lo.
- Reutiliza de propósito o mesmo `CLIENT_ID` OAuth desta app, para que a pasta "ciclismo" do Drive seja visível aos dois projetos.
- **Não há ligação automática entre os dois repositórios.** O parser da app é agora bastante mais tolerante do que era, por isso `~/garmin-dashboard/sync/plan_generator.py` continua compatível sem alterações; mas se o formato gerado mudar, é preciso confirmar manualmente contra o parser em `ciclismo/index.html`.

## `convidados/` — Convidados (casamento)

Gestão da lista de convidados do casamento real do utilizador (Camila & Bruno). CRUD direto à API do Google Sheets (`SHEET_ID: 1UcjSO3P7RbreTtKeg4T8jsoRa2KwzTEPE4Wsrkf2Eos`), sem Apps Script, sem manifest nem service worker — a mais simples das apps do repositório, só `index.html`. Versão **v1.3.0**.

Há um projeto **separado e maior** para o próprio casamento em `~/casamento` (fora deste repositório, com o seu próprio `PROJECT-CONTEXT.md`/`CLAUDE.md`), que inclui a pasta `Mesas/` com o plano de lugares "a sério" (`mesas.csv`, scripts de geração). Esta app (`convidados/`) é só a PWA de acompanhamento de RSVPs — os dois não estão ligados automaticamente.

Colunas da sheet `Convidados!A2:G1000`: `Nome, Nº Pessoas, Nº Confirmados, Fase, Estado, Notas, Mesa`. `Fase` e `Estado` são listas configuráveis via a sheet `Config!A2:B50`; `Mesa` é fixa no código (ver abaixo).

### Campo "Mesa" (v1.1.0, corrigido em v1.2.0)

Pedido do utilizador: organizar os convidados por mesa (1 a 10, fixo por agora). O pedido inicial era não alterar o modelo de dados, e a v1.1.0 cumpriu isso à letra embutindo a mesa dentro de "Notas" com um marcador de texto — mas o pedido **na verdade** era só não obrigar o utilizador a editar a Sheet à mão; a app podia perfeitamente criar a coluna sozinha. A v1.2.0 corrige isto: `RANGE_GUESTS` passou a `Convidados!A2:G1000`, e `ensureMesaColumn()` (chamada uma vez no arranque, antes de carregar os convidados) lê `Convidados!G1` e escreve lá o cabeçalho `"Mesa"` se ainda estiver vazio — idempotente, nunca pisa um cabeçalho já existente. O utilizador nunca precisa de tocar na Sheet.

- **Retrocompatibilidade**: convidados gravados pela v1.1.0 ainda têm a mesa dentro de Notas (`#mesa:N`). `extractMesaLegado()`/`stripMesaLegado()` continuam a lê-la de lá como recurso de retaguarda quando a coluna G vier vazia — mas só para leitura; qualquer gravação seguinte desse convidado já escreve o número só na coluna G e limpa o marcador de Notas.
- **Só convidados "Confirmado" podem ter mesa** (`ESTADO_COM_MESA`), outro pedido do utilizador: o campo Mesa no modal fica desativado (`updateMesaFieldState()`) enquanto o Estado não for Confirmado, e é sempre forçado a vazio no momento de gravar — tanto no modal principal como na gravação rápida de estado — se o Estado gravado não for Confirmado. Mudar o Estado de um convidado com mesa para outra coisa **larga a mesa automaticamente**, em qualquer um dos dois modais.
- **Aviso de mesa cheia, não bloqueante**: ao escolher uma mesa no modal, `pessoasNaMesa()` soma as pessoas já atribuídas a essa mesa (excluindo a própria linha, para reedições) e, se o total chegar a `CAPACIDADE_MESA` (10), mostra um toast de aviso — mas continua a deixar guardar. Só dispara no `change` do campo Mesa, não é reverificado no momento de gravar.
- `MESAS = ["1",...,"10"]` continua hardcoded no JS (não vem do `Config`) — é a lista fixa pedida pelo utilizador; se o número de mesas mudar, é aqui que se edita.
- Mesa aparece como filtro (`#filterMesa`, terceiro chip da toolbar), campo no modal de edição, badge dourado no cartão (reaproveita `.status-badge`/`.status-dot` existentes, sem CSS novo), secção "Por Mesa" no separador Resumo, e coluna extra na lista exportada/impressa — como só convidados Confirmados podem ter mesa, estes contadores já refletem só gente confirmada, sem filtro extra.

### Detalhe da mesa: ver e retirar convidados (v1.3.0)

Pedido do utilizador: clicar numa linha de mesa no "Por Mesa" do Resumo mostra quem lá está sentado, com opção de os retirar da mesa (não de os apagar da lista). `breakdownRow()` ganhou um 4º parâmetro opcional `mesa` — só as 10 linhas de mesa o recebem (não "Sem mesa", nem as linhas de Por Estado/Por Fase, que continuam sem serem clicáveis) — e passa a ter `data-mesa`/`role="button"`/`tabindex`. Um clique chama `openMesaDetail(mesa)`, que abre um `.modal-overlay` novo (`#mesaDetailOverlay`, mesmo padrão visual dos outros modais da app) listando os convidados dessa mesa por ordem alfabética, cada um com um botão "Remover da mesa".

- `removeGuestFromMesa()` escreve só a célula `Convidados!G{row}` (não a linha inteira A:G) — mantém tudo o resto do convidado intacto (Estado continua Confirmado, Notas não muda) — e chama `refreshAll()` a seguir, o mesmo padrão de "recarregar da fonte de verdade depois de escrever" usado no resto da app.
- O modal fica aberto depois de remover alguém (a lista lá dentro atualiza-se sozinha, para permitir tirar vários convidados seguidos sem reabrir); `renderResumo()` volta a chamar `renderMesaDetail()` no fim sempre que o modal estiver aberto, para os números da mesa e a lista nunca ficarem dessincronizados de um refresh (manual, pull-to-refresh, ou depois de uma remoção).
- **Testado com o código real da app**, não só visualmente: `window.fetch` foi substituído antes da navegação por um mock que intercepta os pedidos ao Sheets API (`ensureMesaColumn`, `loadConfig`, `loadGuests`, `loadSheetMeta`, e o `PUT` de remoção) com dados sintéticos com estado próprio, deixando todo o resto do código da app (incluindo `openMesaDetail`/`removeGuestFromMesa`/`refreshAll`) correr sem alterações — confirmou a mesa a abrir com os 4 convidados certos e a lista a atualizar-se de imediato ao remover um deles. **Cuidado ao repetir**: `encodeURIComponent` escreve `:` como `%3A` nos URLs pedidos (ex. `Convidados!A2:G1000` → `...A2%3AG1000`); o mock de fetch tem de fazer `decodeURIComponent(url)` antes de comparar por `includes(...)`, senão os padrões com `:` nunca combinam e cai sempre no `fetch` real (que devolve 401 com um token falso).

### Monograma (v1.1.0)

O logótipo no cabeçalho e no rodapé era um placeholder gerado ("C·B" em círculo). Substituído pelo monograma real do casamento, recortado a partir de `~/casamento/Mesas/monogram_circle.png` (700×700, fundo transparente) e reduzido para 160×160 antes de embutir em base64 — mais pequeno do que o placeholder que substituiu. O favicon (ícone "Claudinho", partilhado com as outras apps da família) não foi tocado — é intencionalmente diferente do logótipo do casamento.

---

## Pendências que exigem ação manual do utilizador

1. **`tarefas/InstanciasGenerator.gs`** e **`tarefas/NotificationSender.gs`** — copiar o conteúdo atual para o projeto Apps Script em script.google.com e reimplementar. Sem isto, o lock contra duplicação de tarefas e a tolerância a falhas de notificação não têm efeito real, apesar de já estarem no repositório.
2. **Cliente OAuth partilhado** (`108256538530-...apps.googleusercontent.com`) — para o botão "Enviar para o Drive" do `~/garmin-dashboard` funcionar, é preciso adicionar `http://127.0.0.1:8787` a "Authorized JavaScript origins" desse cliente, na Google Cloud Console. Até lá, esse botão específico falha; o resto do `garmin-dashboard`, incluindo o download do ficheiro, funciona sem este passo.

## Backlog

**[Backlog das Apps](https://claude.ai/code/artifact/b9db4308-45f8-47e8-b48a-16587de08cd0)** — artifact com 24 ideias de melhoria organizadas pelas 5 apps, com prioridade sugerida. Nada daquilo foi implementado.
