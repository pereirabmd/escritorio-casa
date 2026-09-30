from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from pulse.accounts import ContaErro
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa
from pulse.services import modulos

router = APIRouter(tags=["módulos"])


def exigir_modulo(nome: str):
    """Dependência de router: a sessão tem de ser válida e o módulo não pode estar desativado pelo administrador."""
    def dep(s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)) -> None:
        modulos.exigir(conn, nome, user_id=s.user["id"])
    return dep


@router.get("/modules")
def ver(s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Os módulos do Pulse para esta conta: `ativo` = ligado para todos e com acesso (a interface esconde os outros)."""
    return {"modulos": modulos.lista(conn, s.user["id"])}


class AlterarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modulos: dict[str, bool] = Field(min_length=1, max_length=20)


@router.put("/admin/modules")
def alterar(d: AlterarIn, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Só administradores. Ativa ou desativa módulos para todos os utilizadores (fica no centro de atividade)."""
    if not s.user["admin"]:
        raise ContaErro(403, "sem_permissao", "só o administrador pode alterar os módulos")
    antes = {m["id"]: m["ativo"] for m in modulos.lista(conn)}
    r = modulos.alterar(conn, d.modulos)
    for m, ativo in d.modulos.items():
        if antes.get(m) != ativo:
            conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem, resultado, detalhe) VALUES (?, 'conta', ?, 'ui', 'ok', ?)",
                         (s.user["email"], "modulo.ativar" if ativo else "modulo.desativar", m))
    return {"modulos": modulos.lista(conn, s.user["id"])}
