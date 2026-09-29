from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from pulse import actions
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa

router = APIRouter(prefix="/actions", tags=["ações"])


class ExecutarIn(BaseModel):
    params: dict = Field(default_factory=dict)
    confirmado: bool = False


@router.get("")
def catalogo(_: Sessao = Depends(sessao_ativa)):
    """As ações disponíveis (a interface e a IA usam o mesmo catálogo)."""
    return {"acoes": actions.catalogo()}


@router.post("/{nome}")
def executar(nome: str, dados: ExecutarIn, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    app = request.app.state
    ctx = actions.Contexto(app.dados, s.user["email"], app.agora(), app.avisos, lambda: app.avisos.recalcular_em_fundo(s.user["email"]), app.google)
    return {"resultado": actions.executar(conn, ctx, nome, dados.params, origem="ui", confirmado=dados.confirmado)}
