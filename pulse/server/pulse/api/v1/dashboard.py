from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import calendario, compras, contas_google, correio, dashboard, modulos

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CACHE_GOOGLE_S = 60          # os cartões Google (chamadas lentas à rede) repetem-se no máximo 1×/min por utilizador
CARTOES = ("calendario", "tarefas", "email", "bilhetes", "rto", "peso", "compras", "financas")   # ordem de origem do Hoje


def ordem_guardada(conn, uid: int) -> list[str]:
    """A ordem do utilizador completada com os cartões que ela não menciona (novos módulos entram no fim, na ordem de origem)."""
    linha = conn.execute("SELECT ordem FROM pulse_hoje_ordem WHERE user_id = ?", (uid,)).fetchone()
    try:
        guardada = [x for x in json.loads(linha["ordem"]) if x in CARTOES] if linha else []
    except (ValueError, TypeError):
        guardada = []
    vistos = list(dict.fromkeys(guardada))
    return vistos + [c for c in CARTOES if c not in vistos]


def ocultos_guardados(conn, uid: int) -> list[str]:
    """Os cartões que esta pessoa escondeu do seu Hoje."""
    linha = conn.execute("SELECT ocultos FROM pulse_hoje_ordem WHERE user_id = ?", (uid,)).fetchone()
    try:
        return [x for x in dict.fromkeys(json.loads(linha["ocultos"])) if x in CARTOES] if linha else []
    except (ValueError, TypeError):
        return []


def _estado_do_hoje(conn, uid: int) -> dict:
    """Ordem e cartões escondidos da pessoa, e quais cartões existem para ela (módulo ligado e com acesso)."""
    indisponiveis = modulos.indisponiveis_para(conn, uid)
    return {"ordem": ordem_guardada(conn, uid), "ocultos": ocultos_guardados(conn, uid), "disponiveis": [c for c in CARTOES if c not in indisponiveis]}


class OrdemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordem: list[str] | None = Field(default=None, min_length=1, max_length=len(CARTOES))
    ocultos: list[str] | None = Field(default=None, max_length=len(CARTOES))


@router.get("/order")
def ver_ordem(s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """O «Hoje» desta pessoa (ordem, cartões escondidos e cartões disponíveis), para o ecrã das Definições."""
    return _estado_do_hoje(conn, s.user["id"])


@router.put("/order")
def guardar_ordem(d: OrdemIn, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Guarda a ordem e/ou os cartões escondidos do Hoje desta pessoa (ids desconhecidos ou repetidos são recusados; o que não vem não muda)."""
    for lista in (d.ordem, d.ocultos):
        if lista is not None and (len(set(lista)) != len(lista) or any(x not in CARTOES for x in lista)):
            raise ContaErro(422, "ordem_invalida", "a lista tem ids de cartões desconhecidos ou repetidos")
    uid = s.user["id"]
    ordem = d.ordem if d.ordem is not None else ordem_guardada(conn, uid)
    ocultos = d.ocultos if d.ocultos is not None else ocultos_guardados(conn, uid)
    conn.execute("INSERT INTO pulse_hoje_ordem (user_id, ordem, ocultos) VALUES (?, ?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET ordem = excluded.ordem, ocultos = excluded.ocultos", (uid, json.dumps(ordem), json.dumps(ocultos)))
    return _estado_do_hoje(conn, uid)


@router.get("/today")
def hoje(request: Request, modulos_: str | None = Query(None, alias="modulos"), s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """O «Hoje»: tarefas, próximo bilhete, RTO da semana, peso e contas a pagar, num só pedido (cada módulo independente).
    `?modulos=tarefas,peso` devolve só esses (é o que as interfaces pedem depois de uma ação: o resto não muda e a Google é lenta)."""
    so = {m for m in (modulos_ or "").split(",") if m in CARTOES} if modulos_ else None
    app = request.app.state
    uid = s.user["id"]
    if not hasattr(app, "cache_google"):
        app.cache_google = {}               # por aplicação (não global): cada base de dados tem os seus
    cache_google = app.cache_google

    def compras_hoje(_dia):
        c = app.db()
        try:
            return compras.resumo_hoje(c, uid)
        finally:
            c.close()
    def google_hoje(servico, fn):
        def local(dia):
            if app.google is None:
                raise dashboard.NaoLigado()
            em_cache = cache_google.get((uid, servico))
            if em_cache and time.monotonic() - em_cache[0] < CACHE_GOOGLE_S:
                return em_cache[1]
            c = app.db()
            try:
                contas = contas_google.com_servico(c, uid, servico)
                if not contas:
                    raise dashboard.NaoLigado()
                r = fn(contas, dia)
                for problema in r["comProblemas"]:
                    if problema["estado"] == "reautorizar":
                        contas_google.marcar_estado(c, problema["id"], "reautorizar")
                if not r["comProblemas"]:
                    cache_google[(uid, servico)] = (time.monotonic(), r)
                return r
            finally:
                c.close()
        return local
    tz = app.settings.tz
    locais = {"compras": compras_hoje,
              "calendario": google_hoje("calendar", lambda contas, dia: calendario.hoje(app.google, contas, dia, tz, agora=app.agora())),
              "email": google_hoje("gmail", lambda contas, dia: correio.importantes_hoje(app.google, contas, tz))}
    r = dashboard.hoje(app.dados, s.user["email"], app.agora(), modulos.indisponiveis_para(conn, uid) | set(ocultos_guardados(conn, uid)), locais, so)
    return {**r, "ordem": ordem_guardada(conn, uid), "ocultos": ocultos_guardados(conn, uid)}
