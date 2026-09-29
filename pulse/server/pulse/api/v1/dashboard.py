from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import dashboard, modulos

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today")
def hoje(request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """O «Hoje»: tarefas, próximo bilhete, RTO da semana, peso e contas a pagar, num só pedido (cada módulo independente)."""
    app = request.app.state
    return dashboard.hoje(app.dados, s.user["email"], app.agora(), modulos.desativados(conn))
