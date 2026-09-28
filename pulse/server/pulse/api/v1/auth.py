"""Autenticação do Pulse (ADR-037): e-mail + password, sessão própria.

Web: cookie httpOnly/Secure/SameSite=Lax (e cabeçalho `X-Pulse-Client` obrigatório em pedidos que alteram, contra CSRF).
Android: `cliente: "android"` no login devolve o token, que se envia depois em `Authorization: Bearer`.
Enquanto a conta tiver `must_change_password`, só `/auth/me`, `/auth/password` e `/auth/logout` funcionam.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from pulse import accounts

router = APIRouter(prefix="/auth", tags=["autenticação"])
COOKIE = "pulse_session"


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    cliente: str = Field(default="web", pattern="^(web|android)$")


class PasswordIn(BaseModel):
    atual: str = Field(max_length=200)
    nova: str = Field(max_length=200)


@dataclass
class Sessao:
    user: sqlite3.Row
    sessao: sqlite3.Row


def get_conn(request: Request):
    conn = request.app.state.db()
    try:
        yield conn
    finally:
        conn.close()


def _token(request: Request) -> tuple[str | None, bool]:
    """(token, veio_do_cookie)."""
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip(), False
    return request.cookies.get(COOKIE), True


def sessao_pendente(request: Request, conn=Depends(get_conn)) -> Sessao:
    """Sessão válida, mesmo que a conta ainda tenha de mudar a password."""
    token, cookie = _token(request)
    achada = accounts.resolver_sessao(conn, token or "", request.app.state.settings.session_days)
    if achada is None:
        raise accounts.ContaErro(401, "nao_autenticado", "inicia sessão")
    if cookie and request.method not in ("GET", "HEAD", "OPTIONS") and "x-pulse-client" not in request.headers:
        raise accounts.ContaErro(403, "csrf", "cabeçalho X-Pulse-Client em falta")
    return Sessao(*achada)


def sessao_ativa(s: Sessao = Depends(sessao_pendente)) -> Sessao:
    """Sessão válida e conta pronta a usar (password já mudada). É a dependência dos módulos do Pulse."""
    if s.user["must_change_password"]:
        raise accounts.ContaErro(403, "mudar_password", "tens de mudar a palavra-passe antes de continuar")
    return s


def _user_json(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "email": u["email"], "nome": u["nome"], "admin": bool(u["admin"]),
            "mudarPassword": bool(u["must_change_password"])}


def _atividade(conn, email: str, acao: str, resultado: str = "ok", detalhe: str = "") -> None:
    conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem, resultado, detalhe) "
                 "VALUES (?, 'conta', ?, 'sistema', ?, ?)", (email, acao, resultado, detalhe[:200]))


@router.post("/login")
def login(dados: LoginIn, request: Request, response: Response, conn=Depends(get_conn)):
    app = request.app.state
    ip = request.client.host if request.client else "-"
    if not app.limite_login.allow(ip):
        raise accounts.ContaErro(429, "demasiadas_tentativas", "demasiadas tentativas; abranda")
    try:
        u = accounts.autenticar(conn, dados.email, dados.password)
    except accounts.ContaErro as e:
        if e.status in (401, 429):
            _atividade(conn, dados.email.strip().lower()[:254], "login", "erro", e.codigo)
        raise
    token = accounts.criar_sessao(conn, u["id"], request.headers.get("user-agent", ""), ip, dados.cliente,
                                  app.settings.session_days)
    _atividade(conn, u["email"], "login", detalhe=dados.cliente)
    corpo = {"utilizador": _user_json(u)}
    if dados.cliente == "android":
        corpo["token"] = token          # a app guarda-o de forma segura e envia-o em Authorization: Bearer
    else:
        response.set_cookie(COOKIE, token, max_age=app.settings.session_days * 86400, httponly=True,
                            secure=app.settings.production, samesite="lax", path=app.settings.web_base_path)   # a Web nunca vê o token
    return corpo


@router.get("/me")
def me(s: Sessao = Depends(sessao_pendente)):
    return {"utilizador": _user_json(s.user)}


@router.post("/logout")
def logout(request: Request, response: Response, s: Sessao = Depends(sessao_pendente), conn=Depends(get_conn)):
    accounts.revogar_sessao(conn, s.sessao["id"], s.user["id"])
    _atividade(conn, s.user["email"], "logout")
    response.delete_cookie(COOKIE, path=request.app.state.settings.web_base_path)
    return {"ok": True}


@router.post("/password")
def alterar_password(dados: PasswordIn, s: Sessao = Depends(sessao_pendente), conn=Depends(get_conn)):
    accounts.alterar_password(conn, s.user, dados.atual, dados.nova, s.sessao["id"])
    _atividade(conn, s.user["email"], "alterar_password")
    return {"ok": True}


@router.get("/sessions")
def sessoes(s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    return {"sessoes": [{"id": r["id"], "criada": r["criado"], "ultimoUso": r["ultimo_uso"], "expira": r["expira"],
                         "dispositivo": r["dispositivo"], "ip": r["ip"], "cliente": r["cliente"],
                         "atual": r["id"] == s.sessao["id"]} for r in accounts.listar_sessoes(conn, s.user["id"])]}


@router.delete("/sessions/{sessao_id}")
def terminar_sessao(sessao_id: int, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    if not accounts.revogar_sessao(conn, sessao_id, s.user["id"]):
        raise accounts.ContaErro(404, "nao_encontrada", "sessão inexistente")
    _atividade(conn, s.user["email"], "terminar_sessao", detalhe=str(sessao_id))
    return {"ok": True}
