"""Pessoas (só administradores, ADR-063): criar contas, dar e tirar módulos a cada pessoa, ativar/desativar e repor a palavra-passe provisória.

Não há auto-registo (ADR-037): é aqui que uma pessoa nova entra. Uma conta nova só tem os módulos que o administrador lhe der; a palavra-passe
inicial é provisória e obriga a mudá-la no primeiro acesso. Tudo fica no centro de atividade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from pulse import accounts
from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import modulos

router = APIRouter(prefix="/admin", tags=["administração"])


def _admin(s: Sessao = Depends(sessao_ativa)) -> Sessao:
    if not s.user["admin"]:
        raise ContaErro(403, "sem_permissao", "só o administrador pode gerir as pessoas")
    return s


def _atividade(conn, quem: str, acao: str, detalhe: str) -> None:
    conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem, resultado, detalhe) VALUES (?, 'conta', ?, 'ui', 'ok', ?)", (quem, acao, detalhe[:200]))


def _pessoa(conn, u) -> dict:
    return {"id": u["id"], "email": u["email"], "nome": u["nome"], "admin": bool(u["admin"]), "ativo": bool(u["ativo"]),
            "mudarPassword": bool(u["must_change_password"]), "ultimoLogin": u["ultimo_login"], "modulos": sorted(modulos.permitidos(conn, u["id"]))}


def _alvo(conn, uid: int):
    u = conn.execute("SELECT * FROM pulse_users WHERE id = ?", (uid,)).fetchone()
    if u is None:
        raise ContaErro(404, "nao_encontrado", "essa pessoa não existe")
    return u


@router.get("/users")
def listar(_: Sessao = Depends(_admin), conn=Depends(get_conn)):
    return {"pessoas": [_pessoa(conn, u) for u in conn.execute("SELECT * FROM pulse_users ORDER BY id")]}


class CriarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=5, max_length=254)
    nome: str = Field(default="", max_length=80)
    password: str = Field(min_length=8, max_length=200)           # provisória: a pessoa muda-a no primeiro acesso
    modulos: list[str] = Field(default_factory=list, max_length=20)


@router.post("/users", status_code=201)
def criar(d: CriarIn, s: Sessao = Depends(_admin), conn=Depends(get_conn)):
    uid = accounts.criar_utilizador(conn, d.email, d.password, nome=d.nome, admin=False, must_change=True, modulos=d.modulos)
    _atividade(conn, s.user["email"], "pessoa.criar", f"{d.email.strip().lower()}: {','.join(sorted(d.modulos)) or 'sem módulos'}")
    return _pessoa(conn, _alvo(conn, uid))


class ModulosIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modulos: list[str] = Field(max_length=20)


@router.put("/users/{uid}/modules")
def definir_modulos(uid: int, d: ModulosIn, s: Sessao = Depends(_admin), conn=Depends(get_conn)):
    u = _alvo(conn, uid)
    modulos.definir_permitidos(conn, uid, d.modulos)
    _atividade(conn, s.user["email"], "pessoa.modulos", f"{u['email']}: {','.join(sorted(set(d.modulos))) or 'nenhum'}")
    return _pessoa(conn, _alvo(conn, uid))


class AtivoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativo: bool


@router.put("/users/{uid}/active")
def ativar(uid: int, d: AtivoIn, s: Sessao = Depends(_admin), conn=Depends(get_conn)):
    u = _alvo(conn, uid)
    if u["id"] == s.user["id"]:
        raise ContaErro(400, "a_propria", "não podes desativar a tua própria conta")
    conn.execute("UPDATE pulse_users SET ativo = ? WHERE id = ?", (int(d.ativo), uid))
    if not d.ativo:
        accounts.revogar_todas(conn, uid)           # sessões abertas deixam de valer já
    _atividade(conn, s.user["email"], "pessoa.ativar" if d.ativo else "pessoa.desativar", u["email"])
    return _pessoa(conn, _alvo(conn, uid))


class ReporIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=8, max_length=200)


@router.post("/users/{uid}/password")
def repor_password(uid: int, d: ReporIn, s: Sessao = Depends(_admin), conn=Depends(get_conn)):
    u = _alvo(conn, uid)
    accounts.repor_password(conn, u["email"], d.password)
    _atividade(conn, s.user["email"], "pessoa.repor_password", u["email"])
    return {"ok": True}
