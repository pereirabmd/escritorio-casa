from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import calendario, compras, contas_google, correio, dashboard, modulos

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today")
def hoje(request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """O «Hoje»: tarefas, próximo bilhete, RTO da semana, peso e contas a pagar, num só pedido (cada módulo independente)."""
    app = request.app.state
    uid = s.user["id"]

    def compras_hoje(_dia):
        c = app.db()
        try:
            return compras.resumo_hoje(c, uid)
        finally:
            c.close()
    def google_hoje(servico, fn):
        def local(dia):
            if app.google is None:
                raise dashboard.NaoLigado()
            c = app.db()
            try:
                contas = contas_google.com_servico(c, uid, servico)
                if not contas:
                    raise dashboard.NaoLigado()
                r = fn(contas, dia)
                for problema in r["comProblemas"]:
                    if problema["estado"] == "reautorizar":
                        contas_google.marcar_estado(c, problema["id"], "reautorizar")
                return r
            finally:
                c.close()
        return local
    tz = app.settings.tz
    locais = {"compras": compras_hoje,
              "calendario": google_hoje("calendar", lambda contas, dia: calendario.hoje(app.google, contas, dia, tz)),
              "email": google_hoje("gmail", lambda contas, dia: correio.importantes_hoje(app.google, contas, tz))}
    return dashboard.hoje(app.dados, s.user["email"], app.agora(), modulos.desativados(conn), locais)
