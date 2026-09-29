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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pulse import google_api as g
from pulse.accounts import ContaErro
from pulse.google_api import GoogleApi
from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel
from pulse.clients.tarefas_api import TarefasApiClient
from pulse.services import calendario, compras, contas_google, correio, modulos
from pulse.services import piscina as piscina_regras
from pulse.services import rto as rto_regras
from pulse.services import tarefas as tarefas_regras

CID = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{8,64}$")]


@dataclass
class Contexto:
    client: DadosClient
    email: str
    agora: datetime
    tarefas_api: TarefasApiClient | None = None          # servidor dos avisos ntfy (forçar a geração de ocorrências)
    avisos_tarefas: Callable[[], None] | None = None     # pede o recálculo dos avisos ntfy depois de mudar tarefas (melhor esforço)
    google: GoogleApi | None = None                     # Gmail/Calendar (ADR-049); None = não configurado
    conn: sqlite3.Connection | None = None              # o `pulse.db`: só as ações de módulos do próprio Pulse (Compras) o usam; `executar` preenche-o

    @property
    def hoje(self) -> date:
        return self.agora.date()


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InstanciaIn(_Params):
    instancia: str = Field(pattern=r"^I\d{1,20}$")


class ReabrirIn(InstanciaIn):
    tambem: list[Annotated[str, Field(pattern=r"^I\d{1,20}$")]] = Field(default_factory=list, max_length=100)     # as que «concluir» fechou de uma vez


class TarefaIn(_Params):
    """Uma tarefa do catálogo (campos e regras da app dedicada; o servidor do módulo volta a validar)."""
    nome: str = Field(min_length=1, max_length=200)
    categoria: str = Field(min_length=1, max_length=100)
    recorrencia: Literal["Diaria", "Semanal", "Dias especificos", "Mensal", "Trimestral", "Semestral", "Pontual"]
    dias: list[Literal["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"]] = Field(default_factory=list)      # Semanal / Dias especificos
    data: date | None = None                                                                                  # Pontual / Trimestral / Semestral
    diaMes: int | None = Field(default=None, ge=1, le=31)                                                     # Mensal
    hora: str = Field(default="", pattern=r"^([01]\d|2[0-3]):[0-5]\d$|^$")
    pessoa: str = Field(default="", max_length=60)
    prioridade: Literal["Alta", "Media", "Baixa"] = "Media"
    rotacao: list[str] = Field(default_factory=list, max_length=20)
    dependeDe: str = Field(default="", max_length=12)
    cid: CID | None = None

    @model_validator(mode="after")
    def _coerente(self):
        if self.recorrencia in tarefas_regras.COM_DIAS and not self.dias:
            raise ValueError("escolhe pelo menos um dia da semana")
        if self.recorrencia in tarefas_regras.COM_DATA and self.data is None:
            raise ValueError("falta a data")
        if self.recorrencia == "Mensal" and self.diaMes is None:
            raise ValueError("falta o dia do mês")
        return self


class TarefaEditarIn(TarefaIn):
    tarefa: str = Field(pattern=r"^T\d{1,8}$")


class TarefaApagarIn(_Params):
    tarefa: str = Field(pattern=r"^T\d{1,8}$")


class AdiarIn(InstanciaIn):
    data: date | None = None            # por omissão, amanhã


NOME_PESSOA = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[^,\x00-\x1f]+$")]      # sem vírgulas: as listas de pessoas guardam-se separadas por vírgula
EMAIL_OPC = Annotated[str, Field(default="", max_length=120, pattern=r"^$|^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")]
HORA_OPC = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$|^$")]


class PiscinaRegistarIn(_Params):
    item: str = Field(pattern=r"^P\d{2}$")


class PiscinaReporIn(PiscinaRegistarIn):
    """Volta ao estado anterior (o «Desfazer» de «marcar feita»)."""
    ultimaData: date | None = None
    proximaData: date | None = None
    usarIntervaloLongo: bool = False
    notificacaoEnviada: bool = False


class AvisosHorarioIn(_Params):
    ativos: bool


class PreferenciasIn(_Params):
    naoIncomodarInicio: HORA_OPC
    naoIncomodarFim: HORA_OPC


class PessoaAdicionarIn(_Params):
    nome: NOME_PESSOA
    email: EMAIL_OPC = ""


class PessoaEditarIn(_Params):
    nome: NOME_PESSOA               # o nome atual
    novoNome: NOME_PESSOA
    email: EMAIL_OPC = ""


class PessoaRemoverIn(_Params):
    nome: NOME_PESSOA
    substituto: NOME_PESSOA | None = None       # obrigatório se a pessoa tiver tarefas por fazer


class ReatribuirIn(_Params):
    de: NOME_PESSOA
    para: NOME_PESSOA


class AdminIn(_Params):
    admins: list[Annotated[str, Field(max_length=120)]] | None = Field(default=None, max_length=20)
    notificacoes: dict[Literal["piscina", "horario"], list[NOME_PESSOA]] | None = None

    @model_validator(mode="after")
    def _algo(self):
        if self.admins is None and self.notificacoes is None:
            raise ValueError("nada para alterar")
        return self


class VazioIn(_Params):
    pass


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


DESCRICAO_FIN = Annotated[str, Field(min_length=1, max_length=100)]
COR = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
MES_FIN = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class LancamentoNovoIn(_Params):
    tipo: Literal["despesa", "rendimento"]
    descricao: DESCRICAO_FIN
    valor: float = Field(gt=0, le=1_000_000_000)
    categoriaId: int = Field(ge=1)
    dataVencimento: date
    dataPagamento: date | None = None
    recorrente: bool = False
    mesReferencia: MES_FIN | None = None        # por omissão, o mês do vencimento
    cid: CID | None = None

    @field_validator("valor")
    @classmethod
    def _valor_ok(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("valor tem de ser um número")
        return round(v, 2)


class LancamentoEditarIn(_Params):
    """Só se enviam os campos a mudar; `dataPagamento: null` volta a pôr por pagar."""
    lancamento: int = Field(ge=1)
    tipo: Literal["despesa", "rendimento"] | None = None
    descricao: DESCRICAO_FIN | None = None
    valor: float | None = Field(default=None, gt=0, le=1_000_000_000)
    categoriaId: int | None = Field(default=None, ge=1)
    dataVencimento: date | None = None
    dataPagamento: date | None = None
    recorrente: bool | None = None
    mesReferencia: MES_FIN | None = None

    @model_validator(mode="after")
    def _algo(self):
        if not (self.model_fields_set - {"lancamento"}):
            raise ValueError("nada para alterar")
        if self.valor is not None:
            if not math.isfinite(self.valor):
                raise ValueError("valor tem de ser um número")
            self.valor = round(self.valor, 2)
        return self


class MesIn(_Params):
    mes: MES_FIN


class CategoriaIn(_Params):
    nome: Annotated[str, Field(min_length=1, max_length=40)]
    cor: COR | None = None


class CategoriaEditarIn(_Params):
    categoria: int = Field(ge=1)
    nome: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    cor: COR | None = None

    @model_validator(mode="after")
    def _algo(self):
        if not (self.model_fields_set - {"categoria"}):
            raise ValueError("nada para alterar")
        return self


class CategoriaRefIn(_Params):
    categoria: int = Field(ge=1)


HORA_FIN = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class LembreteIn(_Params):
    titulo: Annotated[str, Field(min_length=1, max_length=100)]
    nota: str = Field(default="", max_length=300)
    data: date
    hora: HORA_FIN
    repeticao: Literal["unica", "mensal"] = "unica"


class LembreteEditarIn(_Params):
    lembrete: int = Field(ge=1)
    titulo: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    nota: str | None = Field(default=None, max_length=300)
    data: date | None = None
    hora: HORA_FIN | None = None
    repeticao: Literal["unica", "mensal"] | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def _algo(self):
        if not (self.model_fields_set - {"lembrete"}):
            raise ValueError("nada para alterar")
        return self


class LembreteRefIn(_Params):
    lembrete: int = Field(ge=1)


ESTACAO = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[^\x00-\x1f\x7f]+$")]


class ViagemIn(_Params):
    data: date
    origem: ESTACAO
    destino: ESTACAO
    comboio: int = Field(ge=1, le=99999)
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ativo: bool = True

    @model_validator(mode="after")
    def _distintas(self):
        if self.origem.strip().lower() == self.destino.strip().lower():
            raise ValueError("origem e destino são iguais")
        return self


class SemanaIn(_Params):
    """Substitui as viagens da semana (segunda a domingo) pelas enviadas; o servidor preserva os ids das que continuam (a chave do lock de compra)."""
    inicio: date
    viagens: list[ViagemIn] = Field(max_length=100)

    @model_validator(mode="after")
    def _coerente(self):
        if self.inicio.weekday() != 0:
            raise ValueError("a semana começa à segunda-feira")
        fim = self.inicio + timedelta(days=6)
        chaves = set()
        for v in self.viagens:
            if not self.inicio <= v.data <= fim:
                raise ValueError("há viagens fora da semana")
            k = (v.data, v.comboio, v.hora)
            if k in chaves:
                raise ValueError("há viagens repetidas")
            chaves.add(k)
        return self


class PasseIn(_Params):
    dataUltimaCompra: date
    validadeDias: int | None = Field(default=None, ge=1, le=366)


class PedidoRepetirIn(_Params):
    pedido: int = Field(ge=1)
    retry: bool
    intervaloMinutos: int | None = Field(default=None, ge=1, le=1440)


class PedidoRefIn(_Params):
    pedido: int = Field(ge=1)


# --- Compras (dados do próprio Pulse) ----------------------------------------------------------------------------------------------

ID = Annotated[int, Field(ge=1)]
NOME_PRODUTO = Annotated[str, Field(min_length=1, max_length=80)]
CATEGORIA_COMPRAS = Annotated[str, Field(min_length=1, max_length=40)]
ICONE_COMPRAS = Annotated[str, Field(min_length=1, max_length=40)]


class ComprasAdicionarIn(_Params):
    """Por `produto` (id do catálogo) ou por `nome` (usa o produto com esse nome ou cria um próprio, na `categoria`)."""
    lista: ID
    produto: ID | None = None
    nome: NOME_PRODUTO | None = None
    categoria: CATEGORIA_COMPRAS | None = None
    icone: ICONE_COMPRAS | None = None
    cid: CID | None = None

    @model_validator(mode="after")
    def _um_so(self):
        if (self.produto is None) == (self.nome is None):
            raise ValueError("indica o produto ou o nome")
        return self


class ItemRefIn(_Params):
    item: ID


class ItemCompradoIn(ItemRefIn):
    comprado: bool


class ItemDetalhesIn(ItemRefIn):
    quantidade: int | None = Field(default=None, ge=1, le=999)
    nota: str = Field(default="", max_length=80)


class ItemMoverIn(ItemRefIn):
    lista: ID


class ListaRefIn(_Params):
    lista: ID


class ItemRestaurarIn(_Params):
    produto: ID
    quantidade: int | None = Field(default=None, ge=1, le=999)
    nota: str = Field(default="", max_length=80)
    estado: Literal["pendente", "comprado"] = "pendente"


class ComprasRestaurarIn(ListaRefIn):
    itens: list[ItemRestaurarIn] = Field(max_length=500)


class ProdutoRefIn(_Params):
    produto: ID


class ProdutoMarcaIn(ProdutoRefIn):
    valor: bool


class CategoriaMarcaIn(_Params):
    categoria: CATEGORIA_COMPRAS
    valor: bool


class ProdutoCriarIn(_Params):
    nome: NOME_PRODUTO
    categoria: CATEGORIA_COMPRAS
    icone: ICONE_COMPRAS | None = None


class ProdutoEditarIn(ProdutoRefIn):
    nome: NOME_PRODUTO | None = None
    categoria: CATEGORIA_COMPRAS | None = None
    icone: ICONE_COMPRAS | None = None

    @model_validator(mode="after")
    def _algo(self):
        if not (self.model_fields_set - {"produto"}):
            raise ValueError("nada para alterar")
        return self


class ListaCriarIn(_Params):
    nome: Annotated[str, Field(min_length=1, max_length=60)]
    tipo: Literal["partilhada", "pessoal"] = "pessoal"


class ListaEditarIn(ListaRefIn):
    nome: Annotated[str, Field(min_length=1, max_length=60)]


# --- Google: Calendar e Gmail (ADR-049) --------------------------------------------------------------------------------------------

HORA_G = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
ID_GOOGLE = Annotated[str, Field(pattern=r"^[A-Za-z0-9_@.\-]{1,200}$")]        # ids de calendário (o e-mail) e de evento/mensagem


class CalendarioCriarIn(_Params):
    conta: ID
    calendario: ID_GOOGLE = "primary"
    titulo: Annotated[str, Field(min_length=1, max_length=200)]
    data: date
    dataFim: date | None = None                     # inclusive; por omissão o mesmo dia
    inicio: HORA_G | None = None                    # sem horas = dia inteiro
    fim: HORA_G | None = None
    local: str = Field(default="", max_length=200)
    descricao: str = Field(default="", max_length=500)


class CalendarioEditarIn(_Params):
    conta: ID
    calendario: ID_GOOGLE = "primary"
    evento: ID_GOOGLE
    titulo: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    data: date | None = None
    dataFim: date | None = None
    inicio: HORA_G | None = None
    fim: HORA_G | None = None
    local: str | None = Field(default=None, max_length=200)
    descricao: str | None = Field(default=None, max_length=500)


class CalendarioApagarIn(_Params):
    conta: ID
    calendario: ID_GOOGLE = "primary"
    evento: ID_GOOGLE


class MensagemIn(_Params):
    conta: ID
    mensagem: Annotated[str, Field(pattern=r"^[A-Za-z0-9_\-]{6,64}$")]


class MensagemLidaIn(MensagemIn):
    lida: bool


class MensagemArquivadaIn(MensagemIn):
    arquivado: bool


class MensagemEstrelaIn(MensagemIn):
    estrela: bool


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
    """Concluir uma tarefa atrasada conclui também as outras ocorrências atrasadas da mesma tarefa (só a última aparece nas listas),
    numa só chamada atómica — como na app dedicada. O resultado diz quais foram, para o «Desfazer» as reabrir todas."""
    _, dados = c.client.pedir("GET", "/tarefas/dados", c.email)
    atual = next((i for i in (dados or {}).get("instancias", []) if i["id"] == p.instancia), None)
    if atual is None:
        raise ErroDoModulo(404, "nao_encontrado", f"instância {p.instancia} inexistente")
    quando = c.agora.strftime("%Y-%m-%d %H:%M")
    anteriores = [i["id"] for i in dados["instancias"] if atual["estado"] == "Atrasada" and i["id"] != atual["id"]
                  and i["tarefaId"] == atual["tarefaId"] and i["estado"] == "Atrasada"]
    if not anteriores:
        r = _instancia(c, p.instancia, {"estado": "Feita", "dataConclusao": quando})
        return {**r, "tambem": []}, p.instancia
    _, r = c.client.pedir("PUT", "/tarefas/instancias", c.email,
                          corpo={"atualizacoes": [{"id": i, "estado": "Feita", "dataConclusao": quando} for i in [p.instancia, *anteriores]]})
    return {**(r or {}), "tambem": anteriores}, f"{p.instancia} (+{len(anteriores)} atrasadas)"


def _reabrir(c: Contexto, p: ReabrirIn):
    if not p.tambem:
        return _instancia(c, p.instancia, {"estado": "Pendente", "dataConclusao": ""}), p.instancia
    _, r = c.client.pedir("PUT", "/tarefas/instancias", c.email,
                          corpo={"atualizacoes": [{"id": i, "estado": "Pendente", "dataConclusao": ""} for i in [p.instancia, *p.tambem]]})
    return r or {}, f"{p.instancia} (+{len(p.tambem)})"


def _saltar(c: Contexto, p: InstanciaIn):
    return _instancia(c, p.instancia, {"estado": "Saltada"}), p.instancia


def _corpo_tarefa(p: TarefaIn) -> dict:
    ehData = p.recorrencia in tarefas_regras.COM_DATA
    return {"nome": p.nome.strip(), "categoria": p.categoria.strip(), "recorrencia": p.recorrencia,
            # como na app dedicada: `diasSemana` guarda os dias («Seg,Qua») ou, nas tarefas com data, a data ISO
            "diasSemana": p.data.isoformat() if ehData and p.data else ",".join(p.dias) if p.recorrencia in tarefas_regras.COM_DIAS else "",
            "diaMes": p.diaMes if p.recorrencia == "Mensal" else None, "horaNotificacao": p.hora, "pessoaPadrao": p.pessoa,
            "prioridade": p.prioridade, "rotacaoPessoas": ",".join(p.rotacao), "dependeDe": p.dependeDe}


def _tarefa_criar(c: Contexto, p: TarefaIn):
    corpo = _corpo_tarefa(p)
    if p.cid:
        corpo["cid"] = p.cid
    _, r = c.client.pedir("POST", "/tarefas/tarefas", c.email, corpo=corpo)
    return r, f"tarefa {(r.get('tarefa') or {}).get('id', '?')}"


def _tarefa_editar(c: Contexto, p: TarefaEditarIn):
    _, r = c.client.pedir("PUT", f"/tarefas/tarefas/{p.tarefa}", c.email, corpo=_corpo_tarefa(p))
    return r, f"tarefa {p.tarefa}"


def _tarefa_apagar(c: Contexto, p: TarefaApagarIn):
    """«Apagar» é desativar e saltar o que estava por fazer; o histórico mantém-se (o módulo trata de tudo numa transação)."""
    _, r = c.client.pedir("DELETE", f"/tarefas/tarefas/{p.tarefa}", c.email)
    return r or {}, f"tarefa {p.tarefa}"


def _adiar(c: Contexto, p: AdiarIn):
    destino = p.data or c.hoje + timedelta(days=1)
    if destino < c.hoje:
        raise ContaErro(400, "data_passada", "não se pode adiar para uma data que já passou")
    # se já existir a mesma tarefa nesse dia, o módulo responde 409 e o Pulse não funde nada (ADR-033)
    return _instancia(c, p.instancia, {"data": destino.isoformat()}), f"{p.instancia} -> {destino.isoformat()}"


# --- Tarefas: piscina, horário e configuração ---------------------------------------------------------------------------------

def _dados_tarefas(c: Contexto) -> dict:
    _, d = c.client.pedir("GET", "/tarefas/dados", c.email)
    return d or {}


def _config_put(c: Contexto, valores: dict | None = None, apagar: list | None = None) -> dict:
    corpo = {k: v for k, v in (("valores", valores), ("apagar", apagar)) if v}
    _, r = c.client.pedir("PUT", "/tarefas/config", c.email, corpo=corpo)
    return r or {}


def _piscina_registar(c: Contexto, p: PiscinaRegistarIn):
    item = piscina_regras.POR_ID.get(p.item)
    if item is None:
        raise ErroDoModulo(404, "nao_encontrado", "tarefa da piscina inexistente")
    dados = _dados_tarefas(c)
    atual = next((x for x in dados.get("piscina", []) if x["id"] == p.item), None)
    if atual is None:
        raise ErroDoModulo(404, "nao_encontrado", "tarefa da piscina ainda não está na base")
    est = piscina_regras.estacao(tarefas_regras.config_de(dados.get("config", [])), c.hoje)
    novo = piscina_regras.novo_estado(item, est, atual, c.hoje)
    c.client.pedir("PUT", f"/tarefas/piscina/{p.item}", c.email, corpo=novo)
    nome = tarefas_regras.pessoa_do_utilizador(tarefas_regras.config_de(dados.get("config", [])), c.email) or ""
    try:                                            # quem fez o quê: nunca impede o registo principal
        c.client.pedir("POST", "/tarefas/auditoria", c.email, corpo={"acao": "piscina_feita", "tarefa": item["nome"], "pessoa": nome, "instanciaId": ""})
    except (ErroDoModulo, ModuloIndisponivel):
        pass
    anterior = {"ultimaData": atual.get("ultimaData") or None, "proximaData": atual.get("proximaData") or None,
                "usarIntervaloLongo": bool(atual.get("usarIntervaloLongo")), "notificacaoEnviada": bool(atual.get("notificacaoEnviada"))}
    return {"anterior": anterior, "atual": novo}, p.item


def _piscina_repor(c: Contexto, p: PiscinaReporIn):
    corpo = {"ultimaData": p.ultimaData.isoformat() if p.ultimaData else None, "proximaData": p.proximaData.isoformat() if p.proximaData else None,
             "usarIntervaloLongo": p.usarIntervaloLongo, "notificacaoEnviada": p.notificacaoEnviada}
    _, r = c.client.pedir("PUT", f"/tarefas/piscina/{p.item}", c.email, corpo=corpo)
    return r or {}, p.item


def _avisos_horario(c: Contexto, p: AvisosHorarioIn):
    _config_put(c, {"HorarioAvisos": "TRUE" if p.ativos else "FALSE"})
    return {"ativos": p.ativos}, "ativos" if p.ativos else "pausados"


def _preferencias(c: Contexto, p: PreferenciasIn):
    if bool(p.naoIncomodarInicio) != bool(p.naoIncomodarFim):
        raise ContaErro(400, "parametros_invalidos", "parâmetros inválidos: indica o início e o fim da janela (ou deixa ambos vazios)")
    _config_put(c, {"NaoIncomodarInicio": p.naoIncomodarInicio, "NaoIncomodarFim": p.naoIncomodarFim})
    return {"ok": True}, ""


def _pessoa_adicionar(c: Contexto, p: PessoaAdicionarIn):
    cfg = tarefas_regras.config_de(_dados_tarefas(c).get("config", []))
    if p.nome in [x["nome"] for x in tarefas_regras.pessoas(cfg)]:
        raise ContaErro(409, "pessoa_existe", "já existe uma pessoa com esse nome")
    n = tarefas_regras.proximo_numero_pessoa(cfg)
    valores = {f"Pessoa{n}_Nome": p.nome}
    if p.email:
        valores[f"Pessoa{n}_Email"] = p.email.lower()
    _config_put(c, valores)
    return {"num": n}, f"pessoa {n}"


def _pessoa_editar(c: Contexto, p: PessoaEditarIn):
    cfg = tarefas_regras.config_de(_dados_tarefas(c).get("config", []))
    atual = next((x for x in tarefas_regras.pessoas(cfg) if x["nome"] == p.nome), None)
    if atual is None:
        raise ErroDoModulo(404, "nao_encontrado", "pessoa inexistente")
    if p.novoNome != p.nome:
        if p.novoNome in [x["nome"] for x in tarefas_regras.pessoas(cfg)]:
            raise ContaErro(409, "pessoa_existe", "já existe uma pessoa com esse nome")
        # o nome novo, as tarefas e as ocorrências dessa pessoa mudam todos no mesmo passo (atómico)
        c.client.pedir("POST", "/tarefas/pessoas/reatribuir", c.email,
                       corpo={"de": p.nome, "para": p.novoNome, "apenasPendentes": False, "configChave": f"Pessoa{atual['num']}_Nome"})
    if p.email.lower() != atual["email"]:
        _config_put(c, {f"Pessoa{atual['num']}_Email": p.email.lower()})
    return {"num": atual["num"]}, f"pessoa {atual['num']}"


def _pessoa_remover(c: Contexto, p: PessoaRemoverIn):
    dados = _dados_tarefas(c)
    cfg = tarefas_regras.config_de(dados.get("config", []))
    todas = tarefas_regras.pessoas(cfg)
    atual = next((x for x in todas if x["nome"] == p.nome), None)
    if atual is None:
        raise ErroDoModulo(404, "nao_encontrado", "pessoa inexistente")
    if len(todas) <= 1:
        raise ContaErro(400, "ultima_pessoa", "tem de existir pelo menos uma pessoa")
    afetadas = sum(1 for t in dados.get("tarefas", []) if t.get("ativa") and t.get("pessoaPadrao") == p.nome) \
        + sum(1 for i in dados.get("instancias", []) if i["pessoa"] == p.nome and i["estado"] != "Feita")
    if afetadas:
        if not p.substituto or p.substituto == p.nome or p.substituto not in [x["nome"] for x in todas]:
            raise ContaErro(400, "substituto_necessario", f"{p.nome} tem {afetadas} tarefa(s) por fazer: escolhe quem fica responsável")
        c.client.pedir("POST", "/tarefas/pessoas/reatribuir", c.email, corpo={"de": p.nome, "para": p.substituto, "apenasPendentes": True})
    # remove todas as chaves dessa pessoa (nome, e-mail, cor, credenciais ntfy)
    prefixo = f"Pessoa{atual['num']}_"
    _config_put(c, apagar=[k for k in cfg if k.startswith(prefixo)])
    return {"reatribuidas": afetadas}, f"pessoa {atual['num']}" + (f", {afetadas} passadas" if afetadas else "")


def _reatribuir(c: Contexto, p: ReatribuirIn):
    nomes = [x["nome"] for x in tarefas_regras.pessoas(tarefas_regras.config_de(_dados_tarefas(c).get("config", [])))]
    if p.de == p.para:
        raise ContaErro(400, "pessoas_iguais", "escolhe pessoas diferentes")
    if p.de not in nomes or p.para not in nomes:
        raise ErroDoModulo(404, "nao_encontrado", "pessoa inexistente")
    _, r = c.client.pedir("POST", "/tarefas/pessoas/reatribuir", c.email, corpo={"de": p.de, "para": p.para, "apenasPendentes": True})
    return r or {}, f"{p.de} -> {p.para}"


def _admin(c: Contexto, p: AdminIn):
    corpo = {k: getattr(p, k) for k in ("admins", "notificacoes") if getattr(p, k) is not None}
    _, r = c.client.pedir("PUT", "/tarefas/admin", c.email, corpo=corpo)
    return r or {}, ", ".join(sorted(corpo))


def _gerar(c: Contexto, p: VazioIn):
    r = c.tarefas_api.gerar(c.email) if c.tarefas_api else None
    if not r or not r.get("ok"):
        raise ModuloIndisponivel("o servidor das tarefas não respondeu")
    return {"criadas": r.get("criadas", 0)}, f"{r.get('criadas', 0)} novas"


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


_CAMPOS_FIN = {"tipo": "tipo", "descricao": "descricao", "valor": "valor", "categoriaId": "categoria_id",
               "recorrente": "recorrente", "mesReferencia": "mes_referencia"}


def _corpo_lancamento(p: BaseModel, campos: set[str] | None = None) -> dict:
    """Do formato do Pulse (camelCase, datas) para o do módulo (snake_case, texto ISO); só os campos indicados."""
    v = p.model_dump(exclude={"lancamento", "cid"})
    corpo = {}
    for k, val in v.items():
        if campos is not None and k not in campos:
            continue
        if k == "dataVencimento":
            if val is not None:
                corpo["data_vencimento"] = val.isoformat()
        elif k == "dataPagamento":
            corpo["data_pagamento"] = val.isoformat() if val else None
        elif k in _CAMPOS_FIN and val is not None:
            corpo[_CAMPOS_FIN[k]] = val
    return corpo


def _lancamento_criar(c: Contexto, p: LancamentoNovoIn):
    corpo = _corpo_lancamento(p)
    if p.cid:
        corpo["cid"] = p.cid
    _, r = c.client.pedir("POST", "/financas/lancamentos", c.email, corpo=corpo)
    return r, f"lançamento {(r or {}).get('id', '?')}"


def _lancamento_editar(c: Contexto, p: LancamentoEditarIn):
    _, r = c.client.pedir("PUT", f"/financas/lancamentos/{p.lancamento}", c.email, corpo=_corpo_lancamento(p, p.model_fields_set - {"lancamento"}))
    return r, f"lançamento {p.lancamento}"


def _lancamento_apagar(c: Contexto, p: LancamentoIn):
    """Devolve o lançamento apagado: a interface usa-o para o «Desfazer» (voltar a criá-lo)."""
    _, r = c.client.pedir("DELETE", f"/financas/lancamentos/{p.lancamento}", c.email)
    return r, f"lançamento {p.lancamento}"


def _mes_preparar(c: Contexto, p: MesIn):
    _, r = c.client.pedir("POST", f"/financas/meses/{p.mes}/preparar", c.email)
    return r, f"{p.mes}: {(r or {}).get('criados', 0)} criados"


def _categoria_criar(c: Contexto, p: CategoriaIn):
    _, r = c.client.pedir("POST", "/financas/categorias", c.email, corpo=p.model_dump(exclude_none=True))
    return r, f"categoria {(r or {}).get('id', '?')}"


def _categoria_editar(c: Contexto, p: CategoriaEditarIn):
    _, r = c.client.pedir("PUT", f"/financas/categorias/{p.categoria}", c.email, corpo=p.model_dump(exclude={"categoria"}, exclude_none=True))
    return r, f"categoria {p.categoria}"


def _categoria_eliminar(c: Contexto, p: CategoriaRefIn):
    _, r = c.client.pedir("DELETE", f"/financas/categorias/{p.categoria}", c.email)
    return r or {}, f"categoria {p.categoria}"


def _corpo_lembrete(p: BaseModel, campos: set[str]) -> dict:
    v = p.model_dump(exclude={"lembrete"})
    return {k: (val.isoformat() if isinstance(val, date) else val) for k, val in v.items() if k in campos and val is not None}


def _lembrete_criar(c: Contexto, p: LembreteIn):
    _, r = c.client.pedir("POST", "/financas/lembretes", c.email, corpo=_corpo_lembrete(p, set(LembreteIn.model_fields)))
    return r, f"lembrete {(r or {}).get('id', '?')}"


def _lembrete_editar(c: Contexto, p: LembreteEditarIn):
    _, r = c.client.pedir("PUT", f"/financas/lembretes/{p.lembrete}", c.email, corpo=_corpo_lembrete(p, p.model_fields_set - {"lembrete"}))
    return r, f"lembrete {p.lembrete}"


def _lembrete_eliminar(c: Contexto, p: LembreteRefIn):
    _, r = c.client.pedir("DELETE", f"/financas/lembretes/{p.lembrete}", c.email)
    return r, f"lembrete {p.lembrete}"


# --- Bilhetes CP -----------------------------------------------------------------------------------------------------------------

def _corpo_viagem(v: ViagemIn) -> dict:
    return {"data": v.data.isoformat(), "origem": v.origem.strip(), "destino": v.destino.strip(), "comboio": v.comboio, "hora": v.hora, "ativo": "SIM" if v.ativo else "NAO"}


def _semana(c: Contexto, p: SemanaIn):
    """Guarda a semana. Devolve também as viagens que lá estavam, para o «Desfazer» (voltar a gravar a semana com elas)."""
    fim = (p.inicio + timedelta(days=6)).isoformat()
    _, d = c.client.pedir("GET", "/bilhetes/dados", c.email)
    antes = [{k: v[k] for k in ("data", "origem", "destino", "comboio", "hora", "ativo")} for v in (d or {}).get("viagens", []) if p.inicio.isoformat() <= v["data"] <= fim]
    _, r = c.client.pedir("PUT", "/bilhetes/semana", c.email, corpo={"inicio": p.inicio.isoformat(), "viagens": [_corpo_viagem(v) for v in p.viagens]})
    return {**(r or {}), "anteriores": antes}, f"semana {p.inicio.isoformat()}: {len(p.viagens)} viagens"


def _passe(c: Contexto, p: PasseIn):
    corpo = {"dataUltimaCompra": p.dataUltimaCompra.isoformat(), **({"validadeDias": p.validadeDias} if p.validadeDias else {})}
    _, r = c.client.pedir("PUT", "/bilhetes/passe", c.email, corpo=corpo)
    return r, f"passe {p.dataUltimaCompra.isoformat()}"


def _pedido_repetir(c: Contexto, p: PedidoRepetirIn):
    _, r = c.client.pedir("PUT", f"/bilhetes/pedidos/{p.pedido}", c.email, corpo={"retry": p.retry, "intervaloMinutos": p.intervaloMinutos})
    return r, f"pedido {p.pedido}"


def _pedido_forcar(c: Contexto, p: PedidoRefIn):
    _, r = c.client.pedir("POST", f"/bilhetes/pedidos/{p.pedido}/forcar", c.email)
    return r, f"pedido {p.pedido}"


# --- Compras -----------------------------------------------------------------------------------------------------------------------

def _quem(c: Contexto) -> tuple[int, bool]:
    """(id, administrador) da conta que executa a ação. As ações de Compras escrevem no `pulse.db` (é o único módulo cujos dados são do Pulse)."""
    if c.conn is None:
        raise ContaErro(500, "sem_base", "ação sem ligação à base do Pulse")
    r = c.conn.execute("SELECT id, admin FROM pulse_users WHERE email = ?", (c.email,)).fetchone()
    if r is None:
        raise ContaErro(403, "sem_acesso", "conta desconhecida")
    return r["id"], bool(r["admin"])


def _c_adicionar(c: Contexto, p: ComprasAdicionarIn):
    uid, _ = _quem(c)
    r = compras.adicionar(c.conn, uid, p.lista, p.produto, p.nome, p.categoria, p.icone, p.cid, int(c.agora.timestamp()))
    return r, f"item {r['id']}"


def _c_remover(c: Contexto, p: ItemRefIn):
    uid, _ = _quem(c)
    return compras.remover(c.conn, uid, p.item), f"item {p.item}"


def _c_comprado(c: Contexto, p: ItemCompradoIn):
    uid, _ = _quem(c)
    return compras.comprado(c.conn, uid, p.item, p.comprado, int(c.agora.timestamp()), c.hoje.isoformat()), f"item {p.item} {'comprado' if p.comprado else 'por comprar'}"


def _c_detalhes(c: Contexto, p: ItemDetalhesIn):
    uid, _ = _quem(c)
    return compras.detalhes(c.conn, uid, p.item, p.quantidade, p.nota), f"item {p.item}"


def _c_mover(c: Contexto, p: ItemMoverIn):
    uid, _ = _quem(c)
    return compras.mover(c.conn, uid, p.item, p.lista), f"item {p.item} -> lista {p.lista}"


def _c_limpar(c: Contexto, p: ListaRefIn):
    uid, _ = _quem(c)
    r = compras.limpar_comprados(c.conn, uid, p.lista)
    return r, f"lista {p.lista}: {len(r['removidos'])} comprados"


def _c_restaurar(c: Contexto, p: ComprasRestaurarIn):
    uid, _ = _quem(c)
    r = compras.restaurar(c.conn, uid, p.lista, [i.model_dump() for i in p.itens], int(c.agora.timestamp()))
    return r, f"lista {p.lista}: {r['repostos']} repostos"


def _c_favorito(c: Contexto, p: ProdutoMarcaIn):
    uid, _ = _quem(c)
    return compras.favorito(c.conn, uid, p.produto, p.valor), f"produto {p.produto}"


def _c_ocultar(c: Contexto, p: ProdutoMarcaIn):
    uid, _ = _quem(c)
    return compras.ocultar(c.conn, uid, p.produto, p.valor), f"produto {p.produto}"


def _c_sugestao_ignorar(c: Contexto, p: ProdutoMarcaIn):
    uid, _ = _quem(c)
    return compras.sugestao_ignorar(c.conn, uid, p.produto, p.valor), f"produto {p.produto}"


def _c_categoria_ocultar(c: Contexto, p: CategoriaMarcaIn):
    uid, _ = _quem(c)
    return compras.categoria_ocultar(c.conn, uid, p.categoria, p.valor), f"categoria {p.categoria}"


def _c_produto_criar(c: Contexto, p: ProdutoCriarIn):
    uid, _ = _quem(c)
    r = compras.produto_criar(c.conn, uid, p.nome, p.categoria, p.icone, int(c.agora.timestamp()))
    return r, f"produto {r['id']}"


def _c_produto_editar(c: Contexto, p: ProdutoEditarIn):
    uid, admin = _quem(c)
    return compras.produto_editar(c.conn, uid, admin, p.produto, p.nome, p.categoria, p.icone), f"produto {p.produto}"


def _c_produto_apagar(c: Contexto, p: ProdutoRefIn):
    uid, admin = _quem(c)
    return compras.produto_apagar(c.conn, uid, admin, p.produto), f"produto {p.produto}"


def _c_lista_criar(c: Contexto, p: ListaCriarIn):
    uid, _ = _quem(c)
    r = compras.lista_criar(c.conn, uid, p.nome, p.tipo, int(c.agora.timestamp()))
    return r, f"lista {r['id']}"


def _c_lista_editar(c: Contexto, p: ListaEditarIn):
    uid, _ = _quem(c)
    return compras.lista_editar(c.conn, uid, p.lista, p.nome), f"lista {p.lista}"


def _c_lista_apagar(c: Contexto, p: ListaRefIn):
    uid, _ = _quem(c)
    return compras.lista_apagar(c.conn, uid, p.lista), f"lista {p.lista}"


# --- Google -----------------------------------------------------------------------------------------------------------------------

def _google(c: Contexto, servico: str, conta: int) -> tuple[GoogleApi, dict]:
    if c.google is None:
        raise ContaErro(503, "google_desligado", "a integração com a Google não está configurada neste servidor")
    uid, _ = _quem(c)
    return c.google, contas_google.obter(c.conn, uid, conta, servico)


def _traduzir(c: Contexto, conta: int, e: g.GoogleErro) -> ContaErro:
    if e.reautorizar:
        contas_google.marcar_estado(c.conn, conta, "reautorizar")
        return ContaErro(409, "reautorizar", "a autorização desta conta Google terminou: volta a ligá-la em Definições")
    if e.codigo == "sem_permissao":
        return ContaErro(403, "sem_permissao", "esta conta Google não deu permissão para isto")
    return ContaErro(502, "google_indisponivel", "a Google não respondeu como esperado; tenta de novo")


def _chamar(c: Contexto, conta: int, fn):
    try:
        return fn()
    except g.GoogleErro as e:
        raise _traduzir(c, conta, e) from e


def _cal_criar(c: Contexto, p: CalendarioCriarIn):
    api, conta = _google(c, "calendar", p.conta)
    r = _chamar(c, p.conta, lambda: calendario.criar(api, conta, c.agora.tzinfo, p.calendario, p.titulo, p.data, p.dataFim, p.inicio, p.fim, p.local, p.descricao))
    return r, f"evento em {p.data.isoformat()}"


def _cal_editar(c: Contexto, p: CalendarioEditarIn):
    api, conta = _google(c, "calendar", p.conta)
    campos = p.model_fields_set
    r = _chamar(c, p.conta, lambda: calendario.editar(api, conta, c.agora.tzinfo, p.calendario, p.evento, p.titulo, p.data, p.dataFim, p.inicio, p.fim,
                                                     p.local if "local" in campos else None, p.descricao if "descricao" in campos else None))
    return r, "evento editado"


def _cal_apagar(c: Contexto, p: CalendarioApagarIn):
    api, conta = _google(c, "calendar", p.conta)
    r = _chamar(c, p.conta, lambda: calendario.apagar(api, conta, c.agora.tzinfo, p.calendario, p.evento))
    return r, "evento apagado"


def _mail_lida(c: Contexto, p: MensagemLidaIn):
    api, conta = _google(c, "gmail", p.conta)
    return _chamar(c, p.conta, lambda: correio.marcar_lida(api, conta, p.mensagem, p.lida, c.agora.tzinfo)), f"mensagem {'lida' if p.lida else 'por ler'}"


def _mail_arquivar(c: Contexto, p: MensagemArquivadaIn):
    api, conta = _google(c, "gmail", p.conta)
    return _chamar(c, p.conta, lambda: correio.arquivar(api, conta, p.mensagem, p.arquivado, c.agora.tzinfo)), f"mensagem {'arquivada' if p.arquivado else 'na entrada'}"


def _mail_estrela(c: Contexto, p: MensagemEstrelaIn):
    api, conta = _google(c, "gmail", p.conta)
    return _chamar(c, p.conta, lambda: correio.estrela(api, conta, p.mensagem, p.estrela, c.agora.tzinfo)), f"mensagem {'com' if p.estrela else 'sem'} estrela"


ACOES: dict[str, Acao] = {a.nome: a for a in (
    Acao("tarefas.concluir", "tarefas", "safe_action", "Marca uma tarefa como feita (e as atrasadas anteriores da mesma tarefa).", InstanciaIn, _concluir),
    Acao("tarefas.reabrir", "tarefas", "safe_action", "Volta a pôr uma tarefa como por fazer (desfaz «concluir»).", ReabrirIn, _reabrir),
    Acao("tarefas.saltar", "tarefas", "safe_action", "Salta uma tarefa (não a faz desta vez).", InstanciaIn, _saltar),
    Acao("tarefas.criar", "tarefas", "safe_action", "Cria uma tarefa no catálogo.", TarefaIn, _tarefa_criar),
    Acao("tarefas.editar", "tarefas", "safe_action", "Altera uma tarefa do catálogo.", TarefaEditarIn, _tarefa_editar),
    Acao("tarefas.apagar", "tarefas", "sensitive_action", "Apaga uma tarefa (desativa-a e salta as ocorrências por fazer).", TarefaApagarIn, _tarefa_apagar),
    Acao("tarefas.adiar", "tarefas", "safe_action", "Passa uma tarefa para outra data (por omissão, amanhã).", AdiarIn, _adiar),
    Acao("tarefas.piscina_registar", "tarefas", "safe_action", "Regista uma tarefa da piscina como feita hoje (calcula a próxima data).", PiscinaRegistarIn, _piscina_registar),
    Acao("tarefas.piscina_repor", "tarefas", "safe_action", "Repõe o estado anterior de uma tarefa da piscina (desfaz «feita hoje»).", PiscinaReporIn, _piscina_repor),
    Acao("tarefas.avisos_horario", "tarefas", "safe_action", "Ativa ou pausa os avisos do horário escolar.", AvisosHorarioIn, _avisos_horario),
    Acao("tarefas.preferencias", "tarefas", "safe_action", "Define a janela «não incomodar» das notificações.", PreferenciasIn, _preferencias),
    Acao("tarefas.pessoa_adicionar", "tarefas", "safe_action", "Adiciona uma pessoa às tarefas.", PessoaAdicionarIn, _pessoa_adicionar),
    Acao("tarefas.pessoa_editar", "tarefas", "safe_action", "Renomeia uma pessoa (e as suas tarefas) ou muda o e-mail.", PessoaEditarIn, _pessoa_editar),
    Acao("tarefas.pessoa_remover", "tarefas", "sensitive_action", "Remove uma pessoa, passando as tarefas por fazer para outra.", PessoaRemoverIn, _pessoa_remover),
    Acao("tarefas.reatribuir", "tarefas", "sensitive_action", "Passa as tarefas por fazer de uma pessoa para outra.", ReatribuirIn, _reatribuir),
    Acao("tarefas.admin", "tarefas", "sensitive_action", "Altera os administradores e quem recebe as notificações gerais (só administradores).", AdminIn, _admin),
    Acao("tarefas.gerar", "tarefas", "safe_action", "Cria já as ocorrências dos próximos dias.", VazioIn, _gerar),
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
    Acao("bilhetes.semana", "bilhetes", "safe_action", "Guarda as viagens de uma semana (substitui as da semana; o Pi lê a nova configuração).", SemanaIn, _semana),
    Acao("bilhetes.passe", "bilhetes", "safe_action", "Regista a data do último carregamento do passe.", PasseIn, _passe),
    Acao("bilhetes.pedido_repetir", "bilhetes", "safe_action", "Liga ou desliga a repetição automática de um pedido avulso.", PedidoRepetirIn, _pedido_repetir),
    Acao("bilhetes.pedido_forcar", "bilhetes", "safe_action", "Pede ao Pi uma tentativa imediata de um pedido avulso.", PedidoRefIn, _pedido_forcar),
    Acao("calendario.criar", "calendario", "safe_action", "Cria um evento no Google Calendar (sem horas = dia inteiro).", CalendarioCriarIn, _cal_criar),
    Acao("calendario.editar", "calendario", "safe_action", "Altera um evento do Google Calendar.", CalendarioEditarIn, _cal_editar),
    Acao("calendario.apagar", "calendario", "sensitive_action", "Apaga um evento do Google Calendar.", CalendarioApagarIn, _cal_apagar),
    Acao("email.lida", "email", "safe_action", "Marca uma mensagem do Gmail como lida ou por ler.", MensagemLidaIn, _mail_lida),
    Acao("email.arquivar", "email", "safe_action", "Arquiva uma mensagem do Gmail (ou volta a pô-la na entrada).", MensagemArquivadaIn, _mail_arquivar),
    Acao("email.estrela", "email", "safe_action", "Marca ou desmarca uma mensagem do Gmail com estrela.", MensagemEstrelaIn, _mail_estrela),
    Acao("compras.adicionar", "compras", "safe_action", "Põe um produto (do catálogo ou pelo nome) numa lista de compras.", ComprasAdicionarIn, _c_adicionar),
    Acao("compras.remover", "compras", "safe_action", "Tira um item de uma lista de compras.", ItemRefIn, _c_remover),
    Acao("compras.comprado", "compras", "safe_action", "Marca um item como comprado (ou volta a pô-lo por comprar).", ItemCompradoIn, _c_comprado),
    Acao("compras.detalhes", "compras", "safe_action", "Define a quantidade (opcional) e a nota de um item.", ItemDetalhesIn, _c_detalhes),
    Acao("compras.mover", "compras", "safe_action", "Passa um item para outra lista.", ItemMoverIn, _c_mover),
    Acao("compras.limpar_comprados", "compras", "sensitive_action", "Apaga os itens já comprados de uma lista.", ListaRefIn, _c_limpar),
    Acao("compras.restaurar", "compras", "safe_action", "Repõe itens que se tinham tirado (o «Desfazer» de remover e de limpar).", ComprasRestaurarIn, _c_restaurar),
    Acao("compras.favorito", "compras", "safe_action", "Marca ou desmarca um produto como favorito (por conta).", ProdutoMarcaIn, _c_favorito),
    Acao("compras.ocultar", "compras", "safe_action", "Esconde ou mostra um produto no catálogo (por conta).", ProdutoMarcaIn, _c_ocultar),
    Acao("compras.sugestao_ignorar", "compras", "safe_action", "Deixa de sugerir (ou volta a sugerir) um produto a esta conta.", ProdutoMarcaIn, _c_sugestao_ignorar),
    Acao("compras.categoria_ocultar", "compras", "safe_action", "Esconde ou mostra uma categoria inteira do catálogo desta conta.", CategoriaMarcaIn, _c_categoria_ocultar),
    Acao("compras.produto_criar", "compras", "safe_action", "Cria um produto próprio no catálogo.", ProdutoCriarIn, _c_produto_criar),
    Acao("compras.produto_editar", "compras", "safe_action", "Altera um produto próprio (nome, categoria ou ícone).", ProdutoEditarIn, _c_produto_editar),
    Acao("compras.produto_apagar", "compras", "sensitive_action", "Apaga um produto próprio e os itens que o usam.", ProdutoRefIn, _c_produto_apagar),
    Acao("compras.lista_criar", "compras", "safe_action", "Cria uma lista de compras (pessoal ou partilhada).", ListaCriarIn, _c_lista_criar),
    Acao("compras.lista_editar", "compras", "safe_action", "Renomeia uma lista de compras.", ListaEditarIn, _c_lista_editar),
    Acao("compras.lista_apagar", "compras", "sensitive_action", "Apaga uma lista de compras e os seus itens.", ListaRefIn, _c_lista_apagar),
    Acao("financas.pagar", "financas", "safe_action", "Marca uma conta como paga.", PagarIn, _pagar),
    Acao("financas.anular_pagamento", "financas", "safe_action", "Volta a pôr uma conta como por pagar.", LancamentoIn, _anular_pagamento),
    Acao("financas.criar", "financas", "safe_action", "Cria um lançamento (despesa ou rendimento).", LancamentoNovoIn, _lancamento_criar),
    Acao("financas.editar", "financas", "safe_action", "Altera um lançamento.", LancamentoEditarIn, _lancamento_editar),
    Acao("financas.apagar", "financas", "sensitive_action", "Apaga um lançamento.", LancamentoIn, _lancamento_apagar),
    Acao("financas.preparar_mes", "financas", "safe_action", "Prepara o mês copiando os lançamentos recorrentes do mês anterior.", MesIn, _mes_preparar),
    Acao("financas.categoria_criar", "financas", "safe_action", "Cria uma categoria.", CategoriaIn, _categoria_criar),
    Acao("financas.categoria_editar", "financas", "safe_action", "Renomeia uma categoria ou muda a cor.", CategoriaEditarIn, _categoria_editar),
    Acao("financas.categoria_eliminar", "financas", "sensitive_action", "Apaga uma categoria sem lançamentos.", CategoriaRefIn, _categoria_eliminar),
    Acao("financas.lembrete_criar", "financas", "safe_action", "Agenda um lembrete (aviso ntfy), único ou mensal.", LembreteIn, _lembrete_criar),
    Acao("financas.lembrete_editar", "financas", "safe_action", "Altera ou pausa um lembrete.", LembreteEditarIn, _lembrete_editar),
    Acao("financas.lembrete_eliminar", "financas", "sensitive_action", "Apaga um lembrete.", LembreteRefIn, _lembrete_eliminar),
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
    modulos.exigir(conn, acao.modulo)
    ctx.conn = ctx.conn or conn
    if acao.nivel == "sensitive_action" and not confirmado:
        raise ContaErro(409, "confirmacao_necessaria", "esta ação precisa de confirmação")
    try:
        resultado, detalhe = acao.executar(ctx, p)
    except (ErroDoModulo, ModuloIndisponivel, ContaErro) as e:
        _registar(conn, ctx.email, acao, origem, "erro", getattr(e, "codigo", "modulo_indisponivel"))
        raise
    _registar(conn, ctx.email, acao, origem, "ok", detalhe)
    if acao.modulo == "tarefas" and ctx.avisos_tarefas:
        ctx.avisos_tarefas()
    return resultado
