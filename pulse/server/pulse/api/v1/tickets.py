from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from pulse.accounts import ContaErro
from pulse.api.v1.modules import exigir_modulo
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import bilhetes, bilhetes_favoritos, cp_horarios

router = APIRouter(prefix="/tickets", tags=["bilhetes"], dependencies=[Depends(exigir_modulo("bilhetes"))])


@router.get("")
def ver(request: Request, semana: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"), utilizador: int | None = Query(default=None, ge=1),
        s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Bilhetes CP: próxima viagem, semana em edição, bilhetes, passe, pedidos e registo (regras em `services/bilhetes.py`).
    `semana` = uma data qualquer da semana pretendida (usa-se a sua segunda-feira). `utilizador` = ver e marcar por outra pessoa (só o administrador,
    decidido no `dados-api`); por omissão, os da própria conta."""
    app = request.app.state
    try:
        alvo = bilhetes.segunda_de(date.fromisoformat(semana)) if semana else None
    except ValueError:
        raise ContaErro(400, "semana_invalida", "data inválida") from None
    _, d = app.dados.pedir("GET", "/bilhetes/dados", s.user["email"], {"utilizador": utilizador} if utilizador else None)
    r = bilhetes.visao(d or {}, app.agora(), alvo)
    bilhetes_favoritos.semear(conn, s.user["id"], r["historico"])        # 1.ª vez: os comboios que já usou
    return {**r, "favoritos": bilhetes_favoritos.listar(conn, s.user["id"])}


@router.get("/history")
def historico(request: Request, dias: int = Query(default=90, ge=1, le=90), s: Sessao = Depends(sessao_ativa)):
    """Todos os pedidos feitos à CP nas compras (hora, fase, resposta, tempo) e o desfecho de cada compra, até 90 dias. Só o administrador (decidido no `dados-api`)."""
    _, d = request.app.state.dados.pedir("GET", "/bilhetes/historico", s.user["email"], {"dias": dias}, timeout=20)
    return d or {"dias": dias, "truncado": False, "pedidos": [], "desfechos": []}


CP_TIMEOUT_S = 100        # a CP pode pedir um início de sessão (o `dados-api` espera até 90 s)


@router.get("/cp/futuros")
def cp_futuros(request: Request, utilizador: int | None = Query(default=None, ge=1), s: Sessao = Depends(sessao_ativa)):
    """Os bilhetes futuros da conta da CP de quem viaja (consulta ao vivo à CP, pelo `dados-api`; ADR-075)."""
    _, d = request.app.state.dados.pedir("GET", "/bilhetes/cp/futuros", s.user["email"], {"utilizador": utilizador} if utilizador else None, timeout=CP_TIMEOUT_S)
    return d or {"bilhetes": []}


@router.get("/cp/passe")
def cp_passe(request: Request, utilizador: int | None = Query(default=None, ge=1), s: Sessao = Depends(sessao_ativa)):
    """A validade do Passe Verde, lida da CP (ADR-075)."""
    _, d = request.app.state.dados.pedir("GET", "/bilhetes/cp/passe", s.user["email"], {"utilizador": utilizador} if utilizador else None, timeout=CP_TIMEOUT_S)
    return d or {"passes": []}


@router.get("/cp/simular")
def simular_devolucao(request: Request, venda: int = Query(ge=1), utilizador: int | None = Query(default=None, ge=1), s: Sessao = Depends(sessao_ativa)):
    """Simula a devolução de um bilhete futuro (só leitura, nunca cancela): a CP deixa devolver e quanto se recebe? Para a troca e «mudar de lugar» (ADR-087)."""
    q = {"venda": venda, **({"utilizador": utilizador} if utilizador else {})}
    _, d = request.app.state.dados.pedir("GET", "/bilhetes/trocas/simular", s.user["email"], q, timeout=CP_TIMEOUT_S)
    return d or {}


@router.get("/timetable")
def horario(request: Request, comboio: int = Query(ge=1, le=99999), data: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
            origem: str = Query(min_length=1, max_length=60), destino: str = Query(min_length=1, max_length=60),
            hora: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"), s: Sessao = Depends(sessao_ativa)):
    """Confere na CP o comboio, a data, o percurso e a hora (consultivo: o editor mostra o resultado, nunca bloqueia; ADR-068)."""
    try:
        d = date.fromisoformat(data)
    except ValueError:
        raise ContaErro(400, "data_invalida", "data inválida") from None
    return cp_horarios.verificar(request.app.state.cp, comboio, d, origem, destino, hora)
