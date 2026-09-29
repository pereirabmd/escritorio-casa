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
    def ultimo_desde(desde: str | None):
        _, corpo = c.pedir("GET", "/peso/registos", email, {"desde": desde} if desde else None)
        regs = (corpo or {}).get("registos", [])
        return regs[-1] if regs else None

    ultimo = ultimo_desde((hoje - timedelta(days=90)).isoformat()) or ultimo_desde(None)
    return {"ultimo": ultimo and {"quando": ultimo["quando"], "peso": ultimo["peso"]},
            "registadoHoje": bool(ultimo and ultimo["quando"][:10] == hoje.isoformat()),
            "sugestao": ultimo["peso"] if ultimo else None}      # pré-preenche o campo de hoje


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
    return {"hoje": hoje_l, "atrasadas": atrasadas, "feitasHoje": feitas, "totalHoje": len(hoje_l) + feitas,
            "pessoa": pessoa}


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
         locais: dict[str, Callable[[date], dict]] | None = None) -> dict:
    """`locais`: módulos cujos dados não vêm do `dados-api` (Compras e Google, no `pulse.db`/na rede). Cada função recebe o dia,
    abre a sua própria ligação (as threads do agregado não partilham ligações SQLite) e corre em paralelo com os outros."""
    dia = agora.date()
    locais = locais or {}
    fontes = {**MODULOS, **{n: (lambda f: lambda _c, _e, d: f(d))(f) for n, f in locais.items()}}
    ativos = {n: fn for n, fn in fontes.items() if n not in desativados}
    with ThreadPoolExecutor(max_workers=max(len(ativos), 1)) as pool:
        resultados = dict(pool.map(lambda kv: _correr(kv[0], kv[1], c, email, dia), ativos.items()))
    modulos = {n: resultados.get(n, {"estado": "desativado", "dados": None}) for n in fontes}      # desativado pelo administrador: não se pede nada ao módulo
    modulos.update({n: {"estado": "nao_ligado", "dados": None} for n in NAO_LIGADOS if n not in modulos})
    # «sem_acesso» não é uma falha: o utilizador simplesmente não tem esse módulo
    degradado = any(m["estado"] in ("indisponivel", "erro") for m in modulos.values())
    return {"estado": "degradado" if degradado else "ok", "geradoEm": agora.isoformat(timespec="seconds"),
            "data": dia.isoformat(), "resumo": None, "modulos": modulos}
