"""Regras do módulo Tarefas para o «Hoje» das tarefas (porta da app dedicada `tarefas/index.html`).

Entrada: o `GET /tarefas/dados` do dados-api (`tarefas`, `instancias`, `config`, `piscina`). Saída: o que o ecrã mostra — só tarefas ativas,
listas de hoje / atrasadas (a ocorrência mais recente de cada tarefa) / amanhã, pessoas e categorias da Config.
Funções puras: a data de hoje entra por parâmetro. O filtro por pessoa fica na interface (é uma escolha do utilizador).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from pulse.services.rto import pascoa

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


# --- Calendário -----------------------------------------------------------------------------------------------------------

MAX_DIAS_CALENDARIO = 62


def feriados(ano: int) -> dict[str, str]:
    """Feriados nacionais como na app dedicada (sem o feriado municipal do RTO)."""
    p = pascoa(ano)
    fixos = [(1, 1, "Ano Novo"), (4, 25, "Dia da Liberdade"), (5, 1, "Dia do Trabalhador"), (6, 10, "Dia de Portugal"),
             (8, 15, "Assunção de Nossa Senhora"), (10, 5, "Implantação da República"), (11, 1, "Todos os Santos"),
             (12, 1, "Restauração da Independência"), (12, 8, "Imaculada Conceição"), (12, 25, "Natal")]
    out = {date(ano, m, d).isoformat(): nome for m, d, nome in fixos}
    out[(p - timedelta(days=2)).isoformat()] = "Sexta-feira Santa"
    out[p.isoformat()] = "Páscoa"
    out[(p + timedelta(days=60)).isoformat()] = "Corpo de Deus"
    return out


def calendario(dados: dict, de: date, ate: date, hoje: date) -> dict:
    """Uma entrada por dia de `de` a `ate` (no máximo 62 dias): feriado e ocorrências (de tarefas ativas), na ordem do «Hoje»."""
    if ate < de or (ate - de).days + 1 > MAX_DIAS_CALENDARIO:
        raise ValueError("intervalo inválido")
    cfg = config_de(dados.get("config", []))
    hora_padrao = cfg.get("HoraPadrao") or "08:00"
    ativas = {t["id"]: t for t in dados.get("tarefas", []) if t.get("ativa")}
    por_dia: dict[str, list[dict]] = {}
    for i in dados.get("instancias", []):
        if i["tarefaId"] in ativas and de.isoformat() <= i["data"] <= ate.isoformat():
            por_dia.setdefault(i["data"], []).append(_item(i, ativas[i["tarefaId"]], hora_padrao))
    ordem = lambda x: (x["hora"] or "99:99", {"Alta": 0, "Media": 1, "Baixa": 2}.get(x["prioridade"], 9), x["nome"])   # noqa: E731
    fer = {}
    for ano in {de.year, ate.year}:
        fer.update(feriados(ano))
    dias, d = [], de
    while d <= ate:
        iso = d.isoformat()
        dias.append({"data": iso, "feriado": fer.get(iso), "itens": sorted(por_dia.get(iso, []), key=ordem)})
        d += timedelta(days=1)
    return {"de": de.isoformat(), "ate": ate.isoformat(), "hoje": hoje.isoformat(), "horaPadrao": hora_padrao, "dias": dias}


# --- Config: resumo por pessoa ----------------------------------------------------------------------------------------------

def resumo_pessoas(dados: dict, agora: datetime) -> dict:
    """Tarefas concluídas por cada pessoa nos últimos 7 dias e o aviso de desequilíbrio (regra da app dedicada)."""
    cfg = config_de(dados.get("config", []))
    contagem = {p["nome"]: 0 for p in pessoas(cfg)}
    limite = (agora - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    for i in dados.get("instancias", []):
        if i.get("estado") == "Feita" and (i.get("dataConclusao") or "") >= limite and i.get("pessoa") in contagem:
            contagem[i["pessoa"]] += 1
    valores = list(contagem.values())
    quem = None
    if len(valores) >= 2 and max(valores) >= 3 and max(valores) >= min(valores) * 2:
        quem = next(n for n, v in contagem.items() if v == max(valores))
    return {"pessoas": [{"nome": n, "feitas": v} for n, v in contagem.items()], "desequilibrio": quem}


def preferencias(cfg: dict[str, str]) -> dict:
    def inteiro(chave: str, padrao: int) -> int:
        try:
            return int(float(cfg.get(chave) or padrao))
        except ValueError:
            return padrao
    return {"horaPadrao": cfg.get("HoraPadrao") or "08:00", "naoIncomodarInicio": cfg.get("NaoIncomodarInicio", ""),
            "naoIncomodarFim": cfg.get("NaoIncomodarFim", ""), "horarioAvisos": cfg.get("HorarioAvisos", "TRUE").strip().upper() != "FALSE",
            "horarioAvisoMinutos": inteiro("HorarioAvisoMinutos", 30)}


def proximo_numero_pessoa(cfg: dict[str, str]) -> int:
    nums = [int(m.group(1)) for k in cfg if (m := re.fullmatch(r"Pessoa(\d+)_\w+", k, re.IGNORECASE))]
    return max(nums, default=0) + 1


def numero_da_pessoa(cfg: dict[str, str], nome: str) -> int | None:
    return next((p["num"] for p in pessoas(cfg) if p["nome"] == nome), None)
