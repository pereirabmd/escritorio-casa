# Automação de bilhetes CP — Passe Ferroviário Verde

> **Nota:** existe `PLANO_FINAL.md`, revisão posterior deste documento (com o HAR de 21/09/2026). Em caso de conflito prevalece o `PLANO_FINAL.md`; ver `PLANO_UP.md` para as diferenças.

Automação para comprar bilhetes CP (Comboios de Portugal) ida e volta, a €0
via desconto do Passe Ferroviário Verde, correndo num Raspberry Pi. Os
bilhetes esgotam tipicamente em 2-3 segundos, por isso o timing exato da
compra é o requisito mais crítico de todo o projeto.

Este documento é o hand-off completo para continuar a implementação com o
Claude Code.

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
  partida** (ex: partida segunda 06:45 → disparo domingo 06:45). Ida e volta
  têm disparos separados, porque têm horas de partida diferentes.
- O **ID do comboio tem prioridade sobre a hora** na escolha da viagem a
  comprar — a hora configurada serve principalmente para calcular o
  instante do disparo, não para procurar por aproximação.
- Todos os sábados, um lembrete (ntfy) pede a configuração da semana
  seguinte via PWA. Se a configuração continuar em falta, há lembretes
  extra ao meio-dia e à noite do mesmo sábado.

### 1.1 Princípio transversal: nada falha em silêncio

**Nada deve passar despercebido.** Qualquer falha, erro, ou situação
anómala em qualquer componente tem de gerar sinal visível (notificação
ntfy e/ou linha de log) — nunca falhar calada e só se descobrir depois de
já ser tarde (ex: o comboio já ter partido sem bilhete). Isto aplica-se a
todo o sistema, não só à compra em si. Mecanismos já previstos no plano
que concretizam este princípio — usar como checklist ao implementar cada
componente, e não adicionar nenhum código com falha silenciosa:
- Compra: distinguir esgotado de erro técnico, sempre notificar o
  resultado (3.3.1), ler `messages` mesmo com HTTP 200 (secção 2)
- Agendamento: Scheduler deteta e recria jobs perdidos num reboot (3.3.1)
- Configuração em falta: 3 lembretes escalados ao sábado (3.6)
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

Sequência confirmada a partir de um HAR capturado manualmente:

1. **Login** — Keycloak / OAuth2 com PKCE, em `login.cp.pt` (realm
   `cpclients`, client_id `websitecp`). Login direto com email+password
   (a conta em causa não usa Google/Apple/Chave Móvel Digital).
   - `access_token`: válido 5 minutos
   - `refresh_token`: válido ~30 minutos
2. `POST /travel-api/journeys` — pesquisa de horários (usar só na véspera
   para confirmar que o comboio pretendido ainda está disponível; **nunca
   no caminho crítico da compra**)
3. `POST /ticketing-api/sale` — cria a venda com o comboio exato (nº de
   comboio, estações, `serviceCode`). **Este é o pedido crítico ao
   segundo** — depois deste, há ~15 min de folga para completar o resto.
4. `PUT /ticketing-api/sale/{id}/passengers` — dados do passageiro (nome,
   Cartão de Cidadão)
5. `PUT /ticketing-api/sale/{id}/client` — email, telemóvel, nome
6. `PUT /ticketing-api/sale/{id}/fiscal` — NIF para efeitos fiscais
7. `PUT /ticketing-api/sale/{id}/items` — aplica o desconto do Passe
   Ferroviário Verde: `{"itemCode": "302", "type": "DISCOUNT", "inputData":
   "<número do passe>"}` → zera o `totalAmount`
8. `PUT /ticketing-api/sale/{id}/confirm` — confirma a compra (sem
   pagamento, porque o total já é €0). Resposta inclui `seatData` com
   `carriageNumber` e `seatNumber`.

Headers usados nas chamadas à API (`api-gateway.cp.pt`): `x-access-token`
(o access_token OAuth), `X-Api-Key` (varia por serviço), `x-cp-connect-id`
e `x-cp-connect-secret` (constantes embutidas no frontend, não são
segredos pessoais), `x-cp-client-id` (o email do cliente, em alguns
endpoints).

**Sempre verificar o campo `messages` da resposta**, não confiar só no
status HTTP — pode vir 200 com avisos/erros parciais.

O e-ticket em si (PDF/QR) **não é guardado por esta automação** — fica
disponível na App CP oficial para consulta.

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

---

## 3. Arquitetura

### 3.1 Autenticação desacoplada da compra
- `login()` isolado, grava `access_token`/`refresh_token` em `token.json`
  local (`chmod 600`)
- Modo `--login-only` corre ~3 min antes de cada disparo
- Se o processo "quente" ficar à espera mais de ~5 min, fazer refresh do
  token antes do disparo (o access_token não dura mais que isso)

### 3.2 Scheduler — liga a Sheet aos jobs de agendamento

Job periódico — mesma cadência do polling da Sheet, ~5 min via cron — que:
1. Lê a aba Config (tabela semanal, linhas com `Ativo = SIM`)
2. Para cada perna (ida/volta) de cada dia configurado, calcula o instante
   de disparo (T-24h da partida, timezone-aware — ver 3.4)
3. Verifica se já existe um job agendado para essa perna/data (evitar
   duplicados — ex: nomear os jobs de forma previsível, tipo
   `cp-warm-<data>-<perna>`, e consultar `atq`/`systemctl list-timers`
   antes de criar um novo)
4. Cria o job em falta (via `at` ou `systemd-run --on-calendar=...`,
   transiente) para o instante calculado, apontando para o processo
   "quente" (3.3)
5. Se uma linha da Config for desativada ou alterada depois de já ter sido
   agendada, o Scheduler também remove/atualiza o job correspondente

O **lembrete de partida (T-30min)** não é criado pelo Scheduler — é criado
pelo próprio script de compra, imediatamente a seguir a uma compra
confirmada com sucesso (nesse momento já se sabe a hora exata de partida,
carruagem e lugar a incluir na notificação).

### 3.3 Processo "quente" por disparo (precisão ao segundo)
- Arranca uns minutos antes do instante exato (T-24h da partida)
- Já com login feito, aquece a ligação TCP/TLS a `api-gateway.cp.pt`
- Calcula o instante exato com `time.monotonic()` + `sleep`, usando o
  relógio local **sincronizado por `chrony`** (3.4/3.10.1) como
  referência principal — o `Date` da CP serve só de cross-check pontual,
  não de fonte de calibração fina (ver 3.11.1, corrigido)
- Dispara `POST /sale` **no instante-alvo, uma única vez**. Qualquer
  retry obedece exclusivamente à política de 3.3.1; nunca são enviados
  múltiplos `POST /sale` cegamente
- Resto da sequência (passengers/client/fiscal/items/confirm) corre depois,
  sem pressa

### 3.3.1 Mecânica de agendamento
- Usar `at` ou timer systemd transiente — **não** editar crontab
  manualmente. O agendador só precisa de lançar o processo "quente" cedo;
  a precisão ao segundo vem de dentro do processo, não do agendador.
- Jobs **persistentes a reboot** (`Persistent=true` em timers systemd, ou
  equivalente no spool do `at`) — importante também para o Scheduler
  conseguir recriar jobs perdidos num reboot, comparando o que devia
  existir (Config) com o que existe de facto (`atq`/`list-timers`)
- Job remove-se a si próprio depois de correr
- **Proteção contra compra duplicada**: verificar no log/Sheet se já existe
  compra confirmada para aquela perna/data antes de tentar de novo (mesmo
  o site já prevenindo isto, fazer também deste lado)
- **Política de retry no `POST /sale` — refinada (revisão externa)**: a
  resposta a uma tentativa cai em 4 categorias — **esgotado** (sem
  lugares, resposta clara da API — nada a fazer, notificar e parar);
  **erro conhecido não recuperável** (4xx claro — não repetir); **erro
  técnico transitório** (5xx, ou ligação falhou antes de enviar — retry
  seguro); ou **AMBÍGUO** (timeout depois do request poder ter sido
  entregue — não repetir às cegas, ver abaixo). Um retry ingénuo neste
  último caso pode criar uma segunda venda se a primeira resposta se
  perdeu na rede sem o pedido se ter perdido:
  1. Ligação falhou antes de enviar → retry seguro
  2. Servidor respondeu com erro conhecido → retry conforme o código
     (5xx tenta de novo, 4xx normalmente não)
  3. Timeout depois do request poder ter sido entregue → estado
     **AMBÍGUO**: em teoria, verificar primeiro se a venda já foi criada
     antes de disparar outro `/sale`, via `GET
     /ticketing-api/trips/<email>?filter=FUTURE`. **⚠️ Não assumir que
     isto funciona** — este endpoint aparece no HAR original, mas só foi
     observado a listar vendas já **CONFIRMED**; nunca foi testado se
     também mostra vendas `PENDING` (criadas mas ainda não confirmadas),
     que é precisamente o cenário do estado AMBÍGUO. **Por verificar
     antes de confiar nisto**: criar uma venda de teste em modo
     `--dry-run`/isolado e consultar este endpoint antes do `/confirm`,
     para ver se aparece. Se não aparecer (ou o comportamento for
     inconclusivo), a resolução do AMBÍGUO fica sem solução automática
     fiável — nesse caso, tratar como TODO em aberto: por agora, registar
     o caso AMBÍGUO no log/ntfy e não retentar automaticamente,
     deixando para confirmação manual (App CP) em vez de arriscar duplicar
- **Lock local** (`flock`/lock file, nomeado por data+perna+nº de
  comboio): impede duas instâncias a tentar a mesma compra em simultâneo
  — protege contra scheduler duplicado, execução manual acidental, ou
  duas units concorrentes depois de um reboot estranho. O lock guarda
  também o `saleID` assim que a venda é criada, para permitir retomar
  (ver 3.10.3) em vez de repetir do zero.

### 3.4 Timezone e sincronização horária
- RPi configurado para `Europe/Lisbon` (`timedatectl set-timezone
  Europe/Lisbon`)
- Todo o cálculo de T-24h feito com datas **timezone-aware** (dia de
  calendário + mesma hora local), não offset fixo de 86400s — para não
  desfasar nas mudanças de hora (DST)
- **Instalar e verificar o `chrony`** no RPi: confirmar que o serviço
  está ativo (`systemctl status chrony`) e sincronizado via NTP
  (`chronyc tracking`) — isto é a instalação/configuração de base; a
  **validação do offset em runtime**, antes de cada disparo, é feita à
  parte em 3.10.1

### 3.5 Camada de dados: Google Sheets
Em vez de API própria + Tailscale, os dados são partilhados via Google
Sheets:
- **PWA → Sheet**: escreve a config semanal via OAuth Google client-side
  no browser (mesmo padrão já usado noutra app do mesmo ecossistema —
  login Google no browser, sem backend)
- **RPi → Sheet**: lê periodicamente por polling (cron a cada ~5 min) via
  **service account** própria; escreve logs de execução e bilhetes
  confirmados de volta na Sheet
- Ver secção 4 para a estrutura exata da Sheet

### 3.6 Notificações (ntfy self-hosted)

**Estado: instalado e a funcionar** (21/09/2026). O plano assumia que o ntfy
já corria em Docker, mas no RPi não havia ntfy nem Docker: foi instalado de
raiz via SSH com o **pacote nativo Debian `ntfy`** (serviço systemd `ntfy`,
utilizador de sistema `_ntfy`), mais simples e sem contornar o `ufw`, como o
Docker faria. As configurações aplicadas estão versionadas em `deploy/`
(ver 7.1 e `deploy/README.md`).

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
  `192.168.68.0/24` é ignorada). O `nginx-http-auth` sugerido inicialmente
  **não serve**: vigia autenticação basic do nginx, mas aqui quem autentica é
  o próprio ntfy, que responde 401/403 — por isso o filtro `ntfy-auth` lê
  esses códigos no log de acesso do vhost. O jail `sshd` existente ficou
  intacto
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
  config da semana seguinte ainda estiver em falta (não é "só a primeira
  incondicional + escalada" — as 3 verificações usam a mesma lógica)
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

**Sessão Google o mais persistente possível.** Mesmo padrão já identificado
noutra app do ecossistema: ao abrir a app, se o token guardado tiver
expirado, tentar renovar em silêncio (prompt vazio, `prompt: 'none'`, sem
popup) *antes* de mostrar o ecrã de login — quem já autorizou antes não
deve precisar de tocar em nada. Ressalva conhecida: depende de cookies de
terceiros permitidos no browser; funciona bem em Chrome Android, pode
falhar por vezes em Safari/iOS (incluindo PWA instalada) por causa do ITP.
Persistência 100% garantida só seria possível com um backend a gerir
refresh token, o que este projeto não tem por desenho (ver secção 3.5).

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
- Validade: 30 dias corridos
- Dados reais atuais: comprado 21/09/2026, válido até 20/10/2026
- Guardado na aba Config do Sheet (ver secção 4)
- Job diário calcula dias restantes e notifica via ntfy 3 dias e 1 dia
  antes de expirar
- **Decidido**: `Data_Ultima_Compra` é atualizada manualmente — Bruno
  renova o passe via App CP oficial e depois escreve a nova data na Sheet;
  não há deteção automática pelo RPi (não existe endpoint de renovação
  mapeado na API)

### 3.10 Robustez adicional (revisão externa)

Conjunto de pontos identificados numa revisão externa ao plano, todos
adotados:

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
última configuração válida + timestamp/revisão; o Scheduler só
atualiza/remove timers depois de uma leitura bem-sucedida e validada —
uma leitura falhada é tratada como "sem novidade", não como "config
vazia".

**3.10.3 Validação forte dos dados da Config, no RPi, não só no PWA.**
Nunca confiar só na validação do frontend. O RPi valida antes de agendar
qualquer job: formato de hora válido (não `25:90`), origem ≠ destino,
data não passada, sem linhas duplicadas (mesma data+perna), `Ativo=SIM`
sem comboio de volta preenchido (se for suposto ida e volta), etc. Uma
linha inválida gera notificação de erro (1.1) e não é agendada — não
falha em silêncio nem trava o resto da config.

**3.10.4 Pre-flight formal a T-5min** (antes do processo "quente" a
T-3min de 3.1): confirmar, por esta ordem, que: internet OK → DNS da CP
resolve → relógio sincronizado (3.10.1) → credenciais/config presentes
→ config local válida (cache de 3.10.2) → login CP bem-sucedido →
endpoint da CP alcançável → ntfy operacional (publicar uma mensagem de
teste e confirmar HTTP 2xx, não só assumir). Qualquer falha crítica
aqui dispara notificação imediata e o processo continua a tentar
recuperar até perto do disparo, em vez de desistir logo.

**3.10.5 Estado interno da compra**, guardado localmente (não na Sheet,
para não sobrecarregar as colunas — só o resultado final vai para a
aba Logs): `SCHEDULED → WARMING → SALE_CREATED → PASSENGERS_OK →
DISCOUNT_OK → CONFIRMED`, mais os estados terminais `SOLD_OUT`,
`FAILED`, `AMBIGUOUS`. Guardado no mesmo lock file de 3.3.1 (que já
guarda o `saleID`).

**3.10.6 Recuperação de compra interrompida.** Se o RPi reiniciar depois
de já ter criado a venda (`saleID` obtido) mas antes do `/confirm`, o
processo, ao retomar, lê o estado local (3.10.5) e **continua essa venda
em vez de começar outra** — usa o `saleID` guardado para retomar a
sequência a partir do passo em que ficou.

**3.10.7 Modo `--dry-run` e testes**, obrigatório antes de ligar compras
automáticas a sério:
- `--dry-run`: corre todo o fluxo (scheduler, login, leitura da Sheet,
  notificações, cálculo do instante exato, seleção do comboio) sem
  confirmar nenhum bilhete real
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

### 3.11 Verificação empírica da janela real de abertura da CP

O sistema assume que a disponibilidade de compra abre exatamente em
`partida − 24h`. Esta é uma suposição fundamental de que tudo depende, e
nunca foi verificada empiricamente — só documentada nos Termos da CP
("60 dias de antecedência", sem precisão ao segundo). Antes de confiar
o disparo a este pressuposto: instrumentar timestamps com milissegundos
de cada pedido/resposta durante os testes iniciais, e usar essas
observações para determinar se a janela abre exatamente à hora
(`06:45:00.000`), com atraso, ou com avanço, e se está ancorada ao
relógio do cliente ou do servidor da CP. Só depois de calibrado desta
forma o disparo deve deixar de ser "uma suposição" e passar a ser um
valor medido.

**Há forma real de medir a hora do servidor: confirmado no HAR.** Todas
as respostas de `api-gateway.cp.pt` incluem o header HTTP `Date` padrão
(precisão ao segundo, GMT) — confirmado em várias chamadas do HAR
original (ex: `Date: Mon, 21 Sep 2026 12:50:10 GMT`). Isto permite, sem
inventar nenhum mecanismo novo:
- Medir o desvio entre o relógio do RPi e o relógio do servidor da CP,
  comparando o `Date` da resposta com o instante local de receção
  (compensando a latência de rede, ex: usando o ponto médio entre
  pedido e resposta)
- Durante os testes de calibração da janela (acima), usar este `Date`
  para saber se a abertura está ancorada ao relógio do servidor e não
  ao do cliente
- Nota: precisão ao segundo, não ao milissegundo. Um único `Date`, ou
  mesmo vários, **não permite calibrar com confiança a milissegundos** —
  latência assimétrica, jitter, caches/proxies intermédios, e o instante
  em que o servidor gera o header introduzem erro que a técnica de
  deteção da transição de segundo não elimina. Corrigido abaixo (3.11.1):
  o `Date` fica reservado a cross-check grosseiro, `chrony` continua a
  ser a referência principal para o instante do disparo.

**3.11.1 `chrony` como referência principal; `Date` da CP só como
cross-check pontual (não como calibração fina).** Versão anterior deste
plano propunha disparar com base numa "hora do servidor + 10ms",
calibrada por amostragem contínua a cada 50-100ms desde T-5min — **isto
foi revisto e descartado**: prometia uma precisão que o mecanismo não
sustenta, e implicava 3.000-6.000 pedidos antes de cada compra, com
risco de rate limiting e de prejudicar precisamente a ligação que se
quer preservar para o pedido crítico. Abordagem correta:
1. **`chrony`, já instalado/verificado (3.4) e validado antes de cada
   disparo (3.10.1), é a referência principal** para calcular o instante
   exato do `sleep()` antes do `POST /sale` — não o `Date` da CP
2. O `Date` serve só para um **cross-check pontual e barato**: um número
   pequeno de amostras (poucas unidades, não centenas/milhares) durante
   o pre-flight (3.10.4), espaçadas no tempo (não em rajada), para
   confirmar que a hora do servidor da CP está grosseiramente alinhada
   com a hora local — o objetivo é apanhar um erro grosseiro (relógio da
   CP ou do RPi desviado por segundos/minutos/horas), não afinar a
   milissegundos
3. Se o cross-check revelar um desvio grosseiro, notificar via ntfy
   (1.1) — não tentar "corrigir automaticamente" o instante do disparo
   com base nisso, apenas alertar para investigação
4. A verificação empírica da janela (início desta secção) continua
   válida como forma de perceber, com instrumentação nos testes
   iniciais, se a abertura está ancorada ao relógio do servidor ou do
   cliente — mas isso é uma atividade de calibração feita durante os
   testes, não um mecanismo a correr em cada disparo de produção

---

## 4. Estrutura do Google Sheets

Sheet: `https://docs.google.com/spreadsheets/d/1PNY134CrkxVhcpKHjTDZMYqYv3q-_oeDusJ-hgLRMBk`

Ver `config/sheet_schema.json` para a estrutura em formato máquina. Resumo:

### Aba "Config"
Bloco do Passe (topo, linhas 4-6):
| Data_Ultima_Compra | Validade_Dias | Data_Expira (fórmula) | Dias_Restantes (fórmula) |

Tabela semanal (a partir da linha 11):
| Data | Origem | Destino | Comboio_Ida | Hora_Ida | Comboio_Volta | Hora_Volta | Ativo |

### Aba "Logs"
| Timestamp | Tipo | Data_Viagem | Perna | Comboio | Status_HTTP | Resultado | Referencia | Mensagem_Erro |

### Aba "Bilhetes"
| Data | Comboio | Origem | Destino | Hora_Partida | Carruagem | Lugar | Referencia |

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
├── PLANO.md                     este documento
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
│   ├── scheduler.py             lê a Config, cria/remove timers (3.2)
│   ├── timetable.py             valida a Config contra o horário oficial (secção 2)
│   ├── pre_flight.py            checklist de T-5min (3.10.4); também corre à mão
│   ├── config_reminder.py       lembretes de sábado (3.6)
│   ├── pass_expiry_check.py     validade do Passe (3.9)
│   └── pwa_link.py              link que liga a PWA às chaves da CP
├── tests/                       unittest (87) e teste da PWA em Chromium real (pwa_smoke.mjs)
└── deploy/                      configs aplicadas no RPi, sem segredos (ver deploy/README.md)
```

Tudo aqui é código/config genérico e sem segredos — seguro para git
público ou privado.

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
- **systemd**: novos units/timers (scheduler, lembretes, validade do
  passe), sem tocar em serviços já a correr
- **updater DDNS**: estender o script existente para também atualizar
  `bmdpereira`, mantendo a atualização de `camilaebruno` intacta — **feito**
- **ntfy**: instalado como pacote nativo Debian (serviço systemd `ntfy`),
  não em Docker — ver 3.6

Legenda: sem marcação = já entregue nesta conversa; `[A GERAR]` = para o
Claude Code construir/aplicar; `[TU preenches]`/`[TU colocas]` = fornecido
por ti diretamente (segredos como `.env`/`service-account.json` nunca vão
para o git; o `icon-source.png` não é segredo, mas também não é gerado —
é um ficheiro que forneces).

## 8. Notas de segurança

- O `token.json`, a chave da service account e o `.env` são tão sensíveis
  como passwords — `chmod 600`, nunca no git
- Todas as passwords/segredos partilhados durante o planeamento desta
  automação (ntfy incluído) são temporários/de teste — confirmado que
  devem ser trocados antes de produção a sério
- Antes deste projeto começar a correr a sério, considerar terminar
  sessões ativas / mudar a password da conta CP, já que um HAR de teste
  anterior expôs tokens de sessão reais
- Logs (ficheiro local e aba Logs da Sheet) nunca guardam Cartão de
  Cidadão, NIF, telefone, email, tokens ou nº do passe completos —
  ver 3.10.8; `logrotate`/retenção configurados para não encher o
  cartão SD — ver 3.10.9

## 9. Estado da implementação

Ver `PLANO_FINAL.md`, secção 9 (estado real do código e do RPi, o que está por verificar e o que depende de Bruno).
