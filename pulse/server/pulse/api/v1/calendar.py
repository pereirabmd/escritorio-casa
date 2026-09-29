from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from pulse import google_api as g
from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.api.v1.modules import exigir_modulo
from pulse.services import calendario, contas_google

router = APIRouter(prefix="/calendar", tags=["calendário"], dependencies=[Depends(exigir_modulo("calendario"))])


def marcar_reautorizar(conn, estados: list[dict]) -> None:
    for e in estados:
        if e["estado"] == "reautorizar":
            contas_google.marcar_estado(conn, e["id"], "reautorizar")


@router.get("")
def ver(request: Request, de: date = Query(), ate: date = Query(), s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """A agenda de todas as contas Google do utilizador entre duas datas (máx. 62 dias), por dia. Sem contas ligadas: `ligado: false`."""
    app = request.app.state
    contas = contas_google.com_servico(conn, s.user["id"], "calendar")
    if app.google is None or not contas:
        return {"ligado": False, "configurado": app.google is not None, "de": de.isoformat(), "ate": ate.isoformat(), "contas": [], "calendarios": [], "dias": []}
    r = calendario.agenda(app.google, contas, de, ate, app.settings.tz)
    marcar_reautorizar(conn, r["contas"])
    return {"ligado": True, "configurado": True, **r}
