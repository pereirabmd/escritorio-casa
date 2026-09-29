"""Piscina no Pulse (porta de `tarefas/index.html`): catálogo fixo de manutenção com regime por estação, próxima data sugerida e atraso.

O catálogo é estático (não editável pela interface, como na app dedicada); o estado (última/próxima data, alternância de intervalo)
vive na tabela `tarefas_piscina` do dados-api. Funções puras: a data de hoje entra por parâmetro.
"""

from __future__ import annotations

from datetime import date, timedelta

CATALOGO: tuple[dict, ...] = (
    {"id": "P01", "nome": "Cloro rápido", "nota": "75 g", "quente": {"intervalo": 7}, "fria": {"intervalo": 14}},
    {"id": "P02", "nome": "Testar pH e cloro", "quente": {"intervalo": 3, "intervaloAlt": 4, "atraso": 4}, "fria": {"intervalo": 7}},
    {"id": "P03", "nome": "Anti-algas", "nota": "460 cc", "quente": {"intervalo": 7}, "fria": {"intervalo": 14, "atraso": 30}},
    {"id": "P04", "nome": "Robô aspirador", "quente": {"intervalo": 3, "atraso": 4}, "fria": {"intervalo": 7}},
    {"id": "P05", "nome": "Escovar paredes/fundo/linha de água", "quente": {"intervalo": 7}, "fria": {"intervalo": 14}},
    {"id": "P06", "nome": "Limpar cesto skimmer/pré-filtro bomba", "quente": {"intervalo": 7}, "fria": {"intervalo": 14}},
    {"id": "P07", "nome": "Testar alcalinidade (TAC)", "nota": "ideal 80-120 ppm", "anoTodo": {"intervalo": 30}},
    {"id": "P08", "nome": "Trocar areia do filtro", "nota": "85 kg", "anoTodo": {"intervalo": 1095, "atraso": 1460}, "avisoLongo": True},
    {"id": "P11", "nome": "Verificar pressão do filtro e contralavagem", "nota": "baseline ~12 psi",
     "notaLonga": "Contralavagem quando o manómetro atingir ou ultrapassar ~16 psi / ~1,1 bar / ~110 kPa (~3-4 psi / ~0,2-0,3 bar / ~20-30 kPa acima da "
                  "baseline de 12 psi / 0,83 bar / 83 kPa). Válvula multiport, por esta ordem: Backwash → Rinse → Filter. A bomba tem de estar sempre "
                  "desligada antes de mudar a posição da válvula.",
     "quente": {"intervalo": 7, "intervaloAlt": 14}, "fria": {"intervalo": 28, "intervaloAlt": 42}},
    {"id": "P09", "nome": "Repor cloro lento (pastilhas)", "tipo": "log"},
    {"id": "P10", "nome": "Ajustar pH", "nota": "pH- ou pH+ conforme leitura", "tipo": "log"},
    {"id": "P12", "nome": "Floculante", "nota": "230 cc, se água turva", "tipo": "log"},
    {"id": "P13", "nome": "Choque de cloro", "nota": "300-450 g, se contaminação/chuva forte", "tipo": "log"},
)
POR_ID = {i["id"]: i for i in CATALOGO}


def estacao(cfg: dict[str, str], hoje: date) -> str:
    def mes(chave: str, padrao: int) -> int:
        try:
            return int(float(cfg.get(chave) or padrao))
        except ValueError:
            return padrao
    return "quente" if mes("PiscinaMesInicioQuente", 5) <= hoje.month <= mes("PiscinaMesFimQuente", 9) else "fria"


def regime(item: dict, est: str) -> dict | None:
    return item.get("anoTodo") or item.get(est)


def limite_atraso(r: dict) -> int:
    return r.get("atraso") or max(r["intervalo"], r.get("intervaloAlt", 0))


def calcular_proxima(r: dict, usar_longo_anterior: bool) -> tuple[int, bool]:
    """(dias até à próxima, usar o intervalo «longo» da próxima vez). Com intervalo alternado, a média não desvia da frequência real."""
    if not r.get("intervaloAlt"):
        return r["intervalo"], False
    return (r["intervalo"] if usar_longo_anterior else r["intervaloAlt"]), not usar_longo_anterior


def novo_estado(item: dict, est: str, atual: dict | None, hoje: date) -> dict:
    """O que gravar quando a tarefa é feita hoje: última data, próxima (vazia nas de registo) e a alternância."""
    r = regime(item, est) if item.get("tipo") != "log" else None
    if not r:
        return {"ultimaData": hoje.isoformat(), "proximaData": None, "notificacaoEnviada": False, "usarIntervaloLongo": False}
    dias, longo = calcular_proxima(r, bool(atual and atual.get("usarIntervaloLongo")))
    return {"ultimaData": hoje.isoformat(), "proximaData": (hoje + timedelta(days=dias)).isoformat(), "notificacaoEnviada": False, "usarIntervaloLongo": longo}


def em_falta(linhas: list[dict]) -> list[dict]:
    ids = {p["id"] for p in linhas}
    return [{"id": i["id"], "nome": i["nome"], "avisoLongo": bool(i.get("avisoLongo"))} for i in CATALOGO if i["id"] not in ids]


def _cartao(item: dict, linha: dict | None, est: str, hoje: date) -> dict:
    ultima = (linha or {}).get("ultimaData") or ""
    proxima = (linha or {}).get("proximaData") or ""
    base = {"id": item["id"], "nome": item["nome"], "nota": item.get("nota", ""), "notaLonga": item.get("notaLonga", ""),
            "tipo": "log" if item.get("tipo") == "log" else "periodica", "ultima": ultima, "proxima": proxima}
    if base["tipo"] == "log":
        return {**base, "estado": "registo", "diasDesde": None}
    r = regime(item, est)
    dias = (hoje - date.fromisoformat(ultima)).days if ultima else None
    if ultima and dias is not None and dias > limite_atraso(r):
        estado = "atrasada"
    elif proxima and proxima <= hoje.isoformat():
        estado = "hoje"
    else:
        estado = "ok" if ultima else "nunca"
    return {**base, "estado": estado, "diasDesde": dias, "sugeridoHoje": proxima == hoje.isoformat(), "destacar": bool(proxima) and proxima <= hoje.isoformat()}


def visao(linhas: list[dict], cfg: dict[str, str], hoje: date) -> dict:
    est = estacao(cfg, hoje)
    por_id = {p["id"]: p for p in linhas}
    per = [_cartao(i, por_id.get(i["id"]), est, hoje) for i in CATALOGO if i.get("tipo") != "log"]
    # nunca registadas primeiro (mantendo a ordem do catálogo); as restantes pela próxima data mais próxima
    per.sort(key=lambda c: (bool(c["ultima"]), c["proxima"] if c["ultima"] else ""))
    return {"estacao": est, "periodicas": per, "outras": [_cartao(i, por_id.get(i["id"]), est, hoje) for i in CATALOGO if i.get("tipo") == "log"]}
