"""Regras do módulo RTO (porta fiel da app dedicada `RTO/index.html`): feriados, notas (férias, astreinte, suspensão),
totais e saldo face à quota anual, estado de hoje e próxima mudança. Funções puras: a data de hoje entra por parâmetro.

Marcas dos dias: `T` = Escritório, `C` = Casa. Um dia de férias nunca conta para T/C; cada dia de astreinte vale -1 dia em casa
(crédito); durante a «RTO suspensão» os dias em casa não contam no saldo condicional.
"""

from __future__ import annotations

import math
import unicodedata
from datetime import date, timedelta

QUOTA_ANUAL = 120
MAX_DIAS_NOTA = 3700          # uma nota não pode gerar mais dias do que isto (contra intervalos absurdos)


def pascoa(ano: int) -> date:
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados(ano: int) -> dict[str, str]:
    p = pascoa(ano)
    fixos = [(1, 1, "Ano Novo"), (4, 25, "Dia da Liberdade"), (5, 1, "Dia do Trabalhador"), (6, 10, "Dia de Portugal"),
             (6, 13, "Santo António (Lisboa)"), (8, 15, "Assunção de Nossa Senhora"), (10, 5, "Implantação da República"),
             (11, 1, "Todos os Santos"), (12, 1, "Restauração da Independência"), (12, 8, "Imaculada Conceição"), (12, 25, "Natal")]
    out = {date(ano, m, d).isoformat(): nome for m, d, nome in fixos}
    out[(p - timedelta(days=2)).isoformat()] = "Sexta-feira Santa"
    out[(p + timedelta(days=60)).isoformat()] = "Corpo de Deus"
    return out


def _cat(s: str | None) -> str:
    n = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(ch for ch in n if unicodedata.category(ch) != "Mn").strip()


def categoria_de(nota: dict) -> str | None:
    """'ferias' | 'astreinte' | 'suspensao' | None, pela categoria (tolera acentos e «astrainte»)."""
    c = _cat(nota.get("categoria"))
    if "suspens" in c:
        return "suspensao"
    if "feria" in c:
        return "ferias"
    if "astr" in c:
        return "astreinte"
    return None


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


def intervalo(nota: dict) -> tuple[date, date] | None:
    ini = _d(nota.get("dataInicio")) or _d(nota.get("dataFim"))
    if ini is None:
        return None
    fim = _d(nota.get("dataFim")) or ini
    return (ini, fim) if fim >= ini and (fim - ini).days < MAX_DIAS_NOTA else None


def classificar(notas: list[dict]) -> dict:
    """Conjuntos de datas ISO de férias, astreinte e suspensão + a letra que cada dia mostra no calendário (`marcas`)."""
    ferias: set[str] = set(); astreinte: set[str] = set(); suspensao: set[str] = set(); marcas: dict[str, str] = {}
    for n in notas:
        cat = categoria_de(n)
        iv = intervalo(n)
        if cat is None or iv is None:
            continue
        d = iv[0]
        while d <= iv[1]:
            iso, fds = d.isoformat(), d.weekday() >= 5
            if cat == "suspensao":
                suspensao.add(iso)
            elif cat == "ferias":
                ferias.add(iso)                       # férias ao fim de semana também nunca entram nos cálculos
                if not fds:
                    marcas[iso] = "F"
            else:
                astreinte.add(iso)
                marcas[iso] = "A"                     # a astreinte aparece mesmo ao fim de semana
            d += timedelta(days=1)
    return {"ferias": ferias, "astreinte": astreinte, "suspensao": suspensao, "marcas": marcas}


def _arred1(x: float) -> float:
    return math.floor(x * 10 + 0.5) / 10             # Math.round do JavaScript (meio para cima)


def totais(dias: dict[str, str], cls: dict, ano: int, hoje: date) -> dict:
    t = c = c_cond = 0
    for data, marca in dias.items():
        if int(data[:4]) != ano or data in cls["ferias"]:
            continue
        if marca == "T":
            t += 1
        elif marca == "C":
            c += 1
            if data not in cls["suspensao"]:
                c_cond += 1
    creditos = sum(1 for d in cls["astreinte"] if int(d[:4]) == ano and d not in cls["suspensao"])
    c_cond -= creditos
    ini, fim = date(ano, 1, 1), date(ano, 12, 31)
    dias_ano = (fim - ini).days + 1
    decorridos = 0 if hoje < ini else dias_ano if hoje > fim else (hoje - ini).days + 1
    quota = _arred1(QUOTA_ANUAL * decorridos / dias_ano)
    return {"T": t, "C": c, "CCondicional": c_cond, "creditosAstreinte": creditos, "decorridos": decorridos, "diasAno": dias_ano,
            "quotaAnual": QUOTA_ANUAL, "quotaProRata": quota, "saldo": _arred1(quota - c), "saldoCondicional": _arred1(quota - c_cond),
            "pctQuota": round(c / QUOTA_ANUAL * 100)}


def mensal(dias: dict[str, str], ferias: set[str], ano: int) -> list[dict]:
    """T e C por mês (12 posições), sem dias de férias."""
    out = [{"t": 0, "c": 0} for _ in range(12)]
    for data, marca in dias.items():
        if data[:4] != str(ano) or data in ferias:
            continue
        if marca in ("T", "C"):
            out[int(data[5:7]) - 1]["t" if marca == "T" else "c"] += 1
    return out


def estado_hoje(dias: dict[str, str], cls: dict, hoje: date) -> dict:
    iso = hoje.isoformat()
    marca, astr = dias.get(iso, ""), iso in cls["astreinte"]
    fer = feriados(hoje.year)
    if marca == "T":
        return {"estado": "escritorio", "astreinte": astr}
    if marca == "C":
        return {"estado": "casa", "astreinte": astr}
    if iso in cls["ferias"]:
        return {"estado": "ferias", "astreinte": False}
    if iso in fer:
        return {"estado": "feriado", "nome": fer[iso], "astreinte": False}
    if hoje.weekday() >= 5:
        return {"estado": "fim_de_semana", "astreinte": astr}
    if astr:
        return {"estado": "astreinte", "astreinte": True}
    return {"estado": "por_definir", "astreinte": False}


def proxima_mudanca(cls: dict, hoje: date) -> dict | None:
    """Próximo feriado ou início de férias já conhecido nos próximos 60 dias (nunca inventa T/C futuros)."""
    em_ferias = hoje.isoformat() in cls["ferias"]
    for i in range(1, 61):
        d = hoje + timedelta(days=i)
        iso = d.isoformat()
        fer = feriados(d.year)
        if iso in fer:
            return {"tipo": "feriado", "dias": i, "nome": fer[iso], "data": iso}
        if not em_ferias and iso in cls["ferias"]:
            return {"tipo": "ferias", "dias": i, "data": iso}
    return None


def visao(dias: dict[str, str], notas: list[dict], ano: int, hoje: date) -> dict:
    cls = classificar(notas)
    dez_anterior = mensal(dias, cls["ferias"], ano - 1)[11]
    return {
        "ano": ano, "quotaAnual": QUOTA_ANUAL,
        "feriados": {**feriados(ano - 1), **feriados(ano), **feriados(ano + 1)},         # três anos: navegar entre Dezembro e Janeiro não precisa de novo pedido
        "ferias": sorted(cls["ferias"]), "astreinte": sorted(cls["astreinte"]), "suspensao": sorted(cls["suspensao"]),
        "marcasNotas": cls["marcas"], "totais": totais(dias, cls, ano, hoje), "mensal": mensal(dias, cls["ferias"], ano),
        "dezembroAnterior": dez_anterior, "hoje": estado_hoje(dias, cls, hoje), "proximaMudanca": proxima_mudanca(cls, hoje),
    }


def dia_util_anterior(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def dia_util_seguinte(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d
