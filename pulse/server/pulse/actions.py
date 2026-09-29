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
from pulse.services import rto as rto_regras

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


QUANDO = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")]


class PesoIn(_Params):
    peso: float = Field(ge=1, le=1000)
    nota: str = Field(default="", max_length=500)
    cid: CID | None = None
    quando: QUANDO | None = None        # por omissão, agora (o «Desfazer» de uma eliminação repõe a data original)

    @field_validator("peso")
    @classmethod
    def _finito(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("peso tem de ser um número")
        return round(v, 2)


class PesoEditarIn(_Params):
    registo: int = Field(ge=1)
    quando: QUANDO
    peso: float = Field(ge=1, le=1000)
    nota: str = Field(default="", max_length=500)


class RegistoIn(_Params):
    registo: int = Field(ge=1)


class PesoConfigIn(_Params):
    """Só se enviam os campos indicados; `null` apaga o valor (como na app dedicada)."""
    altura: float | None = Field(default=None, ge=50, le=260)
    nascimento: date | None = None
    sexo: Literal["M", "F"] | None = None
    pesoAlvo: float | None = Field(default=None, ge=1, le=1000)
    atividade: float | None = Field(default=None, ge=1, le=3)
    diaControlo: int | None = Field(default=None, ge=0, le=6)
    pesoMin: float | None = Field(default=None, ge=1, le=1000)
    pesoMax: float | None = Field(default=None, ge=1, le=1000)


class RtoIn(_Params):
    data: date
    marca: Literal["T", "C", ""]
    admin: bool = False                 # modo administrador: permite fins de semana e dias já passados (como na app dedicada)


class FeriasIn(_Params):
    data: date
    admin: bool = False


class NotaIn(_Params):
    inicio: date | None = None
    fim: date | None = None
    categoria: str = Field(default="", max_length=100)
    descricao: str = Field(default="", max_length=500)
    admin: bool = False       # «modo administrador» da app dedicada: notas em datas já passadas
    cid: CID | None = None


class NotaEditarIn(NotaIn):
    nota: int = Field(ge=1)


class NotaEliminarIn(_Params):
    nota: int = Field(ge=1)
    admin: bool = False


class ValidacoesIn(_Params):
    referencia: date
    ate: date
    tipo: Literal["Validação", "Validação Batica"] = "Validação"


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
    if p.quando:
        corpo["quando"] = p.quando
    _, r = c.client.pedir("POST", "/peso/registos", c.email, corpo=corpo)
    return r, ""                                            # o valor do peso não vai para o registo de atividade


def _peso_editar(c: Contexto, p: PesoEditarIn):
    _, r = c.client.pedir("PUT", f"/peso/registos/{p.registo}", c.email, corpo={"quando": p.quando, "peso": round(p.peso, 2), "nota": p.nota})
    return r, f"registo {p.registo}"


def _peso_eliminar(c: Contexto, p: RegistoIn):
    _, r = c.client.pedir("DELETE", f"/peso/registos/{p.registo}", c.email)
    return r, f"registo {p.registo}"                        # `r` é o registo apagado: a interface usa-o para «Desfazer»


def _peso_config(c: Contexto, p: PesoConfigIn):
    corpo = {}
    for campo in p.model_fields_set:
        v = getattr(p, campo)
        corpo[campo] = v.isoformat() if isinstance(v, date) else v
    if not corpo:
        raise ContaErro(400, "parametros_invalidos", "parâmetros inválidos: nada para alterar")
    if corpo.get("pesoMin") is not None and corpo.get("pesoMax") is not None and corpo["pesoMin"] > corpo["pesoMax"]:
        raise ContaErro(400, "parametros_invalidos", "o peso mínimo não pode ser maior do que o máximo")
    _, r = c.client.pedir("PUT", "/peso/config", c.email, corpo=corpo)
    return r, ", ".join(sorted(corpo))


def _exigir_dia_livre(c: Contexto, d: date, admin: bool) -> None:
    """Regra da app dedicada: no modo normal só se marcam dias úteis de hoje em diante; o modo administrador levanta a restrição."""
    if not admin and (d.weekday() >= 5 or d < c.hoje):
        raise ContaErro(400, "dia_bloqueado", "fins de semana e dias já passados só se alteram no modo administrador")


def _rto(c: Contexto, p: RtoIn):
    _exigir_dia_livre(c, p.data, p.admin)
    _, r = c.client.pedir("PUT", f"/rto/dias/{p.data.isoformat()}", c.email, corpo={"marca": p.marca})
    return r, f"{p.data.isoformat()} = {p.marca or 'limpo'}"


# --- RTO: férias, notas e validações (regras da app dedicada) ---------------------------------------------------------

def _notas(c: Contexto) -> list[dict]:
    _, r = c.client.pedir("GET", "/rto/notas", c.email)
    return (r or {}).get("notas", [])


def _corpo_nota(n: dict, **muda) -> dict:
    return {"dataInicio": n.get("dataInicio"), "dataFim": n.get("dataFim"), "categoria": n.get("categoria") or "",
            "descricao": n.get("descricao") or "", **muda}


def _e_ferias(n: dict) -> bool:
    return rto_regras.categoria_de(n) == "ferias"


def _ferias_dia(c: Contexto, p: FeriasIn):
    """Marca ou desmarca um dia de férias como na app dedicada: encolhe/divide/apaga a nota que o cobre, ou junta o dia às notas de
    férias vizinhas (dias úteis) e limpa a marca T/C desse dia (um dia de férias deixa de ser dia de trabalho)."""
    d, iso = p.data, p.data.isoformat()
    _exigir_dia_livre(c, d, p.admin)
    notas = _notas(c)
    pedir = c.client.pedir
    cobre = next((n for n in notas if _e_ferias(n) and (iv := rto_regras.intervalo(n)) and iv[0] <= d <= iv[1]), None)
    if cobre:
        ini, fim = rto_regras.intervalo(cobre)
        if ini == d == fim:
            pedir("DELETE", f"/rto/notas/{cobre['id']}", c.email)
        elif d == ini:
            pedir("PUT", f"/rto/notas/{cobre['id']}", c.email, corpo=_corpo_nota(cobre, dataInicio=(d + timedelta(days=1)).isoformat()))
        elif d == fim:
            pedir("PUT", f"/rto/notas/{cobre['id']}", c.email, corpo=_corpo_nota(cobre, dataFim=(d - timedelta(days=1)).isoformat()))
        else:
            pedir("PUT", f"/rto/notas/{cobre['id']}", c.email, corpo=_corpo_nota(cobre, dataFim=(d - timedelta(days=1)).isoformat()))
            pedir("POST", "/rto/notas", c.email, corpo={"dataInicio": (d + timedelta(days=1)).isoformat(), "dataFim": cobre.get("dataFim"),
                                                        "categoria": cobre.get("categoria") or "", "descricao": cobre.get("descricao") or ""})
        return {"ferias": False, "data": iso}, f"{iso} sem férias"
    ant = next((n for n in notas if _e_ferias(n) and n.get("dataFim") == rto_regras.dia_util_anterior(d).isoformat()), None)
    seg = next((n for n in notas if _e_ferias(n) and n.get("dataInicio") == rto_regras.dia_util_seguinte(d).isoformat()), None)
    if ant and seg:
        descr = " / ".join(dict.fromkeys(x.strip() for x in (ant.get("descricao"), seg.get("descricao")) if x and x.strip()))
        pedir("PUT", f"/rto/notas/{ant['id']}", c.email, corpo=_corpo_nota(ant, dataFim=seg.get("dataFim"), categoria=ant.get("categoria") or seg.get("categoria") or "", descricao=descr))
        pedir("DELETE", f"/rto/notas/{seg['id']}", c.email)
    elif ant:
        pedir("PUT", f"/rto/notas/{ant['id']}", c.email, corpo=_corpo_nota(ant, dataFim=iso))
    elif seg:
        pedir("PUT", f"/rto/notas/{seg['id']}", c.email, corpo=_corpo_nota(seg, dataInicio=iso))
    else:
        pedir("POST", "/rto/notas", c.email, corpo={"dataInicio": iso, "dataFim": iso, "categoria": "Férias", "descricao": ""})
    pedir("PUT", f"/rto/dias/{iso}", c.email, corpo={"marca": ""})
    return {"ferias": True, "data": iso}, f"{iso} férias"


def _vazia(p: NotaIn) -> bool:
    return not (p.inicio or p.fim or p.categoria.strip() or p.descricao.strip())


def _validar_nota(c: Contexto, p: NotaIn, existente: dict | None = None) -> None:
    if _vazia(p):
        raise ContaErro(400, "parametros_invalidos", "parâmetros inválidos: a nota não pode estar vazia")
    if p.inicio and p.fim and p.fim < p.inicio:
        raise ContaErro(400, "intervalo_invalido", "a data de fim é anterior à de início")
    if p.admin:
        return
    for fim in (p.fim or p.inicio, existente and (rto_regras.intervalo(existente) or (None, None))[1]):
        if fim and fim < c.hoje:
            raise ContaErro(400, "data_passada", "não é possível registar ou alterar notas em datas que já passaram sem o modo administrador")


def _corpo_de(p: NotaIn) -> dict:
    return {"dataInicio": p.inicio.isoformat() if p.inicio else None, "dataFim": p.fim.isoformat() if p.fim else None,
            "categoria": p.categoria.strip(), "descricao": p.descricao.strip()}


def _nota_criar(c: Contexto, p: NotaIn):
    _validar_nota(c, p)
    corpo = _corpo_de(p)
    if p.cid:
        corpo["cid"] = p.cid
    _, r = c.client.pedir("POST", "/rto/notas", c.email, corpo=corpo)
    return r, f"nota {r.get('id')}"


def _nota_existente(c: Contexto, nid: int) -> dict:
    n = next((x for x in _notas(c) if x["id"] == nid), None)
    if n is None:
        raise ErroDoModulo(404, "nao_encontrado", "nota inexistente")
    return n


def _nota_editar(c: Contexto, p: NotaEditarIn):
    _validar_nota(c, p, _nota_existente(c, p.nota))
    _, r = c.client.pedir("PUT", f"/rto/notas/{p.nota}", c.email, corpo=_corpo_de(p))
    return r, f"nota {p.nota}"


def _nota_eliminar(c: Contexto, p: NotaEliminarIn):
    if not p.admin:
        fim = (rto_regras.intervalo(_nota_existente(c, p.nota)) or (None, None))[1]
        if fim and fim < c.hoje:
            raise ContaErro(400, "data_passada", "não é possível eliminar notas de datas que já passaram sem o modo administrador")
    _, r = c.client.pedir("DELETE", f"/rto/notas/{p.nota}", c.email)
    return r, f"nota {p.nota}"                           # `r` é a nota apagada: a interface usa-a para «Desfazer»


def _nota_restaurar(c: Contexto, p: NotaEditarIn):
    """Volta a criar uma nota apagada com o mesmo id (o `PUT` do dados-api é um upsert por id)."""
    if _vazia(p):
        raise ContaErro(400, "parametros_invalidos", "parâmetros inválidos: a nota não pode estar vazia")
    _, r = c.client.pedir("PUT", f"/rto/notas/{p.nota}", c.email, corpo=_corpo_de(p))
    return r, f"nota {p.nota}"


MAX_VALIDACOES = 400


def _validacoes(c: Contexto, p: ValidacoesIn):
    """Validações de 14 em 14 dias, alternando os dois tipos, a partir de uma conhecida (sem repetir as que já existem)."""
    if p.ate < p.referencia:
        raise ContaErro(400, "intervalo_invalido", "a data limite tem de ser depois da data de referência")
    if (p.ate - p.referencia).days // 14 + 1 > MAX_VALIDACOES:
        raise ContaErro(400, "intervalo_invalido", f"intervalo demasiado grande (no máximo {MAX_VALIDACOES} validações)")
    outro = "Validação Batica" if p.tipo == "Validação" else "Validação"
    existentes = {(n.get("dataInicio"), n.get("dataFim"), n.get("categoria")) for n in _notas(c)}
    novas, ja, d, i = [], 0, p.referencia, 0
    while d <= p.ate:
        cat, iso = (p.tipo if i % 2 == 0 else outro), d.isoformat()
        if (iso, iso, cat) in existentes:
            ja += 1
        else:
            novas.append({"dataInicio": iso, "dataFim": iso, "categoria": cat, "descricao": ""})
            existentes.add((iso, iso, cat))
        d += timedelta(days=14); i += 1
    for k in range(0, len(novas), 100):                  # o dados-api aceita até 100 por chamada (atómica)
        c.client.pedir("POST", "/rto/notas/lote", c.email, corpo={"notas": novas[k:k + 100]})
    return {"criadas": len(novas), "existentes": ja}, f"{len(novas)} criadas, {ja} já existiam"


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
    Acao("peso.editar", "peso", "safe_action", "Corrige um registo de peso.", PesoEditarIn, _peso_editar),
    Acao("peso.eliminar", "peso", "sensitive_action", "Apaga um registo de peso.", RegistoIn, _peso_eliminar),
    Acao("peso.configurar", "peso", "safe_action", "Altera a configuração do Peso (altura, objetivo, controlo…).", PesoConfigIn, _peso_config),
    Acao("rto.marcar_dia", "rto", "safe_action", "Marca um dia como Escritório (T) ou Casa (C), ou limpa a marca.", RtoIn, _rto),
    Acao("rto.ferias_dia", "rto", "safe_action", "Marca ou desmarca um dia de férias (junta ou divide as notas de férias).", FeriasIn, _ferias_dia),
    Acao("rto.nota_criar", "rto", "safe_action", "Cria uma nota do RTO (férias, astreinte, suspensão, validação…).", NotaIn, _nota_criar),
    Acao("rto.nota_editar", "rto", "safe_action", "Altera uma nota do RTO.", NotaEditarIn, _nota_editar),
    Acao("rto.nota_eliminar", "rto", "sensitive_action", "Apaga uma nota do RTO.", NotaEliminarIn, _nota_eliminar),
    Acao("rto.nota_restaurar", "rto", "safe_action", "Repõe uma nota apagada, com o mesmo id (desfaz «eliminar»).", NotaEditarIn, _nota_restaurar),
    Acao("rto.gerar_validacoes", "rto", "safe_action", "Gera validações de 14 em 14 dias, alternando os dois tipos.", ValidacoesIn, _validacoes),
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
