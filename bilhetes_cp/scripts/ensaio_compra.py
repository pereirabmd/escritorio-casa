"""Ensaio da compra REAL, sem comprar (nada é confirmado): corre o `Buyer` verdadeiro contra a CP verdadeira, mas o passo
«confirmar» cancela a venda (`DELETE /sale/{id}`) em vez de a confirmar. Serve para validar o caminho crítico (ligação viva,
retenção antes de T, corrida ao desconto, guarda do total) sem gastar um bilhete.

    python scripts/ensaio_compra.py --date 2026-09-26 --train 521 --origin lisboa_oriente --dest aveiro --hhmm 06:30

- não escreve na base de dados dos bilhetes nem na Config; o lock usa a perna `ens` (não colide com nenhuma viagem real);
- os avisos levam «[ENSAIO]» no título e o lembrete de partida (agendado) é descartado;
- a CP pode recusar por outros motivos (esgotado, comboio que não circula): o ensaio regista-o e cancela o que tiver criado.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import datetime, timedelta

import common
import hot_buy
import timetable
from common import Leg, PurchaseLock
from cp_ticket import CPClient, CPResponse


class CPEnsaio(CPClient):
    """Como o cliente real, mas o `confirm` cancela a venda e devolve uma confirmação de mentira (só para o ensaio)."""

    def confirm(self, sale_id: int) -> CPResponse:
        r = self.cancel_sale(sale_id)
        print(f"ensaio: venda {sale_id} cancelada em vez de confirmada (HTTP {getattr(r, 'status', '?')})", flush=True)
        body = {"status": {"code": "CONFIRMED"}, "reference": "ENSAIO-CANCELADA", "seatData": {}}
        return CPResponse(status=200, body=body, text="ensaio", date_header=None, sent_at=r.sent_at if r else 0.0,
                          received_at=r.received_at if r else 0.0, elapsed_ms=r.elapsed_ms if r else 0.0)


class SheetsMudas:
    """Não escreve nada (nem lê bilhetes já comprados)."""
    def read_tickets(self): return []
    def append_log(self, *a, **k): pass
    def append_ticket(self, *a, **k): pass
    def append_request(self, *a, **k): pass
    def update_request(self, *a, **k): pass

    def append_attempts(self, rows):
        """O registo de pedidos à CP grava-se a sério (perna «ens»): é o que se quer verificar num ensaio."""
        return common.get_store().append_attempts(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--train", type=int, required=True)
    ap.add_argument("--origin", default="lisboa_oriente")
    ap.add_argument("--dest", default="aveiro")
    ap.add_argument("--hhmm", required=True, help="hora de partida na 1.ª estação (ou de embarque)")
    ap.add_argument("--t-em", type=float, default=None, metavar="MIN",
                    help="inventa um T daqui a MIN minutos (a data/hora da viagem só vão à CP): ensaia a retenção num comboio com lugares "
                         "sem esperar pelo T real; o desconto da CP já está aberto se o T real passou")
    ap.add_argument("--sem-ancora", action="store_true",
                    help="usa --hhmm como hora de T-base tal como está (sem a 1.ª estação do horário): serve para ensaiar a retenção "
                         "com um T inventado daqui a uns minutos; o desconto da CP já está aberto se o T real passou")
    a = ap.parse_args()
    d = datetime.strptime(a.date, "%Y-%m-%d").date()
    leg = Leg(d, "ens", a.origin, a.dest, a.train, a.hhmm, 0)
    if a.t_em is not None:
        t = common.now_local() + timedelta(minutes=a.t_em)
        anchor_dt = t + timedelta(hours=24)                   # T = partida na 1.ª estação − 24 h
        leg = dataclasses.replace(leg, anchor=anchor_dt.strftime("%H:%M"), anchor_date=anchor_dt.date())
    elif not a.sem_ancora:
        leg = timetable.apply_anchor(leg)
    print(f"perna {leg.key}: T = {leg.fire:%d/%m %H:%M:%S}; agora {common.now_local():%d/%m %H:%M:%S}", flush=True)
    common.lock_path(leg.lock_key).unlink(missing_ok=True)          # ensaio limpo
    lock = PurchaseLock(leg.lock_key)

    def notify_fn(title, message, **kw):
        if kw.get("at") is not None:          # lembrete de partida: não se agenda em ensaios
            return True
        return common.notify(f"[ENSAIO] {title}", message, tags=kw.get("tags") or (), logger=kw.get("logger"))

    hot_buy.Buyer.do_preflight = lambda self: None            # o pré-voo não é o que se ensaia (e falha para pernas fora da Config)
    buyer = hot_buy.Buyer(leg, lock, sheets=SheetsMudas(), cp_factory=CPEnsaio, notify_fn=notify_fn)
    code = buyer.run()
    st = common.peek_state(leg.lock_key)
    print("resultado:", code, st.get("state"), "|", st.get("final_message", "")[:200], "|", st.get("timing", "")[:300],
          "|", st.get("discount_timing", "")[:300], "| pedidos ao desconto:", st.get("discount_attempts"), "| lugar:", st.get("seat_changed") or "não mudado", st.get("seats"), flush=True)
    common.lock_path(leg.lock_key).unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
