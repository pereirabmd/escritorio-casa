from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services.tempo import TempoIndisponivel

router = APIRouter(prefix="/weather", tags=["tempo"])


@router.get("")
def previsao(request: Request, lat: float | None = Query(default=None), lon: float | None = Query(default=None), s: Sessao = Depends(sessao_ativa)):
    """A previsão (agora, hoje, próximas 24 horas e 5 dias) para as coordenadas do aparelho; sem coordenadas válidas, Aveiro (`localizacao: omissao`).
    As coordenadas só servem para este pedido (arredondadas, em cache, nunca nos registos)."""
    app = request.app.state
    try:
        return app.tempo.previsao(lat, lon, app.agora())
    except TempoIndisponivel as e:
        raise ContaErro(503, "tempo_indisponivel", "a previsão do tempo não está disponível agora; tenta daqui a pouco") from e
