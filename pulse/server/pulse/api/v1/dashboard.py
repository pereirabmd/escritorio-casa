from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import calendario, compras, contas_google, correio, dashboard, modulos

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

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


class OrdemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordem: list[str] = Field(min_length=1, max_length=len(CARTOES))


@router.put("/order")
def guardar_ordem(d: OrdemIn, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Guarda a ordem dos cartões do Hoje do utilizador (ids desconhecidos ou repetidos são recusados)."""
    if len(set(d.ordem)) != len(d.ordem) or any(x not in CARTOES for x in d.ordem):
        raise ContaErro(422, "ordem_invalida", "a ordem tem ids de cartões desconhecidos ou repetidos")
    conn.execute("INSERT INTO pulse_hoje_ordem (user_id, ordem) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET ordem = excluded.ordem",
                 (s.user["id"], json.dumps(d.ordem)))
    return {"ordem": ordem_guardada(conn, s.user["id"])}


@router.get("/today")
def hoje(request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """O «Hoje»: tarefas, próximo bilhete, RTO da semana, peso e contas a pagar, num só pedido (cada módulo independente)."""
    app = request.app.state
    uid = s.user["id"]

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
            c = app.db()
            try:
                contas = contas_google.com_servico(c, uid, servico)
                if not contas:
                    raise dashboard.NaoLigado()
                r = fn(contas, dia)
                for problema in r["comProblemas"]:
                    if problema["estado"] == "reautorizar":
                        contas_google.marcar_estado(c, problema["id"], "reautorizar")
                return r
            finally:
                c.close()
        return local
    tz = app.settings.tz
    locais = {"compras": compras_hoje,
              "calendario": google_hoje("calendar", lambda contas, dia: calendario.hoje(app.google, contas, dia, tz)),
              "email": google_hoje("gmail", lambda contas, dia: correio.importantes_hoje(app.google, contas, tz))}
    r = dashboard.hoje(app.dados, s.user["email"], app.agora(), modulos.desativados(conn), locais)
    return {**r, "ordem": ordem_guardada(conn, uid)}
