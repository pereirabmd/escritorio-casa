"""manutencao.py — porta de Manutencao.gs.

Limpeza mensal: apaga instâncias já concluídas (Feita/Saltada) com mais de
DIAS_RETER_HISTORICO dias, para a aba Instancias não crescer para sempre.

`limpar_subscricoes_inativas()` fica só por compatibilidade enquanto a aba
`Subscriptions` ainda existir com esse nome — deixa de ter nada a fazer
(silenciosamente) assim que for renomeada para "Subscriptions (deprecated)"
ou removida, já que o ntfy tornou os tokens FCM por dispositivo obsoletos
(ver PLANO).

    python manutencao.py               # aplica
    python manutencao.py --plan-only   # só mostra quantas linhas apagaria
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from common import FileLock, SheetsClient, get_logger, now_local, parse_sheet_date

log = get_logger("manutencao")

DIAS_RETER_HISTORICO = 90
DIAS_RETER_SUBSCRICOES_INATIVAS = 30


def limpar_historico_antigo(sheets: SheetsClient, plan_only: bool = False) -> int:
    hoje = now_local().date()
    limite = hoje - timedelta(days=DIAS_RETER_HISTORICO)

    linhas_para_apagar = []
    for inst in sheets.read_objects("Instancias"):
        estado = str(inst.get("Estado", ""))
        if estado not in ("Feita", "Saltada"):
            continue
        d = parse_sheet_date(inst.get("Data"))
        if d is not None and d < limite:
            linhas_para_apagar.append(inst["_rowIndex"])

    if linhas_para_apagar and not plan_only:
        sheets.delete_rows("Instancias", linhas_para_apagar)
    return len(linhas_para_apagar)


def limpar_subscricoes_inativas(sheets: SheetsClient, plan_only: bool = False) -> int:
    """Compatibilidade com o modelo antigo (tokens FCM) — sem efeito nenhum
    depois de "Subscriptions" ser renomeada/removida (ver PLANO)."""
    if not sheets.tab_exists("Subscriptions"):
        return 0
    hoje = now_local().date()
    limite = hoje - timedelta(days=DIAS_RETER_SUBSCRICOES_INATIVAS)

    linhas_para_apagar = []
    for sub in sheets.read_objects("Subscriptions"):
        inativa = str(sub.get("Ativa", "")).strip().upper() == "FALSE"
        if not inativa:
            continue
        criada = parse_sheet_date(sub.get("Criada"))
        if criada is not None and criada < limite:
            linhas_para_apagar.append(sub["_rowIndex"])

    if linhas_para_apagar and not plan_only:
        sheets.delete_rows("Subscriptions", linhas_para_apagar)
    return len(linhas_para_apagar)


def manutencao(sheets: SheetsClient | None = None, plan_only: bool = False) -> dict[str, int]:
    lock = FileLock("manutencao")
    if not lock.acquire(timeout_s=15):
        log.warning("manutencao: outra execução em curso, a saltar.")
        return {}
    try:
        sheets = sheets or SheetsClient()
        n_instancias = limpar_historico_antigo(sheets, plan_only)
        n_subs = limpar_subscricoes_inativas(sheets, plan_only)
        resultado = {"instancias_apagadas": n_instancias, "subscricoes_apagadas": n_subs}
        log.info("Manutenção: %s", resultado)
        return resultado
    finally:
        lock.release()


def main() -> int:
    ap = argparse.ArgumentParser(description="Limpeza mensal de histórico antigo")
    ap.add_argument("--plan-only", action="store_true", help="só mostra quantas linhas apagaria")
    args = ap.parse_args()
    manutencao(plan_only=args.plan_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
