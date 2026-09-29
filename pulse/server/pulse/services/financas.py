"""Regras das Finanças (porta das da app `financas/`): estados derivados, resumo «ativo − passivo» e relatórios.

Os estados (pendente/hoje/vencido/pago) nunca se guardam: derivam de `data_pagamento` e `data_vencimento`.
Tudo em euros com 2 casas; o servidor devolve os valores já somados para a Web e o Android mostrarem o mesmo.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
JANELAS = ("mes", "30d")


def estado(l: dict, hoje: date) -> str:
    if l.get("data_pagamento"):
        return "pago"
    v = l["data_vencimento"]
    h = hoje.isoformat()
    return "vencido" if v < h else "hoje" if v == h else "pendente"


def _soma(itens) -> float:
    return round(sum(float(x["valor"]) for x in itens), 2)


def janela(modo: str, mes: str, hoje: date) -> tuple[str, str]:
    """`mes`: do 1.º ao último dia do mês escolhido; `30d`: de hoje a hoje+29."""
    if modo == "30d":
        return hoje.isoformat(), (hoje + timedelta(days=29)).isoformat()
    ano, m = int(mes[:4]), int(mes[5:])
    return f"{mes}-01", f"{mes}-{calendar.monthrange(ano, m)[1]:02d}"


def com_estado(lancs: list[dict], hoje: date) -> list[dict]:
    return [{**l, "estado": estado(l, hoje)} for l in lancs]


def _por_categoria(despesas: list[dict], categorias: list[dict]) -> list[dict]:
    cor = {c["id"]: c.get("cor") for c in categorias}
    acc: dict[int, dict] = {}
    for d in despesas:
        e = acc.setdefault(d["categoria_id"], {"categoriaId": d["categoria_id"], "nome": d["categoria"], "cor": cor.get(d["categoria_id"]), "total": 0.0})
        e["total"] += float(d["valor"])
    return sorted(({**e, "total": round(e["total"], 2)} for e in acc.values()), key=lambda e: -e["total"])


def visao(mes: str, modo: str, hoje: date, do_mes: list[dict], da_janela: list[dict], atrasadas: list[dict], categorias: list[dict]) -> dict:
    de, ate = janela(modo, mes, hoje)
    ordem = lambda x: (x["data_vencimento"], x["id"])
    do_mes = sorted(com_estado(do_mes, hoje), key=ordem)
    atrasadas = sorted(com_estado(atrasadas, hoje), key=ordem)
    ren = [x for x in da_janela if x["tipo"] == "rendimento"]
    dep = [x for x in da_janela if x["tipo"] == "despesa"]
    por_pagar = _soma(x for x in dep if not x["data_pagamento"])
    saldo = round(_soma(ren) - por_pagar, 2)
    antes = [x for x in atrasadas if x["data_vencimento"] < de]
    em_atraso = _soma(antes)
    mes_dep = [x for x in do_mes if x["tipo"] == "despesa"]
    return {
        "mes": mes, "hoje": hoje.isoformat(), "categorias": categorias,
        "totaisMes": {"rendimento": _soma(x for x in do_mes if x["tipo"] == "rendimento"), "despesas": _soma(mes_dep),
                      "porPagar": _soma(x for x in mes_dep if not x["data_pagamento"])},
        "lancamentos": do_mes,
        "atrasadas": {"total": _soma(atrasadas), "itens": atrasadas},
        "janela": {"modo": modo, "de": de, "ate": ate},
        "resumo": {"rendimento": _soma(ren), "porPagar": por_pagar, "saldo": saldo, "emAtraso": em_atraso,
                   "saldoComAtraso": round(saldo - em_atraso, 2), "porCategoria": _por_categoria(dep, categorias)},
    }


def meses_entre(de: str, ate: str) -> list[str]:
    a, b = int(de[:4]) * 12 + int(de[5:]) - 1, int(ate[:4]) * 12 + int(ate[5:]) - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(a, b + 1)]


def relatorio(linhas: list[dict], de: str, ate: str, categorias: list[dict]) -> dict:
    """Totais por mês (rendimento, despesas, saldo) e por categoria a partir de `/financas/agregado`."""
    meses = meses_entre(de, ate)
    por_mes = {m: {"mes": m, "rendimento": 0.0, "despesas": 0.0} for m in meses}
    cats: dict[int, dict] = {}
    cor = {c["id"]: c.get("cor") for c in categorias}
    for l in linhas:
        m = por_mes.get(l["mes"])
        if m is None:
            continue
        if l["tipo"] == "rendimento":
            m["rendimento"] += float(l["total"])
        else:
            m["despesas"] += float(l["total"])
            c = cats.setdefault(l["categoria_id"], {"categoriaId": l["categoria_id"], "nome": l["categoria"], "cor": cor.get(l["categoria_id"]),
                                                   "total": 0.0, "meses": {k: 0.0 for k in meses}})
            c["total"] += float(l["total"]); c["meses"][l["mes"]] += float(l["total"])
    serie = [{**m, "rendimento": round(m["rendimento"], 2), "despesas": round(m["despesas"], 2),
              "saldo": round(m["rendimento"] - m["despesas"], 2)} for m in por_mes.values()]
    por_cat = sorted(({**c, "total": round(c["total"], 2), "meses": {k: round(v, 2) for k, v in c["meses"].items()}} for c in cats.values()),
                     key=lambda c: -c["total"])
    return {"de": de, "ate": ate, "meses": serie, "categorias": por_cat,
            "totais": {"rendimento": round(sum(m["rendimento"] for m in serie), 2), "despesas": round(sum(m["despesas"] for m in serie), 2)}}
