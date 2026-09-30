"""Verificação do horário oficial da CP para o editor da semana dos Bilhetes (ADR-068).

Consulta `travel-api/trains/<n>/timetable/<data>` (sem login, só as chaves públicas da app da CP, que ficam no servidor e nunca no telemóvel) e,
quando o comboio só faz parte da viagem (transbordo), a pesquisa `journeys`. É **consultiva**: nunca impede de guardar, como na PWA e no
`bilhetes_cp/scripts/timetable.py`, de que este ficheiro segue a lógica.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import date
from typing import Callable

API = "https://api-gateway.cp.pt/cp/services"
ESTACOES_BASE = {"aveiro": "94-38000", "lisboa_oriente": "94-31039"}
CACHE_S = 6 * 3600
Transporte = Callable[[str, str, dict, dict | None], tuple[int, object]]      # (método, url, cabeçalhos, corpo JSON) -> (código, JSON | None)


def chave_da_estacao(nome: str) -> str:
    return re.sub(r"[\s\-]+", "_", nome.strip().lower())


def _http(metodo: str, url: str, cabecalhos: dict, corpo: dict | None) -> tuple[int, object]:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None


class CpHorarios:
    def __init__(self, connect_id: str, connect_secret: str, api_key: str, estacoes_extra: str = "", transporte: Transporte | None = None, agora=time.time):
        self.chaves = (connect_id, connect_secret, api_key)
        self.estacoes = dict(ESTACOES_BASE)
        try:
            self.estacoes.update({chave_da_estacao(k): str(v) for k, v in (json.loads(estacoes_extra) if estacoes_extra else {}).items()})
        except (ValueError, AttributeError):
            pass
        self.transporte, self.agora = transporte or _http, agora
        self._cache: dict[tuple, tuple[float, object]] = {}

    @property
    def ligado(self) -> bool:
        return all(self.chaves)

    def _cab(self) -> dict:
        i, s, k = self.chaves
        return {"Accept": "application/json", "Content-Type": "application/json", "X-Api-Key": k, "x-cp-connect-id": i, "x-cp-connect-secret": s,
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Pulse/1.0"}

    def _com_cache(self, chave: tuple, obter):
        t = self.agora()
        hit = self._cache.get(chave)
        if hit and t - hit[0] < CACHE_S:
            return hit[1]
        r = obter()
        if r != "erro":                       # falhas de rede não ficam em cache
            self._cache = {k: v for k, v in self._cache.items() if t - v[0] < CACHE_S}
            self._cache[chave] = (t, r)
        return r

    def horario(self, comboio: int, d: date):
        """`{"stops": [...]}`, `"nenhum"` (a CP não tem esse comboio nessa data) ou `"erro"`."""
        def obter():
            codigo, corpo = self.transporte("GET", f"{API}/travel-api/trains/{comboio}/timetable/{d.isoformat()}", self._cab(), None)
            if codigo in (400, 404):
                return "nenhum"
            if codigo == 200 and isinstance(corpo, dict):
                return {"stops": corpo.get("trainStops") or []}
            return "erro"
        return self._com_cache(("tt", comboio, d), obter)

    def viagem_com_comboio(self, origem: str, destino: str, d: date, comboio: int):
        """A viagem (com transbordos) entre as estações que inclui este comboio: dict, `None` (não existe) ou `"erro"`."""
        def obter():
            corpo = {"arrivalStationCode": destino, "classes": [2], "configID": 200, "departureStationCode": origem, "lang": "PT",
                     "quantities": [{"quantity": 1, "type": 1}], "returnDate": None, "returnTimeLimit": {"endTime": "23:59", "limitType": 0, "startTime": "00:00"},
                     "saleableOnly": False, "searchType": 3, "services": [], "timeLimit": {"endTime": "23:59", "limitType": 0, "startTime": "00:00"},
                     "travelDate": d.isoformat(), "username": "sivNetticket"}
            codigo, r = self.transporte("POST", f"{API}/travel-api/journeys", self._cab(), corpo)
            if codigo != 200 or not isinstance(r, dict):
                return "erro"
            return next((t for t in (r.get("outwardTrip") or []) if any(s.get("trainNumber") == comboio for s in (t.get("travelSections") or []))), None)
        return self._com_cache(("jn", origem, destino, d, comboio), obter)


def _hm(v) -> str:
    return str(v or "")[:5]


def _dia(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def verificar(cp: CpHorarios, comboio: int, d: date, origem: str, destino: str, hora: str | None) -> dict:
    """O resultado para o editor: `estado` ∈ desligado | confirmado | preenchido | aviso | sem_informacao, `mensagem` em pt-PT e, se fizer sentido,
    `sugestaoHora` (a hora da 1.ª estação, a que abre a venda). Nunca levanta: qualquer falha da CP é «sem_informacao»."""
    if not cp.ligado:
        return {"estado": "desligado", "mensagem": ""}
    org, dst = cp.estacoes.get(chave_da_estacao(origem)), cp.estacoes.get(chave_da_estacao(destino))
    sem = {"estado": "sem_informacao", "mensagem": "Não foi possível confirmar o horário na CP agora."}
    tt = cp.horario(comboio, d)
    if tt == "nenhum":
        return {"estado": "aviso", "mensagem": f"A CP não tem o comboio {comboio} em {_dia(d)}."}
    if tt == "erro":
        return sem
    if not (org and dst):
        return {"estado": "sem_informacao", "mensagem": "Só sei confirmar viagens entre estações conhecidas (Aveiro e Lisboa Oriente)."}
    paragens = tt["stops"]
    codigos = [(p.get("station") or {}).get("code") for p in paragens]
    oi = codigos.index(org) if org in codigos else -1
    di = codigos.index(dst, oi + 1) if oi >= 0 and dst in codigos[oi + 1:] else -1
    if oi >= 0 and di >= 0:
        partida, chegada = _hm(paragens[oi].get("departure")), _hm(paragens[di].get("arrival"))
        primeira, nome1 = _hm(paragens[0].get("departure")), (paragens[0].get("station") or {}).get("designation") or ""
        info = (f"{nome1} {primeira} → " if oi > 0 else "") + f"{origem} {partida} → {destino} {chegada}"
        transbordo = False
    else:
        viagem = cp.viagem_com_comboio(org, dst, d, comboio)
        if viagem == "erro":
            return sem
        if viagem is None:
            return {"estado": "aviso", "mensagem": f"O comboio {comboio} não para em {origem}." if oi < 0 else f"O comboio {comboio} não segue de {origem} para {destino}."}
        secs = viagem.get("travelSections") or []
        primeira, nome1 = _hm(secs[0].get("departureTime")), (secs[0].get("departureStation") or {}).get("designation") or origem
        chegada = _hm(secs[-1].get("arrivalTime"))
        partida = _hm(paragens[oi].get("departure")) if oi >= 0 else primeira
        transbordo = len(secs) > 1
        info = f"{nome1} {primeira} → {destino} {chegada}" + (" (com transbordo)" if transbordo else "")
    base = {"primeira": {"estacao": nome1, "hora": primeira}, "partida": partida, "chegada": chegada, "transbordo": transbordo}
    if not hora:
        return {**base, "estado": "preenchido", "sugestaoHora": primeira or partida,
                "mensagem": f"Hora da partida do comboio ({nome1 or origem}) às {primeira or partida}: {info}."}
    if hora in {primeira, partida}:
        return {**base, "estado": "confirmado", "mensagem": f"Confirmado pela CP: {info}."}
    return {**base, "estado": "aviso", "sugestaoHora": primeira or partida,
            "mensagem": f"A CP indica {primeira} ({nome1}) e {partida} ({origem}); tens {hora}."}
