"""Teste de contrato: as ações e o agregado do Pulse contra o código REAL do dados-api (bases temporárias `teste-*`).

Arranca `dados/api.py` como script, exatamente como em produção (é assim que o bug do ApiError como `__main__` apareceria),
com bases novas numa pasta temporária. Nunca toca em bases reais. Falha se um contrato do dados-api mudar sem o Pulse acompanhar.
"""

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pulse import actions
from pulse.clients.dados import DadosClient, ErroDoModulo
from pulse.services import dashboard
from zoneinfo import ZoneInfo

DADOS = Path(__file__).resolve().parents[3] / "dados"
EMAIL, CHAVE = "eu@exemplo.pt", "c" * 40
TZ = ZoneInfo("Europe/Lisbon")

pytestmark = pytest.mark.skipif(not (DADOS / "api.py").is_file(), reason="pasta dados/ não encontrada")


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dados-real")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]
    env = {**os.environ, "DADOS_DB": str(tmp / "teste-dados.db"), "BILHETES_DB": str(tmp / "teste-bilhetes.db"),
           "DADOS_API_PORT": str(porta), "GOOGLE_CLIENT_IDS": "x.apps.googleusercontent.com", "PULSE_SERVICE_KEY": CHAVE,
           "RATE_IP_POR_MIN": "100000", "RATE_USER_POR_MIN": "100000", "TZ": "Europe/Lisbon",
           **{f"ACL_{a}": EMAIL for a in ("PESO", "RTO", "TAREFAS", "FINANCAS", "BILHETES", "CONVIDADOS")}}
    proc = subprocess.Popen([sys.executable, "api.py"], cwd=DADOS, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = DadosClient(f"http://127.0.0.1:{porta}", CHAVE, timeout=10)
    try:
        for _ in range(100):
            if c.saude():
                break
            time.sleep(0.2)
        else:
            pytest.fail("o dados-api não arrancou")
        yield c
    finally:
        proc.terminate(); proc.wait(5)


@pytest.fixture
def ctx(cliente):
    return actions.Contexto(cliente, EMAIL, datetime.now(TZ))


@pytest.fixture
def conn(tmp_path):
    from pulse import db
    c = db.connect(tmp_path / "teste-pulse.db"); db.migrate(c)
    yield c
    c.close()


def pedir(c, metodo, caminho, corpo=None, query=None):
    return c.pedir(metodo, caminho, EMAIL, query=query, corpo=corpo)[1]


def instancia(c, ctx, nome="Tarefa de contrato"):
    hoje = ctx.hoje.isoformat()
    r = pedir(c, "POST", "/tarefas/tarefas", {"nome": nome, "recorrencia": "Pontual", "diasSemana": hoje, "prioridade": "Alta"})
    return r["tarefa"]["id"], r["instancia"]["id"]


def estado(c, iid):
    return next(i for i in pedir(c, "GET", "/tarefas/dados")["instancias"] if i["id"] == iid)


def test_concluir_e_reabrir_tarefa(cliente, conn, ctx):
    _, iid = instancia(cliente, ctx)
    actions.executar(conn, ctx, "tarefas.concluir", {"instancia": iid})
    i = estado(cliente, iid)
    assert i["estado"] == "Feita" and i["dataConclusao"] == ctx.agora.strftime("%Y-%m-%d %H:%M")
    actions.executar(conn, ctx, "tarefas.reabrir", {"instancia": iid})
    i = estado(cliente, iid)
    assert (i["estado"], i["dataConclusao"]) == ("Pendente", "")


def test_adiar_muda_a_data_e_o_conflito_e_409(cliente, conn, ctx):
    tid, iid = instancia(cliente, ctx, "Tarefa para adiar")
    amanha = (ctx.hoje + timedelta(days=1)).isoformat()
    actions.executar(conn, ctx, "tarefas.adiar", {"instancia": iid})
    assert estado(cliente, iid)["data"] == amanha
    pedir(cliente, "POST", "/tarefas/instancias", {"tarefaId": tid, "data": ctx.hoje.isoformat()})       # outra ocorrência, hoje
    hoje_id = next(i["id"] for i in pedir(cliente, "GET", "/tarefas/dados")["instancias"] if i["tarefaId"] == tid and i["data"] == ctx.hoje.isoformat())
    with pytest.raises(ErroDoModulo) as e:
        actions.executar(conn, ctx, "tarefas.adiar", {"instancia": hoje_id})                      # amanhã já tem esta tarefa
    assert (e.value.status, e.value.codigo) == (409, "conflito")
    assert estado(cliente, hoje_id)["data"] == ctx.hoje.isoformat()                                # nada foi fundido nem mudado


def test_adiar_instancia_inexistente_e_404(cliente, conn, ctx):
    with pytest.raises(ErroDoModulo) as e:
        actions.executar(conn, ctx, "tarefas.concluir", {"instancia": "I99999"})
    assert e.value.status == 404


def test_peso_com_cid_e_idempotente(cliente, conn, ctx):
    p = {"peso": 104.8, "cid": "contrato-peso-01"}
    a = actions.executar(conn, ctx, "peso.registar", p)
    b = actions.executar(conn, ctx, "peso.registar", p)
    regs = pedir(cliente, "GET", "/peso/registos")["registos"]
    assert len(regs) == 1 and regs[0]["peso"] == 104.8 and a["id"] == b["id"]


def test_rto_marcar_e_limpar(cliente, conn, ctx):
    d = ctx.hoje.isoformat()
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": d, "marca": "T"})
    assert pedir(cliente, "GET", "/rto/dias", query={"desde": d, "ate": d})["dias"] == {d: "T"}
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": d, "marca": ""})
    assert pedir(cliente, "GET", "/rto/dias", query={"desde": d, "ate": d})["dias"] == {}


def test_pagar_e_anular_pagamento(cliente, conn, ctx):
    venc = (ctx.hoje + timedelta(days=3)).isoformat()
    l = pedir(cliente, "POST", "/financas/lancamentos", {"tipo": "despesa", "descricao": "Conta de contrato", "valor": 12.5,
                                                          "categoria_id": 1, "data_vencimento": venc})
    actions.executar(conn, ctx, "financas.pagar", {"lancamento": l["id"]})
    pagos = pedir(cliente, "GET", "/financas/lancamentos", query={"mes": venc[:7]})["lancamentos"]
    assert next(x for x in pagos if x["id"] == l["id"])["data_pagamento"] == ctx.hoje.isoformat()
    actions.executar(conn, ctx, "financas.anular_pagamento", {"lancamento": l["id"]})
    pagos = pedir(cliente, "GET", "/financas/lancamentos", query={"mes": venc[:7]})["lancamentos"]
    assert next(x for x in pagos if x["id"] == l["id"])["data_pagamento"] is None


def test_agregado_do_hoje_contra_o_dados_api_real(cliente, ctx):
    instancia(cliente, ctx, "Aparece no Hoje")
    r = dashboard.hoje(cliente, EMAIL, ctx.agora)
    assert r["estado"] == "ok", {k: m["estado"] for k, m in r["modulos"].items()}
    assert any(t["nome"] == "Aparece no Hoje" for t in r["modulos"]["tarefas"]["dados"]["hoje"])
    assert len(r["modulos"]["rto"]["dados"]["dias"]) == 7
    assert r["modulos"]["bilhetes"]["dados"]["proximo"] is None
    assert r["modulos"]["financas"]["dados"]["total"] >= 1                   # a conta do teste anterior, por pagar de novo
    assert r["modulos"]["peso"]["dados"]["sugestao"] == 104.8


def test_utilizador_fora_da_acl_fica_sem_acesso(cliente, ctx):
    r = dashboard.hoje(cliente, "intruso@exemplo.pt", ctx.agora)
    assert {r["modulos"][m]["estado"] for m in dashboard.MODULOS} == {"sem_acesso"}
