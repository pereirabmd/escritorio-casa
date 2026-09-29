"""Regras do módulo Tarefas para o «Hoje» das tarefas (porta da app dedicada `tarefas/index.html`).

Entrada: o `GET /tarefas/dados` do dados-api (`tarefas`, `instancias`, `config`, `piscina`). Saída: o que o ecrã mostra — só tarefas ativas,
listas de hoje / atrasadas (a ocorrência mais recente de cada tarefa) / amanhã, pessoas e categorias da Config.
Funções puras: a data de hoje entra por parâmetro. O filtro por pessoa fica na interface (é uma escolha do utilizador).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

DIAS = ("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab")
RECORRENCIAS = ("Diaria", "Semanal", "Dias especificos", "Mensal", "Trimestral", "Semestral", "Pontual")
COM_DATA = ("Pontual", "Trimestral", "Semestral")
COM_DIAS = ("Semanal", "Dias especificos")


def config_de(lista: list[dict]) -> dict[str, str]:
    return {str(c["chave"]).strip(): c.get("valor", "") for c in lista}


def pessoas(config: dict[str, str]) -> list[dict]:
    """`Pessoa<N>_Nome` (com e-mail de `Pessoa<N>_Email`), por ordem do número."""
    out = []
    for chave, valor in config.items():
        m = re.fullmatch(r"Pessoa(\d+)_Nome", chave, re.IGNORECASE)
        if m and str(valor).strip():
            out.append({"num": int(m.group(1)), "nome": str(valor).strip(), "email": str(config.get(f"Pessoa{m.group(1)}_Email", "")).strip().lower()})
    return sorted(out, key=lambda p: p["num"])


def categorias(config: dict[str, str]) -> list[str]:
    achadas = [(int(m.group(1)), str(v).strip()) for k, v in config.items() if (m := re.fullmatch(r"Categoria(\d+)", k, re.IGNORECASE)) and str(v).strip()]
    return [v for _, v in sorted(achadas)]


def _data_pt(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return "?"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def resumo_recorrencia(t: dict) -> str:
    r = t.get("recorrencia")
    if r == "Diaria":
        return "Todos os dias"
    if r in COM_DIAS:
        return t.get("diasSemana") or ""
    if r == "Mensal":
        return f"Dia {t.get('diaMes')} de cada mês"
    if r in ("Trimestral", "Semestral"):
        return f"A cada {3 if r == 'Trimestral' else 6} meses, desde {_data_pt(t.get('diasSemana') or '')}"
    if r == "Pontual":
        return f"Uma vez, {_data_pt(t.get('diasSemana') or '')}"
    return r or ""


def _item(i: dict, t: dict, hora_padrao: str) -> dict:
    return {"id": i["id"], "tarefaId": i["tarefaId"], "nome": t["nome"], "categoria": t["categoria"], "prioridade": t["prioridade"],
            "hora": t.get("horaNotificacao") or hora_padrao, "pessoa": i["pessoa"], "estado": i["estado"], "data": i["data"],
            "dataConclusao": i.get("dataConclusao") or ""}


def ultima_atrasada_por_tarefa(instancias: list[dict]) -> list[dict]:
    """Uma tarefa que ficou vários dias por fazer acumula uma ocorrência Atrasada por dia; para a pessoa é uma só coisa por fazer."""
    mais_recente: dict[str, dict] = {}
    for i in instancias:
        atual = mais_recente.get(i["tarefaId"])
        if atual is None or i["data"] > atual["data"]:
            mais_recente[i["tarefaId"]] = i
    return [i for i in instancias if mais_recente[i["tarefaId"]] is i]


def pessoa_do_utilizador(config: dict[str, str], email: str) -> str | None:
    return next((p["nome"] for p in pessoas(config) if p["email"] and p["email"] == email.lower()), None)


def visao(dados: dict, hoje: date, email: str) -> dict:
    cfg = config_de(dados.get("config", []))
    hora_padrao = cfg.get("HoraPadrao") or "08:00"
    ativas = {t["id"]: t for t in dados.get("tarefas", []) if t.get("ativa")}
    insts = [i for i in dados.get("instancias", []) if i["tarefaId"] in ativas]
    h, amanha = hoje.isoformat(), (hoje + timedelta(days=1)).isoformat()
    item = lambda i: _item(i, ativas[i["tarefaId"]], hora_padrao)                      # noqa: E731
    ordem = lambda x: (x["hora"] or "99:99", {"Alta": 0, "Media": 1, "Baixa": 2}.get(x["prioridade"], 9), x["nome"])   # noqa: E731
    return {
        "data": h, "pessoa": pessoa_do_utilizador(cfg, email), "pessoas": [p["nome"] for p in pessoas(cfg)], "categorias": categorias(cfg),
        "horaPadrao": hora_padrao,
        "hoje": sorted((item(i) for i in insts if i["data"] == h and i["estado"] != "Feita"), key=ordem),
        "feitas": sorted((item(i) for i in insts if i["data"] == h and i["estado"] == "Feita"), key=ordem),
        "atrasadas": sorted((item(i) for i in ultima_atrasada_por_tarefa([i for i in insts if i["estado"] == "Atrasada"])), key=lambda x: (x["data"], x["nome"])),
        "amanha": sorted((item(i) for i in insts if i["data"] == amanha and i["estado"] not in ("Feita", "Saltada")), key=ordem),
        "tarefas": [{**t, "resumo": resumo_recorrencia(t), "hora": t.get("horaNotificacao") or hora_padrao}
                    for t in sorted(ativas.values(), key=lambda t: t["id"])],
    }
