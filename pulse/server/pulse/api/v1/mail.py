from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from pulse import google_api as g
from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.api.v1.calendar import marcar_reautorizar
from pulse.api.v1.modules import exigir_modulo
from pulse.services import contas_google, correio

router = APIRouter(prefix="/mail", tags=["email"], dependencies=[Depends(exigir_modulo("email"))])


def traduzir(e: g.GoogleErro) -> ContaErro:
    """Um erro da Google → um erro do Pulse com o motivo em pt-PT."""
    if e.reautorizar:
        return ContaErro(409, "reautorizar", "a autorização desta conta Google terminou: volta a ligá-la em Definições")
    if e.codigo == "sem_permissao":
        return ContaErro(403, "sem_permissao", "esta conta Google não deu permissão para isto")
    return ContaErro(502, "google_indisponivel", "a Google não respondeu como esperado; tenta de novo")


@router.get("")
def caixa(request: Request, filtro: str = Query(default="importantes", pattern="^(importantes|entrada|por_ler)$"), conta: int | None = Query(default=None, ge=1),
          s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """As mensagens das contas Gmail do utilizador (ou só de uma), mais recentes primeiro. Uma conta que falha vem em `contas` com o motivo."""
    app = request.app.state
    contas = contas_google.com_servico(conn, s.user["id"], "gmail", conta)
    if app.google is None or not contas:
        return {"ligado": False, "configurado": app.google is not None, "filtro": filtro, "contas": [], "mensagens": []}
    r = correio.caixa(app.google, contas, filtro, app.settings.tz)
    marcar_reautorizar(conn, r["contas"])
    return {"ligado": True, "configurado": True, **r}


@router.get("/{conta}/{mensagem}")
def detalhe(conta: int, mensagem: str, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Uma mensagem em texto simples (sem HTML, sem anexos). Ler não a marca como lida: isso é uma ação."""
    app = request.app.state
    if app.google is None:
        raise ContaErro(503, "google_desligado", "a integração com a Google não está configurada neste servidor")
    c = contas_google.obter(conn, s.user["id"], conta, "gmail")
    try:
        return correio.detalhe(app.google, c, mensagem, app.settings.tz)
    except g.GoogleErro as e:
        if e.reautorizar:
            contas_google.marcar_estado(conn, conta, "reautorizar")
        raise traduzir(e) from e
