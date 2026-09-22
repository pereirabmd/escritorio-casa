"""Fila de pedidos avulsos (PLANO_FINAL.md 3.2) — cron a cada minuto, independente do daemon.

Lê a aba Pedidos (uma linha = um comboio, sem par ida/volta — permite mais de dois comboios no
mesmo dia) e, para cada linha ativa cuja partida ainda seja futura:
- primeira vez (sem Estado ainda): tenta logo, uma vez, mesmo com `Retry=NAO`
- `Retry=SIM`: volta a tentar de `pedido_retry_interval_minutes` em minutos, até a compra ficar
  CONFIRMADA ou o comboio partir
- `Forcar=SIM` (escrito pela PWA): tenta já, ignorando o intervalo
- `CONFIRMADO` ou `AMBIGUO`: nunca se relança sozinho — AMBÍGUO fica só para leitura (3.3.1)

Corre completamente à parte do `cp-scheduler.service` (que só trata da Config semanal, com a
precisão ao segundo do T-24h): um bug aqui nunca arrisca esse daemon. Cada tentativa é lançada
como subprocesso (`hot_buy.py --leg pedidoN`), com o mesmo lock/estado de sempre — por isso nunca
há duas tentativas em curso para a mesma linha (`scheduler.is_running`), mesmo que uma rajada
interna (esgotado, ~12 min) ainda esteja a decorrer quando o cron volta a correr.

    python scripts/pedidos.py               # aplica
    python scripts/pedidos.py --plan-only   # só mostra o que faria
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime

import common
import scheduler
from common import REQUEST_TERMINAL, TZ, app_config, get_logger, lock_path

log = get_logger("pedidos")


def cfg(name, default):
    return app_config().get("purchase", {}).get(name, default)


def is_due(raw_row: list, retry: bool, interval_s: float, now_ts: float) -> tuple[bool, bool]:
    """(está_pronta_a_tentar, foi_por_forçar) a partir das colunas de controlo da linha (H..J)."""
    cells = list(raw_row) + [""] * 12
    estado = str(cells[8]).strip().upper()
    forcar = str(cells[7]).strip().upper() == "SIM"
    if estado in REQUEST_TERMINAL:
        return False, False
    if forcar:
        return True, True
    if not estado:                 # nunca tentado: primeira tentativa é sempre automática
        return True, False
    if not retry:
        return False, False
    ultima = str(cells[9]).strip()
    try:
        last_ts = datetime.fromisoformat(ultima).timestamp() if ultima else 0
    except ValueError:
        last_ts = 0
    return (now_ts - last_ts >= interval_s), False


MAX_LAUNCHES = 5   # relançamentos seguidos que morrem sem gravar nada de novo no lock (ver launch())


def launch(leg, out=log.info) -> bool:
    """Lança `hot_buy.py --leg pedidoN`. Trava (com aviso, 1.1) se o mesmo processo morrer
    sempre antes de gravar estado — foi exatamente isto que aconteceu em produção a 22/09
    (`--leg` só aceitava ida/volta; `pedidoN` rebentava no argparse antes de qualquer log, e
    esta função relançava-o a cada minuto, sem fim, sem nunca tentar comprar nem notificar).
    Uma retentativa legítima (Retry/Forçar depois de uma tentativa real, mesmo falhada ou
    esgotada) nunca é travada por isto: só conta contra o limite quando a tentativa anterior
    não chegou sequer a escrever no lock — nesse caso `peek_state` continua vazio."""
    path = common._state_file("launched_pedidos.json")
    launched = common._read_json(path, {})
    rec = launched.get(leg.lock_key, {})
    now_ts = time.time()
    if now_ts - rec.get("ts", 0) < 30:
        return False                                            # acabou de ser lançado
    prev = common.peek_state(leg.lock_key)
    if prev.get("updated_at"):                                  # a tentativa anterior fez algo real
        rec = {}
    if rec.get("n", 0) >= MAX_LAUNCHES and prev.get("state") not in scheduler.RESUMABLE:
        common.notify_once(f"pedido-stuck-{leg.lock_key}", f"Pedido preso — {leg.key}",
                           f"Tentei lançar a compra {MAX_LAUNCHES} vezes e o processo morre sempre antes de "
                           "gravar estado (nunca chegou a tentar comprar). Parei de tentar; vê "
                           "logs/hot_buy.stdout.log e logs/pedidos.log no RPi.",
                           cooldown_s=3600, logger=log)
        return False
    lock_path(leg.lock_key).unlink(missing_ok=True)   # cada retentativa é uma tentativa nova (3.2)
    out(f"A lançar {leg.key}: comboio {leg.train} {leg.origin} -> {leg.destination} {leg.hhmm}")
    try:
        with open(common.BASE_DIR / "logs" / "hot_buy.stdout.log", "ab") as stdout:
            subprocess.Popen([sys.executable, "scripts/hot_buy.py", "--date", leg.date.isoformat(), "--leg", leg.leg],
                             cwd=common.BASE_DIR, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        log.error("Não consegui lançar %s: %s", leg.key, e)
        common.notify_once(f"pedido-launch-fail-{leg.lock_key}", f"Não consegui lançar o pedido — {leg.key}",
                           f"{type(e).__name__}: a tentativa NÃO arrancou. Vê os logs no RPi.",
                           cooldown_s=1800, logger=log)
        return False
    launched[leg.lock_key] = {"ts": now_ts, "n": rec.get("n", 0) + 1}
    common._write_json_atomic(path, launched)
    return True


def run(plan_only: bool = False) -> int:
    try:
        raw_rows = common.SheetsClient().read_requests()
    except Exception as e:  # noqa: BLE001 — nunca falha calado (1.1), mas sem inundar
        log.error("Não consegui ler a aba Pedidos: %s: %s", type(e).__name__, e)
        if not plan_only:
            common.notify_once("pedidos-sheet-read", "Não consegui ler a aba Pedidos",
                               f"Erro: {type(e).__name__}. Os pedidos avulsos ficam parados até a "
                               "leitura recuperar; a Config semanal não é afetada.", cooldown_s=3600, logger=log)
        return 1

    legs, issues = common.parse_request_rows(raw_rows, common.now_local().date())
    for issue in issues:
        log.warning("Pedidos: %s", issue)
        if not plan_only:
            common.notify_once(f"pedido-issue-{common.short_hash(issue)}", "Linha de Pedidos com problema",
                               f"{issue}. Corrige-a na app.", cooldown_s=24 * 3600, logger=log)

    interval_s = float(cfg("pedido_retry_interval_minutes", 15)) * 60
    now_ts = time.time()
    launched = 0
    for leg in legs:
        if leg.departure.timestamp() <= now_ts:
            continue                                           # o comboio já partiu (3.2)
        raw = raw_rows[leg.row - 5]
        due, forced = is_due(raw, leg.retry, interval_s, now_ts)
        if not due or scheduler.is_running(leg):
            continue
        if plan_only:
            log.info("[plano] lançaria %s (comboio %s)%s", leg.key, leg.train, " — forçado" if forced else "")
        elif launch(leg):
            launched += 1
    log.info("Pedidos: %d perna(s) válida(s), %d problema(s), %d lançada(s) agora",
             len(legs), len(issues), launched)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fila de pedidos avulsos (3.2)")
    ap.add_argument("--plan-only", action="store_true", help="mostra o que faria, sem lançar nem notificar")
    args = ap.parse_args()
    return run(plan_only=args.plan_only)


if __name__ == "__main__":
    sys.exit(main())
