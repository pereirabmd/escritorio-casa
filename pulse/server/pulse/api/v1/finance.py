from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request

from pulse.accounts import ContaErro
from pulse.api.v1.modules import exigir_modulo
from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import financas

router = APIRouter(prefix="/finance", tags=["finanças"], dependencies=[Depends(exigir_modulo("financas"))])
MES = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def _categorias(app, email: str) -> list[dict]:
    _, c = app.dados.pedir("GET", "/financas/categorias", email)
    return (c or {}).get("categorias", [])


@router.get("")
def ver(request: Request, mes: str | None = MES, janela: str = Query(default="mes", pattern="^(mes|30d)$"), s: Sessao = Depends(sessao_ativa)):
    """Um mês de lançamentos, o resumo «ativo − passivo» da janela escolhida e as despesas vencidas por pagar."""
    app = request.app.state
    email, hoje = s.user["email"], app.agora().date()
    mes = mes or hoje.strftime("%Y-%m")
    de, ate = financas.janela(janela, mes, hoje)
    lista = lambda q: (app.dados.pedir("GET", "/financas/lancamentos", email, q)[1] or {}).get("lancamentos", [])
    do_mes = lista({"mes": mes})
    da_janela = lista({"de": de, "ate": ate})
    atrasadas = lista({"pendentes": "1", "tipo": "despesa", "ate": (hoje - timedelta(days=1)).isoformat()})
    return financas.visao(mes, janela, hoje, do_mes, da_janela, atrasadas, _categorias(app, email))


@router.get("/reports")
def relatorio(request: Request, de: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), ate: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
              s: Sessao = Depends(sessao_ativa)):
    """Totais por mês e por categoria entre dois meses (no máximo 61)."""
    if de > ate or len(financas.meses_entre(de, ate)) > 61:
        raise ContaErro(400, "intervalo_invalido", "intervalo inválido (máximo 61 meses)")
    app = request.app.state
    email = s.user["email"]
    _, r = app.dados.pedir("GET", "/financas/agregado", email, {"de": de, "ate": ate})
    return financas.relatorio((r or {}).get("linhas", []), de, ate, _categorias(app, email))


@router.get("/reminders")
def lembretes(request: Request, s: Sessao = Depends(sessao_ativa)):
    """Os lembretes agendados (avisos ntfy próprios, únicos ou mensais)."""
    _, r = request.app.state.dados.pedir("GET", "/financas/lembretes", s.user["email"])
    return {"lembretes": (r or {}).get("lembretes", [])}
