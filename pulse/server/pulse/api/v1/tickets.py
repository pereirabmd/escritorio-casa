from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from pulse.accounts import ContaErro
from pulse.api.v1.modules import exigir_modulo
from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.services import bilhetes, cp_horarios

router = APIRouter(prefix="/tickets", tags=["bilhetes"], dependencies=[Depends(exigir_modulo("bilhetes"))])


@router.get("")
def ver(request: Request, semana: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"), s: Sessao = Depends(sessao_ativa)):
    """Bilhetes CP: próxima viagem, semana em edição, bilhetes, passe, pedidos e registo (regras em `services/bilhetes.py`).
    `semana` = uma data qualquer da semana pretendida (usa-se a sua segunda-feira)."""
    app = request.app.state
    try:
        alvo = bilhetes.segunda_de(date.fromisoformat(semana)) if semana else None
    except ValueError:
        raise ContaErro(400, "semana_invalida", "data inválida") from None
    _, d = app.dados.pedir("GET", "/bilhetes/dados", s.user["email"])
    return bilhetes.visao(d or {}, app.agora(), alvo)


@router.get("/timetable")
def horario(request: Request, comboio: int = Query(ge=1, le=99999), data: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
            origem: str = Query(min_length=1, max_length=60), destino: str = Query(min_length=1, max_length=60),
            hora: str | None = Query(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$"), s: Sessao = Depends(sessao_ativa)):
    """Confere na CP o comboio, a data, o percurso e a hora (consultivo: o editor mostra o resultado, nunca bloqueia; ADR-068)."""
    try:
        d = date.fromisoformat(data)
    except ValueError:
        raise ContaErro(400, "data_invalida", "data inválida") from None
    return cp_horarios.verificar(request.app.state.cp, comboio, d, origem, destino, hora)
