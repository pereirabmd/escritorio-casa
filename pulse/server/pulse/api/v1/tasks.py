from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import tarefas

router = APIRouter(prefix="/tasks", tags=["tarefas"])


@router.get("")
def ver(request: Request, s: Sessao = Depends(sessao_ativa)):
    """O módulo Tarefas: hoje, atrasadas, amanhã, catálogo de tarefas, pessoas e categorias (regras partilhadas Web/Android)."""
    app = request.app.state
    _, dados = app.dados.pedir("GET", "/tarefas/dados", s.user["email"])
    return tarefas.visao(dados or {}, app.agora().date(), s.user["email"])
