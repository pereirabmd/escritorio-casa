"""A previsão do tempo do cartão do Hoje e do ecrã Tempo (ADR-092): Open-Meteo (gratuito, sem chave), pedida pelo servidor.

O telemóvel (ou o browser) manda só as coordenadas, arredondadas a 2 casas (cerca de 1 km): o servidor faz o pedido, guarda-o em cache 30 min
(pedidos iguais de qualquer aparelho partilham-no; se a Open-Meteo falhar serve-se a cache velha até 6 h) e devolve já em pt-PT. As
coordenadas nunca vão para os registos. `transporte` existe para os testes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

URL = "https://api.open-meteo.com/v1/forecast"
PADRAO = (40.64, -8.65)                  # Aveiro: o que se mostra quando o aparelho não dá a localização
CACHE_S = 1800
CACHE_VELHA_S = 6 * 3600
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
DIAS_CURTOS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


class TempoIndisponivel(Exception):
    pass


def _http(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Pulse/1.0 (uso doméstico)", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read(500_000))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise TempoIndisponivel("a Open-Meteo não respondeu") from e


def estado_do_ceu(codigo: int | None, dia: bool = True) -> tuple[str, str]:
    """Código WMO (usado pela Open-Meteo) → (ícone, descrição em pt-PT). Os ícones: sol, lua, pouco_nublado, nublado, nevoeiro, chuva, aguaceiros, neve, trovoada."""
    c = -1 if codigo is None else int(codigo)
    if c == 0:
        return ("sol", "Céu limpo") if dia else ("lua", "Céu limpo")
    if c in (1, 2):
        return "pouco_nublado", "Pouco nublado" if c == 1 else "Parcialmente nublado"
    if c == 3:
        return "nublado", "Nublado"
    if c in (45, 48):
        return "nevoeiro", "Nevoeiro"
    if c in (51, 53, 55, 56, 57):
        return "chuva", "Chuvisco"
    if c in (61, 63, 65, 66, 67):
        return "chuva", "Chuva fraca" if c == 61 else "Chuva" if c == 63 else "Chuva forte"
    if c in (71, 73, 75, 77, 85, 86):
        return "neve", "Neve"
    if c in (80, 81, 82):
        return "aguaceiros", "Aguaceiros"
    if c in (95, 96, 99):
        return "trovoada", "Trovoada"
    return "nublado", "Tempo variável"


def _hm(iso: str) -> str:
    return iso[11:16] if len(iso) >= 16 else ""


def _num(v, casas: int = 1):
    return None if v is None else round(float(v), casas)


class Tempo:
    def __init__(self, transporte=None, agora=time.time):
        self.transporte, self.agora = transporte or _http, agora
        self._cache: dict[tuple, tuple[float, dict]] = {}

    @staticmethod
    def arredondar(lat: float | None, lon: float | None) -> tuple[float, float, bool]:
        """(lat, lon, é_do_aparelho): sem coordenadas válidas usa-se Aveiro."""
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return PADRAO[0], PADRAO[1], False
        return round(lat, 2), round(lon, 2), True

    def previsao(self, lat: float | None, lon: float | None, agora: datetime) -> dict:
        la, lo, real = self.arredondar(lat, lon)
        chave = (la, lo)
        t = self.agora()
        hit = self._cache.get(chave)
        if hit and t - hit[0] < CACHE_S:
            bruto = hit[1]
        else:
            q = urllib.parse.urlencode({
                "latitude": la, "longitude": lo, "timezone": "Europe/Lisbon", "forecast_days": 6, "wind_speed_unit": "kmh",
                "current": "temperature_2m,weather_code,is_day,wind_speed_10m",
                "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"})
            try:
                bruto = self.transporte(f"{URL}?{q}")
                if not isinstance(bruto, dict) or "current" not in bruto:
                    raise TempoIndisponivel("resposta inesperada da Open-Meteo")
                self._cache[chave] = (t, bruto)
                self._cache = {k: v for k, v in self._cache.items() if t - v[0] < CACHE_VELHA_S}
            except TempoIndisponivel:
                if hit and t - hit[0] < CACHE_VELHA_S:
                    bruto = hit[1]                                  # a cache velha é melhor do que nada
                else:
                    raise
        return self._formatar(bruto, real, agora)

    @staticmethod
    def _formatar(b: dict, real: bool, agora: datetime) -> dict:
        cur, hor, dia = b.get("current", {}), b.get("hourly", {}), b.get("daily", {})
        e_dia = bool(cur.get("is_day", 1))
        icone, desc = estado_do_ceu(cur.get("weather_code"), e_dia)
        datas = dia.get("time", [])

        def d(i: int) -> dict:
            ic, ds = estado_do_ceu((dia.get("weather_code") or [None] * 9)[i], True)
            data = datas[i]
            dd = datetime.fromisoformat(data)
            return {"data": data, "diaSemana": DIAS[dd.weekday()], "diaCurto": DIAS_CURTOS[dd.weekday()], "icone": ic, "descricao": ds,
                    "max": _num(dia["temperature_2m_max"][i]), "min": _num(dia["temperature_2m_min"][i]),
                    "chuva": (dia.get("precipitation_probability_max") or [None] * 9)[i],
                    "nascer": _hm(dia["sunrise"][i]) if dia.get("sunrise") else "", "poer": _hm(dia["sunset"][i]) if dia.get("sunset") else ""}
        dias = [d(i) for i in range(min(len(datas), 6))]
        agora_iso = agora.replace(minute=0, second=0, microsecond=0, tzinfo=None).isoformat(timespec="minutes")
        horas = []
        for i, t in enumerate(hor.get("time", [])):
            if t >= agora_iso and len(horas) < 24:
                ic, _ = estado_do_ceu(hor["weather_code"][i], bool(hor.get("is_day", [1] * 999)[i]))
                horas.append({"hora": _hm(t), "dia": t[:10], "temp": _num(hor["temperature_2m"][i]), "chuva": (hor.get("precipitation_probability") or [None] * 999)[i], "icone": ic})
        hoje = dias[0] if dias else None
        return {"localizacao": "dispositivo" if real else "omissao", "atualizadoEm": agora.isoformat(timespec="minutes"),
                "agora": {"temp": _num(cur.get("temperature_2m")), "icone": icone, "descricao": desc, "vento": _num(cur.get("wind_speed_10m"), 0), "dia": e_dia},
                "hoje": hoje, "horas": horas, "dias": dias}
