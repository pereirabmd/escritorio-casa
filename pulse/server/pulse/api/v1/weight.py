from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import peso

router = APIRouter(prefix="/weight", tags=["peso"])


@router.get("")
def ver(request: Request, s: Sessao = Depends(sessao_ativa)):
    """O módulo Peso completo: registos, configuração e as estatísticas calculadas (partilhadas por Web e Android)."""
    app = request.app.state
    email = s.user["email"]
    _, r = app.dados.pedir("GET", "/peso/registos", email)
    _, cfg = app.dados.pedir("GET", "/peso/config", email)
    registos = (r or {}).get("registos", [])
    cfg = cfg or {}
    return {"registos": registos, "config": cfg, "resumo": peso.resumo(registos, cfg, app.agora().date())}
