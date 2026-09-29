"""Regras dos Bilhetes CP (porta das da app `bilhetes_cp/`): viagens, bilhetes, passe, pedidos e registo.

Os dados vêm de `GET /bilhetes/dados` do `dados-api` (que lê a `bilhetes.db`, também escrita pelo Pi). Aqui só se junta e classifica:
- uma viagem tem estado `comprado` (há bilhete para a mesma data, comboio e hora), `por_comprar`, `inativa`, `em_curso` (já partiu e, pela
  estimativa, ainda não chegou) ou `passada`;
- a chegada **não está guardada** em lado nenhum: estima-se partida + `DURACAO_ESTIMADA_MIN` (a mesma regra do cartão «Próximo comboio»).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

DURACAO_ESTIMADA_MIN = 180
ESTACOES_BASE = ("Aveiro", "Lisboa Oriente")
MAX_ANTERIORES = 20
MAX_REGISTOS = 80
MAX_HISTORICO = 30


def segunda_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _inicio(v: dict) -> datetime:
    return datetime.fromisoformat(f"{v['data']}T{v['hora']}")


def _passe(p: dict, hoje: date) -> dict:
    """O servidor já calcula `dataExpira` e `diasRestantes`; aqui só o estado para a interface."""
    dias = p.get("diasRestantes")
    estado = "sem_data" if dias is None else "expirado" if dias < 0 else "hoje" if dias == 0 else "a_expirar" if dias <= 3 else "ok"
    validade = p.get("validadeDias") or 29
    pct = None if dias is None else max(0, min(100, round(dias / (validade + 1) * 100)))
    return {**p, "estado": estado, "percentagem": pct}


def _com_estado(v: dict, compras: dict, agora: datetime) -> dict:
    ini = _inicio(v)
    fim = ini + timedelta(minutes=DURACAO_ESTIMADA_MIN)
    c = compras.get((v["data"], v["comboio"], v["hora"]))
    if v["ativo"] != "SIM":
        estado = "inativa"
    elif fim < agora:
        estado = "passada"
    elif ini <= agora:
        estado = "em_curso"
    else:
        estado = "comprado" if c else "por_comprar"
    return {"id": v["id"], "data": v["data"], "hora": v["hora"], "origem": v["origem"], "destino": v["destino"], "comboio": v["comboio"],
            "ativo": v["ativo"] == "SIM", "estado": estado, "fimEstimado": fim.strftime("%H:%M"), "compra": c and {
                "carruagem": c["carruagem"], "lugar": c["lugar"], "referencia": c["referencia"]}}


def _bilhete(c: dict) -> dict:
    return {"id": c["id"], "data": c["data"], "hora": c["hora"], "origem": c["origem"], "destino": c["destino"], "comboio": c["comboio"],
            "carruagem": c["carruagem"], "lugar": c["lugar"], "referencia": c["referencia"]}


def visao(dados: dict, agora: datetime, semana: date | None = None) -> dict:
    """Tudo o que o ecrã precisa, calculado de uma vez. `semana` = a segunda-feira da semana em edição (por omissão, a próxima)."""
    hoje = agora.date()
    agora = agora.replace(tzinfo=None)
    compras = {(c["data"], c["comboio"], c["hora"]): c for c in dados.get("compras", [])}
    viagens = [_com_estado(v, compras, agora) for v in dados.get("viagens", [])]
    viagens.sort(key=lambda v: (v["data"], v["hora"], v["id"]))
    proximas = [v for v in viagens if v["estado"] in ("em_curso", "comprado", "por_comprar")]

    segunda = semana or segunda_de(hoje) + timedelta(days=7)
    dias_semana = [(segunda + timedelta(days=i)).isoformat() for i in range(7)]
    da_semana = [v for v in viagens if v["data"] in dias_semana]
    seguinte = segunda_de(hoje) + timedelta(days=7)
    ativas_seguinte = sum(1 for v in viagens if v["ativo"] and seguinte.isoformat() <= v["data"] <= (seguinte + timedelta(days=6)).isoformat())

    bilhetes = sorted((_bilhete(c) for c in dados.get("compras", [])), key=lambda b: (b["data"], b["hora"], b["id"]))
    hoje_iso = hoje.isoformat()
    pedidos = [p for p in dados.get("pedidos", []) if p["estado"] != "CONFIRMADO" and p["data"] >= hoje_iso]
    pedidos.sort(key=lambda p: (p["data"], p["hora"], p["id"]))
    pedidos = [{**p, "retry": p["retry"] == "SIM", "forcar": p["forcar"] == "SIM", "ativo": p["ativo"] == "SIM"} for p in pedidos]

    vistos: dict[tuple, dict] = {}
    for v in sorted(dados.get("viagens", []), key=lambda v: (v["data"], v["hora"]), reverse=True):     # o mais recente primeiro
        vistos.setdefault((v["comboio"], v["origem"], v["destino"], v["hora"]), {"comboio": v["comboio"], "origem": v["origem"], "destino": v["destino"], "hora": v["hora"]})
    estacoes = list(ESTACOES_BASE)
    for v in dados.get("viagens", []) + dados.get("compras", []):
        for nome in (v["origem"], v["destino"]):
            if nome.lower() not in {e.lower() for e in estacoes}:
                estacoes.append(nome)

    return {
        "hoje": hoje_iso, "passe": _passe(dados.get("passe", {}), hoje),
        "proxima": proximas[0] if proximas else None, "proximas": proximas[:10],
        "semanaSeguinte": {"inicio": seguinte.isoformat(), "ativas": ativas_seguinte},
        "semana": {"inicio": segunda.isoformat(), "dias": dias_semana, "viagens": da_semana},
        "bilhetes": {"proximos": [b for b in bilhetes if b["data"] >= hoje_iso], "anteriores": [b for b in reversed(bilhetes) if b["data"] < hoje_iso][:MAX_ANTERIORES]},
        "pedidos": pedidos, "registo": list(reversed(dados.get("logs", [])))[:MAX_REGISTOS],
        "estacoes": estacoes, "historico": list(vistos.values())[:MAX_HISTORICO],
    }
