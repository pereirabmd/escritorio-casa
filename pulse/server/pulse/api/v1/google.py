"""Ligar contas Google ao Pulse (ADR-049). O login do Pulse é outra coisa (ADR-037): aqui só se dá ao servidor acesso ao Gmail/Calendar."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from pulse import google_api as g
from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import contas_google

router = APIRouter(prefix="/google", tags=["google"])


def _api(request: Request) -> g.GoogleApi:
    api = request.app.state.google
    if api is None:
        raise ContaErro(503, "google_desligado", "a integração com a Google não está configurada neste servidor")
    return api


def _atividade(conn, email: str, acao: str, resultado: str = "ok", detalhe: str = "") -> None:
    conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem, resultado, detalhe) VALUES (?, 'conta', ?, 'ui', ?, ?)", (email, acao, resultado, detalhe[:200]))


@router.get("/accounts")
def contas(request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """As contas Google ligadas por este utilizador (sem tokens) e se o servidor tem a integração configurada."""
    return {"configurado": request.app.state.google is not None, "servicos": list(g.SERVICOS), "contas": contas_google.listar(conn, s.user["id"])}


class LigarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servicos: list[str] = Field(min_length=1, max_length=2)


@router.post("/connect")
def ligar(d: LigarIn, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Devolve o endereço do ecrã de consentimento da Google. A interface abre-o; o Google regressa a `/google/callback`."""
    return {"url": contas_google.iniciar(conn, _api(request), s.user["id"], d.servicos, s.user["email"])}


@router.get("/callback")
def regresso(request: Request, code: str = Query(default=""), state: str = Query(default=""), error: str = Query(default=""), conn=Depends(get_conn)):
    """O regresso do Google. Não usa a sessão: o `state` (um só uso, 10 min) é que diz quem pediu a ligação."""
    web = request.app.state.settings.web_base_path
    destino = lambda ok, motivo="": RedirectResponse(f"{web}definicoes?google={'ok' if ok else 'erro'}{('&motivo=' + motivo) if motivo else ''}", status_code=303)
    if error or not code or not state:
        return destino(False, "recusado" if error == "access_denied" else "invalido")
    api = request.app.state.google
    if api is None:
        return destino(False, "google_desligado")
    try:
        r = contas_google.concluir(conn, api, state, code)
    except ContaErro as e:
        return destino(False, e.codigo)
    u = conn.execute("SELECT email FROM pulse_users WHERE id = ?", (r["user_id"],)).fetchone()
    _atividade(conn, u["email"] if u else "?", "google.ligar", detalhe=f"conta {r['conta']}: {','.join(r['servicos'])}")
    return destino(True)


@router.delete("/accounts/{conta}")
def remover(conta: int, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    r = contas_google.remover(conn, request.app.state.google, s.user["id"], conta)
    _atividade(conn, s.user["email"], "google.remover", detalhe=f"conta {conta}")
    return {"id": r["id"]}
