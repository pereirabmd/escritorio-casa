"""Validação da Config contra o horário oficial da CP (PLANO_FINAL.md secção 2 e 3.10.3).

`GET /travel-api/trains/<comboio>/timetable/<data>` funciona SEM login (só as
chaves da app) e devolve `trainStops` com estação e horas. Serve para apanhar,
dias antes do disparo, um comboio que não circula nessa data, que não vai de X
para Y, ou cuja hora de partida não bate com a da Config — em vez de o
descobrir no instante crítico.

O aviso é consultivo: a compra continua a ser feita pelo nº do comboio.
"""

from __future__ import annotations

import dataclasses
import re
import time
from datetime import date, timedelta
from typing import Any, Callable

import common
from common import Leg, station_code
from cp_ticket import X_API_KEY_TRAVEL, CPClient, CPError, pick_trip, trip_sections

log = common.get_logger("timetable")

CACHE_TTL_S = 6 * 3600
ANCHOR_TTL_S = 24 * 3600


def fetch_timetable(train: int, d: date) -> dict | None:
    """Horário oficial de um comboio numa data; None se a CP disser que não existe."""
    client = CPClient(access_token="")
    r = client.request("GET", f"/travel-api/trains/{train}/timetable/{d.isoformat()}",
                       api_key=X_API_KEY_TRAVEL, with_token=False, timeout=(4.0, 10.0))
    if r.status in (400, 404):
        return None
    if not r.ok or not isinstance(r.body, dict):
        raise RuntimeError(f"HTTP {r.status} no timetable do comboio {train}")
    return r.body


def fetch_journeys(leg: Leg) -> dict:
    """Pesquisa de horários entre as estações da perna (não exige login)."""
    return CPClient("").search_journeys(station_code(leg.origin) or "", station_code(leg.destination) or "",
                                        leg.date.isoformat())


def journey_with_train(leg: Leg, journeys: Callable[[Leg], dict] = fetch_journeys) -> dict | None:
    """A viagem (origem -> destino) que inclui este comboio, ou None se não existir. Conhece os
    transbordos (ex.: 511 até Pampilhosa e 4609 até Aveiro). Se a rede falhar, propaga: "sem informação"."""
    data = journeys(leg)
    try:
        return pick_trip(data, train_number=leg.train, require_saleable=False)
    except RuntimeError:
        return None


def check_via_journeys(leg: Leg, journeys: Callable[[Leg], dict] = fetch_journeys) -> str | None:
    """Segunda fonte, quando o `timetable` não responde: o `journeys` lista todos os comboios
    do dia entre as duas estações. Se o comboio não consta, é problema."""
    label = f"comboio {leg.train} em {leg.date:%d/%m}"
    data = journeys(leg)          # se a rede falhar, propaga: "sem informação", nunca "não existe"
    try:
        trip = pick_trip(data, train_number=leg.train, require_saleable=False)
    except RuntimeError:
        return (f"o {label} não consta dos horários entre {leg.origin.replace('_', ' ')} "
                f"e {leg.destination.replace('_', ' ')}")
    return None     # o `journeys` só dá a hora de embarque: a da Config pode ser a da 1.ª estação, não se compara


def check_leg(leg: Leg, fetch: Callable[[int, date], dict | None] = fetch_timetable,
              journeys: Callable[[Leg], dict] = fetch_journeys) -> str | None:
    """Devolve o problema encontrado (texto) ou None se tudo bate certo.

    Usa o `timetable`; se este falhar, confirma pelo `journeys`. Só levanta exceção se
    nenhuma das duas fontes responder (o chamador trata como "sem informação").
    """
    try:
        tt = fetch(leg.train, leg.date)
    except (CPError, RuntimeError, ValueError, TypeError):
        return check_via_journeys(leg, journeys)
    label = f"comboio {leg.train} em {leg.date:%d/%m}"
    stops = (tt or {}).get("trainStops") or []
    if not stops:
        return f"o {label} não consta do horário oficial (não circula nessa data?)"
    codes = [(s.get("station") or {}).get("code") for s in stops]
    org, dst = station_code(leg.origin), station_code(leg.destination)
    if org not in codes:
        # pode ser a 2.ª secção de uma viagem com transbordo: a pesquisa de horários decide
        if journey_with_train(leg, journeys) is not None:
            return None
        return f"o {label} não para em {leg.origin.replace('_', ' ')}"
    i = codes.index(org)
    if dst not in codes[i + 1:]:
        # o comboio não chega sozinho ao destino: só é problema se também não houver viagem com transbordo
        if journey_with_train(leg, journeys) is None:
            return (f"o {label} não segue de {leg.origin.replace('_', ' ')} "
                    f"para {leg.destination.replace('_', ' ')}, nem com transbordo")
    dep = str(stops[i].get("departure") or "")[:5]
    first = str(stops[0].get("departure") or "")[:5]
    if leg.hhmm not in {h for h in (dep, first) if h}:      # vale a hora da 1.ª estação OU a de embarque
        if i > 0 and first and first != dep:
            return (f"o {label} parte de {(stops[0].get('station') or {}).get('designation') or 'a 1.ª estação'} "
                    f"às {first} e de {leg.origin.replace('_', ' ')} às {dep} segundo a CP, "
                    f"mas a Config tem {leg.hhmm}")
        return (f"o {label} parte de {leg.origin.replace('_', ' ')} às {dep} segundo a CP, "
                f"mas a Config tem {leg.hhmm}")
    return None


def anchor_from_stops(leg: Leg, stops: list[dict]) -> tuple[str, date, str, str, date] | None:
    """(hora e data da partida na 1.ª estação, nome dessa estação, hora e data de embarque).

    A hora da Config é normalmente a da 1.ª estação (a que abre a venda); aceita-se também a de
    embarque. Se o comboio passa a meia-noite entre as duas, a data da Config é a da estação cuja hora
    foi escrita (a 1.ª estação: data do início da viagem; senão: a do embarque).
    """
    codes = [(s.get("station") or {}).get("code") for s in stops]
    org = station_code(leg.origin)
    if not stops or org not in codes:
        return None
    first = str(stops[0].get("departure") or "")[:5]
    if not re.fullmatch(r"\d{2}:\d{2}", first):
        return None
    board = str(stops[codes.index(org)].get("departure") or "")[:5] or leg.hhmm
    wraps = timedelta(days=1) if board < first else timedelta(0)
    if leg.hhmm == first and first != board:          # Bruno escreveu a hora da 1.ª estação
        start, board_date = leg.date, leg.date + wraps
    else:                                             # escreveu a de embarque
        start, board_date = leg.date - wraps, leg.date
    return first, start, (stops[0].get("station") or {}).get("designation") or "", board, board_date


def anchor_for(leg: Leg, fetch: Callable[[int, date], dict | None] = fetch_timetable
               ) -> tuple[str, date, str, str, date] | None:
    """Âncora do disparo (PLANO_FINAL 3.11). Cache de 24 h; se a CP falhar, mantém o último valor
    conhecido em vez de voltar à hora da Config. None = sem informação."""
    path = common._state_file("anchors.json")
    cache = common._read_json(path, {})
    key = f"{leg.key}|{leg.train}|{leg.origin}|{leg.hhmm}"
    hit, now = cache.get(key), time.time()

    def unpack(h: dict) -> tuple[str, date, str, str, date]:
        return (h["hhmm"], date.fromisoformat(h["date"]), h.get("station", ""),
                h.get("board", h["hhmm"]), date.fromisoformat(h.get("board_date", h["date"])))

    if hit and now - hit["ts"] < ANCHOR_TTL_S:
        return unpack(hit)
    try:
        res = anchor_from_stops(leg, ((fetch(leg.train, leg.date) or {}).get("trainStops") or []))
    except (CPError, RuntimeError, ValueError, TypeError) as e:
        log.warning("Sem informação da 1.ª estação de %s: %s", leg.key, type(e).__name__)
        res = None
    if res:
        cache = {k: v for k, v in cache.items() if now - v["ts"] < 7 * 86400}
        cache[key] = {"ts": now, "hhmm": res[0], "date": res[1].isoformat(), "station": res[2],
                      "board": res[3], "board_date": res[4].isoformat()}
        common._write_json_atomic(path, cache)
        return res
    return unpack(hit) if hit else None


def apply_anchor(leg: Leg, fetch: Callable[[int, date], dict | None] = fetch_timetable) -> Leg:
    """A mesma perna, com o disparo ancorado à 1.ª estação e a hora de embarque real (se se souber)."""
    a = anchor_for(leg, fetch)
    return dataclasses.replace(leg, anchor=a[0], anchor_date=a[1], board=a[3], board_date=a[4]) if a else leg


def check_leg_cached(leg: Leg, fetch: Callable[[int, date], dict | None] = fetch_timetable,
                     journeys: Callable[[Leg], dict] = fetch_journeys) -> tuple[str | None, bool]:
    """(problema, consultou_agora). Cache de 6h para não repetir pedidos de 5 em 5 minutos."""
    path = common._state_file("timetable_checks.json")
    cache = common._read_json(path, {})
    key = f"{leg.key}|{leg.train}|{leg.origin}|{leg.destination}|{leg.hhmm}"
    hit = cache.get(key)
    now = time.time()
    if hit and now - hit["ts"] < CACHE_TTL_S:
        return hit["problem"], False
    try:
        problem = check_leg(leg, fetch, journeys)
    except (CPError, RuntimeError, ValueError, TypeError) as e:
        log.warning("Sem informação do horário oficial para %s: %s", leg.key, type(e).__name__)
        return None, False
    cache = {k: v for k, v in cache.items() if now - v["ts"] < 2 * CACHE_TTL_S}
    cache[key] = {"ts": now, "problem": problem}
    common._write_json_atomic(path, cache)
    return problem, True
