"""Agregado do «Hoje» (SCOPE.md): só o essencial e imediato de cada módulo, num único pedido.

Cada módulo é independente: se um falha, os outros continuam e o falhado aparece com `estado` diferente de `ok` (modo
degradado). Os dados vêm das APIs oficiais (dados-api, ADR-031) em nome do utilizador; o Pulse não lê bases de origem.
Calendário e Email ainda não estão ligados (fase 10).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Callable

from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel
from pulse.services import horario as horario_regras
from pulse.services import piscina as piscina_regras
from pulse.services import tarefas as tarefas_regras

class NaoLigado(Exception):
    """O módulo existe mas o utilizador ainda não o ligou (ex.: sem conta Google): o cartão convida a ligar."""


MAX_CONTAS = 5
_PRIORIDADE = {"Alta": 0, "Media": 1, "Baixa": 2}


# --- módulos -----------------------------------------------------------------------------------------------------

def rto_semana(c: DadosClient, email: str, hoje: date) -> dict:
    segunda = hoje - timedelta(days=hoje.weekday())
    domingo = segunda + timedelta(days=6)
    _, corpo = c.pedir("GET", "/rto/dias", email, {"desde": segunda.isoformat(), "ate": domingo.isoformat()})
    marcas = (corpo or {}).get("dias", {})
    dias = []
    for i in range(7):
        d = segunda + timedelta(days=i)
        dias.append({"data": d.isoformat(), "diaSemana": i + 1, "marca": marcas.get(d.isoformat(), ""), "hoje": d == hoje})
    contagem = {m: sum(1 for d in dias if d["marca"] == m) for m in ("T", "C")}
    return {"semana": {"inicio": segunda.isoformat(), "fim": domingo.isoformat()}, "dias": dias, "contagem": contagem}


def peso_hoje(c: DadosClient, email: str, hoje: date) -> dict:
    def registos_desde(desde: str | None) -> list:
        _, corpo = c.pedir("GET", "/peso/registos", email, {"desde": desde} if desde else None)
        return (corpo or {}).get("registos", [])

    regs = registos_desde((hoje - timedelta(days=90)).isoformat()) or registos_desde(None)
    ultimo = regs[-1] if regs else None
    desde7 = (hoje - timedelta(days=6)).isoformat()
    por_dia: dict[str, float] = {}
    for r in regs:                                                   # os registos vêm por ordem: fica o último de cada dia
        if r["quando"][:10] >= desde7:
            por_dia[r["quando"][:10]] = r["peso"]
    return {"ultimo": ultimo and {"quando": ultimo["quando"], "peso": ultimo["peso"]},
            "registadoHoje": bool(ultimo and ultimo["quando"][:10] == hoje.isoformat()),
            "sugestao": ultimo["peso"] if ultimo else None,          # pré-preenche o campo de hoje
            "ultimos7": [{"data": d, "peso": por_dia[d]} for d in sorted(por_dia)]}     # o minigráfico dos últimos 7 dias (hoje incluído)


def contas_a_pagar(c: DadosClient, email: str, hoje: date) -> dict:
    ate = (hoje + timedelta(days=30)).isoformat()
    _, corpo = c.pedir("GET", "/financas/lancamentos", email, {"pendentes": "1", "tipo": "despesa", "ate": ate})
    pendentes = sorted((corpo or {}).get("lancamentos", []), key=lambda l: (l["data_vencimento"], l["id"]))
    def item(l: dict) -> dict:
        venc = date.fromisoformat(l["data_vencimento"])
        return {"id": l["id"], "descricao": l["descricao"], "valor": l["valor"], "categoria": l["categoria"],
                "dataVencimento": l["data_vencimento"], "diasAte": (venc - hoje).days, "vencida": venc < hoje}
    itens = [item(l) for l in pendentes]
    return {"proximas": itens[:MAX_CONTAS], "vencidas": sum(1 for i in itens if i["vencida"]), "total": len(itens),
            "valorTotal": round(sum(i["valor"] for i in itens), 2)}


def _pessoa_do_utilizador(config: list[dict], email: str) -> str | None:
    """Nome da pessoa das Tarefas cujo `Pessoa<N>_Email` é o e-mail do utilizador (se houver)."""
    valores = {x["chave"]: x["valor"] for x in config}
    for chave, valor in valores.items():
        m = re.fullmatch(r"Pessoa(\d+)_Email", chave)
        if m and valor.strip().lower() == email.lower():
            return valores.get(f"Pessoa{m.group(1)}_Nome", "").strip() or None
    return None


def tarefas_hoje(c: DadosClient, email: str, hoje: date) -> dict:
    _, corpo = c.pedir("GET", "/tarefas/dados", email)
    corpo = corpo or {}
    tarefas = {t["id"]: t for t in corpo.get("tarefas", []) if t.get("ativa")}
    pessoa = _pessoa_do_utilizador(corpo.get("config", []), email)
    iso = hoje.isoformat()
    hoje_l, atrasadas, feitas = [], 0, 0
    for i in corpo.get("instancias", []):
        t = tarefas.get(i["tarefaId"])
        if t is None or (pessoa and i["pessoa"] not in (pessoa, "")):
            continue                      # tarefa desativada, ou de outra pessoa
        if i["data"] == iso and i["estado"] == "Feita":
            feitas += 1
        elif i["estado"] in ("Pendente", "Atrasada"):
            if i["data"] == iso:
                hoje_l.append({"id": i["id"], "tarefaId": t["id"], "nome": t["nome"], "categoria": t["categoria"],
                               "icone": t["icone"], "prioridade": t["prioridade"], "hora": t["horaNotificacao"],
                               "pessoa": i["pessoa"], "estado": i["estado"]})
            elif i["data"] < iso:
                atrasadas += 1
    hoje_l.sort(key=lambda x: (x["hora"] or "99:99", _PRIORIDADE.get(x["prioridade"], 9), x["nome"]))
    cfg = tarefas_regras.config_de(corpo.get("config", []))
    return {"hoje": hoje_l, "atrasadas": atrasadas, "feitasHoje": feitas, "totalHoje": len(hoje_l) + feitas,
            "pessoa": pessoa, "piscina": piscina_do_dia(corpo.get("piscina", []), cfg, hoje), "horario": saida_do_aluno(c, email, cfg, hoje)}


def piscina_do_dia(linhas: list[dict], cfg: dict[str, str], hoje: date) -> list[dict]:
    """A manutenção da piscina sugerida para hoje ou já passada da data (as atrasadas primeiro): entra no cartão das Tarefas."""
    cartoes = piscina_regras.visao(linhas, cfg, hoje)["periodicas"]
    dela = [k for k in cartoes if k.get("destacar") or k["estado"] == "atrasada"]
    dela.sort(key=lambda k: (k["estado"] != "atrasada", k["proxima"] or "9999", k["nome"]))
    return [{"id": k["id"], "nome": k["nome"], "nota": k["nota"], "estado": k["estado"], "ultima": k["ultima"], "proxima": k["proxima"], "diasDesde": k["diasDesde"]} for k in dela]


ALUNO_DO_CARTAO = "bruno"          # o aluno do horário escolar cuja saída de hoje aparece no cartão das Tarefas (comparação sem maiúsculas)


def saida_do_aluno(c: DadosClient, email: str, cfg: dict[str, str], hoje: date) -> dict | None:
    """A hora de saída de hoje (e o aviso) do aluno do cartão, do Horário das Tarefas. `None` sem aulas hoje, sem esse aluno ou se o módulo não responder."""
    try:
        _, r = c.pedir("GET", "/tarefas/horario", email)
    except (ModuloIndisponivel, ErroDoModulo):
        return None
    v = horario_regras.visao((r or {}).get("aulas", []), cfg, hoje)
    aluno = next((a for a in v["alunos"] if ALUNO_DO_CARTAO in a["nome"].lower()), None)
    dia = next((d for d in (aluno or {}).get("dias", []) if d["dia"] == hoje.isoweekday()), None)
    if aluno is None or dia is None or not dia["sai"]:
        return None
    return {"aluno": aluno["nome"], "entra": dia["entra"], "sai": dia["sai"], "aviso": dia["aviso"]}


def proximo_bilhete(c: DadosClient, email: str, hoje: date) -> dict:
    _, corpo = c.pedir("GET", "/bilhetes/proximo", email)
    return corpo or {"proximo": None, "passe": None}


MODULOS = {"tarefas": tarefas_hoje, "bilhetes": proximo_bilhete, "rto": rto_semana, "peso": peso_hoje,
           "financas": contas_a_pagar}
NAO_LIGADOS = ("calendario", "email")


# --- agregado ----------------------------------------------------------------------------------------------------

def _correr(nome: str, fn, c: DadosClient, email: str, hoje: date) -> tuple[str, dict]:
    try:
        return nome, {"estado": "ok", "dados": fn(c, email, hoje)}
    except NaoLigado:
        return nome, {"estado": "nao_ligado", "dados": None}
    except ModuloIndisponivel as e:
        return nome, {"estado": "indisponivel", "erro": {"codigo": "modulo_indisponivel", "mensagem": str(e)}}
    except ErroDoModulo as e:
        estado = "sem_acesso" if e.status == 403 else "erro"
        return nome, {"estado": estado, "erro": {"codigo": e.codigo, "mensagem": e.mensagem}}
    except (KeyError, TypeError, ValueError, AttributeError):
        return nome, {"estado": "erro", "erro": {"codigo": "resposta_inesperada", "mensagem": "resposta inesperada do módulo"}}


def hoje(c: DadosClient, email: str, agora: datetime, desativados: frozenset[str] | set[str] = frozenset(),
         locais: dict[str, Callable[[date], dict]] | None = None, so: set[str] | None = None) -> dict:
    """`locais`: módulos cujos dados não vêm do `dados-api` (Compras e Google, no `pulse.db`/na rede). Cada função recebe o dia,
    abre a sua própria ligação (as threads do agregado não partilham ligações SQLite) e corre em paralelo com os outros."""
    dia = agora.date()
    locais = locais or {}
    fontes = {**MODULOS, **{n: (lambda f: lambda _c, _e, d: f(d))(f) for n, f in locais.items()}}
    if so is not None:                      # atualização parcial (depois de uma ação): só os módulos pedidos, sem tocar nos outros (nem na Google)
        fontes = {n: f for n, f in fontes.items() if n in so}
    ativos = {n: fn for n, fn in fontes.items() if n not in desativados}
    with ThreadPoolExecutor(max_workers=max(len(ativos), 1)) as pool:
        resultados = dict(pool.map(lambda kv: _correr(kv[0], kv[1], c, email, dia), ativos.items()))
    modulos = {n: resultados.get(n, {"estado": "desativado", "dados": None}) for n in fontes}      # desativado pelo administrador: não se pede nada ao módulo
    modulos.update({n: {"estado": "nao_ligado", "dados": None} for n in NAO_LIGADOS if n not in modulos and (so is None or n in so)})
    # «sem_acesso» não é uma falha: o utilizador simplesmente não tem esse módulo
    degradado = any(m["estado"] in ("indisponivel", "erro") for m in modulos.values())
    return {"estado": "degradado" if degradado else "ok", "geradoEm": agora.isoformat(timespec="seconds"),
            "data": dia.isoformat(), "resumo": None, "modulos": modulos}
