"""Camada de ações do Pulse (Action/Tool layer, docs/AI_SPEC.md): tudo o que altera dados passa por aqui.

A interface (Web/Android) e, mais tarde, a IA chamam as MESMAS ações. Cada ação:
- declara o módulo e o nível (`read`, `safe_action`, `sensitive_action`; as sensíveis exigem confirmação);
- valida os parâmetros (pydantic) antes de tocar em nada;
- escreve pela API oficial do módulo (ADR-031), nunca na base de origem;
- fica registada no centro de atividade (`pulse_activity`), com a origem (`ui`/`ia`) e sem valores pessoais (só ids/datas).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel

CID = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{8,64}$")]


@dataclass
class Contexto:
    client: DadosClient
    email: str
    agora: datetime

    @property
    def hoje(self) -> date:
        return self.agora.date()


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InstanciaIn(_Params):
    instancia: str = Field(pattern=r"^I\d{1,20}$")


class AdiarIn(InstanciaIn):
    data: date | None = None            # por omissão, amanhã


class PesoIn(_Params):
    peso: float = Field(ge=1, le=1000)
    nota: str = Field(default="", max_length=500)
    cid: CID | None = None

    @field_validator("peso")
    @classmethod
    def _finito(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("peso tem de ser um número")
        return round(v, 2)


class RtoIn(_Params):
    data: date
    marca: Literal["T", "C", ""]


class PagarIn(_Params):
    lancamento: int = Field(ge=1)
    data: date | None = None            # por omissão, hoje


class LancamentoIn(_Params):
    lancamento: int = Field(ge=1)


@dataclass(frozen=True)
class Acao:
    nome: str
    modulo: str
    nivel: str
    descricao: str
    params: type[_Params]
    executar: Callable[[Contexto, _Params], tuple[dict, str]]      # (resultado, detalhe para o registo)


def _instancia(c: Contexto, iid: str, corpo: dict) -> dict:
    _, r = c.client.pedir("PUT", f"/tarefas/instancias/{iid}", c.email, corpo=corpo)
    return r


def _concluir(c: Contexto, p: InstanciaIn):
    return _instancia(c, p.instancia, {"estado": "Feita", "dataConclusao": c.agora.strftime("%Y-%m-%d %H:%M")}), p.instancia


def _reabrir(c: Contexto, p: InstanciaIn):
    return _instancia(c, p.instancia, {"estado": "Pendente", "dataConclusao": ""}), p.instancia


def _adiar(c: Contexto, p: AdiarIn):
    destino = p.data or c.hoje + timedelta(days=1)
    if destino < c.hoje:
        raise ContaErro(400, "data_passada", "não se pode adiar para uma data que já passou")
    # se já existir a mesma tarefa nesse dia, o módulo responde 409 e o Pulse não funde nada (ADR-033)
    return _instancia(c, p.instancia, {"data": destino.isoformat()}), f"{p.instancia} -> {destino.isoformat()}"


def _peso(c: Contexto, p: PesoIn):
    corpo = {"peso": p.peso, "nota": p.nota}
    if p.cid:
        corpo["cid"] = p.cid
    _, r = c.client.pedir("POST", "/peso/registos", c.email, corpo=corpo)
    return r, ""                                            # o valor do peso não vai para o registo de atividade


def _rto(c: Contexto, p: RtoIn):
    _, r = c.client.pedir("PUT", f"/rto/dias/{p.data.isoformat()}", c.email, corpo={"marca": p.marca})
    return r, f"{p.data.isoformat()} = {p.marca or 'limpo'}"


def _pagar(c: Contexto, p: PagarIn):
    _, r = c.client.pedir("PUT", f"/financas/lancamentos/{p.lancamento}", c.email,
                          corpo={"data_pagamento": (p.data or c.hoje).isoformat()})
    return r, f"lançamento {p.lancamento}"


def _anular_pagamento(c: Contexto, p: LancamentoIn):
    _, r = c.client.pedir("PUT", f"/financas/lancamentos/{p.lancamento}", c.email, corpo={"data_pagamento": None})
    return r, f"lançamento {p.lancamento}"


ACOES: dict[str, Acao] = {a.nome: a for a in (
    Acao("tarefas.concluir", "tarefas", "safe_action", "Marca uma tarefa de hoje como feita.", InstanciaIn, _concluir),
    Acao("tarefas.reabrir", "tarefas", "safe_action", "Volta a pôr uma tarefa como por fazer (desfaz «concluir»).", InstanciaIn, _reabrir),
    Acao("tarefas.adiar", "tarefas", "safe_action", "Passa uma tarefa para outra data (por omissão, amanhã).", AdiarIn, _adiar),
    Acao("peso.registar", "peso", "safe_action", "Regista o peso.", PesoIn, _peso),
    Acao("rto.marcar_dia", "rto", "safe_action", "Marca um dia como Escritório (T) ou Casa (C), ou limpa a marca.", RtoIn, _rto),
    Acao("financas.pagar", "financas", "safe_action", "Marca uma conta como paga.", PagarIn, _pagar),
    Acao("financas.anular_pagamento", "financas", "safe_action", "Volta a pôr uma conta como por pagar.", LancamentoIn, _anular_pagamento),
)}


def catalogo() -> list[dict]:
    return [{"nome": a.nome, "modulo": a.modulo, "nivel": a.nivel, "descricao": a.descricao} for a in ACOES.values()]


def _registar(conn: sqlite3.Connection, email: str, acao: Acao, origem: str, resultado: str, detalhe: str) -> None:
    conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem, resultado, detalhe) VALUES (?, ?, ?, ?, ?, ?)",
                 (email, acao.modulo, acao.nome, origem, resultado, detalhe[:200]))


def executar(conn: sqlite3.Connection, ctx: Contexto, nome: str, params: dict, origem: str = "ui", confirmado: bool = False) -> dict:
    acao = ACOES.get(nome)
    if acao is None:
        raise ContaErro(404, "acao_desconhecida", "ação desconhecida")
    try:
        p = acao.params.model_validate(params)
    except ValidationError as e:
        campos = ", ".join(sorted({str(x["loc"][0]) for x in e.errors() if x["loc"]}))
        raise ContaErro(400, "parametros_invalidos", f"parâmetros inválidos: {campos}" if campos else "parâmetros inválidos") from None
    if acao.nivel == "sensitive_action" and not confirmado:
        raise ContaErro(409, "confirmacao_necessaria", "esta ação precisa de confirmação")
    try:
        resultado, detalhe = acao.executar(ctx, p)
    except (ErroDoModulo, ModuloIndisponivel, ContaErro) as e:
        _registar(conn, ctx.email, acao, origem, "erro", getattr(e, "codigo", "modulo_indisponivel"))
        raise
    _registar(conn, ctx.email, acao, origem, "ok", detalhe)
    return resultado
