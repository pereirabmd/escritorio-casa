"""Scheduler — daemon único (PLANO_FINAL 3.2, 3.3.1, 3.10.2, 3.10.3).

Corre como serviço systemd (`cp-scheduler.service`, `Restart=always`, `WatchdogSec`) e
substitui os jobs individuais por disparo: não há `at`, nem timers por perna. Em ciclo:

1. lê a aba Config (de ~5 em ~5 min) e valida-a; uma leitura falhada é "sem novidade" (usa a
   cache), nunca "config vazia"
2. recalcula, do zero, quais as pernas a lançar e quando (T-24h menos a antecedência de
   arranque); desativar ou alterar uma linha não exige remover nada
3. dorme até ao próximo marco e, nessa altura, arranca o processo "quente" (`hot_buy.py`) como
   subprocesso SEPARADO: o daemon nunca faz o `POST /sale`, e um erro no processo quente não o
   derruba. Lançar é idempotente (lock por perna + estado local)
4. ao arrancar (reboot, crash) recalcula tudo; um disparo que passou há pouco (tolerância
   `late_start_grace_minutes`) só é lançado se a perna já era conhecida ANTES da hora do disparo;
   uma linha que chega depois da hora gera aviso, não compra (3.10.3)
5. avisa o systemd de que está vivo (watchdog): um daemon parado falharia em silêncio (1.1)

    python scripts/scheduler.py               # daemon (é o que o systemd corre)
    python scripts/scheduler.py --once        # um único ciclo: avalia e lança o que já é devido
    python scripts/scheduler.py --plan-only   # mostra o plano; não lança, não notifica, não grava estado
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime

import common
import pass_expiry_check
import timetable
from common import (STATES, TERMINAL, TZ, Leg, PurchaseLock, app_config, get_logger, lock_path,
                    notify_once, peek_state, short_hash)

log = get_logger("scheduler")

RESUMABLE = set(STATES[2:7])          # SALE_CREATED .. DISCOUNT_OK: há venda a concluir
SALE_DEADLINE_S = 15 * 60             # prazo da CP para concluir uma venda (2.5)
MAX_LAUNCHES = 3                      # relançamentos de um processo que morreu antes de gravar estado


def cfg(name: str, default):
    return app_config().get("purchase", {}).get(name, default)


# ---------------------------------------------------------------------------
# systemd: sd_notify sem dependências
# ---------------------------------------------------------------------------

class SdNotify:
    """Fala com o systemd por NOTIFY_SOCKET (READY, WATCHDOG, STATUS). Sem systemd, não faz nada."""

    def __init__(self) -> None:
        addr = os.environ.get("NOTIFY_SOCKET", "")
        self.addr = ("\0" + addr[1:]) if addr.startswith("@") else addr

    def send(self, msg: str) -> None:
        if not self.addr:
            return
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                s.sendto(msg.encode(), self.addr)
        except OSError as e:
            log.warning("sd_notify falhou: %s", type(e).__name__)

    def ready(self) -> None:
        self.send("READY=1")

    def watchdog(self) -> None:
        self.send("WATCHDOG=1")

    def status(self, text: str) -> None:
        self.send(f"STATUS={text}")


# ---------------------------------------------------------------------------
# Leitura da Config
# ---------------------------------------------------------------------------

def read_config() -> tuple[dict | None, bool]:
    """(snapshot, veio_da_cache). Uma falha nunca é silenciosa."""
    try:
        snap = common.SheetsClient().read_config()
        common.save_config_cache(snap)
        return snap, False
    except Exception as e:  # noqa: BLE001 — rede, quota, permissões, cabeçalhos, Google em baixo...
        log.error("Leitura da Sheet falhou: %s: %s", type(e).__name__, e)
        notify_once(f"sheet-read-{type(e).__name__}", "Não consegui ler a Sheet",
                    f"Erro: {type(e).__name__}. Mantenho o plano atual e uso a última configuração "
                    "válida. Se persistir, confirma a partilha da Sheet com a service account e a API Sheets.",
                    cooldown_s=3 * 3600, logger=log)
        return common.load_config_cache(), True


# ---------------------------------------------------------------------------
# Avaliação: o que lançar e quando
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    leg: Leg
    launch_ts: float      # quando arrancar o processo quente
    fire_ts: float        # T-24h da partida


def _warn(plan_only: bool, key: str, title: str, message: str, cooldown_h: float = 24) -> None:
    log.warning("%s: %s", title, message)
    if not plan_only:
        notify_once(key, title, message, cooldown_s=cooldown_h * 3600, logger=log)


def evaluate(snap: dict, from_cache: bool, now_ts: float, plan_only: bool = False) -> list[Item]:
    """Recalcula, do zero, as pernas a lançar. Também gera os avisos (linhas inválidas, passe,
    horário oficial, configuração tardia). `from_cache` não muda nada: mesmo com a Sheet em baixo
    o plano continua a ser cumprido."""
    now = datetime.fromtimestamp(now_ts, TZ)
    legs, issues = common.parse_snapshot(snap, now.date())
    expiry = pass_expiry_check.expiry_date(snap.get("passe", []))
    seen_path = common._state_file("seen.json")
    seen = common._read_json(seen_path, {})
    lead_s = float(cfg("launch_lead_minutes", 6)) * 60
    grace_s = float(cfg("late_start_grace_minutes", 10)) * 60
    check_days = float(cfg("timetable_check_days", 14))

    for issue in issues:
        _warn(plan_only, f"config-issue-{short_hash(issue)}", "Linha da Config com problema",
              f"{issue}. Não agendei esta linha; corrige-a na app.")

    items: list[Item] = []
    for leg in sorted(legs, key=lambda l: l.fire):
        state = peek_state(leg.lock_key).get("state")
        if state in TERMINAL or leg.departure.timestamp() <= now_ts:
            continue                                   # já tratada, ou viagem passada
        if expiry and leg.date > expiry:
            _warn(plan_only, f"after-pass-{leg.key}-{expiry}", f"Viagem depois de o passe expirar — {leg.key}",
                  f"O passe termina a {expiry:%d/%m/%Y} e esta viagem é a {leg.date:%d/%m/%Y}: sem passe "
                  "válido o desconto não se aplica. Renova o passe na App CP e atualiza a data na Sheet; "
                  "não agendei esta compra.")
            continue
        if leg.departure.timestamp() - now_ts <= check_days * 86400:
            problem, _ = timetable.check_leg_cached(leg)      # 3.10.3: a Config tem de bater com o horário oficial
            if problem:
                _warn(plan_only, f"timetable-{leg.key}-{short_hash(problem)}", f"Linha inválida — {leg.key}",
                      problem[0].upper() + problem[1:] + ". Não agendei esta compra; corrige a Config.", 12)
                continue
            # A venda abre 24 h antes da partida do comboio na sua 1.ª estação (3.11), não na de embarque
            leg = timetable.apply_anchor(leg)
            if leg.anchor is None:
                _warn(plan_only, f"anchor-{leg.key}", f"Não confirmei a partida do comboio — {leg.key}",
                      f"Não consegui saber a hora a que o comboio {leg.train} parte da 1.ª estação; uso a hora da "
                      f"Config ({leg.hhmm}). Se o comboio parte mais cedo de outra estação, o disparo pode chegar tarde.", 12)
            elif leg.anchor != leg.hhmm:
                log.info("%s: disparo ancorado à partida do comboio na 1.ª estação (%s), não às %s de embarque",
                         leg.key, leg.anchor, leg.hhmm)
            else:
                log.info("%s: disparo às %s (partida na 1.ª estação; embarque às %s)", leg.key, leg.anchor,
                         leg.board or leg.hhmm)
        fire_ts = leg.fire.timestamp()

        first_seen = seen.setdefault(leg.key, now_ts)         # 1.º ciclo em que a perna foi vista
        if fire_ts <= now_ts:
            # O disparo já passou e a partida ainda é futura. Só se recupera o que já era conhecido
            # antes da hora (reboot/crash); uma linha que chega depois avisa e não compra.
            known = first_seen < fire_ts or bool(state)
            limit = fire_ts + (SALE_DEADLINE_S if state in RESUMABLE else grace_s)
            if not known:
                _warn(plan_only, f"late-config-{leg.lock_key}", f"Configuração tardia — {leg.key}",
                      f"O instante de compra ({leg.fire:%d/%m %H:%M}) já tinha passado quando esta viagem foi "
                      f"configurada (comboio {leg.train}). Não vou comprar automaticamente: compra na App CP.")
                continue
            if now_ts > limit:
                _warn(plan_only, f"missed-{leg.lock_key}", f"Janela de compra perdida — {leg.key}",
                      f"O instante de compra ({leg.fire:%d/%m %H:%M}) já passou sem bilhete para o comboio "
                      f"{leg.train}. Não vou comprar automaticamente.")
                continue
            items.append(Item(leg, now_ts, fire_ts))
        else:
            items.append(Item(leg, fire_ts - lead_s, fire_ts))

    if not plan_only:
        common._write_json_atomic(seen_path, {k: v for k, v in seen.items() if now_ts - v < 30 * 86400})
    return sorted(items, key=lambda i: (i.launch_ts, i.leg.key))


# ---------------------------------------------------------------------------
# Lançamento do processo quente
# ---------------------------------------------------------------------------

def is_running(leg: Leg) -> bool:
    """O processo quente está a correr se o lock da perna estiver ocupado."""
    if not lock_path(leg.lock_key).exists():
        return False
    lock = PurchaseLock(leg.lock_key)
    if lock.acquire():
        lock.release()
        return False
    return True


def launch(item: Item, now_ts: float) -> bool:
    """Arranca `hot_buy.py` como subprocesso separado (sessão própria: sobrevive a um restart do daemon)."""
    leg = item.leg
    if is_running(leg):
        return False
    path = common._state_file("launched.json")
    launched = common._read_json(path, {})
    rec = launched.get(leg.lock_key, {})
    state = peek_state(leg.lock_key).get("state")
    if now_ts - rec.get("ts", 0) < 30:
        return False                                          # acabou de ser lançado
    if rec.get("n", 0) >= MAX_LAUNCHES and state not in RESUMABLE:
        return False                                          # morre sempre antes de gravar estado
    out = open(common.BASE_DIR / "logs" / "hot_buy.stdout.log", "ab")
    try:
        subprocess.Popen([sys.executable, "scripts/hot_buy.py", "--date", leg.date.isoformat(), "--leg", leg.leg],
                         cwd=common.BASE_DIR, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        log.error("Não consegui lançar %s: %s", leg.key, e)
        notify_once(f"launch-fail-{leg.lock_key}", f"Não consegui lançar a compra — {leg.key}",
                    f"{type(e).__name__}: a compra desta perna NÃO arrancou. Vê os logs do scheduler.",
                    cooldown_s=1800, logger=log)
        return False
    finally:
        out.close()
    launched[leg.lock_key] = {"ts": now_ts, "n": rec.get("n", 0) + 1}
    common._write_json_atomic(path, launched)
    log.info("Lançado o processo de compra %s (comboio %s, disparo %s, tentativa %d)", leg.key, leg.train,
             leg.fire.isoformat(), launched[leg.lock_key]["n"])
    return True


def cycle(snap: dict, from_cache: bool, now_ts: float, *, plan_only: bool = False,
          launcher=launch) -> tuple[list[Item], float | None]:
    """Um ciclo: avalia, lança o que já é devido e devolve (plano, próximo marco de lançamento)."""
    items = evaluate(snap, from_cache, now_ts, plan_only)
    if not plan_only:
        for it in items:
            if it.launch_ts <= now_ts:
                launcher(it, now_ts)
    futuro = [i.launch_ts for i in items if i.launch_ts > now_ts]
    return items, (min(futuro) if futuro else None)


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

def sleep_until(ts: float, sd: SdNotify, step: float = 15.0) -> None:
    """Dorme até `ts` em fatias curtas, a avisar o watchdog do systemd."""
    while True:
        sd.watchdog()
        left = ts - time.time()
        if left <= 0:
            return
        time.sleep(min(step, left))


def run_daemon() -> int:
    socket.setdefaulttimeout(30)                              # nenhum pedido pendura o ciclo
    sd = SdNotify()
    poll_s = float(app_config().get("sheets_polling_interval_minutes", 5)) * 60
    snap, from_cache, last_poll = None, False, 0.0
    log.info("Scheduler (daemon) a arrancar; leitura da Sheet a cada %.0f s", poll_s)
    sd.ready()
    while True:
        try:
            now = time.time()
            if snap is None or now - last_poll >= poll_s:
                snap, from_cache = read_config()
                last_poll = now
            if snap is None:
                sd.status("sem Sheet e sem cache")
                sleep_until(now + 60, sd)
                continue
            items, next_launch = cycle(snap, from_cache, now)
            sd.status(f"{len(items)} perna(s) no plano" + (" (config da cache)" if from_cache else ""))
            wake = min(t for t in (next_launch, last_poll + poll_s) if t is not None)
            sleep_until(max(wake, now + 1), sd)
        except Exception as e:  # noqa: BLE001 — o daemon nunca morre calado nem em ciclo apertado
            log.exception("Erro no ciclo do scheduler: %s", e)
            notify_once(f"scheduler-cycle-{type(e).__name__}", "Erro no scheduler",
                        f"{type(e).__name__}: {e}. Vou tentar de novo dentro de 30 s.", cooldown_s=3600, logger=log)
            sleep_until(time.time() + 30, sd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scheduler das compras (daemon)")
    ap.add_argument("--once", action="store_true", help="um único ciclo e sai")
    ap.add_argument("--plan-only", action="store_true", help="mostra o plano; não lança, não notifica, não grava estado")
    args = ap.parse_args()
    if not (args.once or args.plan_only):
        return run_daemon()

    snap, from_cache = read_config()
    if snap is None:
        log.error("Sem Sheet e sem cache: nada a planear.")
        return 1
    items, _ = cycle(snap, from_cache, time.time(), plan_only=args.plan_only)
    for it in items:
        log.info("[plano] %s comboio %s: disparo %s, arranque do processo %s", it.leg.key, it.leg.train,
                 it.leg.fire.isoformat(), datetime.fromtimestamp(it.launch_ts, TZ).strftime("%d/%m %H:%M:%S"))
    log.info("Resumo: %d perna(s) no plano%s", len(items), " [config da cache]" if from_cache else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
