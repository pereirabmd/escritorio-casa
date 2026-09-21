"""Lembrete semanal de configuração (PLANO_FINAL.md 3.6).

Corre aos sábados às 08:00, 12:00 e 20:00 (cron). Em cada execução verifica de
forma independente se a semana seguinte (segunda a domingo) já tem pelo menos
uma viagem ativa e válida na Config; se não tiver, envia um lembrete.

O tom é de lembrete, não de exigência: ajuda a não esquecer, sem prazos nem
escalada de alarme.

    python scripts/config_reminder.py [--today AAAA-MM-DD] [--force]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import common
from common import app_config, get_logger, notify

log = get_logger("config_reminder")

PWA_URL = app_config().get("pwa_url", "https://pereirabmd.github.io/escritorio-casa/bilhetes_cp/")


def next_week(today: date) -> tuple[date, date]:
    """Segunda e domingo da semana seguinte àquela em que `today` cai."""
    monday = today + timedelta(days=7 - today.weekday())
    return monday, monday + timedelta(days=6)


def week_is_configured(weekly: list, monday: date, sunday: date, today: date) -> bool:
    legs, _ = common.parse_config_rows(weekly, min(today, monday))
    return any(monday <= l.date <= sunday for l in legs)


def main() -> int:
    ap = argparse.ArgumentParser(description="Lembrete de configuração da semana seguinte")
    ap.add_argument("--today", help="simular outra data (AAAA-MM-DD), para testes")
    ap.add_argument("--force", action="store_true", help="correr mesmo que hoje não seja sábado")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else common.now_local().date()
    if today.weekday() != 5 and not args.force:
        log.info("Hoje não é sábado (%s); nada a verificar.", today)
        return 0

    monday, sunday = next_week(today)
    try:
        snap = common.SheetsClient().read_config()
        common.save_config_cache(snap)
    except Exception as e:  # noqa: BLE001
        log.error("Leitura da Sheet falhou: %s: %s", type(e).__name__, e)
        # Não sei se está configurada: aviso na mesma, para não ficar em silêncio.
        snap = common.load_config_cache()
        if snap is None:
            notify("Lembrete da semana — não consegui ver a Sheet",
                   f"Não consegui ler a configuração ({type(e).__name__}). "
                   f"Confirma na app se a semana de {monday:%d/%m} a {sunday:%d/%m} está configurada: {PWA_URL}",
                   tags=["calendar"], logger=log)
            return 1

    if week_is_configured(snap["weekly"], monday, sunday, today):
        log.info("Semana %s a %s já configurada.", monday, sunday)
        return 0

    notify(f"Falta configurar a semana de {monday:%d/%m} a {sunday:%d/%m}",
           f"Ainda não há viagens ativas para a semana que vem. Quando puderes: {PWA_URL}",
           tags=["calendar"], logger=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
