"""Vigilância do comboio nos últimos 30 minutos antes da partida (cron, cada minuto).

Para cada bilhete confirmado (aba Bilhetes) cuja partida caia nos próximos 30 minutos, consulta
o horário oficial do comboio (`timetable.fetch_timetable`, já usado em 3.10.3) e compara atraso,
cais e supressão com a última leitura. Só notifica quando algo **muda** — a primeira leitura da
janela fica só como referência, para não notificar sem haver alteração nenhuma.

Corre fora da janela sem fazer nada (sai logo, barato para correr a cada minuto):

    python scripts/live_delay.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import date

import common
import timetable
from common import get_logger, local_dt, norm_station, notify, notify_once, station_code

log = get_logger("live_delay")

WINDOW_S = 30 * 60


@dataclass(frozen=True)
class Watch:
    date: date
    train: int
    origin: str          # chave normalizada (ex.: lisboa_oriente)
    destination: str
    hhmm: str             # hora de embarque, como gravada na aba Bilhetes
    carriage: str
    seat: str

    @property
    def key(self) -> str:
        return f"{self.date.isoformat()}-{self.train}"

    @property
    def departure(self):
        return local_dt(self.date, self.hhmm)


def upcoming_watches(rows: list[list], now) -> list[Watch]:
    """Bilhetes cuja partida cai nos próximos 30 minutos (e ainda não partiu)."""
    out = []
    for r in rows:
        cells = list(r) + [""] * 8
        d = common.parse_sheet_date(cells[0])
        train = cells[1]
        hhmm = common.parse_sheet_time(cells[4]) or (str(cells[4])[:5] if cells[4] else None)
        if not d or not train or not hhmm:
            continue
        try:
            train = int(float(train))
        except (TypeError, ValueError):
            continue
        w = Watch(d, train, norm_station(cells[2]), norm_station(cells[3]), hhmm,
                  str(cells[5] or ""), str(cells[6] or ""))
        left = (w.departure - now).total_seconds()
        if 0 <= left <= WINDOW_S:
            out.append(w)
    return out


def find_stop(stops: list[dict], code: str | None) -> dict | None:
    for s in stops:
        if (s.get("station") or {}).get("code") == code:
            return s
    return None


def snapshot(watch: Watch, fetch=timetable.fetch_timetable) -> dict | None:
    """Estado atual do comboio na estação de embarque, ou None se não se conseguir apurar."""
    body = fetch(watch.train, watch.date)
    stops = (body or {}).get("trainStops") or []
    stop = find_stop(stops, station_code(watch.origin))
    if stop is None:
        return None
    return {
        "delay": stop.get("delay"),
        "platform": stop.get("platform"),
        "supression": bool(stop.get("supression")),
        "eta": stop.get("ETA"),
        "etd": stop.get("ETD"),
        "train_status": (body or {}).get("status"),
        "has_disruptions": bool((body or {}).get("hasDisruptions")),
    }


LABELS = {"delay": "atraso", "platform": "cais", "supression": "supressão",
          "eta": "chegada prevista", "etd": "partida prevista", "train_status": "estado",
          "has_disruptions": "perturbações"}


def describe_changes(old: dict, new: dict) -> list[str]:
    out = []
    for k, label in LABELS.items():
        if old.get(k) != new.get(k):
            ov, nv = old.get(k), new.get(k)
            fmt = lambda v: "sim" if v is True else "não" if v is False else (v if v not in (None, "") else "—")  # noqa: E731
            out.append(f"{label}: {fmt(ov)} → {fmt(nv)}")
    return out


def check_one(watch: Watch, cache: dict, now_ts: float) -> None:
    label = f"comboio {watch.train} ({watch.origin} → {watch.destination}, embarque {watch.hhmm})"
    try:
        snap = snapshot(watch)
    except Exception as e:  # noqa: BLE001 — nunca falha calado, mas sem inundar (cooldown)
        log.warning("Não consegui verificar %s: %s", label, type(e).__name__)
        notify_once(f"live-delay-fail-{watch.key}", f"Sem info em tempo real — {label}",
                    f"Não consegui consultar o horário oficial ({type(e).__name__}). "
                    "Continuo a tentar de minuto a minuto.", cooldown_s=600, logger=log)
        return
    if snap is None:
        log.warning("%s: sem paragem correspondente no horário oficial.", label)
        return

    prev = cache.get(watch.key)
    if prev is None:
        log.info("%s: primeira leitura da janela — %s", label, snap)
        cache[watch.key] = snap
        return
    changes = describe_changes(prev, snap)
    cache[watch.key] = snap
    if not changes:
        return
    urgent = snap["supression"] and not prev["supression"]
    title = ("Comboio suprimido — " if urgent else "Mudou algo no comboio — ") + label
    seat = f" · carruagem {watch.carriage}, lugar {watch.seat}" if watch.carriage or watch.seat else ""
    notify(title, "; ".join(changes) + seat, tags=["rotating_light"] if urgent else ["warning"], logger=log)
    log.info("%s: %s", label, "; ".join(changes))


def main() -> int:
    now = common.now_local()
    try:
        rows = common.get_store().read_tickets()
    except Exception as e:  # noqa: BLE001
        log.error("Não consegui ler a aba Bilhetes: %s: %s", type(e).__name__, e)
        notify_once("live-delay-sheet-fail", "Vigilância do comboio sem dados",
                    f"Não consegui ler a aba Bilhetes ({type(e).__name__}).", cooldown_s=1800, logger=log)
        return 1

    watches = upcoming_watches(rows, now)
    if not watches:
        return 0

    cache_path = common._state_file("live_delay.json")
    cache = common._read_json(cache_path, {})
    now_ts = time.time()
    keep = {w.key for w in watches}
    cache = {k: v for k, v in cache.items() if k in keep}  # limpa comboios já partidos
    for w in watches:
        check_one(w, cache, now_ts)
    common._write_json_atomic(cache_path, cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
