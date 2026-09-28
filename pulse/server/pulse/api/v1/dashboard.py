from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today")
def hoje(request: Request, s: Sessao = Depends(sessao_ativa)):
    """O «Hoje»: tarefas, próximo bilhete, RTO da semana, peso e contas a pagar, num só pedido (cada módulo independente)."""
    app = request.app.state
    return dashboard.hoje(app.dados, s.user["email"], app.agora())
