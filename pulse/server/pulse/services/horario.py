"""Horário escolar no Pulse (porta de `tarefas/index.html` + `tarefas/pi/horario.py`): ano letivo, dias com aulas, blocos (turma dividida),
hora de saída e hora do aviso. Entrada: `GET /tarefas/horario` (aulas) e a Config; funções puras (a data de hoje entra por parâmetro)."""

from __future__ import annotations

from datetime import date

DIAS_CURTO = ("", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
DIAS_NOME = ("", "2ª feira", "3ª feira", "4ª feira", "5ª feira", "6ª feira", "Sábado", "Domingo")
# aulas que aparecem no horário mas a que o aluno não vai: não contam como «última aula» (igual a DISCIPLINAS_SEM_AVISO no Pi)
SEM_AVISO = ("E.M.R.",)


def ano_letivo_atual(aulas: list[dict], hoje: date) -> str | None:
    anos = sorted({a["anoLetivo"] for a in aulas})
    for ano in anos:
        try:
            x, y = ano.split("/")
        except ValueError:
            continue
        if f"{x}-09-01" <= hoje.isoformat() <= f"{y}-07-31":
            return ano
    return anos[-1] if anos else None


def _menos_min(hhmm: str, minutos: int) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    t = max(0, h * 60 + m - minutos)
    return f"{t // 60:02d}:{t % 60:02d}"


def _slots(aulas: list[dict]) -> list[dict]:
    mapa: dict[tuple[str, str], list[dict]] = {}
    for a in aulas:
        mapa.setdefault((a["horaInicio"], a["horaFim"]), []).append({"disciplina": a["disciplina"], "sala": a.get("sala") or ""})
    return [{"ini": ini, "fim": fim, "aulas": v, "dividida": len(v) > 1} for (ini, fim), v in sorted(mapa.items())]


def _dia(aulas: list[dict], dia: int, minutos: int) -> dict:
    slots = _slots([a for a in aulas if a["diaSemana"] == dia])
    fim_dia = ""
    for s in slots:
        if not all(a["disciplina"] in SEM_AVISO for a in s["aulas"]) and s["fim"] > fim_dia:
            fim_dia = s["fim"]
    for s in slots:
        s["ultima"] = bool(fim_dia) and s["fim"] == fim_dia
    return {"dia": dia, "nome": DIAS_CURTO[dia], "entra": slots[0]["ini"] if slots else "", "sai": fim_dia,
            "aviso": _menos_min(fim_dia, minutos) if fim_dia else "", "totalAulas": sum(len(s["aulas"]) for s in slots), "slots": slots}


def visao(aulas: list[dict] | None, cfg: dict[str, str], hoje: date) -> dict:
    """`disponivel` false = o módulo não respondeu; `alunos` vazio = ainda não há horário importado."""
    if aulas is None:
        return {"disponivel": False, "anoLetivo": None, "alunos": [], "diaHoje": hoje.isoweekday(), "avisos": None}
    try:
        minutos = int(float(cfg.get("HorarioAvisoMinutos") or 30))
    except ValueError:
        minutos = 30
    avisos = {"ativos": cfg.get("HorarioAvisos", "TRUE").strip().upper() != "FALSE", "minutos": minutos}
    ano = ano_letivo_atual(aulas, hoje)
    do_ano = [a for a in aulas if a["anoLetivo"] == ano]
    alunos = []
    for nome in sorted({a["aluno"] for a in do_ano}):
        dele = [a for a in do_ano if a["aluno"] == nome]
        alunos.append({"nome": nome, "dias": [_dia(dele, d, minutos) for d in sorted({a["diaSemana"] for a in dele})]})
    return {"disponivel": True, "anoLetivo": ano, "alunos": alunos, "diaHoje": hoje.isoweekday(), "avisos": avisos}
