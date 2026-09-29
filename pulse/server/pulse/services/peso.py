"""Estatísticas do módulo Peso (porta fiel da lógica da app dedicada `peso/index.html`, para a Web e o Android partilharem).

Entrada: os registos do `dados-api` (`{id, quando 'AAAA-MM-DD HH:MM:SS', peso, nota}`, por ordem de data) e a config
(`{altura, nascimento, sexo, pesoAlvo, atividade, diaControlo, pesoMin, pesoMax}`). Saída: tudo o que os ecrãs mostram.
Funções puras: sem rede nem relógio (a data de hoje entra por parâmetro).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

_ATIVIDADES = (1.2, 1.45, 1.7)


def _dt(quando: str) -> datetime:
    return datetime.strptime(quando[:19], "%Y-%m-%d %H:%M:%S")


def normalizar_atividade(raw) -> float:
    """Igual à app dedicada: 1/2/3/4 -> escala antiga; valores 1.2-1.725 -> o mais próximo de 1.2/1.45/1.7."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 1.2
    if not v:
        return 1.2
    escala = {1: 1.2, 2: 1.45, 3: 1.7, 4: 1.7}
    if v == int(v) and int(v) in escala:
        return escala[int(v)]
    if 1.2 <= v <= 1.725:
        return min(_ATIVIDADES, key=lambda x: (abs(x - v), _ATIVIDADES.index(x)))
    return 1.2


def idade_anos(nascimento: str | None, hoje: date) -> int | None:
    if not nascimento:
        return None
    n = date.fromisoformat(nascimento)
    return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))


def imc(peso: float, altura_cm: float | None) -> float | None:
    if not peso or not altura_cm:
        return None
    return peso / ((altura_cm / 100) ** 2)


def classificar_imc(v: float) -> str:
    if v < 18.5: return "Abaixo do peso"
    if v < 25: return "Peso normal"
    if v < 30: return "Excesso de peso"
    if v < 35: return "Obesidade grau I"
    if v < 40: return "Obesidade grau II"
    return "Obesidade grau III"


def tmb(peso: float, altura_cm: float | None, idade: int | None, sexo: str | None) -> float | None:
    if not peso or not altura_cm or idade is None or sexo not in ("M", "F"):
        return None
    base = 10 * peso + 6.25 * altura_cm - 5 * idade
    return base + 5 if sexo == "M" else base - 161


def perda_por_dia(regs: list[dict], dias: float) -> float | None:
    """(primeiro - último) / dias decorridos, dentro dos últimos `dias` dias (contados desde o último registo)."""
    if len(regs) < 2:
        return None
    fim = _dt(regs[-1]["quando"])
    janela = [r for r in regs if _dt(r["quando"]) >= fim - timedelta(days=min(dias, 36500))]   # «sempre» = 100 anos
    if len(janela) < 2:
        return None
    decorridos = (_dt(janela[-1]["quando"]) - _dt(janela[0]["quando"])).total_seconds() / 86400
    if decorridos <= 0:
        return None
    return (janela[0]["peso"] - janela[-1]["peso"]) / decorridos


def sequencia(regs: list[dict]) -> int:
    """Dias seguidos com pelo menos um registo, a contar do mais recente."""
    if not regs:
        return 0
    dias = sorted({r["quando"][:10] for r in regs}, reverse=True)
    n, anterior = 1, date.fromisoformat(dias[0])
    for d in dias[1:]:
        atual = date.fromisoformat(d)
        if (anterior - atual).days == 1:
            n, anterior = n + 1, atual
        else:
            break
    return n


def controlo(peso: float, cfg: dict) -> str | None:
    mn, mx = cfg.get("pesoMin"), cfg.get("pesoMax")
    if mn is None and mx is None:
        return None
    if mx is not None and peso > mx:
        return "acima"
    if mn is not None and peso < mn:
        return "abaixo"
    return "dentro"


def _media(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def analise(regs: list[dict]) -> dict:
    out = {"tendencia": None, "mensal": None, "melhorSemana": None, "piorSemana": None}
    if len(regs) < 5:
        return out
    fim = _dt(regs[-1]["quando"])
    janela = [r for r in regs if _dt(r["quando"]) >= fim - timedelta(days=30)]
    if len(janela) < 5:
        janela = regs
    ini = _dt(janela[0]["quando"])
    span = (_dt(janela[-1]["quando"]) - ini).total_seconds() / 86400
    if len(janela) >= 5 and span >= 5:
        xs = [(_dt(r["quando"]) - ini).total_seconds() / 86400 for r in janela]
        ys = [r["peso"] for r in janela]
        mx, my = _media(xs), _media(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            declive = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
            out["tendencia"] = {"kgSemana": declive * 7, "dias": round(span), "pontos": len(janela)}   # positivo = ganho
    por_mes: dict[str, list[float]] = {}
    por_semana: dict[str, list[float]] = {}
    for r in regs:
        d = _dt(r["quando"])
        por_mes.setdefault(d.strftime("%Y-%m"), []).append(r["peso"])
        segunda = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        por_semana.setdefault(segunda, []).append(r["peso"])
    meses = sorted(por_mes)
    if len(meses) >= 2:
        out["mensal"] = {"diff": _media(por_mes[meses[-1]]) - _media(por_mes[meses[-2]])}
    semanas = sorted(por_semana)
    if len(semanas) >= 3:
        diffs = [_media(por_semana[semanas[i]]) - _media(por_semana[semanas[i - 1]]) for i in range(1, len(semanas))]
        out["melhorSemana"] = {"diff": min(diffs)}
        out["piorSemana"] = {"diff": max(diffs)}
    return out


def previsao(regs: list[dict], alvo: float | None) -> dict:
    """Data prevista para o peso alvo, ao ritmo dos últimos 30 dias (ou do histórico todo)."""
    if len(regs) < 2:
        return {"estado": "poucos_registos"}
    if not alvo:
        return {"estado": "sem_alvo"}
    atual = regs[-1]["peso"]
    if atual <= alvo:
        return {"estado": "atingido"}
    ritmo = perda_por_dia(regs, 30)
    if ritmo is None:
        ritmo = perda_por_dia(regs, 999999)
    if ritmo is None or ritmo <= 0.001:
        return {"estado": "sem_tendencia"}
    import math
    dias = math.ceil((atual - alvo) / ritmo)
    prevista = (_dt(regs[-1]["quando"]) + timedelta(days=dias)).date()
    return {"estado": "ok", "data": prevista.isoformat(), "kgSemana": ritmo * 7}


def resumo(regs: list[dict], cfg: dict, hoje: date) -> dict:
    """Tudo o que o ecrã do Peso mostra, calculado a partir dos registos e da config."""
    base = {"analise": analise(regs), "previsao": previsao(regs, cfg.get("pesoAlvo"))}
    if not regs:
        return {**base, "ultimo": None}
    ultimo, primeiro = regs[-1], regs[0]
    anterior = regs[-2] if len(regs) > 1 else None
    pesos = [r["peso"] for r in regs]
    alvo = cfg.get("pesoAlvo")
    atual = ultimo["peso"]

    pct = None
    if alvo:
        pct = 0.0 if primeiro["peso"] == alvo else ((primeiro["peso"] - atual) / (primeiro["peso"] - alvo)) * 100
        pct = max(0.0, min(100.0, pct))
    dia = perda_por_dia(regs, 999999)
    v_imc = imc(atual, cfg.get("altura"))
    idade = idade_anos(cfg.get("nascimento"), hoje)
    v_tmb = tmb(atual, cfg.get("altura"), idade, cfg.get("sexo"))

    return {
        **base,
        "ultimo": {"id": ultimo["id"], "quando": ultimo["quando"], "peso": atual},
        "anterior": anterior and {"quando": anterior["quando"], "peso": anterior["peso"], "diferenca": atual - anterior["peso"]},
        "sequenciaDias": sequencia(regs),
        "novoMinimo": len(regs) > 1 and atual <= min(pesos) + 0.001,
        "controlo": controlo(atual, cfg),
        "progresso": None if pct is None else {"pct": pct, "inicial": primeiro["peso"], "alvo": alvo},
        "totalPerdido": primeiro["peso"] - atual,
        "ritmo": None if dia is None else {"kgDia": dia, "kgSemana": dia * 7},
        "faltam": None if not alvo else {"kg": abs(atual - alvo), "atingido": abs(atual - alvo) < 0.05},
        "imc": None if v_imc is None else {"valor": v_imc, "classe": classificar_imc(v_imc)},
        "gastoDiario": None if v_tmb is None else round(v_tmb * normalizar_atividade(cfg.get("atividade"))),
        "minimo": min(pesos), "maximo": max(pesos), "registos": len(regs),
    }
