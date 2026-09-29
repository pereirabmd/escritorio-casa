from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from pulse.accounts import ContaErro
from pulse.api.v1.modules import exigir_modulo
from pulse.api.v1.auth import Sessao, sessao_ativa
from pulse.clients.dados import ErroDoModulo, ModuloIndisponivel
from pulse.services import horario as horario_regras
from pulse.services import piscina as piscina_regras
from pulse.services import tarefas

router = APIRouter(prefix="/tasks", tags=["tarefas"], dependencies=[Depends(exigir_modulo("tarefas"))])


def _dados(request: Request, s: Sessao) -> dict:
    _, dados = request.app.state.dados.pedir("GET", "/tarefas/dados", s.user["email"])
    return dados or {}


@router.get("")
def ver(request: Request, s: Sessao = Depends(sessao_ativa)):
    """O módulo Tarefas: hoje, atrasadas, amanhã, catálogo de tarefas, pessoas e categorias (regras partilhadas Web/Android)."""
    return tarefas.visao(_dados(request, s), request.app.state.agora().date(), s.user["email"])


@router.get("/calendar")
def calendario(request: Request, de: date = Query(...), ate: date = Query(...), s: Sessao = Depends(sessao_ativa)):
    """Ocorrências e feriados de um intervalo de datas (até 62 dias): a Web pede o mês ou a semana que está a mostrar."""
    try:
        return tarefas.calendario(_dados(request, s), de, ate, request.app.state.agora().date())
    except ValueError:
        raise ContaErro(400, "intervalo_invalido", f"o intervalo tem de ter entre 1 e {tarefas.MAX_DIAS_CALENDARIO} dias") from None


@router.get("/schedule")
def horario(request: Request, s: Sessao = Depends(sessao_ativa)):
    """Horário escolar por aluno, com blocos, hora de saída e hora do aviso. `disponivel: false` se o módulo não responder."""
    email, app = s.user["email"], request.app.state
    cfg = tarefas.config_de(_dados(request, s).get("config", []))
    try:
        _, r = app.dados.pedir("GET", "/tarefas/horario", email)
        aulas = (r or {}).get("aulas", [])
    except (ModuloIndisponivel, ErroDoModulo):
        aulas = None
    return horario_regras.visao(aulas, cfg, app.agora().date())


@router.get("/pool")
def piscina(request: Request, s: Sessao = Depends(sessao_ativa)):
    """Piscina: o catálogo com o estado de cada tarefa. Se faltar alguma no catálogo da base, acrescenta-a (nunca toca nas existentes)."""
    email, app = s.user["email"], request.app.state
    dados = _dados(request, s)
    faltam = piscina_regras.em_falta(dados.get("piscina", []))
    if faltam:
        _, r = app.dados.pedir("POST", "/tarefas/piscina/catalogo", email, corpo={"itens": faltam})
        dados["piscina"] = (r or {}).get("piscina", dados.get("piscina", []))
    return piscina_regras.visao(dados.get("piscina", []), tarefas.config_de(dados.get("config", [])), app.agora().date())


@router.get("/settings")
def definicoes(request: Request, s: Sessao = Depends(sessao_ativa)):
    """Configuração do módulo: pessoas, preferências, resumo por pessoa, últimas ações, estado do Pi e (para administradores) o painel de admin."""
    email, app = s.user["email"], request.app.state
    dados = _dados(request, s)
    cfg = tarefas.config_de(dados.get("config", []))
    try:
        _, a = app.dados.pedir("GET", "/tarefas/auditoria", email, query={"limite": 10})
        auditoria = (a or {}).get("entradas", [])
    except (ModuloIndisponivel, ErroDoModulo):
        auditoria = []
    admin = None
    if dados.get("souAdmin") is True:
        try:
            _, admin = app.dados.pedir("GET", "/tarefas/admin", email)
        except (ModuloIndisponivel, ErroDoModulo):
            admin = None
    return {"pessoas": [{"nome": p["nome"], "email": p["email"]} for p in tarefas.pessoas(cfg)], "pessoaAtual": tarefas.pessoa_do_utilizador(cfg, email),
            "categorias": tarefas.categorias(cfg), "preferencias": tarefas.preferencias(cfg),
            "resumo": tarefas.resumo_pessoas(dados, app.agora()), "auditoria": auditoria, "souAdmin": dados.get("souAdmin") is True,
            "admin": admin, "saude": app.avisos.saude()}


@router.get("/history")
def historico(request: Request, s: Sessao = Depends(sessao_ativa)):
    """Ocorrências feitas ou saltadas (para exportar em CSV na interface)."""
    dados = _dados(request, s)
    nomes = {t["id"]: t for t in dados.get("tarefas", [])}
    linhas = [{"tarefa": (nomes.get(i["tarefaId"]) or {}).get("nome", i["tarefaId"]), "categoria": (nomes.get(i["tarefaId"]) or {}).get("categoria", ""),
               "data": i["data"], "pessoa": i["pessoa"], "estado": i["estado"], "dataConclusao": i.get("dataConclusao") or ""}
              for i in dados.get("instancias", []) if i["estado"] in ("Feita", "Saltada")]
    return {"linhas": sorted(linhas, key=lambda x: (x["data"], x["tarefa"]))}
