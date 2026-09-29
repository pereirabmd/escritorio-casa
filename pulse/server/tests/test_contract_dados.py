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
           "ADMIN_TAREFAS": EMAIL, "RATE_IP_POR_MIN": "100000", "RATE_USER_POR_MIN": "100000", "TZ": "Europe/Lisbon",
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
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": d, "marca": "T", "admin": True})
    assert pedir(cliente, "GET", "/rto/dias", query={"desde": d, "ate": d})["dias"] == {d: "T"}
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": d, "marca": "", "admin": True})
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


# --- Peso completo (editar, eliminar, configurar, estatísticas) ---------------------------------------------------------

def _registos(c):
    return pedir(c, "GET", "/peso/registos")["registos"]


def test_peso_editar_eliminar_e_desfazer(cliente, conn, ctx):
    novo = actions.executar(conn, ctx, "peso.registar", {"peso": 99.5, "quando": "2026-08-01 07:00:00", "nota": "x", "cid": "contrato-peso-02"})
    actions.executar(conn, ctx, "peso.editar", {"registo": novo["id"], "quando": "2026-08-01 07:30:00", "peso": 99.1, "nota": "jejum"})
    r = next(x for x in _registos(cliente) if x["id"] == novo["id"])
    assert (r["quando"], r["peso"], r["nota"]) == ("2026-08-01 07:30:00", 99.1, "jejum")
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "peso.eliminar", {"registo": novo["id"]})               # sem confirmação não apaga
    apagado = actions.executar(conn, ctx, "peso.eliminar", {"registo": novo["id"]}, confirmado=True)
    assert all(x["id"] != novo["id"] for x in _registos(cliente))
    actions.executar(conn, ctx, "peso.registar", {"peso": apagado["peso"], "quando": apagado["quando"], "nota": apagado["nota"]})   # «Desfazer»
    volta = [x for x in _registos(cliente) if x["quando"] == "2026-08-01 07:30:00"]
    assert len(volta) == 1 and volta[0]["peso"] == 99.1 and volta[0]["nota"] == "jejum"


def test_peso_editar_inexistente_e_404(cliente, conn, ctx):
    with pytest.raises(ErroDoModulo) as e:
        actions.executar(conn, ctx, "peso.editar", {"registo": 99999, "quando": "2026-08-01 07:30:00", "peso": 90})
    assert e.value.status == 404


def test_peso_configurar_e_apagar_valor(cliente, conn, ctx):
    r = actions.executar(conn, ctx, "peso.configurar", {"altura": 180, "sexo": "M", "nascimento": "1990-10-01", "pesoAlvo": 90, "atividade": 1.45})
    assert r["altura"] == 180.0 and r["sexo"] == "M" and r["nascimento"] == "1990-10-01" and r["pesoAlvo"] == 90.0
    r = actions.executar(conn, ctx, "peso.configurar", {"pesoAlvo": None})
    assert "pesoAlvo" not in r and r["altura"] == 180.0


def test_estatisticas_do_peso_com_dados_reais(cliente, conn, ctx):
    from pulse.services import peso
    regs, cfg = _registos(cliente), pedir(cliente, "GET", "/peso/config")
    r = peso.resumo(regs, cfg, ctx.hoje)
    assert r["registos"] == len(regs) and r["imc"] is not None and r["gastoDiario"] is not None
    assert r["minimo"] <= r["ultimo"]["peso"] <= r["maximo"]


# --- RTO completo (notas, férias, validações, visão) contra o dados-api real ---------------------------------------------

def _notas(c):
    return pedir(c, "GET", "/rto/notas")["notas"]


def _limpar_rto(c):
    for n in _notas(c):
        pedir(c, "DELETE", f"/rto/notas/{n['id']}")
    pedir(c, "PUT", "/rto/dias", {"dias": {d: "" for d in pedir(c, "GET", "/rto/dias")["dias"]}}) if pedir(c, "GET", "/rto/dias")["dias"] else None


def _ferias(c):
    return sorted((n["dataInicio"], n["dataFim"]) for n in _notas(c) if n["categoria"].lower().startswith("f"))


@pytest.fixture
def rto_limpo(cliente):
    _limpar_rto(cliente)
    return cliente


def alternar(conn, ctx, dia):
    return actions.executar(conn, ctx, "rto.ferias_dia", {"data": dia})


def test_ferias_um_dia_cria_e_o_mesmo_dia_remove(rto_limpo, conn, ctx):
    assert alternar(conn, ctx, "2027-03-10")["ferias"] is True                      # quarta
    assert _ferias(rto_limpo) == [("2027-03-10", "2027-03-10")]
    assert alternar(conn, ctx, "2027-03-10")["ferias"] is False
    assert _ferias(rto_limpo) == []


def test_ferias_estende_e_junta_notas_vizinhas_ignorando_fins_de_semana(rto_limpo, conn, ctx):
    alternar(conn, ctx, "2027-03-08"); alternar(conn, ctx, "2027-03-12")           # segunda e sexta, sem ligação
    assert _ferias(rto_limpo) == [("2027-03-08", "2027-03-08"), ("2027-03-12", "2027-03-12")]
    alternar(conn, ctx, "2027-03-09")                                                # terça: estende a primeira
    assert _ferias(rto_limpo) == [("2027-03-08", "2027-03-09"), ("2027-03-12", "2027-03-12")]
    alternar(conn, ctx, "2027-03-11")                                                # quinta: o dia útil anterior (quarta) ainda não é férias
    assert _ferias(rto_limpo) == [("2027-03-08", "2027-03-09"), ("2027-03-11", "2027-03-12")]
    alternar(conn, ctx, "2027-03-10")                                                # quarta: liga tudo
    assert _ferias(rto_limpo) == [("2027-03-08", "2027-03-12")]
    alternar(conn, ctx, "2027-03-15")                                                # segunda seguinte: o fim de semana não separa
    assert _ferias(rto_limpo) == [("2027-03-08", "2027-03-15")]


def test_ferias_encolhe_nas_pontas_e_divide_no_meio(rto_limpo, conn, ctx):
    pedir(rto_limpo, "POST", "/rto/notas", {"dataInicio": "2027-04-05", "dataFim": "2027-04-09", "categoria": "Férias", "descricao": "Páscoa"})
    alternar(conn, ctx, "2027-04-05")
    assert _ferias(rto_limpo) == [("2027-04-06", "2027-04-09")]
    alternar(conn, ctx, "2027-04-09")
    assert _ferias(rto_limpo) == [("2027-04-06", "2027-04-08")]
    alternar(conn, ctx, "2027-04-07")                                                # divide
    assert _ferias(rto_limpo) == [("2027-04-06", "2027-04-06"), ("2027-04-08", "2027-04-08")]
    assert {n["descricao"] for n in _notas(rto_limpo)} == {"Páscoa"}                # a descrição acompanha as duas metades


def test_ferias_limpa_a_marca_de_trabalho_desse_dia(rto_limpo, conn, ctx):
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": "2027-05-04", "marca": "C"})
    alternar(conn, ctx, "2027-05-04")
    assert "2027-05-04" not in pedir(rto_limpo, "GET", "/rto/dias")["dias"]


def test_notas_criar_editar_eliminar_e_desfazer(rto_limpo, conn, ctx):
    n = actions.executar(conn, ctx, "rto.nota_criar", {"inicio": "2030-06-01", "fim": "2030-06-03", "categoria": "Astreinte", "descricao": "equipa A"})
    actions.executar(conn, ctx, "rto.nota_editar", {"nota": n["id"], "inicio": "2030-06-01", "fim": "2030-06-04", "categoria": "Astreinte", "descricao": "equipa B"})
    assert next(x for x in _notas(rto_limpo) if x["id"] == n["id"])["dataFim"] == "2030-06-04"
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "rto.nota_eliminar", {"nota": n["id"]})            # sem confirmação
    apagada = actions.executar(conn, ctx, "rto.nota_eliminar", {"nota": n["id"]}, confirmado=True)
    assert _notas(rto_limpo) == []
    actions.executar(conn, ctx, "rto.nota_restaurar", {"nota": apagada["id"], "inicio": apagada["dataInicio"], "fim": apagada["dataFim"],
                                                       "categoria": apagada["categoria"], "descricao": apagada["descricao"]})
    voltou = _notas(rto_limpo)
    assert len(voltou) == 1 and voltou[0]["id"] == n["id"] and voltou[0]["descricao"] == "equipa B"


def test_notas_passadas_exigem_modo_administrador(rto_limpo, conn, ctx):
    ontem = (ctx.hoje - timedelta(days=3)).isoformat()
    with pytest.raises(actions.ContaErro) as e:
        actions.executar(conn, ctx, "rto.nota_criar", {"inicio": ontem, "categoria": "Validação"})
    assert e.value.codigo == "data_passada"
    n = actions.executar(conn, ctx, "rto.nota_criar", {"inicio": ontem, "categoria": "Validação", "admin": True})
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "rto.nota_eliminar", {"nota": n["id"]}, confirmado=True)      # existente no passado
    actions.executar(conn, ctx, "rto.nota_eliminar", {"nota": n["id"], "admin": True}, confirmado=True)


def test_editar_nota_inexistente_e_404(rto_limpo, conn, ctx):
    with pytest.raises(ErroDoModulo) as e:
        actions.executar(conn, ctx, "rto.nota_editar", {"nota": 99999, "inicio": "2030-01-01", "categoria": "x"})
    assert e.value.status == 404


def test_gerar_validacoes_alterna_tipos_e_nao_repete(rto_limpo, conn, ctx):
    r = actions.executar(conn, ctx, "rto.gerar_validacoes", {"referencia": "2030-01-07", "ate": "2030-03-04"})
    assert r == {"criadas": 5, "existentes": 0}                                       # 07/01, 21/01, 04/02, 18/02, 04/03
    notas = sorted(_notas(rto_limpo), key=lambda n: n["dataInicio"])
    assert [n["categoria"] for n in notas] == ["Validação", "Validação Batica", "Validação", "Validação Batica", "Validação"]
    r = actions.executar(conn, ctx, "rto.gerar_validacoes", {"referencia": "2030-01-07", "ate": "2030-04-01"})
    assert r == {"criadas": 2, "existentes": 5}                                       # +18/03 e +01/04
    assert len(_notas(rto_limpo)) == 7


def test_gerar_validacoes_em_lotes_de_100(rto_limpo, conn, ctx):
    r = actions.executar(conn, ctx, "rto.gerar_validacoes", {"referencia": "2030-01-07", "ate": "2033-12-31"})
    assert r["criadas"] > 100 and len(_notas(rto_limpo)) == r["criadas"]


def test_visao_do_rto_com_dados_reais(rto_limpo, conn, ctx):
    from pulse.services import rto as regras
    ano = ctx.hoje.year
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": f"{ano}-01-05", "marca": "C", "admin": True})
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": f"{ano}-01-06", "marca": "T", "admin": True})
    dias, notas = pedir(rto_limpo, "GET", "/rto/dias")["dias"], _notas(rto_limpo)
    v = regras.visao(dias, notas, ano, ctx.hoje)
    assert v["totais"]["C"] == 1 and v["totais"]["T"] == 1 and v["mensal"][0] == {"t": 1, "c": 1}
    assert v["hoje"]["estado"] in ("escritorio", "casa", "ferias", "feriado", "fim_de_semana", "astreinte", "por_definir")


def test_marcar_fim_de_semana_e_passado_so_em_modo_administrador(rto_limpo, conn, ctx):
    sabado = ctx.hoje + timedelta(days=(5 - ctx.hoje.weekday()) % 7 or 7)             # o próximo sábado
    passado = (ctx.hoje - timedelta(days=10)).isoformat()
    for d in (sabado.isoformat(), (sabado + timedelta(days=1)).isoformat(), passado):
        with pytest.raises(actions.ContaErro) as e:
            actions.executar(conn, ctx, "rto.marcar_dia", {"data": d, "marca": "C"})
        assert e.value.codigo == "dia_bloqueado"
        with pytest.raises(actions.ContaErro):
            actions.executar(conn, ctx, "rto.ferias_dia", {"data": d})
    assert pedir(rto_limpo, "GET", "/rto/dias") == {"dias": {}} and _notas(rto_limpo) == []                # nada foi escrito
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": sabado.isoformat(), "marca": "C", "admin": True})
    actions.executar(conn, ctx, "rto.marcar_dia", {"data": passado, "marca": "T", "admin": True})
    assert pedir(rto_limpo, "GET", "/rto/dias")["dias"] == {sabado.isoformat(): "C", passado: "T"}
    actions.executar(conn, ctx, "rto.ferias_dia", {"data": sabado.isoformat(), "admin": True})            # férias ao fim de semana, em admin
    assert _ferias(rto_limpo) == [(sabado.isoformat(), sabado.isoformat())]
    assert sabado.isoformat() not in pedir(rto_limpo, "GET", "/rto/dias")["dias"]                        # e limpa a marca desse dia


# --- Tarefas: catálogo, concluir com atrasadas, saltar (dados-api real) ------------------------------------------------------------------

def _tarefas(c):
    return pedir(c, "GET", "/tarefas/dados")


def _criar(conn, ctx, **kw):
    return actions.executar(conn, ctx, "tarefas.criar", {"nome": "Tarefa de contrato", "categoria": "Casa", "recorrencia": "Diaria", **kw})


def test_criar_editar_e_apagar_tarefa(cliente, conn, ctx):
    r = _criar(conn, ctx, nome="Limpar filtros", recorrencia="Semanal", dias=["Seg", "Qua"], hora="09:30", prioridade="Alta", cid="tarefa-contrato-1")
    tid = r["tarefa"]["id"]
    assert (r["tarefa"]["recorrencia"], r["tarefa"]["diasSemana"], r["tarefa"]["prioridade"], r["tarefa"]["horaNotificacao"]) == ("Semanal", "Seg,Qua", "Alta", "09:30")
    assert actions.executar(conn, ctx, "tarefas.criar", {"nome": "Limpar filtros", "categoria": "Casa", "recorrencia": "Semanal", "dias": ["Seg", "Qua"],
                                                         "cid": "tarefa-contrato-1"})["tarefa"]["id"] == tid              # o mesmo cid não duplica
    e = actions.executar(conn, ctx, "tarefas.editar", {"tarefa": tid, "nome": "Limpar filtros (mês)", "categoria": "Limpeza", "recorrencia": "Mensal", "diaMes": 5, "hora": "10:00"})
    assert (e["tarefa"]["nome"], e["tarefa"]["recorrencia"], e["tarefa"]["diaMes"], e["tarefa"]["diasSemana"]) == ("Limpar filtros (mês)", "Mensal", 5, "")
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "tarefas.apagar", {"tarefa": tid})                                                       # sem confirmação
    actions.executar(conn, ctx, "tarefas.apagar", {"tarefa": tid}, confirmado=True)
    assert next(t for t in _tarefas(cliente)["tarefas"] if t["id"] == tid)["ativa"] is False                                 # desativada, não perdida


def test_tarefa_pontual_cria_a_ocorrencia_e_o_dados_api_valida_o_resto(cliente, conn, ctx):
    r = _criar(conn, ctx, nome="Marcar dentista", recorrencia="Pontual", data=(ctx.hoje + timedelta(days=3)).isoformat())
    assert r["instancia"]["estado"] == "Pendente" and r["instancia"]["data"] == (ctx.hoje + timedelta(days=3)).isoformat()
    with pytest.raises(ErroDoModulo) as e:
        _criar(conn, ctx, nome="Dependência fantasma", dependeDe="T99999")
    assert e.value.status == 400


def test_concluir_atrasada_fecha_as_anteriores_e_o_desfazer_reabre_todas(cliente, conn, ctx):
    tid = _criar(conn, ctx, nome="Regar plantas")["tarefa"]["id"]
    ids = []
    for atras in (4, 3, 2):
        i = pedir(cliente, "POST", "/tarefas/instancias", {"tarefaId": tid, "data": (ctx.hoje - timedelta(days=atras)).isoformat()})["instancia"]["id"]
        pedir(cliente, "PUT", f"/tarefas/instancias/{i}", {"estado": "Atrasada"})
        ids.append(i)
    r = actions.executar(conn, ctx, "tarefas.concluir", {"instancia": ids[-1]})
    assert sorted(r["tambem"]) == sorted(ids[:-1])
    estados = {i["id"]: i["estado"] for i in _tarefas(cliente)["instancias"] if i["id"] in ids}
    assert set(estados.values()) == {"Feita"}
    actions.executar(conn, ctx, "tarefas.reabrir", {"instancia": ids[-1], "tambem": r["tambem"]})
    assert {i["estado"] for i in _tarefas(cliente)["instancias"] if i["id"] in ids} == {"Pendente"}


def test_saltar(cliente, conn, ctx):
    tid = _criar(conn, ctx, nome="Passar aspirador")["tarefa"]["id"]
    i = pedir(cliente, "POST", "/tarefas/instancias", {"tarefaId": tid, "data": ctx.hoje.isoformat()})["instancia"]["id"]
    actions.executar(conn, ctx, "tarefas.saltar", {"instancia": i})
    assert next(x for x in _tarefas(cliente)["instancias"] if x["id"] == i)["estado"] == "Saltada"


def test_visao_das_tarefas_com_dados_reais(cliente, conn, ctx):
    from pulse.services import tarefas as regras
    tid = _criar(conn, ctx, nome="Visível no módulo")["tarefa"]["id"]
    pedir(cliente, "POST", "/tarefas/instancias", {"tarefaId": tid, "data": ctx.hoje.isoformat()})
    v = regras.visao(_tarefas(cliente), ctx.hoje, EMAIL)
    assert any(i["nome"] == "Visível no módulo" for i in v["hoje"])
    assert any(t["nome"] == "Visível no módulo" and t["resumo"] == "Todos os dias" for t in v["tarefas"])


# --- Tarefas: piscina, horário e configuração (dados reais) ----------------------------------------------------------------

def _config(c):
    return {x["chave"]: x["valor"] for x in _tarefas(c)["config"]}


def _piscina(c, ctx):
    from pulse.services import piscina as regras
    linhas = _tarefas(c)["piscina"]
    faltam = regras.em_falta(linhas)
    if faltam:
        linhas = pedir(c, "POST", "/tarefas/piscina/catalogo", {"itens": faltam})["piscina"]
    return {p["id"]: p for p in linhas}


def test_piscina_catalogo_registar_e_desfazer(cliente, conn, ctx):
    from pulse.services import piscina as regras
    assert len(_piscina(cliente, ctx)) == len(regras.CATALOGO)                  # o catálogo completo cabe no que o dados-api aceita
    r = actions.executar(conn, ctx, "tarefas.piscina_registar", {"item": "P02"})       # quente 3/4 (junho–setembro) ou fria 7
    linha = _piscina(cliente, ctx)["P02"]
    assert linha["ultimaData"] == ctx.hoje.isoformat() and linha["proximaData"] > ctx.hoje.isoformat()
    assert r["anterior"] == {"ultimaData": None, "proximaData": None, "usarIntervaloLongo": False, "notificacaoEnviada": False}
    assert any(e["acao"] == "piscina_feita" and e["tarefa"] == "Testar pH e cloro" for e in pedir(cliente, "GET", "/tarefas/auditoria")["entradas"])
    actions.executar(conn, ctx, "tarefas.piscina_repor", {"item": "P02", **r["anterior"]})
    linha = _piscina(cliente, ctx)["P02"]
    assert (linha["ultimaData"], linha["proximaData"]) == (None, None)
    actions.executar(conn, ctx, "tarefas.piscina_registar", {"item": "P13"})           # tarefa de registo: sem próxima data
    assert not _piscina(cliente, ctx)["P13"]["proximaData"]
    with pytest.raises(ErroDoModulo) as e:
        actions.executar(conn, ctx, "tarefas.piscina_registar", {"item": "P99"})
    assert e.value.status == 404


def test_avisos_do_horario_e_preferencias(cliente, conn, ctx):
    actions.executar(conn, ctx, "tarefas.avisos_horario", {"ativos": False})
    assert _config(cliente)["HorarioAvisos"] == "FALSE"
    actions.executar(conn, ctx, "tarefas.avisos_horario", {"ativos": True})
    assert _config(cliente)["HorarioAvisos"] == "TRUE"
    actions.executar(conn, ctx, "tarefas.preferencias", {"naoIncomodarInicio": "22:00", "naoIncomodarFim": "07:00"})
    assert (_config(cliente)["NaoIncomodarInicio"], _config(cliente)["NaoIncomodarFim"]) == ("22:00", "07:00")
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "tarefas.preferencias", {"naoIncomodarInicio": "22:00", "naoIncomodarFim": ""})
    r = pedir(cliente, "GET", "/tarefas/horario")
    from pulse.services import horario
    assert horario.visao(r["aulas"], _config(cliente), ctx.hoje)["disponivel"] is True


def test_pessoas_adicionar_editar_reatribuir_e_remover(cliente, conn, ctx):
    a = actions.executar(conn, ctx, "tarefas.pessoa_adicionar", {"nome": "Contrato A", "email": "A@Exemplo.pt"})
    b = actions.executar(conn, ctx, "tarefas.pessoa_adicionar", {"nome": "Contrato B"})
    assert b["num"] == a["num"] + 1 and _config(cliente)[f"Pessoa{a['num']}_Email"] == "a@exemplo.pt"
    with pytest.raises(actions.ContaErro) as e:
        actions.executar(conn, ctx, "tarefas.pessoa_adicionar", {"nome": "Contrato A"})
    assert e.value.codigo == "pessoa_existe"
    tid = _criar(conn, ctx, nome="Tarefa da pessoa A", pessoa="Contrato A")["tarefa"]["id"]
    iid = pedir(cliente, "POST", "/tarefas/instancias", {"tarefaId": tid, "data": ctx.hoje.isoformat(), "pessoa": "Contrato A"})["instancia"]["id"]
    # renomear leva as tarefas e as ocorrências no mesmo passo
    actions.executar(conn, ctx, "tarefas.pessoa_editar", {"nome": "Contrato A", "novoNome": "Contrato A2", "email": "novo@exemplo.pt"})
    cfg = _config(cliente)
    assert cfg[f"Pessoa{a['num']}_Nome"] == "Contrato A2" and cfg[f"Pessoa{a['num']}_Email"] == "novo@exemplo.pt"
    assert next(t for t in _tarefas(cliente)["tarefas"] if t["id"] == tid)["pessoaPadrao"] == "Contrato A2"
    assert estado(cliente, iid)["pessoa"] == "Contrato A2"
    # reatribuir e remover exigem confirmação
    with pytest.raises(actions.ContaErro) as e:
        actions.executar(conn, ctx, "tarefas.reatribuir", {"de": "Contrato A2", "para": "Contrato B"})
    assert e.value.codigo == "confirmacao_necessaria"
    with pytest.raises(actions.ContaErro) as e:                                                       # tem tarefas por fazer e não há substituto
        actions.executar(conn, ctx, "tarefas.pessoa_remover", {"nome": "Contrato A2"}, confirmado=True)
    assert e.value.codigo == "substituto_necessario"
    r = actions.executar(conn, ctx, "tarefas.pessoa_remover", {"nome": "Contrato A2", "substituto": "Contrato B"}, confirmado=True)
    assert r["reatribuidas"] >= 2
    assert estado(cliente, iid)["pessoa"] == "Contrato B" and not any(k.startswith(f"Pessoa{a['num']}_") for k in _config(cliente))
    assert next(t for t in _tarefas(cliente)["tarefas"] if t["id"] == tid)["pessoaPadrao"] == "Contrato B"
    with pytest.raises(actions.ContaErro) as e:                                                       # sobrou só o B: a última pessoa não se remove
        actions.executar(conn, ctx, "tarefas.pessoa_remover", {"nome": "Contrato B"}, confirmado=True)
    assert e.value.codigo == "ultima_pessoa"


def test_administracao_e_estado_do_pi(cliente, conn, ctx):
    n = actions.executar(conn, ctx, "tarefas.pessoa_adicionar", {"nome": "Admin Contrato", "email": "admin.contrato@exemplo.pt"})["num"]
    with pytest.raises(actions.ContaErro):
        actions.executar(conn, ctx, "tarefas.admin", {"admins": ["admin.contrato@exemplo.pt"]})              # sem confirmação
    r = actions.executar(conn, ctx, "tarefas.admin", {"admins": ["admin.contrato@exemplo.pt"], "notificacoes": {"piscina": ["Admin Contrato"]}}, confirmado=True)
    assert "admin.contrato@exemplo.pt" in r["admins"] and next(x for x in r["notificacoes"] if x["id"] == "piscina")["destinatarios"] == ["Admin Contrato"]
    with pytest.raises(ErroDoModulo) as e:                                                              # só quem está registado com e-mail
        actions.executar(conn, ctx, "tarefas.admin", {"admins": ["desconhecido@exemplo.pt"]}, confirmado=True)
    assert e.value.status == 400
    actions.executar(conn, ctx, "tarefas.admin", {"admins": [], "notificacoes": {"piscina": []}}, confirmado=True)
    assert pedir(cliente, "GET", "/tarefas/dados")["souAdmin"] is True
    actions.executar(conn, ctx, "tarefas.pessoa_remover", {"nome": "Admin Contrato"}, confirmado=True)      # há mais pessoas: pode sair
    assert not any(k.startswith(f"Pessoa{n}_") for k in _config(cliente))
