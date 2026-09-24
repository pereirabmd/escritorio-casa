"""Validade do Passe Ferroviário Verde (PLANO_FINAL.md 3.9) — job diário (cron, 09:00).

Lê o bloco do passe da Config (Data_Ultima_Compra, Validade_Dias,
Data_Expira, encontrados pelo nome do cabeçalho) e avisa 3 dias e 1 dia antes de expirar, e no próprio dia.
Se os dados faltarem ou estiverem ilegíveis, avisa uma vez por semana (nada
falha em silêncio, mas sem insistir).

A renovação do passe é manual: Bruno renova na App CP e escreve a nova data na Sheet.

    python scripts/pass_expiry_check.py [--today AAAA-MM-DD]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import common
from common import get_logger, notify, notify_once, parse_sheet_date

log = get_logger("pass_expiry")

NOTIFY_AT_DAYS = (3, 1, 0)


def expiry_date(passe: list) -> date | None:
    """Data em que o passe expira.

    A validade é de 30 dias contando o dia do carregamento: expira a compra + 29
    (comprado a 21/09 vale até 20/10). Na Sheet isto é `Validade_Dias = 29` e
    `Data_Expira = Data_Ultima_Compra + Validade_Dias`. A coluna Data_Expira da Sheet é a
    fonte da regra; se estiver vazia ou ilegível, calcula-se A + B da mesma forma.
    """
    cells = list(passe) + [""] * 4
    expira = parse_sheet_date(cells[2])
    if expira is not None:
        return expira
    ultima = parse_sheet_date(cells[0])
    try:
        dias = int(float(cells[1]))
    except (TypeError, ValueError):
        return None
    return ultima + timedelta(days=dias) if ultima is not None else None


def message_for(days_left: int, expira: date) -> tuple[str, str] | None:
    if days_left == 3:
        return "O passe expira em 3 dias", f"O Passe Ferroviário Verde termina a {expira:%d/%m/%Y}."
    if days_left == 1:
        return "O passe expira amanhã", f"O Passe Ferroviário Verde termina a {expira:%d/%m/%Y}."
    if days_left == 0:
        return "O passe expira hoje", "Depois de renovar na App CP, atualiza a data na Sheet."
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Aviso de validade do passe")
    ap.add_argument("--today", help="simular outra data (AAAA-MM-DD), para testes")
    args = ap.parse_args()
    today = date.fromisoformat(args.today) if args.today else common.now_local().date()

    try:
        snap = common.get_store().read_config()
        common.save_config_cache(snap)
    except Exception as e:  # noqa: BLE001
        log.error("Leitura da Sheet falhou: %s: %s", type(e).__name__, e)
        notify_once("pass-sheet-read", "Não consegui verificar o passe",
                    f"A leitura da Sheet falhou ({type(e).__name__}); não sei quantos dias faltam.",
                    cooldown_s=24 * 3600, logger=log)
        return 1

    expira = expiry_date(snap["passe"])
    if expira is None:
        log.error("Bloco do passe ilegível: %r", snap["passe"])
        notify_once("pass-unreadable", "Não consigo ler a validade do passe",
                    "Faltam Data_Ultima_Compra/Validade_Dias na Config. Preenche-as para eu avisar "
                    "antes de expirar.", cooldown_s=7 * 24 * 3600, logger=log)
        return 1

    days_left = (expira - today).days
    log.info("Passe expira a %s (faltam %d dias).", expira, days_left)
    if days_left < 0:
        notify_once(f"pass-expired-{expira}", "O passe já expirou",
                    f"Expirou a {expira:%d/%m/%Y}. Renova na App CP e atualiza a data na Sheet; "
                    "sem passe válido as compras automáticas não têm desconto.",
                    cooldown_s=7 * 24 * 3600, tags=["warning"], logger=log)
        return 0
    msg = message_for(days_left, expira)
    if msg:
        notify_once(f"pass-{expira}-{days_left}", msg[0], msg[1], cooldown_s=20 * 3600,
                    tags=["ticket"], logger=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
