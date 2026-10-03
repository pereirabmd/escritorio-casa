# Análise de robustez da compra de bilhetes (03/10/2026)

Estado: **análise, nada implementado**. Feita a partir do código (`scheduler.py`, `hot_buy.py`, `cp_ticket.py`, `pedidos.py`, `consulta_cp.py`, `pre_flight.py`, `store.py`) e da produção no Pi (bases, logs, systemd, kernel) a 03/10/2026. Não se partiu do princípio de que havia melhorias: o que está bem fica dito. Os itens 3, 4 e 6 vêm da leitura do código (não se simulou o corte nem a falha); os itens 10 e 11 dependem de comportamento da CP que não foi verificado. Enviada por email a `niculae@gmail.com` no mesmo dia.

## O que está bem (verificado)
- **Relógio:** chrony sincronizado, desvio de 0,14 ms.
- **Precisão:** a 1.ª venda saiu a +1 ms de T nas 3 pernas medidas (`v106`, `v112`, `v114`).
- **systemd:** `Restart=always`, `WatchdogSec=300` (o daemon avisa de ≤15 em ≤15 s) e `KillMode=process` (reiniciar o scheduler não mata uma compra em curso).
- **Retoma de uma compra da Config** depois de um crash (estados `SALE_CREATED` a `DISCOUNT_OK`, `Buyer._run`).
- **Lock por perna** (`flock`), lançamento idempotente (`launched.json`, `MAX_LAUNCHES`), 0 «Erro inesperado» e 0 respostas 429 nos logs.
- **O guarda do total 0 €** protege também de uma compra duplicada: a CP recusa o desconto se já existe reserva do mesmo comboio (`SIV:BSC:5151`).
- **Cópia diária das bases**, cifrada (`age`), para um repositório privado fora do Pi.
- **Segredos:** `.env` e `token.json` com permissões 600, `tokens/` 700. Logs com rotação.

## Achados, por prioridade

### Altos
1. **Subtensão contínua no Pi (hardware).** `vcgencmd get_throttled` = `0x50005` (subtensão e limitação de CPU ativas). Deteções de `Undervoltage detected!` no kernel: 1 a 21/09, 1 a 01/10, 7 a 02/10, 63 a 03/10 (desde as 04:36), com a carga a ~0,2: é a fonte ou o cabo. Risco: reinício, corrupção do cartão SD ou CPU limitado na hora de T. **Correção:** fonte oficial 5V/3A com cabo curto; acrescentar ao pre-flight a leitura de `get_throttled` com aviso. (Liga-se a `pulse/docs/ANALISE_SERVIDOR_NOVO_E_IA_LOCAL.md`.)
2. **Sem alerta externo se o Pi ou a internet cair.** `HEALTHCHECKS_PING_URL` vazio no `.env` (o `heartbeat.log` diz «RPi em baixo NÃO gera alerta»). **Correção (5 min, do utilizador):** criar o check no healthchecks.io (período 5 min, tolerância 10) e pôr o URL no `.env`.
3. **A troca não aguenta um corte entre «devolver o antigo» e «confirmar o novo» (~5–10 s).** `PedidoAttempt` não tem retoma (`RESUMABLE` só existe no `Buyer`) e `_antigo_cancelado` só vive em memória. Se o processo morrer aí (reinício, corte), o utilizador fica sem bilhete e sem pedido de recuperação: na repetição seguinte o antigo já foi apagado da lista (`delete_ticket`), a troca trata-se como outro comboio, `cancelar` falha e dá «Troca não feita… ficas com o bilhete antigo» (falso). **Correção:** gravar a intenção **antes** de devolver (dados do antigo e pedido de recuperação já criado) e apagá-la só depois da confirmação; dar retoma ao `PedidoAttempt`; testes que matam o processo em cada passo.
4. **Devolução ambígua.** `consulta_cp.cancelar` tem 2 passos (`POST refund` e `PUT refund/{id}`). Se o `PUT` falhar por rede (`_pedir` → `rede_cp`) ou o estado não vier `CONFIRMED`, `trocar_bilhete_antigo` trata como «não devolveu», cancela a reserva nova e diz «ficas com o antigo», mas a CP pode ter concluído a devolução. **Correção:** após qualquer erro depois do `POST`, reverificar o estado da venda na CP antes de decidir; se for incerto, manter a reserva nova e avisar como incerto.

### Médios
5. **Ciclo do scheduler bloqueante na rede.** `evaluate` consulta o horário oficial por perna (`check_leg_cached`), sem cache negativa nem limite de tempo; uma falha não fica em cache e repete-se a cada ciclo. Medido a 02/10: uma perna demorou 32 s e houve 3 erros do scheduler com a CP a responder mal. Com muitas pernas e a CP lenta aproxima-se do watchdog (300 s) e atrasa o lançamento. **Correção:** cache negativa de 5 min, orçamento de tempo por ciclo, lançar primeiro as pernas devidas.
6. **Recuperação de um crash até 5 min.** Se o `hot_buy` morrer sem estado final, o scheduler só relança no ciclo seguinte (`wake = min(próximo marco, último poll + 5 min)`). Nenhum crash em produção. **Correção:** durante a janela de compra acordar de 10 em 10 s e relançar de imediato.
7. **Pre-flight incompleto.** Verifica rede, DNS, relógio, credenciais, config e alcance da CP, mas não a alimentação (item 1), nem a escrita na base e o espaço, nem faz um login real. **Correção:** um «canário» diário fora de horas (login, horário, criar e cancelar uma venda, como o `ensaio_compra.py`) apanharia dias antes uma mudança no login da CP.
8. **Cópia de segurança sem `.env`, `tokens/` e config.** Perder o cartão SD deixa as bases mas sem a `BILHETES_FERNET_KEY` (as passwords dos outros utilizadores ficam indecifráveis). Não se viu cópia manual. **Correção:** cópia cifrada do `.env` e da config para o mesmo repositório de backup.

### Baixos
9. **Escritas SQLite e notificações síncronas no caminho crítico** (`busy_timeout` de 10 s). Visto `database is locked` 1 vez, a 29/09, na migração. **Correção:** fila ou thread para os logs; timeout curto com repetição diferida.
10. **(A verificar)** Dois processos com o mesmo T (duas pessoas) duplicam o ritmo de pedidos; o orçamento anti-429 é por processo e não se sabe se o limite da CP é por IP ou por conta. Zero 429 até hoje. **Correção:** orçamento partilhado entre processos.
11. **(A verificar)** Mudança de hora: assume-se que a janela da CP segue o relógio (comentário em `fire_time`), nunca confirmado. Só afeta viagens ao domingo da mudança (próxima: 25/10/2026).
12. **(Processo)** O deploy é manual e sem guarda: nada impede copiar scripts ou reiniciar o scheduler perto de uma compra. **Correção:** script de deploy com pré-condições (próximo lançamento a mais de 20 min, nenhum lock ativo), cópia atómica, verificação de `import` e rollback.

## Observação (efetividade, não robustez)
3 das 9 pernas falharam por esgotado (comboios da tarde), já a T-10 min na retenção: reter mais cedo não ajuda; só comprar antes, que é o plano B manual decidido (ADR-088/089).

## Ordem sugerida
1 e 2 já (sem código) → 4 e 3 → 5 e 6 → 7 a 9 quando houver tempo → 10 a 12 só se se confirmarem.
