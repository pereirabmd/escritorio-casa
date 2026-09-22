# PLANO_UP — alterações ao plano do bilhetes_cp

**Regra: `PLANO.md` (como está hoje) + as alterações deste ficheiro = `PLANO_FINAL.md`.**
Tudo o que difere entre os dois planos está listado aqui, e nada que não
esteja aqui difere. O `PLANO_FINAL.md` é o documento a seguir; este serve para
rever o que mudou e, na implementação, para saber o que aplicar ao código.

**Base de comparação:** `PLANO.md` de 21/09/2026 às 22:40, já com o que a outra
sessão lhe acrescentou (timetable confirmado, árvore de ficheiros atual e a
secção 9 de estado). Essas alterações **não** são minhas e estão nos dois
documentos. Enquanto essa sessão não acabar, o `PLANO.md` pode continuar a mudar
— ver secção 6 (ressincronização).

**Fontes das alterações:**
- HAR de 21/09/2026 (`cp.pt.har`, 574 pedidos, 78 à `api-gateway.cp.pt`): uma
  compra completa (pesquisa → venda → desconto do Passe → confirmação), o
  histórico de viagens da conta e o código JavaScript do site.
- Revisão crítica do `PLANO.md` com o `cp_ticket.py`, o `config/` e o `deploy/`.
- Decisões de Bruno: **a janela de abertura existe** (24 h antes da partida;
  em horas de procura elevada os lugares duram poucos segundos) e o teste do
  HAR foi feito numa hora de pouca procura; o **Scheduler passa a daemon**.

---

## 1. Resumo

| Tipo | O que mudou |
|---|---|
| Decisão | **Scheduler = daemon systemd único** em vez de timers/`at` por disparo (3.2, 3.3.1). |
| Premissa mantida | Disparo exato a T-24h e calibração da janela mantêm-se. `saleableOnline` **não** é sinal da janela. |
| Facto novo (HAR) | O lugar sai no `POST /sale` (a venda `PENDING` bloqueia-o); os `PUT` pós-venda e o `/confirm` são idempotentes; existe `DELETE /sale/{id}` (por testar); `journeys` não exige login; o refresh token não renova o prazo. |
| Segurança da compra | Verificar `totalAmount == €0,00` antes de confirmar. |
| Correção | Timers transientes não sobrevivem a reboot; validade do Passe desalinhada um dia; formato de horas na Sheet; um só login por disparo. |
| Limpeza | Removidas as referências à conversa original, "revisão externa", texto histórico ("corrigido abaixo", "versão anterior… descartado") e um ficheiro que não existe. |
| Movido | O que era uma lista de ajustes ao código passou para **9.8** (a fazer). |

---

## 2. Alterações por secção

Secções **não** listadas são idênticas ao `PLANO.md`: 3, 3.8, 3.10.1, 3.10.8,
3.10.9, 3.10.10, 5 (5.1, 5.2), 6, 7 (introdução), 9 (introdução), 9.2, 9.3, 9.4, 9.5 e 9.7.

| Secção | O que muda | Motivo / evidência |
|---|---|---|
| Introdução | Diz que a venda abre 24 h antes e que os lugares esgotam em segundos **após** a abertura; passa a "plano de referência"; data de atualização | Correção de Bruno |
| 1 | + bullets: a venda abre em T-24h; em pouca procura ainda há lugar, mas não contar com isso. O lembrete de sábado descreve-se como verificação que só notifica se a config faltar | O §1 e o §1.1 estavam desatualizados face a 3.6 |
| 1.1 | Checklist: daemon + watchdog em vez de "Scheduler recria jobs"; total €0 antes de confirmar; lembretes de sábado | Ver 3.2 e 2.4 |
| **2** | Reestruturada em 2.1–2.7: autenticação, tabela da sequência (com coluna "Login?"), cabeçalhos, comportamento observado, regras da CP, outras rotas, o que os HAR não mostram. O parágrafo do timetable confirmado (baseline) passa a 2.6, sem alteração | HAR de 21/09 |
| 2.1 | Tokens: `expires_in` 300 / `refresh_expires_in` 1799; **o prazo do refresh não desliza** (1797 s dois segundos depois); guardar sempre o refresh mais recente; fluxo passo a passo | Entradas de `/token` |
| 2.2 | `journeys` **sem** `x-access-token`; `POST /sale` já devolve `seatData` (bloqueia o lugar); `PUT items` leva o total de €23,45 a €0,00 | HAR |
| 2.3 | + `x-cp-client-registration-date` (só `/trips`; = campo `registered` do perfil); gateway em HTTP/1.1 (`requests` chega) | HAR |
| 2.4 | Comportamento a respeitar: ler `messages`; lugar sai no `/sale`; **total €0 antes de confirmar**; `PUT` idempotentes (2.º `/confirm` → `CONFIRMED` em 136 ms); dúvida sobre `fiscalAddress`; tempos medidos; `timestamp` do servidor com ms; `journeys` devolve `serviceCode` mesmo a >24 h | HAR |
| 2.5 | Regras lidas da API: `sale_deadline` 15, `exchange_limit` 30, `reissue_limit` 120, `calendar_limit` 60, etc. | `/sale/configuration/rules`, `/travel-api/rules` |
| 2.6 | + rotas do código do site nunca testadas: `DELETE /sale/{id}`, `PUT /train-seats/{id}`, `post-sale/refund` e `reissue`, timetable de estação | JS do site |
| 2.7 | O que os HAR não mostram: resposta antes da abertura, resposta "esgotado", `/trips` com `PENDING`. Mantém a nota do e-ticket | Ambos os HAR são compras bem-sucedidas |
| 3.1 | **Um** login por disparo, no pre-flight, reutilizado pelo processo quente; refresh a ~T-30 s e durante a sequência pós-venda; nunca login >20 min antes | Duplo login em 2 min arriscava rate limit/CAPTCHA; sessão morre ~30 min após o login |
| **3.2** | Reescrita: **daemon** `cp-scheduler.service` (`Restart=always`, `WatchdogSec`) com ciclo de 6 passos (poll, calcular disparos, dormir, lançar o processo quente como subprocesso, recalcular ao arrancar, watchdog). Sem `at`, `atq` nem timer por perna. Lembrete T-30 e jobs de sábado/Passe mantêm-se como estavam (script de compra; cron) | Decisão de Bruno. Elimina deduplicar/remover/recriar; isolamento (o daemon nunca faz o `POST /sale`) |
| 3.3 | Antes do disparo: `serviceCode` obtido via `journeys` no pre-flight, corpo do `POST /sale` pré-construído; processo quente **lançado pelo daemon**; keep-alive da ligação; registo de 3 instantes; total €0 e `messages` vazio antes do `confirm` | O `POST /sale` só precisa desses campos; pesquisa no caminho crítico custa ~0,3 s |
| 3.3.1 | Sem `at`/timer transiente. **Persistência a reboot**: o daemon recalcula do zero; o estado vive no lock file. Retry: + categoria "ainda não abriu" (condicional à calibração); + falha **depois** de a venda existir (repetir o `PUT`, prazo 15 min, `DELETE` para abandonar); AMBÍGUO indica o cabeçalho de `/trips` e mantém "sem retry automático". Atraso: dentro de `late_start_grace_minutes` (10) | Timers do `systemd-run` vivem em `/run` e desaparecem num reboot; `PUT` idempotentes; `sale_deadline` |
| 3.4 | + a regra do DST (24 h decorridas vs mesma hora do dia anterior) **está por confirmar**; próxima mudança 25/10/2026 | Só difere em viagens no dia da mudança de hora |
| 3.5 | + "Formato dos dados": datas ISO, horas texto `HH:MM`; a PWA grava `RAW`; o RPi normaliza | `USER_ENTERED` converte `06:45` num valor de hora (mesma causa do bug da notificação às 00:00 na app `tarefas`) |
| 3.6 | Redação limpa (sem narrativa); conteúdo igual, incluindo `Priority: high` em todas | — |
| 3.7 | Só a limpeza de "Sessão Google" e "Bibliotecas": conteúdo igual | — |
| 3.9 | `Data_Expira = compra + validade − 1` **(corrigido em 22/09, ver 9)**; uma viagem posterior à expiração **não** pode ser agendada | Comprado a 21/09 é válido até 20/10, mas 21/09 + 30 = 21/10 |
| 3.10 | Título sem "(revisão externa)" | Limpeza |
| 3.10.2 | "o daemon só recalcula a lista de disparos" em vez de "o Scheduler só atualiza/remove timers" | Ver 3.2 |
| 3.10.3 | + instante de disparo já passado com partida futura; + viagem depois da expiração do Passe; a validação por timetable passa a ser referida como implementada (`scripts/timetable.py`) | Casos não cobertos; baseline já tem o timetable |
| 3.10.4 | + comboio presente no `journeys` com `serviceCode` guardado; o login do pre-flight é o único do disparo | Ver 3.1 e 3.3 |
| 3.10.5 | + como os passos 3–7 são idempotentes, retomar = repetir a sequência sobre o mesmo `saleID` | HAR |
| 3.10.6 | + só dentro dos 15 min de `sale_deadline`; fora disso aplica-se 3.3.1 | Regra da CP |
| 3.10.7 | Dry-run que cria a venda cancela-a com `DELETE`; testar em hora de pouca procura; "daemon" em vez de "scheduler" | Uma venda `PENDING` bloqueia um lugar |
| **3.11** | Reescrita sem texto histórico: o que é facto (janela real), o que os HAR ensinam (`saleableOnline` não a reflete; compra a 24 h 29 min pela app móvel), o que falta medir, método de calibração, papel do `Date` e do `timestamp` com ms. 3.11.1 mantém a decisão (`chrony`), sem a história da versão descartada | Correção de Bruno; HAR |
| 4 | Fórmula do Passe (`−1`); leitura da tabela por nome de cabeçalho, não por linha fixa; formato de dados | Ver 3.5 e 3.9 |
| 7.1 | Árvore do baseline mantida, com `scheduler.py` descrito como **daemon** e o `cp-scheduler.service` em `deploy/`; + aviso de que o repositório é **público** | `gh repo view` → `PUBLIC` |
| 7.2 | Bullet do systemd: novo unit do daemon, lembretes e Passe por cron; legenda sem "nesta conversa" | Limpeza; ver 3.2 |
| 8 | + HAR contém password em texto simples (`*.har` no `.gitignore`, apagar depois de usados); + risco de uso da API interna sem acordo com a CP | O HAR de 21/09 contém o POST de login completo |
| 9.1 | Bullet dos timers `cp-warm-*` marcado como **estado atual; alvo = daemon** | Decisão de Bruno |
| 9.6 | "Sem `at`" passa a "estado atual `systemd-run`; alvo daemon" | Idem |
| **9.8** | **Nova:** alinhamento do código com este plano (12 pontos: daemon, login único, total €0, transbordos, `serviceCode`, `fiscalAddress`, instantes, `--dry-run`, horas na Sheet, validações, DST, `.gitignore`) | O código foi escrito a partir do plano anterior |

---

## 3. Removido por desatualizado

- "Este documento é o hand-off completo…", a legenda "já entregue **nesta
  conversa**" e "revisão externa", "refinada", "todos adotados", "corrigido
  abaixo", "Versão anterior deste plano propunha… foi revisto e descartado". A
  decisão ficou, sem a história.
- "`api-gateway.cp.pt` não está acessível às ferramentas usadas para montar
  este plano" (o timetable já está confirmado no baseline).
- A descrição dos lembretes de sábado no §1 e §1.1 ("3 lembretes escalados"),
  incoerente com 3.6.
- `scripts/cp_ticket_original_notes.md` na árvore (o baseline já o tinha
  retirado); a alegação de que os jobs do `systemd-run` são "persistentes a
  reboot".
- A minha versão anterior de "7.3 Adaptações ao `cp_ticket.py`" e "9 Ordem de
  implementação": o código já existe. Ficaram em 9.8.

---

## 4. Trabalho de implementação (depois de a outra sessão acabar)

Quando pedires para implementar, o ponto de partida é **9.8 do `PLANO_FINAL`**.
Verificar cada ponto contra o código **atual** (foi escrito a partir do plano
anterior) e corrigir o que falta. Outros ficheiros a ajustar:

| Ficheiro | Alteração |
|---|---|
| `scripts/scheduler.py` + `deploy/` | Passar a daemon; `cp-scheduler.service`; retirar `cp-warm-*` e a entrada do cron do scheduler |
| `scripts/hot_buy.py`, `scripts/cp_ticket.py` | 9.8 pontos 2–8 |
| `config/app_config.example.json` | Já sem `attempt_offsets_seconds`. Confirmar que `launch_lead_minutes: 6` / `login_lead_minutes: 3` batem com 3.1 (login único) e que não há tentativas antes do instante calibrado |
| `config/sheet_schema.json` | Nota de `Data_Expira` `=A5+B5` → `=A5+B5-1` |
| Sheet real e PWA (`index.html`) | Fórmula de `Data_Expira`; colunas de hora em texto; escrita `RAW` |
| `.env.example` | `CP_FISCAL_ADDRESS` (opcional) |
| `.gitignore` | `*.har` |
| `~/Transferências/cp.pt.zip` | Apagar: contém a password da CP, tokens, CC e NIF (permissões `rw-rw-rw-`) |

---

## 5. Sugestões que **não** entraram no `PLANO_FINAL`

O `PLANO_FINAL` só leva factos confirmados, correções, limpeza e a decisão do
daemon. Estes pontos de design ficaram por decidir:

1. **AMBÍGUO: repetir em vez de esperar confirmação manual.** Só o `/confirm`
   efetiva a compra; uma segunda venda `PENDING` é lixo que expira (mas
   bloqueia um lugar 15 min). Não repetir e "confirmar à mão" com lugares que
   esgotam em segundos equivale a perder o bilhete. Depende de testar se a CP
   aceita uma 2.ª venda para o mesmo passageiro e comboio.
2. **Healthchecks.io antes de produção.** O ntfy corre no mesmo RPi: se o RPi,
   o router, o DDNS ou a internet caírem, nenhum alerta chega. O
   `PLANO_FINAL` mantém a secção 6 como estava (com o watchdog do daemon como
   proteção local).
3. **Hardening mínimo antes de guardar credenciais no RPi** (SSH só por chave,
   `ufw`, atualizações automáticas). A porta 443 já está exposta.
4. **Estado por perna na Sheet** (agendado / comprado / falhou) e notificação
   de confirmação quando uma semana é agendada.
5. **Service account só com acesso a esta Sheet**, em vez da pasta partilhada.
6. **Token de acesso do ntfy** em vez de basic auth (o repositório é público
   e revela hostname, utilizador e tópico).
7. **Ecrã de consentimento OAuth** do PWA: verificar se em "Testing" as
   autorizações expiram ao fim de 7 dias.
8. **Contradição já existente no `PLANO.md`** (mantida no FINAL): 3.10.7 diz
   que o `--dry-run` é obrigatório antes de compras automáticas, mas 9.5 diz
   que foi adiado por decisão de Bruno e que uma linha `Ativo=SIM` com data
   futura gera uma compra real assim que a API Sheets estiver ativa.

---

## 6. Ressincronização com o `PLANO.md`

A outra sessão ainda está a editar o `PLANO.md`. Quando acabar, para manter
`PLANO.md + PLANO_UP = PLANO_FINAL`:
1. Comparar o `PLANO.md` novo com o de 21/09 22:40 e trazer para o
   `PLANO_FINAL` o que essa sessão tiver mudado (é o que já foi feito com o
   timetable, a árvore de ficheiros e a secção 9).
2. Acrescentar a este ficheiro qualquer linha nova que surja.
3. Reverificar secção a secção: as secções não listadas em 2 têm de continuar
   idênticas.

---

## 7. Por verificar (experiências)

| # | O quê | Onde fica documentado |
|---|---|---|
| 1 | Resposta do `POST /sale` antes da abertura e para um comboio esgotado | 2.7, 3.3.1, 3.11 |
| 2 | Instante exato de abertura e âncora (servidor/cliente); site vs app | 3.11 |
| 3 | `DELETE /sale/{id}` funciona e liberta o lugar | 2.6, 3.10.7 |
| 4 | `GET /trips` lista vendas `PENDING` | 3.3.1 |
| 5 | O fluxo confirma sem `fiscalAddress` | 2.4 |
| 6 | A CP aceita uma 2.ª venda `PENDING` para o mesmo passageiro/comboio | 3.3.1, 5.1 deste ficheiro |
| 7 | Regra do DST (24 h decorridas vs mesma hora) antes de 25/10/2026 | 3.4 |
| 8 | Significado do `timeLimits` do item `302` (`timepoint: TRAIN_ORIGIN`, `timeLimit: 0`, serviço `LC`) | — |

(O timetable sem login e o CORS já estão confirmados no `PLANO.md`.)

---

## 8. Correções às minhas afirmações anteriores

- Propus sondar o `journeys` para ver se `saleableOnline` alguma vez é
  `false`. **Retirado**: a janela existe e o campo não a reflete.
- Escrevi que o refresh token "desliza". **Errado**: o prazo é absoluto.
  Corrigido em 2.1 e 3.1.
- Escrevi que o daemon "eliminaria quase toda a 3.2". **Exagero**: o ganho é a
  reconciliação (nomes, deduplicação, remoção, recriação após reboot). O
  ponto único de falha é tratado com `Restart=always` e `WatchdogSec`, e o
  processo quente continua separado (3.2).

---

## 9. Atualização de 22/09 — implementação e uma correção

- **Correção da validade (3.9, 4).** Bruno confirmou que a Sheet está certa: o passe
  vale 30 dias **contando o dia do carregamento**, isto é, expira a compra + 29
  (`Validade_Dias = 29`, `Data_Expira = Data_Ultima_Compra + Validade_Dias`). A
  alteração "compra + validade − 1" das secções 2 (linhas 3.9 e 4) fica sem efeito: o
  `PLANO_FINAL` já diz a regra correta e a Sheet não precisa de ser alterada.
- **Implementado a partir deste ficheiro:** daemon do Scheduler, um só login por disparo,
  transbordos por secção, `fiscalAddress` opcional, `*.har` no `.gitignore`, registo do
  `timestamp` do servidor, validações novas (incluindo o horário oficial como condição),
  `--search-only`, heartbeat, token do ntfy. O estado ponto a ponto está em
  `PLANO_FINAL.md` 9.1.
- **Continua por decidir ou por testar:** os pontos 5.1, 5.5, 5.6 e 5.8, o `--dry-run`
  com `DELETE` (7.3), a regra do DST (7.7) e o SSH só por chave.
- **Daqui em diante o `PLANO_FINAL.md` é o único plano mantido.** O `PLANO.md` fica como
  base histórica desta comparação e não deve voltar a ser editado.
- **Regra nova (3.11): a venda abre 24 h antes da partida do comboio na 1.ª estação**
  (Bruno, 22/09). Implementada no disparo e na PWA; ver `PLANO_FINAL.md` 3.11.
- **Regra nova (3.3.1): "ainda não aberto" repete-se na iteração seguinte** (Bruno, 22/09); substitui o "não repetir até à calibração".
- **Regra nova (3.11, 4): a hora da Config é a da 1.ª estação** (Bruno, 22/09); a de embarque também se aceita.
- **Regra nova (3.2): o lembrete de partida leva carruagem e lugar** (Bruno, 22/09), com três fontes e sem falhar a compra se faltarem.
- **Regra corrigida (3.2): uma configuração tardia inicia a compra de imediato** (Bruno, 22/09), em vez de recusar; substitui a tolerância `late_start_grace_minutes` e a condição "já era conhecida antes do disparo".
- **Funcionalidade nova (3.2): vigilância do comboio nos últimos 30 min antes da
  partida** (Bruno, 22/09). `scripts/live_delay.py`, cron a cada minuto, lê a aba
  Bilhetes, consulta o `timetable` do comboio na estação de embarque e notifica só
  quando o atraso, o cais ou a supressão mudam em relação à última leitura.
- **Regra nova, mais agressiva (3.3.1): "esgotado" confirma-se com uma rajada
  de ~12 min antes de desistir** (Bruno, 22/09, tão persistente quanto ele já
  fazia à mão) — o mesmo código pode aparecer com a rede condicionada, não só
  esgotado a sério. Esquema `0, 0.5, 0.5, 0.5, 1×7, 2, 4, 8, 15, 30×3, 60×4,
  120×3` (`sold_out_retry_delays_s`, 25 retentativas), depois o esquema
  normal (para, notifica). Como ultrapassa os 5 min do `access_token`, a
  rajada renova-o a meio; também para se o comboio já tiver partido.
