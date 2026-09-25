# Automação de bilhetes CP — Passe Ferroviário Verde

Automação para comprar bilhetes CP (Comboios de Portugal) ida e volta, a €0
via desconto do Passe Ferroviário Verde, correndo num Raspberry Pi. Em horas
de procura elevada, os lugares só estão garantidos no instante em que a
venda abre — **exatamente 24 h antes da partida** — e esgotam em poucos
segundos. Por isso o timing exato da compra é o requisito mais crítico de
todo o projeto.

Este documento é o plano de referência e o hand-off para continuar a
implementação com o Claude Code. Última atualização: 21/09/2026 (inclui o
que foi confirmado num HAR novo, capturado a 21/09/2026).

**Duas máquinas:**
- A máquina onde o Claude Code corre e faz commits para o GitHub (o
  repositório deste projeto)
- O **Raspberry Pi**, servidor deste projeto, ao qual o Claude Code tem
  **acesso SSH por chave** — e deve fazer aí tudo o que for preciso:
  instalar pacotes, copiar ficheiros, configurar aplicações. Não se limita
  a "gerar ficheiros para depois alguém instalar" — o Claude Code executa
  a instalação e configuração diretamente no RPi via SSH.

**⚠️ Regra crítica: nunca destruir o que já existe no RPi.** O RPi já
corre outras coisas (outro site atrás do nginx, o updater DDNS do
`camilaebruno`, etc.). Todas as alterações têm de ser **aditivas ou
modificações pontuais**, nunca substituições cegas de ficheiros de
configuração inteiros. Exemplo concreto: no nginx, **acrescentar** um novo
`server{}` para o domínio `bmdpereira`/ntfy (ficheiro novo em
`sites-available/` + symlink em `sites-enabled/`, ou um bloco adicional),
nunca sobrescrever a configuração existente. O mesmo princípio aplica-se a
crontab, systemd, firewall, etc. — verificar o que já lá está antes de
mexer, e preferir sempre criar/acrescentar a substituir.

---

## 1. Visão geral

- Viagens necessárias: 2 dias por semana (variável, configurado semanalmente)
- Cada dia de viagem tem uma perna de ida e uma de volta, com comboio e hora
  de partida próprios
- O bilhete de cada perna é comprado **exatamente 24h antes da sua hora de
  partida** (ex: partida segunda 06:45 → disparo domingo 06:45), que é o
  momento em que a venda abre. Ida e volta têm disparos separados, porque
  têm horas de partida diferentes.
- Em horas de pouca procura ainda há lugares depois de a venda abrir (foi
  assim que a compra capturada no HAR de 21/09/2026, a 23 h 37 min da
  partida, funcionou) — **o sistema não pode contar com isso**: nas horas
  que interessam, é preciso acertar no instante.
- O **ID do comboio tem prioridade sobre a hora** na escolha da viagem a
  comprar — a hora configurada serve principalmente para calcular o
  instante do disparo, não para procurar por aproximação.
- Todos os sábados, um lembrete (ntfy) pede a configuração da semana
  seguinte via PWA. A verificação repete-se ao meio-dia e à noite do mesmo
  sábado e só notifica se a configuração continuar em falta (ver 3.6).

### 1.1 Princípio transversal: nada falha em silêncio

**Nada deve passar despercebido.** Qualquer falha, erro, ou situação
anómala em qualquer componente tem de gerar sinal visível (notificação
ntfy e/ou linha de log) — nunca falhar calada e só se descobrir depois de
já ser tarde (ex: o comboio já ter partido sem bilhete). Isto aplica-se a
todo o sistema, não só à compra em si. Mecanismos previstos que
concretizam este princípio — usar como checklist ao implementar cada
componente, e não adicionar nenhum código com falha silenciosa:
- Compra: distinguir esgotado de erro técnico, sempre notificar o
  resultado (3.3.1), ler `messages` mesmo com HTTP 200 e confirmar que o
  total da venda é €0 antes de confirmar (secção 2)
- Agendamento: o daemon recalcula os disparos a cada ciclo e ao arrancar,
  e o watchdog do systemd deteta ciclos bloqueados (3.2, 3.3.1)
- Configuração em falta: verificações de sábado (3.6)
- Passe a expirar: aviso 3 e 1 dia antes (3.9)
- RPi em baixo: heartbeat/watchdog via healthchecks.io (secção 6 —
  deixado para depois dos testes, mas não esquecer)
- Qualquer script/job novo que o Claude Code criar deve seguir o mesmo
  padrão: try/except com notificação de erro, nunca um `except: pass`
  silencioso
- Relógio dessincronizado, Sheet ilegível, ntfy indisponível, config
  inválida: ver conjunto completo de mecanismos em 3.10

---

## 2. Fluxo de compra na API da CP (engenharia inversa via HAR)

Sequência confirmada em dois HAR capturados manualmente (o mais recente a
21/09/2026, com uma compra completa: pesquisa, venda, desconto do Passe e
confirmação). A API é interna do site cp.pt e pode mudar sem aviso.

### 2.1 Autenticação

Keycloak / OAuth2 com PKCE, em `login.cp.pt` (realm `cpclients`, client_id
`websitecp`, scope `openid profile email`). Login direto com email+password
(a conta em causa não usa Google/Apple/Chave Móvel Digital).
- `access_token`: válido 5 minutos (`expires_in: 300`)
- `refresh_token`: `refresh_expires_in: 1799` no login. **O prazo não se
  renova com o refresh**: um refresh feito 2 s depois do login devolveu
  `refresh_expires_in: 1797`, ou seja, a sessão morre ~30 minutos depois do
  login, por mais refreshes que se façam. Guardar sempre o `refresh_token`
  mais recente devolvido.
- Fluxo: `GET .../openid-connect/auth` → formulário (o `action` traz
  `session_code`/`execution`) → `POST` do formulário com `username`,
  `password`, `credentialId` (302) → `code` no fragmento do redirect →
  `POST .../token` com `grant_type=authorization_code` e `code_verifier`.
  Renovação: `POST .../token` com `grant_type=refresh_token`.

### 2.2 Sequência de compra

| # | Pedido | Login? | Notas |
|---|---|---|---|
| 1 | `POST /travel-api/journeys` | **não** | pesquisa de horários; devolve, por comboio, `serviceCode` e `saleableOnline`. **Nunca no caminho crítico da compra.** |
| 2 | `POST /ticketing-api/sale` | sim | **pedido crítico ao segundo.** Cria a venda (`PENDING`) e **já atribui o lugar** (`seatData`: carruagem + lugar), bloqueando-o. Devolve `saleID` e `reference`. |
| 3 | `PUT /ticketing-api/sale/{id}/passengers` | sim | nome e Cartão de Cidadão |
| 4 | `PUT /ticketing-api/sale/{id}/client` | sim | email, telemóvel, nome |
| 5 | `PUT /ticketing-api/sale/{id}/fiscal` | sim | NIF; o site envia depois uma segunda vez com `fiscalAddress` (ver 2.4) |
| 6 | `PUT /ticketing-api/sale/{id}/items` | sim | desconto do Passe: `{"requestedItems":[{"itemCode":"302","relatedTrain":null,"ticketIndex":0,"type":"DISCOUNT","inputData":"<número do passe>"}]}` → `totalAmount` passa de €23,45 para €0,00 |
| 7 | `PUT /ticketing-api/sale/{id}/confirm` | sim | sem pagamento (total €0). Resposta: `status.code = CONFIRMED`, `payment.paymentType = PASS`, número de documento. |

Passo 2 — corpo mínimo: `quantity`, `travelClass.code`, `travelDate`,
`outwardTrip[]` com `trainNumber`, estações e `serviceCode` (`code` +
`designation`, ex: `IC` / `Intercidades`, `R` / `Regional`, `AP`) e `lang`.
Em viagens com transbordo, `outwardTrip[]` leva uma entrada por secção.

Rotas auxiliares usadas pelo site: `GET /sale/{id}/items/available` (lista
de descontos; o `302` "Passe Ferroviário Verde" tem `inputRequired: true`),
`GET /sales/{id}` (estado de uma venda, em qualquer estado),
`GET /train-seats/{saleID}/trains/{n}` (mapa de lugares),
`GET /e-ticket/{saleID}/{reference}/{documentNumber}`,
`GET /trips/<email>?filter=FUTURE` (viagens do cliente).

### 2.3 Cabeçalhos

Todos em `api-gateway.cp.pt`:
- `x-api-key` (varia por serviço: viagens vs bilhética)
- `x-cp-connect-id` e `x-cp-connect-secret` — constantes embutidas no
  frontend, não são segredos pessoais
- `x-access-token` (o access_token OAuth) — **só** nos pedidos de
  bilhética/conta; o `journeys` não o leva
- `x-cp-client-id` (o email do cliente) — nos pedidos de bilhética
- `x-cp-client-registration-date` — só em `/trips` e `/trips-count`; é a data
  de registo da conta (campo `registered` do perfil, formato ISO)

O site usa HTTP/1.1 no gateway (segundo o HAR), por isso a biblioteca
`requests` chega — não é preciso HTTP/2.

### 2.4 Comportamento observado (a respeitar na implementação)

- **Ler sempre o campo `messages`** da resposta, não confiar só no status
  HTTP — pode vir 200 com avisos/erros parciais. Nas respostas do HAR veio
  sempre vazio.
- **O lugar sai no `POST /sale`**, não no `/confirm`. A venda `PENDING`
  bloqueia esse lugar até ser confirmada ou expirar. Para o lembrete T-30
  (3.6) basta guardar carruagem/lugar da resposta do passo 2 (ou ler
  `GET /sales/{id}`).
- **Verificar o total antes de confirmar.** Depois do passo 6,
  `totalAmount` tem de ser `€ 0,00`. Se não for, **não confirmar**: notificar
  (1.1) e tentar aplicar o desconto de novo. Sem o desconto a venda é de
  ~€23,45.
- **`PUT` idempotentes.** Os passos 3 a 7 podem ser repetidos sobre o mesmo
  `saleID`. O `/confirm` repetido devolveu `CONFIRMED` (136 ms) sem erro. Em
  caso de dúvida (timeout, reboot), repetir é seguro.
- **`fiscalAddress`.** Antes do `/confirm` o site voltou a enviar `client` e
  `fiscal`, desta vez com `fiscalAddress`. Ainda não se sabe se é
  obrigatória. Testar o fluxo sem morada; se falhar, acrescentar
  `CP_FISCAL_ADDRESS` ao `.env` e enviá-la no passo 5.
- **Duração medida no browser** (inclui ~110 ms de ligação nas primeiras
  chamadas): `journeys` ~0,3 s; `POST /sale` ~0,67 s (0,54 s de espera do
  servidor); `PUT items` ~1,3 s; `PUT confirm` ~1,0 s; `passengers`/`client`/
  `fiscal` 0,3–0,4 s cada. A sequência pós-venda soma ~2,7 s de espera do
  servidor. O prazo para a completar é de 15 min (2.5).
- **`journeys` devolve comboios e `serviceCode` mesmo para partidas a mais
  de 24 h**, e com `saleableOnline: true`. Isto permite obter o
  `serviceCode` **antes** da abertura (ver 3.3), mas significa também que
  **`saleableOnline` não é um sinal da janela de venda** — não o usar como
  gatilho.
- **A resposta do `POST /sale` traz `timestamp` com milissegundos**, na hora
  do servidor (ex: `2026-09-21T13:50:44.610+01:00`). Registar em cada compra
  o instante local de envio, o de receção e este `timestamp` (3.11).
- **Trocas gratuitas** até 30 minutos depois da venda (`exchange_limit`).

### 2.5 Regras da CP lidas da API

`GET /ticketing-api/sale/configuration/rules` e `GET /travel-api/rules`
(valores a 21/09/2026 — ler da API em vez de os fixar no código):
- `sale_deadline = 15` — prazo (minutos) para finalizar a venda
- `exchange_limit = 30` — troca gratuita depois da venda (minutos)
- `reissue_limit = 120` — prazo de revalidação relativo à partida (minutos)
- `calendar_limit = 60` — dias mostrados no calendário
- `max_tickets_qty = 9`, `min_tickets_qty = 1`, `dep_after_arr_limit = 15`

### 2.6 Outras rotas da API

**Endpoint `timetable` — confirmado em 21/09/2026** (testado a partir do RPi):
`GET /travel-api/trains/<comboio>/timetable/<AAAA-MM-DD>` responde 200
**sem `x-access-token`** (só as chaves da app: `X-Api-Key` de travel,
`x-cp-connect-id` e `x-cp-connect-secret`) e devolve `trainStops`: uma lista
com estação (`code` e `designation`), `departure`, `arrival` e plataforma.
Para um comboio que não circula na data devolve 400/404. O preflight de
CORS aceita o origin `https://pereirabmd.github.io` com esses headers, por
isso o browser pode chamá-lo diretamente. Usos, ambos já implementados:
1. **PWA**: ao escrever nº do comboio + data, confirma o percurso e preenche
   ou valida a hora de partida (as chaves ficam só no telemóvel, ver 3.7)
2. **Validação no RPi** (3.10.3, `scripts/timetable.py`): o Scheduler confronta
   cada perna com o horário oficial nos 3 dias antes da viagem e avisa se o
   comboio não circula, não faz o percurso ou parte a outra hora

Vistas no código do frontend do site, mas nunca exercitadas nem capturadas —
tratar como hipóteses até serem testadas:
- `DELETE /ticketing-api/sale/{id}` — cancelar uma venda pendente. Útil para
  o `--dry-run` (3.10.7) e para libertar lugares de vendas abandonadas.
- `PUT /ticketing-api/train-seats/{saleID}` — escolher/mudar de lugar (corpo
  não capturado). Só interessa se Bruno quiser preferência de lugar; exige
  novo HAR.
- `POST /ticketing-api/post-sale/refund`, `POST /post-sale/reissue` —
  reembolso e troca de bilhetes já confirmados.
- `GET /travel-api/stations/<código>/timetable/<data>` — horário de uma
  estação.

### 2.7 O que os HAR não mostram

- A resposta exata do `POST /sale` **antes** de a venda abrir, e quando um
  comboio está **esgotado** (ambos os HAR são compras bem-sucedidas). Sem
  isto não se classifica "ainda não abriu" versus "esgotado" (3.3.1).
- Se `GET /trips` lista vendas `PENDING` (só se viu a listar `CONFIRMED`).
- O e-ticket (PDF/QR) **não é guardado por esta automação** — fica
  disponível na App CP oficial para consulta.

---

## 3. Arquitetura

### 3.1 Autenticação desacoplada da compra
- `login()` isolado, grava `access_token`/`refresh_token` em `token.json`
  local (`chmod 600`); modo `--login-only` para testes
- **Um único login por disparo**, feito no pre-flight (T-5 min, 3.10.4), que
  serve também de validação das credenciais. O processo "quente" (3.3) reutiliza
  esses tokens em vez de fazer outro login
- O `access_token` dura 5 min: renovar por `refresh_token` pouco antes do
  disparo (~T-30 s) e, na sequência pós-venda, sempre que tenha mais de ~4 min
- A sessão morre ~30 min depois do login (2.1): nunca fazer o login mais de
  ~20 min antes do disparo, e não tentar "manter a sessão viva" durante
  horas

### 3.2 Scheduler — daemon que liga a Sheet aos disparos

Um **serviço systemd único** (`cp-scheduler.service`, `Restart=always`,
`WatchdogSec` com `sd_notify`, arranque com o sistema) substitui os jobs
individuais por disparo. **Não há `at`, nem `atq`, nem um timer por perna**:
o daemon calcula tudo a partir da config e do estado local, em ciclo:
1. A cada ~5 min lê a aba Config (tabela semanal, linhas com `Ativo = SIM`;
   **uma linha = uma viagem, sem par ida/volta** — decisão de Bruno, 22/23-09:
   mais do que uma viagem no mesmo dia é só mais do que uma linha com a mesma
   Data), valida (3.10.3) e grava a cache (3.10.2). Uma leitura falhada conta
   como "sem novidade", nunca como "config vazia"
2. Para cada viagem configurada, calcula o instante de disparo (T-24h da
   partida, timezone-aware — ver 3.4) e os marcos seguintes (pre-flight T-5
   min, processo "quente" ~T-3 min, 3.3)
3. Dorme até ao próximo marco (ou ao próximo poll da Sheet, o que vier
   primeiro). Uma alteração da config é apanhada no poll seguinte e a
   lista de disparos é recalculada — desativar ou mudar uma linha depois de
   já ter sido "agendada" não exige remover nada
4. No marco de lançamento, arranca o **processo "quente" como subprocesso
   separado** (3.3). O daemon **nunca** faz o `POST /sale` ele próprio: um
   erro ou bloqueio no processo quente não derruba o daemon nem as outras
   pernas. Lançar é idempotente: o daemon guarda no estado local que a perna
   já foi lançada e o lock por perna (3.3.1) impede duplicados
5. **Ao arrancar** (reboot, crash, `Restart=always`) recalcula do zero. Um
   disparo cujo instante já passou há menos que a tolerância configurada
   é lançado **de imediato** (decisão de Bruno, 22/09: chegar tarde nunca é
   motivo para desistir, só para tentar já), depois de verificar que não
   existe compra nem lock para essa perna (3.3.1). Só não se lança se a
   partida já passou, ou se havia uma venda em curso cujo prazo de conclusão
   (`sale_deadline`, 15 min) também já passou — aí notifica e a decisão é de
   Bruno (App CP)
6. **Saúde:** o watchdog do systemd reinicia um ciclo bloqueado (sem ele um
   daemon parado falharia em silêncio, contra 1.1). O heartbeat externo
   (healthchecks.io) fica na secção 6

O **lembrete de partida (T-30min)** não é criado pelo daemon — é criado
pelo próprio script de compra, imediatamente a seguir a uma compra
confirmada com sucesso (nesse momento já se sabe a hora exata de partida,
carruagem e lugar a incluir na notificação).

**Carruagem e lugar no lembrete (Bruno, 22/09):** o lembrete de partida leva-os no título e na mensagem. Vêm, por ordem, da resposta do `confirm`, do `seatData` guardado do `POST /sale` (é aí que o lugar sai, 2.4) e, em último recurso, do `GET /sales/{id}`. Se nenhuma fonte os der, a compra não falha: o lembrete segue a dizer onde ver (App CP).

**Vigilância do comboio nos últimos 30 min (Bruno, 22/09, `scripts/live_delay.py`):**
job de cron à parte, correndo **a cada minuto**, que sai logo se nenhum bilhete
da aba Bilhetes tiver partida nos próximos 30 minutos (barato de correr tão
frequentemente). Para cada bilhete nessa janela, consulta o horário oficial do
comboio (`GET /travel-api/trains/<nº>/timetable/<data>`, o mesmo endpoint de
2.6/3.10.3 — cada paragem traz `delay`, `platform`, `supression`, `ETA`, `ETD`)
na estação de embarque e compara com a última leitura, guardada em
`state/live_delay.json`. **Só notifica quando algo muda** — a primeira leitura
da janela fica só como referência, sem notificação. Uma supressão nova é
prioridade alta com etiqueta própria (`rotating_light`); as restantes mudanças
(atraso, cais, previsões) levam a etiqueta `warning`. Uma falha a consultar a
CP nunca é silenciosa, mas tem um intervalo de 10 min entre avisos para não
inundar durante uma indisponibilidade da CP.

Os lembretes de sábado (3.6) e a verificação diária do Passe (3.9) continuam
a ser jobs periódicos separados (cron, `/etc/cron.d/bilhetes-cp`).

### 3.2.1 Pedidos avulsos: retentativa leve, sem hotstart nem rajada (Bruno, 22-23/09)

Uma viagem da Config que esgota a validação/retry normal (3.3.1, 3.10) e
acaba `ESGOTADO`, `FALHOU` ou `AMBIGUO` — com a partida ainda no futuro — é
**espelhada automaticamente** para a aba **Pedidos** (4), por `hot_buy.py`
(`Buyer.terminate()`). Não há formulário manual: só viagens que a Config já
tentou aparecem ali. Cada linha permite:
- **"Tentar agora"** (PWA, escreve `Forcar=SIM`): força uma única tentativa.
- **Repetir de X em X minutos** (PWA, escreve `Retry=SIM` e
  `Intervalo_Minutos`): repetição automática, **por pedido** — não há um
  valor global único como numa primeira versão descartada; sem valor
  preenchido cai no `pedido_retry_interval_minutes` de reserva
  (`app_config.example.json`).
- Continua até a compra ficar `CONFIRMADO` ou o comboio partir. `AMBIGUO`
  nunca se relança sozinho (nem por `Retry` nem por `Forcar`) — fica só para
  leitura, como o estado AMBÍGUO em qualquer outro sítio (3.3.1).

**Deliberadamente leve, e deliberadamente NÃO o `Buyer`:** uma primeira
versão reaproveitava toda a máquina do `Buyer` (login antecipado/"hotstart",
rajada de ~12 min para esgotado) — pensada para a precisão ao segundo do
T-24h, onde cada tentativa é rara e cada segundo conta. Para um pedido
avulso isso é complexidade a mais, e teve um bug real em produção (`--leg`
só aceitava `ida`/`volta`, herdado de antes da Config deixar de ter esse
conceito). Por isso `scripts/hot_buy.py` tem uma classe à parte,
`PedidoAttempt`: login e compra logo (`leg.fire` de um pedido é sempre
"agora" — `Leg.is_request`), **sem** pre-flight nem espera por um instante
preciso, e **no máximo uma repetição por passo** — nunca a rajada do
esgotado nem os ~16 retries por passo da Config. Um "esgotado" ou uma
recusa terminam já a tentativa; a próxima oportunidade é o intervalo
agendado ou um novo "Tentar agora". Reaproveita só o `cp_ticket.py` e os
utilitários puros de lugar/notificação do `Buyer` (nunca o seu *state
machine*).

**`scripts/pedidos.py`** (cron a cada minuto, `/etc/cron.d/bilhetes-cp`,
**independente do `cp-scheduler.service`** de propósito — mesmo princípio
de isolamento da 3.2: um bug aqui nunca arrisca o caminho crítico do T-24h)
lê a aba Pedidos, decide quais linhas estão devidas (`Forcar`, ou `Retry`
com o intervalo já passado desde `Ultima_Tentativa` — a própria Sheet é a
fonte da última tentativa, não estado local, por isso sobrevive a um
reboot) e lança `hot_buy.py --leg pedidoN` como subprocesso, com o mesmo
lock por linha de sempre (nunca duas tentativas em curso para o mesmo
pedido). Tem um **disjuntor**: se o processo morrer sempre sem gravar nada
de novo no lock (ex.: outro bug de argumentos), para ao fim de
`MAX_LAUNCHES` (5) e avisa — nunca volta a ficar a repetir sem fim e em
silêncio, como aconteceu em produção a 22/09. Uma retentativa legítima
(mesmo falhada ou esgotada — o lock mostra que a tentativa fez algo real)
nunca conta para esse limite.

### 3.3 Processo "quente" por disparo (precisão ao segundo)

**Antes do disparo** (pre-flight, 3.10.4):
- Pesquisar o comboio com `journeys` (não exige login) e guardar no
  estado local o `serviceCode` (`code` + `designation`), as estações e a data.
  O `POST /sale` só precisa disto; **não se pesquisa no caminho crítico**.
- Ter o corpo e os cabeçalhos do `POST /sale` já construídos.

**Processo "quente"** (lançado pelo daemon de 3.2, ~T-3 min):
- Reutiliza o login do pre-flight (3.1) e aquece a ligação TCP/TLS a
  `api-gateway.cp.pt`. Os pedidos de aquecimento são baratos e
  espaçados, para a ligação não ser fechada por inatividade antes do
  disparo; ~10 s antes, confirmar que a ligação continua aberta.
- Calcula o instante exato com `time.monotonic()` + `sleep` (sono grosso,
  espera ativa nos últimos milissegundos), usando o relógio local
  **sincronizado por `chrony`** (3.4/3.10.1) como referência principal — o
  `Date` da CP serve só de cross-check pontual, não de fonte de calibração
  fina (ver 3.11)
- Dispara `POST /sale` **no instante-alvo**. Qualquer retry obedece
  exclusivamente à política de 3.3.1; nunca são enviados múltiplos
  `POST /sale` cegamente
- Guarda logo `saleID`, `reference` e lugar (`seatData`) no lock (3.3.1) e
  regista os três instantes de 2.4 (envio, receção, `timestamp` do servidor)
- Resto da sequência (passengers → client → fiscal → items) corre depois,
  sem pressa mas dentro dos 15 min de `sale_deadline`; **verificar
  `totalAmount == € 0,00` e `messages` vazio** e só então `confirm` (2.4)

### 3.3.1 Mecânica de agendamento
- **Um daemon, sem jobs por disparo** (3.2) — e **não** editar o crontab
  para os disparos. O daemon só precisa de lançar o processo "quente" cedo;
  a precisão ao segundo vem de dentro do processo, não do agendador.
- **Persistência a reboot.** O daemon arranca com o sistema e recalcula tudo
  do zero, por isso não há estado de agendamento que se possa perder. O
  estado que interessa (lock, `saleID`, fase da compra) vive no lock file
  (3.10.5). Dentro da tolerância de atraso (3.2), um disparo tardio é melhor
  do que nenhum, desde que o processo "quente" verifique primeiro que a
  partida ainda é futura e que a venda ainda não existe
- O processo "quente" termina no fim; o lock e o estado local impedem que o
  daemon o volte a lançar para a mesma perna
- **Proteção contra compra duplicada**: verificar no log/Sheet se já existe
  compra confirmada para aquela perna/data antes de tentar de novo (mesmo
  o site já prevenindo isto, fazer também deste lado). Só o `/confirm`
  efetiva a compra; uma venda `PENDING` duplicada não é um bilhete, mas
  bloqueia um lugar (2.4)
- **Política de retry no `POST /sale`**: a resposta a uma tentativa cai em
  categorias — **esgotado** (sem lugares, resposta clara da API — confirma-se
  com uma rajada curta antes de parar, ver abaixo); **erro conhecido não
  recuperável** (4xx claro — não repetir); **erro técnico transitório** (5xx,
  ou ligação falhou antes de enviar — retry seguro); **ainda não aberto** (ver
  abaixo); ou **AMBÍGUO** (timeout depois do request poder ter sido entregue —
  não repetir às cegas). Um retry ingénuo neste último caso pode criar uma
  segunda venda se a primeira resposta se perdeu na rede sem o pedido se ter
  perdido:
  1. Ligação falhou antes de enviar → retry seguro
  2. Servidor respondeu com erro conhecido → retry conforme o código
     (5xx tenta de novo, 4xx normalmente não)
  3. **Esgotado confirma-se com uma rajada antes de desistir** (Bruno, 22/09,
     tão persistente quanto ele já fazia à mão). O mesmo código (`WS:RES:116`,
     ou outro da mesma família — `114`, etc.) pode aparecer **com a rede
     condicionada**, sem ser esgotado a sério — e como o servidor respondeu
     sem criar venda, repetir é tão seguro como um erro técnico transitório.
     Esquema `sold_out_retry_delays_s` = `0, 0.5, 0.5, 0.5, 1×7, 2, 4, 8, 15,
     30×3, 60×4, 120×3` — 25 retentativas, 26 tentativas no total, **~12 min**.
     Como isto ultrapassa os 5 min do `access_token`, a rajada renova-o a
     meio (3.1) — sem isso, um 401 a meio seria lido como recusa não
     reconhecida e desistiria aos 15 s. Também para se o comboio já tiver
     partido, mesmo com retentativas por gastar. Se ao fim disso continuar
     esgotado, aplica-se o esquema normal (para, notifica, não insiste mais);
     a notificação final diz quantas tentativas confirmaram o esgotado
  4. **Ainda não aberto** — uma venda que abre mais tarde do que o previsto é
     tratada **na iteração seguinte**: repetir o `POST /sale` é seguro (nada foi
     criado) e desejável. Decisão de Bruno (22/09), antes da calibração: repete de
     0,25 em 0,25 s nos primeiros 20 s e de 2 em 2 s depois, até à venda abrir,
     esgotar, ao fim de 10 min (`not_open_retry_window_s`) ou à partida do
     comboio, avisando uma vez por ntfy. O formato real da resposta ainda é
     desconhecido (2.7), por isso a deteção é por padrões de texto (`NOT_OPEN_RX`)
     e "indisponível" conta como "ainda não aberto", nunca como esgotado: errar
     nesse sentido custa só uns pedidos, o contrário custa o bilhete. Uma recusa
     4xx **não reconhecida** também se repete, mas só durante 15 s
     (`unrecognized_4xx_retry_s`) e depois falha com a resposta completa no log,
     para se aprender o formato. Um estado AMBÍGUO nunca se repete
  5. Timeout depois do request poder ter sido entregue → estado
     **AMBÍGUO**: em teoria, verificar primeiro se a venda já foi criada
     antes de disparar outro `/sale`, via `GET
     /ticketing-api/trips/<email>?filter=FUTURE` (exige o cabeçalho
     `x-cp-client-registration-date`, 2.3). **⚠️ Não assumir que isto
     funciona** — só foi observado a listar vendas já **CONFIRMED**; nunca
     foi testado se também mostra vendas `PENDING` (criadas mas ainda não
     confirmadas), que é precisamente o cenário do estado AMBÍGUO. **Por
     verificar antes de confiar nisto**: criar uma venda de teste em modo
     `--dry-run`/isolado (3.10.7) e consultar este endpoint antes do
     `/confirm`, para ver se aparece. Se não aparecer (ou o comportamento
     for inconclusivo), a resolução do AMBÍGUO fica sem solução automática
     fiável — nesse caso, tratar como TODO em aberto: por agora, registar o
     caso AMBÍGUO no log/ntfy e não retentar automaticamente, deixando para
     confirmação manual (App CP) em vez de arriscar duplicar
- **Falha depois de a venda existir.** Se o `POST /sale` teve sucesso mas um
  passo seguinte falha, **repetir o passo** sobre o mesmo `saleID` (os `PUT`
  são idempotentes, 2.4), dentro dos 15 min de `sale_deadline`. Passado esse
  prazo a venda presume-se expirada: notificar e, se a partida ainda o
  permitir, tentar um novo `POST /sale`. `DELETE /sale/{id}` (2.6, por
  testar) serve para abandonar deliberadamente uma venda e libertar o lugar.
- **Lock local** (`flock`/lock file, nomeado por data+perna+nº de
  comboio): impede duas instâncias a tentar a mesma compra em simultâneo
  — protege contra o daemon a lançar duas vezes, execução manual acidental, ou
  dois processos concorrentes depois de um reboot estranho. O lock guarda
  também o `saleID` assim que a venda é criada, para permitir retomar
  (ver 3.10.6) em vez de repetir do zero.

### 3.4 Timezone e sincronização horária
- RPi configurado para `Europe/Lisbon` (`timedatectl set-timezone
  Europe/Lisbon`)
- Todo o cálculo de T-24h feito com datas **timezone-aware** (dia de
  calendário + mesma hora local), não offset fixo de 86400s — para não
  desfasar nas mudanças de hora (DST)
- **A confirmar:** não se sabe se a CP conta "24 horas decorridas" ou "a
  mesma hora do dia anterior". Só faz diferença em viagens **no dia da
  mudança de hora** (próxima: domingo 25/10/2026; depois 28/03/2027), onde
  as duas regras diferem em 1 h. Verificar antes desses dias e fixar nos
  testes unitários (3.10.7) a regra que se apurar.
- **Instalar e verificar o `chrony`** no RPi: confirmar que o serviço
  está ativo (`systemctl status chrony`) e sincronizado via NTP
  (`chronyc tracking`) — isto é a instalação/configuração de base; a
  **validação do offset em runtime**, antes de cada disparo, é feita à
  parte em 3.10.1

### 3.5 Camada de dados: Google Sheets

> **Substituída a 24/09/2026 (ver 9.10):** os dados vivem agora numa base SQLite no Pi (`bilhetes.db`). O texto
> abaixo descreve a Sheet, que continua a ser o formato de referência (as tabelas da BD têm as mesmas colunas)
> e o plano de recuo (`BILHETES_BACKEND=sheets`). Onde este documento diz "a Sheet", lê-se "os dados".
Em vez de API própria + Tailscale, os dados são partilhados via Google
Sheets:
- **PWA → Sheet**: escreve a config semanal via OAuth Google client-side
  no browser (mesmo padrão já usado noutra app do mesmo ecossistema —
  login Google no browser, sem backend)
- **RPi → Sheet**: lê periodicamente por polling (cron a cada ~5 min) via
  **service account** própria; escreve logs de execução e bilhetes
  confirmados de volta na Sheet
- **Formato dos dados.** Datas em ISO (`YYYY-MM-DD`) e horas em texto
  `HH:MM`. Se a PWA escrever com `valueInputOption=USER_ENTERED`, o Sheets
  converte `06:45` num valor de hora (uma fração de dia) e a leitura devolve
  um número ou uma string no formato do *locale* da folha. Por isso: a PWA
  grava com `RAW` (ou a coluna fica formatada como texto simples) e o RPi
  normaliza tudo o que lê (padding de `6:45` → `06:45`) e valida (3.10.3).
- Ver secção 4 para a estrutura exata da Sheet

### 3.6 Notificações (ntfy self-hosted)

**Estado: instalado e a funcionar** (21/09/2026). O ntfy foi instalado de
raiz no RPi via SSH com o **pacote nativo Debian `ntfy`** (serviço systemd
`ntfy`, utilizador de sistema `_ntfy`), mais simples e sem contornar o `ufw`,
como o Docker faria. As configurações aplicadas estão versionadas em
`deploy/` (ver 7.1 e `deploy/README.md`).

- ntfy escuta só em `127.0.0.1:8080`; o acesso de fora é feito pelo nginx
  (80/443), que faz proxy com websocket/SSE e sem buffering
- Acesso fora de casa: **DDNS existente** (Duck DNS,
  `https://bmdpereira.duckdns.org`, port forward de 80 e 443 já configurado
  no router), **não** Tailscale
- TLS: certificado Let's Encrypt próprio deste hostname, obtido com
  `certbot certonly --webroot` (sem editar nenhum `server{}` existente).
  Renovação automática pelo `certbot.timer`, com hook de reload do nginx
  guardado só neste certificado
- nginx: `server{}` novo em `sites-available/bmdpereira.duckdns.org` (+
  symlink em `sites-enabled/`), com `access_log` próprio; a configuração
  existente (`default`, `camilaebruno`) não foi alterada
- Autenticação: `auth-default-access: deny-all`; utilizador `bpereira` (role
  `user`) com leitura e escrita **só** no tópico `bpereira_cp`; anónimos sem
  acesso a nada
- fail2ban: jail novo `ntfy-auth` (5 falhas em 10 min → ban de 1 h; a LAN
  `192.168.68.0/24` é ignorada). O `nginx-http-auth` **não serve**: vigia
  autenticação basic do nginx, mas aqui quem autentica é o próprio ntfy, que
  responde 401/403 — por isso o filtro `ntfy-auth` lê esses códigos no log
  de acesso do vhost. O jail `sshd` existente ficou intacto
- DDNS: o `~/.duckdns/update.sh` existente passou a atualizar
  `domains=camilaebruno,bmdpereira` (alteração pontual; backup em
  `update.sh.bak-20260921`)
- Logs: `journalctl -u ntfy` (só INFO: arranque e estatísticas),
  `/var/log/nginx/ntfy.access.log` (pedidos, com IP e utilizador; rotação
  diária, 14 dias), `/var/log/fail2ban.log`
- Verificado de ponta a ponta (pelo hostname público e pela LAN): anónimo →
  403, password errada → 401, utilizador correto → 200, outro tópico → 403;
  a mensagem chega à app Android. O cliente móvel usa o servidor próprio
  (não o `ntfy.sh`); no Android não é preciso `upstream-base-url` (só
  relevante para iOS)

Eventos que disparam notificação:
- Resultado de cada compra (sucesso com referência, ou erro específico)
- Lembrete semanal de configuração: verificação independente a cada um
  dos 3 horários de sábado (manhã, meio-dia, noite — ver
  `app_config.example.json`), notificando sempre que, nesse momento, a
  config da semana seguinte ainda estiver em falta (as 3 verificações usam
  a mesma lógica)
- 30 min antes da partida de cada perna, incluindo carruagem e lugar
  (agendado dinamicamente logo após a compra ser confirmada)
- Passe Ferroviário Verde a expirar (3 dias e 1 dia antes)

**Prioridade das notificações — decidido: todas com popup.** Todas as
notificações do sistema (compra confirmada/falhada/esgotada/ambígua,
lembrete de partida, lembrete semanal de configuração, passe a expirar,
falhas de pre-flight, etc.) são enviadas com `Priority: high` (4). No
Android só as prioridades **≥ 4** fazem *popup* em banner sobre o ecrã; a
prioridade 3 (`default`) faz som mas só aparece na barra de notificações
(confirmado no telemóvel de Bruno em 21/09/2026). Regra de implementação:
todo o script que publique no ntfy define `Priority: high` explicitamente,
nunca deixa a prioridade por omissão; `high` chega, não é preciso `max`.

### 3.7 PWA
- Frontend estático, hospedado no GitHub Pages (mesmo ecossistema de PWAs
  já existente)
- Serve para: configurar a semana seguinte (origem, destino, comboio+hora
  ida/volta por dia), e consultar logs/bilhetes
- **Preenchimento automático a partir do timetable — implementado** (ver
  secção 2). Precisa das chaves da CP neste telemóvel: correr
  `python3 scripts/pwa_link.py` no computador do projeto e abrir o link uma vez
  no telemóvel (as chaves vão no fragmento `#...`, ficam no `localStorage` e
  nunca no código público). Sem elas a app funciona na mesma, sem confirmar
- **Corrigido (22/09): comboio de transbordo na PWA.** O preenchimento
  automático usava só o `timetable` do próprio comboio; um comboio que só é
  uma secção de uma viagem (ex.: o 511 só vai até Pampilhosa, liga ao 4609
  até Aveiro) mostrava um aviso de percurso em vez de preencher a hora. A
  PWA passa a confirmar pelo `journeys` (mesmas chaves, sem login) quando o
  `timetable` não cobre o trajeto todo — o mesmo fallback já usado no RPi
  (`scripts/timetable.py`, `check_via_journeys`) — e preenche normalmente,
  com a nota "(com transbordo)"
- **Dropdown de comboios já usados**: no campo do nº de comboio, oferecer
  um dropdown com os comboios que já apareceram nas configurações
  anteriores (histórico na Sheet — Config e/ou Bilhetes), cada opção com
  descrição tipo "524 — Aveiro → Lisboa Oriente", para Bruno escolher em
  vez de ter de se lembrar do número exato. Não substitui a escrita
  manual (podem surgir comboios novos), só facilita para os já
  recorrentes.
- Esquema de cores e princípios de design: ver secção 5
- **Ícone**: vai existir um PNG na pasta do projeto (ver secção 7,
  `assets/icon-source.png`, fornecido por Bruno) a usar como fonte única
  para o ícone da app e o favicon. O Claude Code gera a partir dele todos
  os tamanhos necessários (192x192 e 512x512 para o `manifest.webmanifest`,
  `apple-touch-icon` para iOS, e o `favicon.ico`/`favicon.png` para o
  separador do browser) — não desenhar um ícone novo, usar sempre esta
  fonte.
- **⚠️ Teclado do telemóvel não pode tapar o formulário** (falhou noutros
  projetos do mesmo ecossistema — atenção redobrada aqui). Quando o
  teclado virtual sobe (ao focar um campo de data/hora/nº de comboio), o
  formulário/campo ativo tem de continuar visível — não pode ficar
  escondido atrás do teclado. Tratar isto com viewport handling correto
  (ex: `visualViewport` API para ajustar o layout ao teclado, evitar
  `100vh` fixo que não reage ao teclado em iOS Safari, scroll automático
  do campo focado para a área visível). Testar explicitamente em
  Android e iOS antes de dar como resolvido.

**Sessão Google o mais persistente possível.** Ao abrir a app, se o token
guardado tiver expirado, tentar renovar em silêncio (prompt vazio,
`prompt: 'none'`, sem popup) *antes* de mostrar o ecrã de login — quem já
autorizou antes não deve precisar de tocar em nada. Ressalva conhecida:
depende de cookies de terceiros permitidos no browser; funciona bem em
Chrome Android, pode falhar por vezes em Safari/iOS (incluindo PWA
instalada) por causa do ITP. Persistência 100% garantida só seria possível
com um backend a gerir refresh token, o que este projeto não tem por
desenho (ver secção 3.5).

**Usar as bibliotecas estabelecidas, não reinventar à mão.** Para a
integração com Google (login + leitura/escrita no Sheet a partir do
browser), usar os pacotes/SDKs oficiais e as suas funcionalidades
completas em vez de chamadas fetch manuais a APIs REST cruas:
- **Google Identity Services** (`accounts.google.com/gsi/client`) para o
  login/token silencioso, em vez de gerir OAuth à mão
- **`gapi` client** (ou `googleapis`/`google-auth-library` do lado do RPi,
  em Python: `google-api-python-client` + `google-auth`) para chamadas ao
  Sheets/Drive, aproveitando batch requests, retry automático e
  tratamento de quota em vez de paginação/retry manuais
- Para o PWA em si (service worker, manifest, cache offline): **Workbox**
  em vez de escrever o service worker à mão — aproveitar as estratégias de
  cache já testadas (stale-while-revalidate para a UI, network-only para
  as chamadas ao Sheets)
Isto aplica-se em geral: antes de implementar algo à mão, verificar se a
biblioteca já em uso no projeto (ou uma estabelecida do ecossistema)
resolve isso de forma mais robusta.

### 3.8 Google Cloud / Service Account
- Já criada: `raspberrypi@bmdpereira-5a8f4.iam.gserviceaccount.com`
- Google Sheets API + Google Drive API já ativadas no projeto
  `bmdpereira-5a8f4`
- Acesso dado via **pasta do Drive partilhada** (não ficheiro a ficheiro),
  para cobrir também projetos futuros sem repartilhar cada Sheet novo
- Chave JSON da service account: ver `config/service-account.json` (não
  incluído no repositório — ver `.gitignore`)

### 3.9 Validade do Passe Ferroviário Verde
- Validade: 30 dias corridos, **contando o próprio dia do carregamento**: o
  passe expira a `Data_Ultima_Compra + 29` (comprado a 21/09/2026, válido até
  20/10/2026)
- Na Sheet isto é `Validade_Dias = 29` e `Data_Expira = Data_Ultima_Compra +
  Validade_Dias` (ver secção 4). A coluna `Data_Expira` é a fonte que o RPi e
  a PWA leem; se estiver vazia, calculam `Data_Ultima_Compra + Validade_Dias`
- Guardado na aba Config do Sheet (ver secção 4)
- Job diário calcula dias restantes e notifica via ntfy 3 dias e 1 dia
  antes de expirar
- **Uma viagem cuja data seja posterior a `Data_Expira` não pode ser
  agendada** (o desconto do Passe não se aplicaria e o total deixava de
  ser €0): a validação de 3.10.3 rejeita-a e notifica
- **Decidido**: `Data_Ultima_Compra` é atualizada manualmente — Bruno
  renova o passe via App CP oficial e depois escreve a nova data na Sheet;
  não há deteção automática pelo RPi (não existe endpoint de renovação
  mapeado na API)

### 3.10 Robustez adicional

**3.10.1 Sincronização do relógio — validação em runtime.** O `chrony`
(3.4) trata da sincronização em si, mas falta validar em cada disparo que
o relógio está mesmo sincronizado. No pre-flight (3.10.4), verificar
`chronyc tracking` e confirmar que o desvio está abaixo de ~100-200ms;
se não estiver, **não falhar em silêncio** — notificar via ntfy
imediatamente (liga ao princípio 1.1).

**3.10.2 Cache local da configuração da Sheet** (`config_cache.json`):
o RPi lê a Sheet a cada ~5 min (3.5), o que a torna uma dependência
operacional central. Uma falha temporária do Google (rede, quota, API
em baixo) **nunca deve apagar ou cancelar jobs já agendados**. Guardar a
última configuração válida + timestamp/revisão; o daemon só
recalcula a lista de disparos depois de uma leitura bem-sucedida e validada —
uma leitura falhada é tratada como "sem novidade", não como "config
vazia".

**3.10.3 Validação forte dos dados da Config, no RPi, não só no PWA.**
Nunca confiar só na validação do frontend. O RPi valida antes de agendar
qualquer job: formato de hora válido (não `25:90`), origem ≠ destino,
data não passada, **instante de disparo ainda futuro** (se a config chegar
depois de `partida − 24h` mas a partida ainda for futura, notificar
imediatamente em vez de agendar um disparo que já passou), **data da
viagem não posterior a `Data_Expira` do Passe** (3.9), sem linhas
duplicadas (mesma data+perna), `Ativo=SIM` sem comboio de volta
preenchido (se for suposto ida e volta), etc. Uma linha inválida gera
notificação de erro (1.1) e não é agendada — não falha em silêncio nem
trava o resto da config. Valida-se também, com o endpoint de timetable (2.6,
`scripts/timetable.py`), que o comboio corre nessa data e que a hora
configurada bate certo com o horário oficial.

**3.10.4 Pre-flight formal a T-5min** (antes do processo "quente" a
T-3min de 3.3): confirmar, por esta ordem, que: internet OK → DNS da CP
resolve → relógio sincronizado (3.10.1) → credenciais/config presentes
→ config local válida (cache de 3.10.2) → login CP bem-sucedido (o único
login do disparo, 3.1) → comboio presente no `journeys` da data, com
`serviceCode` guardado (3.3) → endpoint da CP alcançável (cross-check
grosseiro do `Date`, 3.11.1) → ntfy operacional (publicar uma mensagem de
teste e confirmar HTTP 2xx, não só assumir). Qualquer falha crítica aqui
dispara notificação imediata e o processo continua a tentar recuperar até
perto do disparo, em vez de desistir logo.

**3.10.5 Estado interno da compra**, guardado localmente (não na Sheet,
para não sobrecarregar as colunas — só o resultado final vai para a
aba Logs): `SCHEDULED → WARMING → SALE_CREATED → PASSENGERS_OK →
DISCOUNT_OK → CONFIRMED`, mais os estados terminais `SOLD_OUT`,
`FAILED`, `AMBIGUOUS`. Guardado no mesmo lock file de 3.3.1 (que já
guarda o `saleID`). Como os passos 3 a 7 são idempotentes (2.4), retomar
significa simplesmente repetir a sequência sobre o mesmo `saleID`.

**Confirmado com Bruno (22/09) o que isto significa na prática para a rajada
do esgotado (3.3.1):** a app (PWA, separador Registo) só mostra **uma linha
por perna**, escrita quando a rajada termina — sucesso, esgotado confirmado
ou falha — nunca uma linha por tentativa. As 26 tentativas individuais (HTTP,
`timestamp` da CP, atraso a cada uma) ficam só em `logs/hot_buy.log` no RPi,
acessível por SSH (`tail -f ~/bilhetes_cp/logs/hot_buy.log`); não há nada a
configurar para isto funcionar. Decidido: manter assim, sem resumo extra da
rajada na aba Logs.

**3.10.6 Recuperação de compra interrompida.** Se o RPi reiniciar depois
de já ter criado a venda (`saleID` obtido) mas antes do `/confirm`, o
processo, ao retomar, lê o estado local (3.10.5) e **continua essa venda
em vez de começar outra** — usa o `saleID` guardado para retomar a
sequência, desde que ainda dentro dos 15 min de `sale_deadline` (2.5). Fora
desse prazo aplica-se o descrito em 3.3.1.

**3.10.7 Modo `--dry-run` e testes**, obrigatório antes de ligar compras
automáticas a sério:
- `--dry-run`: corre todo o fluxo (daemon, login, leitura da Sheet,
  notificações, cálculo do instante exato, seleção do comboio) sem
  confirmar nenhum bilhete real. Um dry-run que crie a venda deve
  **cancelá-la a seguir** com `DELETE /sale/{id}` (2.6, a testar primeiro) —
  uma venda `PENDING` bloqueia um lugar durante 15 min. Testar num comboio
  e hora de pouca procura, para não roubar lugar disputado
- `--stop-after-sale-search` (ou equivalente): permite testar até à
  pesquisa/seleção sem sequer criar uma venda
- Testes unitários dedicados ao cálculo de T-24h com DST (é o ponto onde
  bugs são mais fáceis de introduzir, ver 3.4)

**3.10.8 Sanitização de logs.** O processo lida com Cartão de Cidadão,
NIF, telefone, email, tokens e número do passe. Nenhum destes deve
aparecer completo nos logs (ficheiro local ou aba Logs da Sheet) —
redação obrigatória de headers de autenticação e de campos sensíveis do
payload antes de qualquer log ser escrito.

**3.10.9 Rotação/retenção de logs** (`logrotate` ou retenção via
`journald`, conforme o mecanismo de logging escolhido): evitar que os
logs cresçam indefinidamente e encham o cartão SD do RPi.

**3.10.10 ntfy: política de acesso e healthcheck.** Para além da
autenticação já prevista (3.6), definir explicitamente
`auth-default-access: deny-all` (não depender só de o utilizador
existir) e incluir o teste de publicação + confirmação HTTP 2xx no
pre-flight (3.10.4), não assumir que está operacional.

### 3.11 Janela de abertura e calibração

A venda abre em `partida − 24h`. Em horas de procura elevada os lugares
esgotam em poucos segundos, por isso acertar no instante é o que decide se
há bilhete. Em horas de pouca procura ainda há lugar depois da abertura —
a compra do HAR de 21/09/2026 (feita a 23 h 37 min da partida) funcionou por
isso, e **não prova nada sobre a janela**.

O que os HAR ensinam, para não voltar a ser mal interpretado:
- `saleableOnline` **não reflete a janela**: no `journeys` de 22/09 veio
  `true` para todos os comboios, incluindo partidas a 31 h de distância. Não
  usar como sinal de que a venda já abriu.
- Uma compra anterior (20/09 às 06:58:23, para o comboio de 21/09 às 07:27,
  ou seja 24 h 29 min antes) foi feita pela app móvel (`configID 100`, o do
  site é `200`) e funcionou antes do T-24h. Pode ser pouca procura ou regras
  diferentes por canal — **medir**, não assumir.

- **Regra adotada em 22/09 (Bruno): a venda abre 24 h antes da partida do
  comboio na sua 1.ª estação**, não na de embarque. Encaixa na compra
  anterior: o comboio das 07:27 em Aveiro parte do Porto às 06:45, e as 06:58
  são 13 min depois de T-24h dessa partida. Por isso o instante de disparo
  (`Leg.fire`) e a data sugerida na PWA partem da hora da 1.ª estação
  (`timetable.apply_anchor`, com a data do comboio nessa estação: se passa a
  meia-noite antes do embarque, parte na véspera). Se a CP não devolver a
  1.ª estação, usa-se a hora da Config e há aviso. É uma hipótese consistente
  com o HAR, não uma prova: continua a medir-se (abaixo).

  **A hora da Config (`Hora_Ida`/`Hora_Volta`) é a da 1.ª estação** (Bruno, 22/09:
  o 520 configura-se às 06:45, a hora a que parte do Porto, embora Bruno embarque
  em Aveiro às 07:27). A data da Config é a do início da viagem nessa estação. A
  hora de embarque também se aceita. A hora de embarque real, lida do horário
  oficial, serve só para o lembrete de partida, para o bilhete e para saber se a
  viagem já passou; se a hora da Config não for nem a da 1.ª estação nem a de
  embarque, a linha é inválida (3.10.3).

**Por medir** (instrumentar nas primeiras compras reais e num modo de
calibração):
1. A resposta exata do `POST /sale` antes da abertura, e a de um comboio
   esgotado (2.7) — é o que permite classificar "ainda não abriu" (3.3.1).
2. Se a abertura acontece em `HH:MM:00.000`, com atraso ou com avanço, e se
   está ancorada ao relógio do servidor da CP ou ao do cliente.
3. Se o canal (site versus app) muda a janela.

Método: no modo de calibração, num comboio de pouca procura e com limpeza
por `DELETE /sale/{id}`, enviar tentativas espaçadas (ex: a partir de
`T-24h − 2 s`, de 100 em 100 ms) e registar cada resposta com milissegundos.
Nunca tentativas antes do instante calibrado em produção.

**Há forma real de medir a hora do servidor.** Todas as respostas de
`api-gateway.cp.pt` incluem o header HTTP `Date` (precisão ao segundo, GMT).
Além disso, a resposta do `POST /sale` traz `timestamp` **com milissegundos**
(2.4). Isto permite medir o desvio entre o relógio do RPi e o da CP, mas
com limites: a precisão do `Date` é ao segundo, e latência assimétrica,
jitter, caches/proxies intermédios e o instante em que o servidor gera a
resposta introduzem erro que nenhuma amostragem elimina. Por isso o `Date`
serve para cross-check grosseiro, e o `timestamp` para acumular, compra a
compra, uma estimativa do desvio (enviado/recebido/`timestamp`).

**3.11.1 `chrony` como referência principal; `Date` da CP só como
cross-check pontual.** Não se dispara com base numa "hora do servidor +
N ms" calibrada por amostragem contínua (a cada 50-100 ms desde T-5min): a
promessa de precisão não se sustenta e implicaria milhares de pedidos antes
de cada compra, com risco de rate limiting e de prejudicar a ligação que se
quer preservar para o pedido crítico. Abordagem:
1. **`chrony`, instalado/verificado (3.4) e validado antes de cada disparo
   (3.10.1), é a referência principal** para calcular o instante exato do
   `sleep()` antes do `POST /sale`
2. O `Date` serve só para um **cross-check pontual e barato**: um número
   pequeno de amostras (poucas unidades) durante o pre-flight (3.10.4),
   espaçadas no tempo, para apanhar um erro grosseiro (relógio da CP ou do
   RPi desviado por segundos/minutos/horas), não para afinar a
   milissegundos
3. Se o cross-check revelar um desvio grosseiro, notificar via ntfy (1.1) —
   não tentar "corrigir automaticamente" o instante do disparo, apenas
   alertar para investigação
4. A verificação empírica da janela (início desta secção) é uma atividade
   de calibração feita durante os testes, não um mecanismo a correr em cada
   disparo de produção

---

### 3.12 Ligação viva e retenção do lugar antes de T (24/09/2026 — medido no Pi)

Duas descobertas, ambas medidas com a CP a sério, mudaram o caminho crítico. Números e gráficos: `analise-bilhetes-timing`
(relatório de 24/09, fora do repositório).

**1. O «aquecimento» destruía a ligação.** `warm()` fazia `HEAD /`, que a CP responde com 404 e **`Connection: close`**: cada
aviso fechava a ligação e o `POST /sale` de T pagava DNS (~20 ms) + TCP (~35 ms) + TLS (~190 ms no Pi 3) **depois** de o
log dizer «enviado a T+1 ms» — o pedido só chegava a ~T+255 ms (venda registada pela CP a T+268…330 ms nas 3 compras a T;
T+37 ms na compra de 22/09 01:42, feita numa ligação que a pesquisa deixara viva). Correção: `warm()` usa o horário de um
comboio (`GET /travel-api/trains/{n}/timetable/{data}`, sem login, `Connection: Keep-Alive`, 26–90 ms) de 10 em 10 s; a
ligação aguenta parada pelo menos 120 s. Cada resposta regista agora «ligação NOVA/reutilizada» (`CPResponse.new_conn`).

**2. O lugar pode ser retido antes de T; o que abre a T é o desconto.** `POST /sale` (e passageiros/cliente/fiscal) são aceites
dias antes de T (venda pendente a 23,45 €, lugar atribuído); o **desconto do passe** (`PUT /sale/{id}/items`, `itemCode 302`)
é recusado antes de T (`500 SIV:DIS:I:302 «Sale item not available»`) e aceite a T (experiência de 24/09 22:30: recusado
até T−7 ms, aceite no pedido enviado a T+119 ms, total 0,00 €; a aceitação demorou ~1 s). `DELETE /sale/{id}` cancela a
venda (200 «CANCELLED»). Uma venda pendente de ensaio ainda estava PENDENTE 29 min depois (não expira aos 15 min).

**Novo fluxo do `Buyer`** (`hold_before_open`, por omissão ligado): login a T−5 min → pesquisa → **retenção**
(`hold_sale`, a `hold_lead_seconds`=600 s (10 min) de T, com `login_lead_minutes`=12 e `launch_lead_minutes`=13 para haver login e pré-voo antes; o token de 5 min é renovado durante a espera; repete de `hold_retry_interval_s`=15 s se esgotado; se não conseguir,
segue o fluxo antigo a T com a rajada do esgotado) → passageiro/cliente/fiscal → **corrida ao desconto**
(`race_discount`: de T−0,6 s a T+1,6 s de 0,1 em 0,1 s, depois 0,3 s até 48 pedidos, depois 1,5 s, até
`discount_window_s`=180 s; o PUT é idempotente) → confirmar. Arranque atrasado (já depois de T−3 s) não retém: fluxo normal.
Se o desconto nunca for aceite, ou o total não for 0 €, **a venda é cancelada** (lugar libertado) e há aviso; nunca se cancela
depois de uma confirmação incerta.

**Guarda do total corrigida.** `to_amount("€ 0,00")` dava `None` (só lia «0,00»), por isso o teste «total ≠ 0 → não confirmar»
nunca esteve ativo (as 4 compras reais registaram «totalAmount não encontrado…»). Agora lê «€ 23,45», «€ 1.234,56», etc.

**Limite de pedidos da CP:** HTTP 429 depois de ~120 pedidos em ~30 s (ensaio de 24/09). O orçamento acima cumpre-o; um 429 no
desconto espera `Retry-After` (≥ 1 s) e continua (desiste ao 9.º).

**Lugar ao corredor (24/09/2026).** O `POST /sale` atribui um lugar mas não deixa escolher; o site tem, porém, o mapa
(`GET /ticketing-api/train-seats/{venda}/trains/{n}`) e a mudança (`PUT /ticketing-api/train-seats/{venda}`, corpo descoberto pelas
mensagens de erro da CP: `{"originalSeats":[{trainNumber,carriageNumber,seatNumber}], "requestedSeats":[{…}]}`; lugar ocupado →
500 `WS:RES:120 «lugar ocupado»`). Funciona numa venda pendente **antes de T** (testado: 21/105 → 21/98 em 160 ms). Leitura do
mapa: cada carruagem tem `rows` = **linhas da disposição** (num 2+2, cinco: janela, corredor, **linha vazia = o corredor**, corredor,
janela); `statusCode` 0 = livre, 1/3 = ocupado/fora de venda, 2 = o lugar desta venda; `placeType` 1/2 = normais (7/9 = especiais,
não escolher). `cp_ticket.pick_aisle_seats` devolve os lugares livres ao corredor (mesma carruagem primeiro, depois os mais
perto). `Buyer.improve_seat` corre logo depois de reter o lugar (antes do passageiro/cliente/fiscal e do desconto), tenta até
`seat_change_max_tries`=4 lugares e **nunca faz falhar a compra** (qualquer erro fica em log e segue com o lugar dado). Só na
retenção antes de T (a T já não se perde tempo). `seat_preference: "aisle"` (por omissão) | `"none"` desliga. Decisão de
Bruno: seguir o comportamento e retirar se falhar por causa disto. Por confirmar: se o `confirm` e o bilhete refletem o lugar mudado
(o `confirm` devolve o lugar final e é esse que vai no lembrete; o lock fica com o lugar novo em `seat_changed`).

**Viagens passadas (25/09/2026).** `parse_config_rows` ignora em silêncio as linhas ativas com data passada (são histórico: cada linha é uma viagem única); os problemas reais das linhas futuras continuam a gerar o aviso «Linha da Config com problema».

**Ferramenta de ensaio:** `scripts/ensaio_compra.py` corre o `Buyer` verdadeiro contra a CP verdadeira, mas o «confirmar»
cancela a venda (nada é comprado); `--sem-ancora` inventa um T daqui a uns minutos para ensaiar a retenção.

**Ensaio a T real (25/09/2026, 521 de 26/09, T 06:30, sem comprar):** login 06:18 → lugar retido às **06:20:00** (T−10 min; 348 ms;
ligação reutilizada) → lugar mudado ao corredor 21/55 → 21/47 (250 ms) → desconto recusado nos 4 pedidos até T (60–69 ms cada)
→ **aceite no 5.º pedido, enviado a T+64 ms** (a resposta demorou 1067 ms; total 0 €) → venda cancelada. Fica provado: a retenção
de 10 min aguenta sem expirar, o desconto abre a T e o fluxo completo funciona numa ligação viva. O disparo real seguinte
(520 domingo 06:45, 731 domingo 17:30) confirma o `confirm` com o lugar mudado.

**Por medir:** se um comboio concorrido (o 731 à sexta) ainda tem lugar 10 min antes de T (ajustar `hold_lead_seconds`); se há disputa pelo desconto a T; a hora exata da abertura do desconto (T … T+1,2 s).


## 4. Estrutura do Google Sheets

> Desde 24/09/2026 as abas correspondem às tabelas `bilhetes_viagens` (Config semanal), `bilhetes_passe`
> (bloco do passe), `bilhetes_compras` (Bilhetes), `bilhetes_logs` (Logs) e `bilhetes_pedidos` (Pedidos) —
> ver 9.10. A Sheet ficou intacta, congelada nessa data.

Sheet: `https://docs.google.com/spreadsheets/d/1PNY134CrkxVhcpKHjTDZMYqYv3q-_oeDusJ-hgLRMBk`

Ver `config/sheet_schema.json` para a estrutura em formato máquina. Resumo:

### Aba "Config"
Bloco do Passe (topo, linhas 4-6):
| Data_Ultima_Compra | Validade_Dias | Data_Expira (fórmula) | Dias_Restantes (fórmula) |

`Validade_Dias = 29` (30 dias contando o dia do carregamento, 3.9),
`Data_Expira = Data_Ultima_Compra + Validade_Dias` e
`Dias_Restantes = Data_Expira − TODAY()`.

Tabela semanal (a partir da linha 11):
| Data | Origem | Destino | Comboio | Hora | Ativo |

**Uma linha = uma viagem, sem par ida/volta** (decisão de Bruno, 22/23-09):
mais do que uma viagem no mesmo dia é só mais do que uma linha com a mesma
Data — não há limite de 2. Datas em ISO e horas em texto `HH:MM` (ver 3.5).
`Hora` é a hora a que o comboio parte da sua 1.ª estação (3.11). A posição
fixa das linhas (bloco do passe nas linhas 4-6, tabela a partir da 11) torna
a leitura frágil a inserções de linhas: o RPi deve procurar os cabeçalhos
pelo nome em vez de confiar só nos números de linha.

### Aba "Logs"
| Timestamp | Tipo | Data_Viagem | Perna | Comboio | Status_HTTP | Resultado | Referencia | Mensagem_Erro |

`Perna` identifica a viagem que originou o registo: `vN` (linha N da
Config) ou `pedidoN` (linha N dos Pedidos) — já não `ida`/`volta`.

### Aba "Bilhetes"
| Data | Comboio | Origem | Destino | Hora_Partida | Carruagem | Lugar | Referencia |

### Aba "Pedidos" (3.2.1)
| Data | Origem | Destino | Comboio | Hora | Ativo | Retry | Intervalo_Minutos | Forcar | Estado | Ultima_Tentativa | Referencia | Mensagem |

Uma linha por viagem da Config que esgotou a validação/retry
(`ESGOTADO`/`FALHOU`/`AMBIGUO`) e cujo comboio ainda não partiu — espelhada
automaticamente pelo RPi, sem formulário manual. `Retry`/`Intervalo_Minutos`/
`Forcar` são escritos pela PWA; `Estado` (`PENDENTE` / `A_TENTAR` /
`CONFIRMADO` / `ESGOTADO` / `FALHOU` / `AMBIGUO`), `Ultima_Tentativa`,
`Referencia` e `Mensagem` só pelo RPi. `Intervalo_Minutos` é por pedido —
sem valor cai no `pedido_retry_interval_minutes` de reserva.

---

## 5. Design do PWA

### 5.1 Paleta (já decidida, seguir exatamente)

```
Primary:       #008542
Primary Dark:  #006B35
Primary Light: #E6F4EC
Primary Hover: #00773B
```
Aplicação: cabeçalho, botões principais, ícones ativos, barra inferior de
navegação, indicadores de bilhete válido, destaques/elementos selecionados.

```
Background principal:   #F7F8F7
Background de cartões:  #FFFFFF
Background secundário:  #F0F2F1
Divisores/bordas:       #E1E5E3
```
Fundos claros, estilo app de transportes moderna. Cartões de bilhetes
brancos, sombra subtil, cantos arredondados.

```
Texto principal:    #1F2925
Texto secundário:   #66736D
Texto desativado:   #9AA49F
Texto sobre verde:  #FFFFFF
```

### 5.2 Fugir dos padrões genéricos de "feito por IA"

A paleta e os fundos já estão decididos acima — mas tudo o resto
(tipografia, estrutura, componentes, micro-interações) deve evitar os
tiques que denunciam um design genérico gerado por IA, nomeadamente:
- Cartões todos idênticos, todos com o mesmo border-radius e a mesma
  sombra cinza suave (`rgba(0,0,0,.1)`) por baixo, independentemente da
  hierarquia — dar propósito a cada card, não aplicar um kit uniforme
- Eyebrow labels em ALL CAPS tracked-out acima de cada secção/título
- Marcadores numerados (01 / 02 / 03) decorativos, a não ser que o
  conteúdo seja mesmo sequencial (ex: os passos de uma viagem)
- Realçar só uma palavra do título a bold/itálico/cor diferente
- Animações genéricas de fade-and-slide-up em cada secção e hover em
  todos os cards — preferir um único momento de transição bem pensado
  (ex: confirmação de compra, drag entre dias da semana) a efeitos
  espalhados por toda a interface
- Tipografia default (ex: Inter em tudo) sem escolha deliberada — escolher
  1-2 tipos de letra com um papel claro cada (display vs. corpo), e um
  type scale com pesos/espaçamento intencionais
- Uma única fonte monospace para "parecer dados técnicos" onde não faz
  sentido (isto é uma app de bilhetes de comboio, não um dashboard de
  engenharia)

Em vez disso: partir do que esta app realmente é — bilhetes de comboio,
horários, cartões que parecem bilhetes físicos, hierarquia clara entre
"o que precisa de ação agora" (configurar a semana, próximo comboio) e
"histórico" (logs, bilhetes passados). Deixar a paleta verde-CP já
definida ser o ponto alto, e manter tudo à volta discreto e disciplinado.

---

## 6. Deixado para depois dos testes (de propósito)

- Hardening/encriptação do RPi: SSH por chave, firewall, LUKS, etc.
- Heartbeat/watchdog via **healthchecks.io**: o RPi faz ping periódico a
  esse serviço externo gratuito, que avisa (email ou webhook para ntfy) se
  o ping falhar/faltar — deteta o RPi estar em baixo, o que um simples
  ping ntfy não consegue sozinho (só avisa quando está vivo, não quando
  morre)

---

## 7. Estrutura de ficheiros: repositório vs. Raspberry Pi

O repositório (onde o Claude Code trabalha e commita) e o RPi (onde o
Claude Code também atua, via SSH) são máquinas diferentes — mas o
Claude Code trata da ponte entre as duas: edita/commita no repositório
**e** aplica as alterações no RPi por SSH, na mesma sessão de trabalho.
Não há passo manual de "correr um script de instalação" — isso é o
próprio Claude Code que faz, via SSH, respeitando sempre a regra de
não-destrutividade acima.

### 7.1 Repositório (`bilhetes_cp/`, GitHub)

```
bilhetes_cp/
├── PLANO_FINAL.md               este documento (a referência; PLANO.md e PLANO_UP.md são histórico)
├── .env.example                 modelo de variáveis de ambiente
├── .gitignore
├── index.html                   PWA (HTML, CSS e JS numa página, como as outras apps)
├── manifest.webmanifest
├── sw.js                        service worker (Workbox)
├── assets/                      ícones derivados de icon-source.png (192, 512, maskable, iOS, favicon)
├── config/
│   ├── sheet_schema.json        estrutura das abas do Sheet
│   └── app_config.example.json  configuração não-secreta (estações, parâmetros); a PWA também a lê
├── scripts/
│   ├── common.py                T-24h/DST, validação da Config, sanitização, notify, cache, lock/estado
│   ├── cp_ticket.py             cliente da API da CP (login, pesquisa, venda), sem retries escondidos
│   ├── hot_buy.py               processo de compra de uma perna (3.3, 3.3.1, 3.10)
│   ├── scheduler.py             daemon: lê a Config e lança os processos quentes (3.2)
│   ├── timetable.py             valida a Config contra o horário oficial (secção 2)
│   ├── pre_flight.py            checklist de T-5min (3.10.4); também corre à mão
│   ├── config_reminder.py       lembretes de sábado (3.6)
│   ├── pass_expiry_check.py     validade do Passe (3.9)
│   ├── heartbeat.py             ping ao healthchecks.io (secção 6); inativo até haver URL no .env
│   ├── live_delay.py            vigilância do comboio nos últimos 30 min (3.2), a cada minuto
│   ├── pedidos.py               fila de pedidos avulsos (3.2.1), a cada minuto, à parte do daemon
│   └── pwa_link.py              link que liga a PWA às chaves da CP
├── tests/                       unittest (209) e teste da PWA em Chromium real (pwa_smoke.mjs, 57 verificações)
└── deploy/                      configs aplicadas no RPi, sem segredos (ver deploy/README.md); inclui o `cp-scheduler.service` do daemon
```

Tudo aqui é código/config genérico e sem segredos. **Atenção:** o repositório
é **público** e as GitHub Pages servem tudo o que estiver commitado — este
plano e o `deploy/` incluídos. Nunca commitar HAR, `.env`, tokens nem a chave
da service account (ver secção 8).

### 7.2 No Raspberry Pi (aplicado pelo Claude Code via SSH)

```
bilhetes_cp/                     (cópia funcional no RPi, mantida pelo Claude Code via SSH)
├── ... (o mesmo conteúdo do repositório)
├── .env                         [TU preenches os valores que faltam, ex. CP_PASSWORD] nunca no git
├── config/
│   └── service-account.json     [TU colocas, ou o Claude Code copia se já lho deres] nunca no git
├── token.json                   [gerado em runtime pelo login()]
├── config_cache.json            [gerado em runtime, última config válida da Sheet — 3.10.2]
└── locks/
    └── <data>-<perna>.lock      [gerado em runtime, por compra em curso — 3.3.1/3.10.5/3.10.6]
```

Fora desta pasta, no sistema do RPi — o Claude Code configura via SSH,
sempre de forma aditiva (ver regra de não-destrutividade):
- **nginx**: novo `server{}` para `bmdpereira`/ntfy, sem tocar na
  configuração existente de outros sites (ex. `camilaebruno`) — **feito**
- **fail2ban**: novo jail para o nginx/ntfy, sem alterar jails já ativos — **feito** (`ntfy-auth`)
- **systemd**: novo unit do daemon do scheduler (`cp-scheduler.service`), sem
  tocar em serviços já a correr; os lembretes e a validade do passe correm por
  cron
- **updater DDNS**: estender o script existente para também atualizar
  `bmdpereira`, mantendo a atualização de `camilaebruno` intacta — **feito**
- **ntfy**: instalado como pacote nativo Debian (serviço systemd `ntfy`),
  não em Docker — ver 3.6

Legenda: sem marcação = já existe; `[A GERAR]` = para o Claude Code
construir/aplicar; `[TU preenches]`/`[TU colocas]` = fornecido por ti
diretamente (segredos como `.env`/`service-account.json` nunca vão para o
git; o `icon-source.png` não é segredo, mas também não é gerado — é um
ficheiro que forneces).

---

## 8. Notas de segurança

- O `token.json`, a chave da service account e o `.env` são tão sensíveis
  como passwords — `chmod 600`, nunca no git
- **Ficheiros HAR contêm tudo**: password em texto simples no POST do login,
  tokens, Cartão de Cidadão, NIF, telefone e email. Nunca os commitar
  (acrescentar `*.har` ao `.gitignore`), guardá-los só o tempo necessário e
  apagá-los depois de usados
- Todas as passwords/segredos partilhados durante o planeamento desta
  automação (ntfy incluído) são temporários/de teste — devem ser trocados
  antes de produção a sério
- Antes deste projeto começar a correr a sério, considerar terminar
  sessões ativas / mudar a password da conta CP, já que HAR de teste
  anteriores expuseram tokens de sessão reais e a password
- Logs (ficheiro local e aba Logs da Sheet) nunca guardam Cartão de
  Cidadão, NIF, telefone, email, tokens ou nº do passe completos —
  ver 3.10.8; `logrotate`/retenção configurados para não encher o
  cartão SD — ver 3.10.9
- O cliente usa a API interna do site cp.pt, sem acordo com a CP: uso
  exclusivamente pessoal, na conta e no passe de Bruno. Os Termos da
  Bilheteira Online podem proibir automação; a CP pode mudar ou bloquear a
  API a qualquer momento (ver 1.1 — o pre-flight deteta isso cedo)

---

## 9. Estado da implementação (22/09/2026)

### 9.1 Conformidade com este plano
Os 12 pontos de alinhamento que este plano pedia, com o estado real
(✅ feito e testado, ⚠️ parcial, ⏳ pendente por decisão ou por falta de dados):

| # | Ponto | Estado |
|---|---|---|
| 1 | Scheduler como daemon (3.2, 3.3.1) | ✅ `cp-scheduler.service` (`Type=notify`, `Restart=always`, `WatchdogSec=300`, `KillMode=process`); timers `cp-warm-*` e entrada do cron removidos; o cron mantém lembretes, passe e heartbeat |
| 2 | Um só login por disparo (3.1) | ✅ login a T-5 min logo a seguir ao pre-flight, renovado por `refresh_token` quando o token tem mais de 4 min (também na sequência pós-venda); `token.json` (chmod 600) com o mais recente; `cp_ticket.py --login-only` |
| 3 | Total €0 e `messages` antes do `confirm` (2.4) | ✅ não confirma se `totalAmount ≠ 0`; mensagens de nível erro falham o passo, avisos ficam no log |
| 4 | Transbordos (2.2, 7.3) | ✅ uma entrada de `outwardTrip` por secção, escolhida pelo nº do comboio; sem estações no horário, falha em vez de adivinhar; testado com `[4656, 510]` |
| 5 | `serviceCode` antes do disparo (3.3) | ⚠️ obtido no arranque (`journeys`, sem login) e nunca no caminho crítico; o corpo do `POST /sale` é montado no instante (microssegundos), não pré-construído |
| 6 | `fiscalAddress` e `x-cp-client-registration-date` (2.3, 2.4) | ⚠️ `fiscalAddress` opcional via `CP_FISCAL_ADDRESS` (JSON do HAR); o cabeçalho de registo só serve o `GET /trips`, que ainda não é usado |
| 7 | Três instantes da compra (2.4, 3.11) | ✅ envio, receção e `timestamp` do servidor (mais o `Date`), na aba Logs |
| 8 | `--dry-run` com `DELETE /sale/{id}` (3.10.7) | ⏳ pendente: o `DELETE` nunca foi testado e exige criar uma venda real em `PENDING`. Feito o nível sem risco: `hot_buy.py --search-only` pesquisa, mostra o que compraria e pára |
| 9 | Formato de horas e validade (3.5, 3.9, 4) | ✅ PWA grava `RAW` (ISO e `HH:MM`), RPi normaliza. Validade: 30 dias contando o dia do carregamento, `Validade_Dias = 29` (regra corrigida em 22/09 segundo a Sheet de Bruno) |
| 10 | Validações novas (3.9, 3.10.3) | ✅ disparo já passado com partida futura (aviso, sem compra), viagem depois do passe (rejeitada), e a Config tem de bater com o horário oficial (`timetable`, com `journeys` como segunda fonte) |
| 11 | Regra do DST (3.4) | ⏳ a confirmar com a CP antes de 25/10/2026; os testes fixam "mesma hora do dia anterior" |
| 12 | `*.har` no `.gitignore`; `CP_FISCAL_ADDRESS` no `.env.example` | ✅ |
| — | Disparo ancorado à partida do comboio na 1.ª estação (3.11, regra de 22/09) | ✅ `Leg.fire` no RPi e data sugerida na PWA; sem a 1.ª estação usa a Config e avisa |
| — | Hora da Config = partida na 1.ª estação (3.11, 4; decisão de 22/09) | ✅ o validador aceita a hora da 1.ª estação ou a de embarque; a de embarque real (`Leg.board`) serve para o lembrete, o bilhete e "viagem já passou"; a PWA preenche e confirma com a da 1.ª estação |
| — | Lembrete de partida com carruagem e lugar (3.2; decisão de 22/09) | ✅ no título e na mensagem; fontes: `confirm`, `seatData` do `POST /sale`, `GET /sales/{id}`; sem lugar em lado nenhum a compra não falha e o lembrete diz onde ver |
| — | Compra atrasada inicia-se de imediato (3.2, decisão de 22/09) | ✅ sem tolerância nem "conhecida antes": qualquer disparo já passado com a partida ainda futura é lançado já; só recusa se a partida já passou ou se uma venda em curso excedeu os 15 min |
| — | "Ainda não aberto" repete-se na iteração seguinte (3.3.1, decisão de 22/09) | ✅ janela de 10 min, fase rápida e lenta; os padrões de texto são um palpite até haver respostas reais |
| — | Rajada de retentativa do esgotado mais agressiva, ~12 min (3.10, decisão de 22/09) | ✅ `sold_out_retry_delays_s` (25 valores, 0 a 120 s) segue o esquema manual que Bruno já fazia; reautentica a meio se o token passar dos 4 min |
| — | Config sem par ida/volta, N viagens por dia (3.2, 4, decisão de 22/23-09) | ✅ uma linha = uma viagem; editor da PWA com lista dinâmica de viagens por dia (duplicar/remover); `leg.leg` passa a `vN` (id estável pela linha) |
| — | Pedidos avulsos: forçar/repetir leve, sem hotstart nem rajada (3.2.1, decisão de 22/23-09) | ✅ `PedidoAttempt` (nova, não reaproveita o `Buyer`), no máximo 1 repetição por passo; `scripts/pedidos.py` (cron, disjuntor contra relançamentos sem progresso); PWA com aba própria (Tentar agora, intervalo por pedido); **por verificar com uma compra real** (9.4) |

Fora da lista de 9.8, por secção:
- **3.3.1** categoria "ainda não aberto": ✅ repete-se (decisão de 22/09); só os padrões de texto que a detetam são um palpite (ver 9.4).
- **3.10.4** pre-flight: ✅. O login é feito a seguir, pelo processo quente, no mesmo minuto.
- **3.11** instrumentação: ✅. Modo de calibração com `DELETE`: ⏳ (ver 8).
- **Secção 6**: heartbeat ✅ em código (`heartbeat.py`, cron de 5 em 5 min), inativo até haver URL no `.env`; hardening: `ufw` ativo e `unattended-upgrades` instalado, mas o SSH ainda aceita password (⏳ decisão de Bruno).
- **ntfy**: ✅ o RPi autentica-se com um token revogável (`NTFY_TOKEN`), com a password de reserva.
- **Pontos de design por decidir** (nenhum implementado): **AMBÍGUO** — repetir o `/sale`
  em vez de pedir confirmação manual (depende de testar se a CP aceita uma 2.ª venda para
  o mesmo passageiro/comboio; por agora o código **não repete**); **estado por perna na
  Sheet** (agendado/comprado/falhou), com notificação quando uma semana fica agendada;
  **service account restrita só a esta Sheet**, em vez da pasta partilhada; **ecrã de
  consentimento OAuth** da PWA em modo "Testing" — por confirmar se expira ao fim de 7 dias.

### 9.2 O que está feito e a correr no RPi
- ntfy, nginx, TLS, fail2ban, DDNS (3.6 e `deploy/README.md`).
- `chrony` (substituiu o `systemd-timesyncd`, que o `chrony` remove) e fuso `Europe/Lisbon`.
- Código em `~/bilhetes_cp` (venv Python). Daemon `cp-scheduler.service`; cron novo em
  `/etc/cron.d/bilhetes-cp` (não toca no crontab do utilizador) para os lembretes de
  sábado, a validade do passe, o heartbeat, a vigilância do comboio a cada minuto
  (`live_delay.py`, 3.2) e a fila de pedidos avulsos a cada minuto (`pedidos.py`, 3.2.1);
  `logrotate` para o `cron.log`.
- Aba "Pedidos" criada na Sheet real (cabeçalho na linha 4, 4).
- PWA completa (Semana, Bilhetes, Pedidos, Registo, editor da semana, definições).

### 9.3 Verificado com o mundo real
Login na CP a partir do RPi; `journeys` sem login; `timetable` sem login e com CORS
aberto ao origin do GitHub Pages; leitura da Sheet real (cabeçalhos por nome); ntfy de
ponta a ponta com token e com entrega agendada; pre-flight; daemon a correr sob o
systemd; validação da Config contra o horário oficial (apanhou a linha de exemplo e, por um
erro meu, a hora da 1.ª estação: corrigido, ver 3.11); `--search-only` e simulação da
Config real (520 às 06:45 com embarque às 07:27; 731 às 17:30 com embarque às 17:39) com a
CP real, sem lançar nada; `pedidos.py --plan-only` contra a aba Pedidos real, sem lançar nada.
209 testes unitários (também no RPi, com a rede bloqueada) e 57 verificações da
PWA em Chromium (offline, teclado, 360 px, manifest, service worker, N viagens/dia, aba Pedidos).

### 9.4 Por verificar — nunca exercitado contra a CP real
- **`POST /sale` e os passos seguintes**: cobertos por testes com uma CP falsa; nenhuma
  compra real foi feita por esta automação.
- **Respostas de esgotado, "ainda não abriu" e erro** (2.7): `classify_sale_response`
  assume padrões de texto em `messages`; os primeiros registos reais dirão se ajusta. Até lá
  uma recusa não reconhecida repete-se 15 s antes de falhar (3.3.1).
- **`totalAmount` e `seatData`**: procurados de forma tolerante.
- **Janela de abertura T-24h (3.11)**: por medir com as primeiras compras reais.
- **Recuperação de reboot a meio de uma compra** (3.10.6): testada com estados
  simulados, não com um reboot verdadeiro. **`DELETE /sale/{id}`** e **`GET /trips`
  com `PENDING`**: por testar.
- **`PedidoAttempt` (3.2.1)**: coberta por testes com uma CP falsa; a canalização está toda
  no ar (cron a correr, aba Pedidos criada) mas nenhuma linha de Pedidos foi ainda
  lançada nem confirmada contra a CP real — a primeira vez que Bruno usar "Tentar agora"
  ou uma viagem da Config esgotar é o primeiro teste real do caminho completo.

### 9.5 Ações que dependem de Bruno
1. **Pôr as viagens reais na Config** (ver 9.6), com `Ativo = SIM` e **antes** da hora do
   disparo: uma linha que chega depois só gera o aviso de configuração tardia.
2. Opcional: abrir no telemóvel o link de `python3 scripts/pwa_link.py`, para a PWA
   confirmar horários.
3. Apagar `~/Transferências/cp.pt.zip` (o HAR tem a password da CP, tokens, CC e NIF) e o
   `anexos.zip`, depois de usados.
4. Criar um check em healthchecks.io (período 5 min, tolerância 10 min) e pôr o URL em
   `HEALTHCHECKS_PING_URL` no `.env` do RPi.
5. Decidir sobre o SSH só por chave (hoje aceita password), sobre repetir o `/sale` num
   estado AMBÍGUO, sobre um estado por perna na Sheet e sobre restringir a service
   account só a esta Sheet (pontos de design por decidir, listados em 9.1).
6. Autorizar (ou não) um teste real de `DELETE /sale/{id}`, que cria uma venda `PENDING`
   num comboio de pouca procura e a cancela: desbloqueia o `--dry-run` e a calibração.

### 9.6 Cuidado: compras reais
Qualquer linha `Ativo = SIM` que bata certo com o horário oficial e cujo disparo ainda
esteja por chegar **gera uma compra real** no instante T-24h.

- **Estado a 22/09 às 01:10:** a Config não tem nenhuma linha de viagem (só a nota de
  exemplo), por isso o daemon tem 0 pernas no plano e não compra nada. A linha de
  exemplo antiga (28/09, comboios 524 e 531 "fictícios") foi rejeitada por 3.10.3 e
  entretanto removida.
- **Caso de referência (520):** Bruno configurou 23/09, comboio 520 às 06:45 (hora a que
  parte do Porto) com embarque em Aveiro às 07:27, e a volta 731 às 17:30 (embarque
  17:39). O plano simulado dá disparo a 22/09 às 06:45 e 17:30 (arranque do processo às
  06:39 e 17:24) e lembrete de partida às 06:57 e 17:09.
- Um disparo que passou há menos de 10 min só se recupera se a perna já era conhecida
  antes da hora (reboot); uma linha que chega tarde só gera um aviso.
- Se a venda abrir mais tarde do que o previsto, repete-se (3.3.1); um estado AMBÍGUO
  nunca se repete.

### 9.7 Decisões e desvios ao plano
- ntfy como pacote nativo, não Docker (3.6). Todas as notificações com `Priority: high`.
- O lembrete T-30min é uma mensagem agendada no próprio ntfy (`delay`), que sobrevive a
  reboots; não há timer para isso.
- Dia só de ida: comboio e hora da volta ambos vazios. Volta a meio é erro.
- O pre-flight publica uma mensagem de estado real em vez de uma mensagem de teste.
- Vigilância do comboio nos últimos 30 min antes da partida (`live_delay.py`), a cada
  minuto, notificando só quando algo muda (atraso, cais, supressão).
- PWA com `gapi client`, Google Identity Services e Workbox, como o plano manda; as chaves
  da CP entram por um link (`scripts/pwa_link.py`), nunca no código público. Ícones
  gerados de `assets/icon-source.png` (o ícone do comboio com bilhete) sobre o verde
  claro da paleta; o service worker sobe de versão sempre que a página muda (`VERSION`).
- Config sem par ida/volta: uma linha = uma viagem (3.2, 4). O editor da PWA mantém o
  interruptor "Ativo" por dia (aplica-se a todas as viagens desse dia ao guardar), mas
  cada viagem tem a sua própria origem/destino/comboio/hora, com "Duplicar" a substituir
  o antigo botão de trocar ida/volta.
- Pedidos avulsos redesenhados como uma tentativa leve (`PedidoAttempt`), deliberadamente
  separada do `Buyer`: sem hotstart, no máximo 1 repetição por passo, intervalo de
  repetição por pedido (3.2.1) — uma primeira versão que reaproveitava o `Buyer` teve um
  bug real em produção e foi revertida.

**Decisões de Bruno nesta implementação** (22/09), todas já refletidas nas secções indicadas:
1. `PLANO_FINAL.md` é o plano de referência; `PLANO.md` fica como histórico (secção 9, cabeçalho).
2. O passe vale 30 dias contando o dia do carregamento: expira a compra + 29 (3.9, 4).
3. A venda abre 24 h antes da partida do comboio na sua 1.ª estação (3.11).
4. A hora da Config é a da 1.ª estação; a de embarque também se aceita (3.11, 4).
5. Uma venda que abre tarde repete-se na iteração seguinte (3.3.1).
6. O lembrete de partida leva carruagem e lugar (3.2).
7. Todas as notificações levam popup (`Priority: high`) (3.6).
8. O `--dry-run` fica adiado até se testar o `DELETE /sale/{id}` (3.10.7).
9. O esgotado confirma-se com uma rajada de ~12 min antes de desistir, igual ao que Bruno
   já fazia à mão (3.10) — só na Config; os Pedidos nunca fazem rajada (3.2.1).
10. Config sem par ida/volta: N viagens por dia, cada uma na sua linha (3.2, 4).
11. Pedidos avulsos: sem hotstart, no máximo 1 repetição por passo, intervalo por pedido —
    não reaproveita o `Buyer` (3.2.1).

### 9.8 Operação
```
# testes (a partir de bilhetes_cp/)
python3 -m unittest discover -s tests
CHROMIUM=/snap/bin/chromium node tests/pwa_smoke.mjs

# no RPi (ssh casamento-pi; cd ~/bilhetes_cp)
systemctl status cp-scheduler                       # o daemon; journalctl -u cp-scheduler -f
.venv/bin/python scripts/scheduler.py --plan-only   # o plano, sem lançar nem notificar
.venv/bin/python scripts/hot_buy.py --date AAAA-MM-DD --leg vN --search-only   # o que compraria, sem venda
.venv/bin/python scripts/pre_flight.py --no-ntfy    # diagnóstico do RPi
.venv/bin/python scripts/pedidos.py --plan-only     # a fila de pedidos avulsos, sem lançar (3.2.1)
tail -f logs/scheduler.log logs/hot_buy.log logs/pedidos.log   # logs
sudo fail2ban-client set ntfy-auth unbanip <IP>     # desbanir
```

### 9.9 Parâmetros ajustáveis (`config/app_config.example.json`, chave `purchase`)
| Parâmetro | Valor | O que faz |
|---|---|---|
| `launch_lead_minutes` | 6 | antecedência com que o daemon arranca o processo de compra |
| `login_lead_minutes` | 5 | quando o processo faz o login (T-5 min, 3.1) |
| `fire_offset_ms` | 0 | ajuste fino do instante de disparo, para a calibração (3.11) |
| `max_sale_attempts` | 3 | tentativas do `POST /sale` em erro técnico (5xx, ligação) |
| `step_retry_delays_s` | 0,5 … 120 | esperas ao repetir um passo pós-venda (somam ~12 min, dentro dos 15 do `sale_deadline`) |
| `not_open_retry_window_s` | 600 | quanto tempo se repete uma venda "ainda não aberta" |
| `not_open_fast_phase_s` / `_fast_interval_s` / `_slow_interval_s` | 20 / 0,25 / 2 | ritmo dessas repetições |
| `unrecognized_4xx_retry_s` | 15 | quanto tempo se repete uma recusa não reconhecida |
| `sold_out_retry_delays_s` | 0 … 120 (25 valores) | rajada de ~12 min antes de confirmar esgotado — só na Config; os Pedidos nunca fazem rajada (3.2.1) |
| `timetable_check_days` | 14 | a partir de quantos dias antes se valida a Config e se descobre a 1.ª estação |
| `clock_max_offset_ms` / `cp_date_max_offset_s` | 150 / 3 | limites do pre-flight (3.10.1, 3.11.1) |
| `pedido_retry_interval_minutes` | 15 | intervalo de reserva quando um pedido não define o seu próprio `Intervalo_Minutos` (3.2.1) |

### 9.10 Migração para SQLite (24/09/2026)

A Sheet deixou de ser a base de dados. Os dados vivem em **`bilhetes.db`** (SQLite, WAL) no Pi — uma base
**separada** da das outras apps (`dados.db`), para a compra com hora certa nunca esperar por um lock de outra
app. Esquema em `dados/migrations_bilhetes/001_bilhetes.sql` (tabelas `bilhetes_viagens`, `bilhetes_passe`,
`bilhetes_compras`, `bilhetes_logs`, `bilhetes_pedidos`); ficheiro em `~/dados/data/bilhetes.db`.

**Quem acede e como**
- **O Pi (scheduler, hot_buy, pedidos.py, live_delay, pass_expiry_check, config_reminder)** lê e escreve em SQL
  direto — `scripts/store.py` (`SqliteStore`), que tem **exatamente a interface da `SheetsClient`** e devolve os
  dados nos mesmos formatos, por isso a lógica de compra, os validadores e as protecções não mudaram. Escolhe-se com
  `BILHETES_BACKEND` no `.env` (`common.get_store()`): **`sqlite`** desde 24/09/2026; **`sheets`** volta à Sheet
  (**recuo**: mudar a variável e `sudo systemctl restart cp-scheduler`; os bilhetes/registos criados depois da
  troca só existem na BD). Uma falha da BD é tratada como uma falha da Sheet: nunca interrompe uma compra
  (`Buyer.sheet()`), avisa, e o lock por perna continua a proteger de compras duplicadas.
- **A PWA** fala com a API do `dados/` (`https://bmdpereira.duckdns.org/dados-api/bilhetes/…`, token Google, ACL
  `ACL_BILHETES`), já não com o Google Sheets nem com o `gapi`: só pede `openid email`. Ver `dados/apps/bilhetes.py`.

**O que teve de mudar de propósito (e porquê)**
- **O id de uma viagem/pedido É o número em `vN`/`pedidoN`** (parte da chave do lock de compra). Na Sheet era a
  linha, que se renumerava ao guardar a semana; agora é o `id` da BD (`AUTOINCREMENT`, nunca reutilizado). As
  viagens importadas **mantêm o número da linha** (`v12` continua `v12`, senão os locks e estados existentes deixavam
  de bater); as novas começam em **100**. `parse_config_rows`/`parse_request_rows` aceitam o id explícito numa coluna
  extra (`_row_id`) e `pedidos.py` procura a linha do pedido **por id** (`request_row`), nunca por posição.
- **Guardar a semana na PWA preserva os ids** (`PUT /bilhetes/semana`): compara por (data, comboio, hora) — o que
  continua existe com o mesmo id (só se atualizam origem/destino/ativo), o que sumiu apaga-se, o novo ganha id.
  Reescrever tudo, como na Sheet, mudava o id a meio de um disparo e arriscava uma compra dupla.
- **A data do passe** deixou de ser uma célula editada à mão: a PWA tem um campo em Definições
  (`PUT /bilhetes/passe`); a expiração e os dias que faltam calculam-se (`data + validade_dias`, 29 = 30 dias).
- **Registos**: a aba Registo da PWA precisa deles, por isso `bilhetes_logs` fica na BD — só eventos com resultado
  (como na Sheet); as tentativas da rajada continuam só em `logs/hot_buy.log`.

**Importação e verificação** (`dados/importar_bilhetes.py`, corre no Pi): 1 viagem (id 12), 3 bilhetes, 0 pedidos,
18 registos, passe de 21/09 (+29 = 20/10, igual à fórmula da folha). Verificado contra os valores **formatados** da
Sheet (bilhetes e registos idênticos) e, o que mais interessa, **o Pi alimentado pela BD vê o mesmo plano**
(`scheduler --plan-only`, `pedidos --plan-only`, `live_delay`, `pass_expiry_check` iguais); com viagens futuras
numa **cópia** da BD, o plano sai certo (disparos às 17:30/06:45 ancorados à 1.ª estação, ids v100/v101).
Testes: 226 no `bilhetes_cp` (12 de `store`, 5 de fluxos reais de compra a escrever numa BD verdadeira) mais os da
API, do importador e do backup em `dados/`, e a PWA em Chromium (58 verificações + um percurso completo PWA↔API↔BD↔Pi).

**Backup**: o backup diário (`dados/backup.py`) cobre `bilhetes.db` (`bilhetes.sql.age`, no mesmo repositório
privado). **Cuidado ao alterar o esquema**: as tabelas são lidas/escritas por dois lados (o Pi em SQL, a PWA pela
API) — mudar uma coluna exige mudar `store.py` e `apps/bilhetes.py` juntos, e uma migração nova (nunca editar uma
já aplicada).
