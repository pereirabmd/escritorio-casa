from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.api.v1.modules import exigir_modulo
from pulse.services import compras

router = APIRouter(prefix="/shopping", tags=["compras"], dependencies=[Depends(exigir_modulo("compras"))])


@router.get("")
def ver(request: Request, lista: int | None = Query(default=None, ge=1), s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Compras: as listas visíveis (a «Casa» partilhada e as pessoais), a lista escolhida (por corredor, e os comprados) e o catálogo com o
    estado de cada produto nessa lista, as categorias escondidas por esta conta e as `sugestoes` (`acabar`, `frequentes`). Regras em `services/compras.py`. Ler nunca escreve."""
    return compras.visao(conn, s.user["id"], lista, request.app.state.agora().date())
