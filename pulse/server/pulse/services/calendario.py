"""Google Calendar no Pulse (ADR-049): agenda de várias contas, num só formato.

Regras: eventos cancelados e recusados não aparecem; um evento de vários dias aparece em cada dia que ocupa (nos de dia inteiro a
data final do Google é exclusiva e aqui passa a inclusiva); as horas mostram-se na hora local do Pulse. Uma conta que falha não
derruba as outras: vem na lista `contas` com o seu estado.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pulse import google_api as g
from pulse.accounts import ContaErro

MAX_DIAS = 62
MAX_POR_CALENDARIO = 250
CACHE_CALENDARIOS_S = 600
_calendarios_cache: dict[int, tuple[float, list[dict]]] = {}


def _sem_titulo(s: str | None) -> str:
    return (s or "").strip() or "(sem título)"


def evento_json(ev: dict, conta: dict, cal: dict, tz: ZoneInfo) -> dict | None:
    """Um evento da API → o formato do Pulse (ou None se cancelado/recusado/ilegível)."""
    if ev.get("status") == "cancelled":
        return None
    if any(a.get("self") and a.get("responseStatus") == "declined" for a in ev.get("attendees", [])):
        return None
    ini, fim = ev.get("start", {}), ev.get("end", {})
    try:
        if "date" in ini:
            data = date.fromisoformat(ini["date"])
            data_fim = date.fromisoformat(fim.get("date", ini["date"])) - timedelta(days=1)         # o fim do Google é exclusivo
            hora_ini = hora_fim = None
            dia_inteiro = True
        else:
            a = datetime.fromisoformat(ini["dateTime"]).astimezone(tz)
            b = datetime.fromisoformat(fim.get("dateTime", ini["dateTime"])).astimezone(tz)
            data, data_fim = a.date(), b.date() if b > a else a.date()
            if b.time() == datetime.min.time() and b > a:
                data_fim = (b - timedelta(minutes=1)).date()                                         # termina à meia-noite: não ocupa o dia seguinte
            hora_ini, hora_fim, dia_inteiro = a.strftime("%H:%M"), b.strftime("%H:%M"), False
    except (KeyError, ValueError):
        return None
    if data_fim < data:
        data_fim = data
    return {"id": ev["id"], "conta": conta["id"], "contaEmail": conta["email"], "calendario": cal["id"], "calendarioNome": cal["nome"], "cor": cal.get("cor"),
            "titulo": _sem_titulo(ev.get("summary")), "data": data.isoformat(), "dataFim": data_fim.isoformat(), "inicio": hora_ini, "fim": hora_fim,
            "diaInteiro": dia_inteiro, "local": (ev.get("location") or "")[:200], "descricao": (ev.get("description") or "")[:500],
            "link": ev.get("htmlLink") or "", "podeEditar": cal.get("podeEditar", False)}


def calendarios(api: g.GoogleApi, conta: dict) -> list[dict]:
    """Os calendários visíveis da conta (os «selecionados» na Google), com cache curta."""
    t = time.monotonic()
    c = _calendarios_cache.get(conta["id"])
    if c and t - c[0] < CACHE_CALENDARIOS_S:
        return c[1]
    _, r = api.pedir(conta["id"], conta["refresh"], "GET", f"{g.CALENDAR}/users/me/calendarList", {"minAccessRole": "reader", "maxResults": 50})
    lista = [{"id": x["id"], "nome": x.get("summaryOverride") or x.get("summary") or x["id"], "cor": x.get("backgroundColor"), "principal": bool(x.get("primary")),
              "podeEditar": x.get("accessRole") in ("owner", "writer")} for x in (r or {}).get("items", []) if x.get("selected") or x.get("primary")]
    _calendarios_cache[conta["id"]] = (t, lista)
    return lista


def esquecer_calendarios(conta: int) -> None:
    _calendarios_cache.pop(conta, None)


def _limites(de: date, ate: date, tz: ZoneInfo) -> tuple[str, str]:
    a = datetime(de.year, de.month, de.day, tzinfo=tz)
    b = datetime(ate.year, ate.month, ate.day, tzinfo=tz) + timedelta(days=1)
    return a.isoformat(), b.isoformat()


def _de_uma_conta(api: g.GoogleApi, conta: dict, de: date, ate: date, tz: ZoneInfo) -> list[dict]:
    a, b = _limites(de, ate, tz)
    out = []
    for cal in calendarios(api, conta):
        _, r = api.pedir(conta["id"], conta["refresh"], "GET", f"{g.CALENDAR}/calendars/{_q(cal['id'])}/events",
                         {"timeMin": a, "timeMax": b, "singleEvents": "true", "orderBy": "startTime", "maxResults": MAX_POR_CALENDARIO})
        for ev in (r or {}).get("items", []):
            e = evento_json(ev, conta, cal, tz)
            if e:
                out.append(e)
    return out


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


def agenda(api: g.GoogleApi, contas: list[dict], de: date, ate: date, tz: ZoneInfo) -> dict:
    """Os eventos entre duas datas (inclusive), por dia, de todas as contas. Devolve também o estado de cada conta e os calendários."""
    if ate < de or (ate - de).days + 1 > MAX_DIAS:
        raise ContaErro(400, "intervalo_invalido", f"intervalo inválido (no máximo {MAX_DIAS} dias)")
    estados, eventos = [], []

    def uma(c):
        try:
            return c, _de_uma_conta(api, c, de, ate, tz), None
        except g.GoogleErro as e:
            return c, [], e
    ativas = [c for c in contas if c["estado"] == "ok"]
    with ThreadPoolExecutor(max_workers=max(len(ativas), 1)) as pool:
        resultados = list(pool.map(uma, ativas))
    for c in contas:
        if c["estado"] != "ok":
            estados.append({"id": c["id"], "email": c["email"], "estado": "reautorizar", "erro": "Volta a ligar esta conta."})
    for c, evs, erro in resultados:
        if erro is None:
            eventos.extend(evs); estados.append({"id": c["id"], "email": c["email"], "estado": "ok"})
        else:
            estados.append({"id": c["id"], "email": c["email"], "estado": "reautorizar" if erro.reautorizar else "erro", "erro": str(erro)})
    dias: dict[str, list[dict]] = {}
    d = de
    while d <= ate:
        dias[d.isoformat()] = []
        d += timedelta(days=1)
    for e in eventos:
        inicio, fim = date.fromisoformat(e["data"]), date.fromisoformat(e["dataFim"])
        k = max(inicio, de)
        while k <= min(fim, ate):
            dias[k.isoformat()].append(e)
            k += timedelta(days=1)
    for lista in dias.values():
        lista.sort(key=lambda e: (not e["diaInteiro"], e["inicio"] or "", e["titulo"].lower()))              # dia inteiro primeiro, depois por hora
    ordem = {c["id"]: i for i, c in enumerate(contas)}
    estados.sort(key=lambda x: ordem.get(x["id"], 99))
    cals = [{"conta": c["id"], **cal} for c in ativas for cal in _calendarios_cache.get(c["id"], (0, []))[1]]
    return {"de": de.isoformat(), "ate": ate.isoformat(), "contas": estados, "calendarios": cals, "dias": [{"data": k, "eventos": v} for k, v in dias.items()]}


def hoje(api: g.GoogleApi, contas: list[dict], dia: date, tz: ZoneInfo, limite: int = 5, agora: datetime | None = None) -> dict:
    """O cartão do Hoje: os próximos `limite` eventos, sejam de que dia forem (já com a data). Os de hoje que já acabaram não contam.
    Procura primeiro nas próximas duas semanas e só alarga (até ao máximo da agenda) se faltarem eventos."""
    agora = agora or datetime.now(tz)
    hora = agora.strftime("%H:%M") if agora.date() == dia else "00:00"
    proximos: list[dict] = []
    vistos: set[tuple] = set()
    com_problemas: list[dict] = []
    for dias in (14, MAX_DIAS):
        a = agenda(api, contas, dia, dia + timedelta(days=dias - 1), tz)
        com_problemas = [c for c in a["contas"] if c["estado"] != "ok"]
        proximos, vistos = [], set()
        for d in a["dias"]:
            for e in d["eventos"]:
                chave = (e["conta"], e["calendario"], e["id"])
                if chave in vistos or (d["data"] == dia.isoformat() and not e["diaInteiro"] and (e["fim"] or "") <= hora and e["dataFim"] == d["data"]):
                    continue
                vistos.add(chave)
                proximos.append({**e, "data": max(d["data"], e["data"])})    # um evento de vários dias aparece na 1.ª data em que conta
        if len(proximos) >= limite or com_problemas:
            break
    return {"eventos": proximos[:limite], "total": len(proximos), "contas": len(contas), "comProblemas": com_problemas}


# --- escrever ----------------------------------------------------------------------------------------------------------------

def _corpo(tz: ZoneInfo, titulo: str | None, data: date | None, data_fim: date | None, inicio: str | None, fim: str | None,
           local: str | None, descricao: str | None, completo: bool) -> dict:
    """O corpo da API. `completo`: criar (tudo obrigatório) ou editar (só o que veio). Horas 'HH:MM' locais; sem horas = dia inteiro."""
    corpo: dict = {}
    if titulo is not None:
        corpo["summary"] = titulo.strip()
    if local is not None:
        corpo["location"] = local.strip()
    if descricao is not None:
        corpo["description"] = descricao.strip()
    if data is not None:
        ate = data_fim or data
        if ate < data:
            raise ContaErro(400, "datas_invalidas", "a data final é anterior à inicial")
        if inicio and fim:
            a, b = datetime.fromisoformat(f"{data.isoformat()}T{inicio}"), datetime.fromisoformat(f"{ate.isoformat()}T{fim}")
            if b <= a:
                raise ContaErro(400, "horas_invalidas", "o fim tem de ser depois do início")
            corpo["start"] = {"dateTime": a.isoformat(), "timeZone": str(tz)}
            corpo["end"] = {"dateTime": b.isoformat(), "timeZone": str(tz)}
        elif inicio or fim:
            raise ContaErro(400, "horas_invalidas", "indica o início e o fim, ou nenhum (dia inteiro)")
        else:
            corpo["start"] = {"date": data.isoformat()}
            corpo["end"] = {"date": (ate + timedelta(days=1)).isoformat()}                # o fim do Google é exclusivo
    elif completo:
        raise ContaErro(400, "parametros_invalidos", "falta a data")
    return corpo


def _calendario_editavel(api: g.GoogleApi, conta: dict, calendario: str) -> dict:
    for c in calendarios(api, conta):
        if c["id"] == calendario or (calendario == "primary" and c["principal"]):
            if not c["podeEditar"]:
                raise ContaErro(403, "calendario_so_leitura", "este calendário é só de leitura")
            return c
    raise ContaErro(404, "nao_encontrado", "calendário inexistente")


def criar(api: g.GoogleApi, conta: dict, tz: ZoneInfo, calendario: str, titulo: str, data: date, data_fim: date | None, inicio: str | None, fim: str | None,
          local: str | None, descricao: str | None) -> dict:
    cal = _calendario_editavel(api, conta, calendario)
    corpo = _corpo(tz, titulo, data, data_fim, inicio, fim, local, descricao, True)
    _, r = api.pedir(conta["id"], conta["refresh"], "POST", f"{g.CALENDAR}/calendars/{_q(cal['id'])}/events", None, corpo)
    return evento_json(r, conta, cal, tz) or {"id": (r or {}).get("id", "")}


def editar(api: g.GoogleApi, conta: dict, tz: ZoneInfo, calendario: str, evento: str, titulo: str | None, data: date | None, data_fim: date | None,
           inicio: str | None, fim: str | None, local: str | None, descricao: str | None) -> dict:
    cal = _calendario_editavel(api, conta, calendario)
    corpo = _corpo(tz, titulo, data, data_fim, inicio, fim, local, descricao, False)
    if not corpo:
        raise ContaErro(400, "sem_alteracoes", "nada para alterar")
    _, r = api.pedir(conta["id"], conta["refresh"], "PATCH", f"{g.CALENDAR}/calendars/{_q(cal['id'])}/events/{_q(evento)}", None, corpo)
    return evento_json(r, conta, cal, tz) or {"id": evento}


def apagar(api: g.GoogleApi, conta: dict, tz: ZoneInfo, calendario: str, evento: str) -> dict:
    """Apaga o evento e devolve o que ele era (para o «Desfazer» o voltar a criar)."""
    cal = _calendario_editavel(api, conta, calendario)
    url = f"{g.CALENDAR}/calendars/{_q(cal['id'])}/events/{_q(evento)}"
    _, antes = api.pedir(conta["id"], conta["refresh"], "GET", url)
    api.pedir(conta["id"], conta["refresh"], "DELETE", url)
    return evento_json(antes or {}, conta, cal, tz) or {"id": evento}
