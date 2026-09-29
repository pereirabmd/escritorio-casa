from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import rto

router = APIRouter(prefix="/rto", tags=["rto"])


@router.get("")
def ver(request: Request, ano: int | None = Query(default=None, ge=2000, le=2100), s: Sessao = Depends(sessao_ativa)):
    """O módulo RTO de um ano: dias marcados, notas, feriados, totais e saldo, estado de hoje (regras partilhadas Web/Android)."""
    app = request.app.state
    email, hoje = s.user["email"], app.agora().date()
    _, d = app.dados.pedir("GET", "/rto/dias", email)
    _, n = app.dados.pedir("GET", "/rto/notas", email)
    dias, notas = (d or {}).get("dias", {}), (n or {}).get("notas", [])
    a = ano or hoje.year
    return {"dias": {k: v for k, v in dias.items() if k[:4] in (str(a - 1), str(a), str(a + 1))},        # o ano pedido e os vizinhos
            "notas": notas, **rto.visao(dias, notas, a, hoje)}
