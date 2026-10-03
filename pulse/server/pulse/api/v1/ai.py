"""Agente de IA (ADR-077): `POST /ai/command` devolve o texto e as propostas; `POST /ai/confirm` corre as que o utilizador confirmou."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import ia

router = APIRouter(prefix="/ai", tags=["ia"])


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    papel: Literal["utilizador", "assistente"]
    texto: Annotated[str, Field(min_length=1, max_length=ia.MAX_TEXTO)]


class Posicao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class ComandoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mensagens: Annotated[list[Mensagem], Field(min_length=1, max_length=ia.MAX_MENSAGENS)]
    posicao: Posicao | None = None            # onde está o aparelho (só serve para o tempo; nunca se guarda)


class Proposta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acao: Annotated[str, Field(min_length=3, max_length=60)]
    params: dict = Field(default_factory=dict)


class ConfirmarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    propostas: Annotated[list[Proposta], Field(min_length=1, max_length=20)]


@router.get("/status")
def estado(request: Request, _: Sessao = Depends(sessao_ativa)):
    return {"ativo": request.app.state.ia.ativo}


@router.post("/command")
def comando(d: ComandoIn, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    app = request.app.state
    return app.ia.conversar(conn, app, s.user, [m.model_dump() for m in d.mensagens], app.agora(), d.posicao.model_dump() if d.posicao else None)


@router.post("/confirm")
def confirmar(d: ConfirmarIn, request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    app = request.app.state
    return {"resultados": ia.confirmar(conn, app, s.user, [p.model_dump() for p in d.propostas], app.agora())}
