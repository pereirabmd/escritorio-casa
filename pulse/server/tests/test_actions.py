from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, config, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel
from pulse.main import create_app
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 30, 10, 5, tzinfo=ZoneInfo("Europe/Lisbon"))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-a.db"); db.migrate(c)
    yield c
    c.close()


def correr(conn, dados_falso, nome, params, **kw):
    ctx = actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), EMAIL, AGORA)
    return actions.executar(conn, ctx, nome, params, **kw)


def atividade(conn):
    return [tuple(r) for r in conn.execute("SELECT modulo, acao, origem, resultado, detalhe FROM pulse_activity ORDER BY id")]


def test_catalogo_declara_modulo_e_nivel():
    c = {a["nome"]: a for a in actions.catalogo()}
    assert set(c) == {"tarefas.concluir", "tarefas.reabrir", "tarefas.adiar", "peso.registar", "rto.marcar_dia",
                      "financas.pagar", "financas.anular_pagamento"}
    assert all(a["nivel"] in ("read", "safe_action", "sensitive_action") and a["descricao"] for a in c.values())


def test_concluir_escreve_no_modulo_em_nome_do_utilizador(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.concluir", {"instancia": "I0042"})
    assert FalsoDados.escritas == [("PUT", "/tarefas/instancias/I0042", {"estado": "Feita", "dataConclusao": "2026-09-30 10:05"}, EMAIL)]
    assert atividade(conn) == [("tarefas", "tarefas.concluir", "ui", "ok", "I0042")]


def test_reabrir_desfaz_o_concluir(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.reabrir", {"instancia": "I0042"})
    assert FalsoDados.escritas[0][2] == {"estado": "Pendente", "dataConclusao": ""}


def test_adiar_por_omissao_e_para_amanha_e_aceita_data(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.adiar", {"instancia": "I0042"})
    correr(conn, dados_falso, "tarefas.adiar", {"instancia": "I0042", "data": "2026-10-15"})
    assert [e[2] for e in FalsoDados.escritas] == [{"data": "2026-10-01"}, {"data": "2026-10-15"}]


def test_adiar_para_o_passado_e_recusado_sem_tocar_no_modulo(conn, dados_falso):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "tarefas.adiar", {"instancia": "I0042", "data": "2026-09-29"})
    assert e.value.codigo == "data_passada" and FalsoDados.escritas == []
    assert atividade(conn)[0][3] == "erro"


def test_adiar_para_dia_que_ja_tem_a_tarefa_devolve_o_409_do_modulo(conn, dados_falso):
    FalsoDados.respostas["PUT /tarefas/instancias/I0042"] = (409, {"erro": {"codigo": "conflito", "mensagem": "essa tarefa já tem uma ocorrência nesse dia"}})
    with pytest.raises(ErroDoModulo) as e:
        correr(conn, dados_falso, "tarefas.adiar", {"instancia": "I0042"})
    assert (e.value.status, e.value.codigo) == (409, "conflito")
    assert atividade(conn) == [("tarefas", "tarefas.adiar", "ui", "erro", "conflito")]


def test_peso_com_cid_e_sem_valores_no_registo_de_atividade(conn, dados_falso):
    correr(conn, dados_falso, "peso.registar", {"peso": 104.8, "cid": "abcd-1234-efgh"})
    assert FalsoDados.escritas == [("POST", "/peso/registos", {"peso": 104.8, "nota": "", "cid": "abcd-1234-efgh"}, EMAIL)]
    assert atividade(conn) == [("peso", "peso.registar", "ui", "ok", "")]          # nada do valor


def test_rto_marca_e_limpa(conn, dados_falso):
    correr(conn, dados_falso, "rto.marcar_dia", {"data": "2026-10-01", "marca": "T"})
    correr(conn, dados_falso, "rto.marcar_dia", {"data": "2026-10-01", "marca": ""})
    assert [(e[1], e[2]) for e in FalsoDados.escritas] == [("/rto/dias/2026-10-01", {"marca": "T"}), ("/rto/dias/2026-10-01", {"marca": ""})]


def test_pagar_e_anular_pagamento(conn, dados_falso):
    correr(conn, dados_falso, "financas.pagar", {"lancamento": 7})
    correr(conn, dados_falso, "financas.pagar", {"lancamento": 7, "data": "2026-09-25"})
    correr(conn, dados_falso, "financas.anular_pagamento", {"lancamento": 7})
    assert [e[2] for e in FalsoDados.escritas] == [{"data_pagamento": "2026-09-30"}, {"data_pagamento": "2026-09-25"}, {"data_pagamento": None}]


@pytest.mark.parametrize("nome,params", [
    ("tarefas.concluir", {}), ("tarefas.concluir", {"instancia": "X1"}), ("tarefas.concluir", {"instancia": "I1", "extra": 1}),
    ("tarefas.adiar", {"instancia": "I1", "data": "31/12/2026"}), ("peso.registar", {"peso": 0}), ("peso.registar", {"peso": 1001}),
    ("peso.registar", {"peso": "abc"}), ("peso.registar", {"peso": 80, "cid": "curto"}), ("rto.marcar_dia", {"data": "2026-10-01", "marca": "X"}),
    ("rto.marcar_dia", {"data": "nao-e-data", "marca": "T"}), ("financas.pagar", {"lancamento": 0}), ("financas.pagar", {"lancamento": "a"})])
def test_parametros_invalidos_nunca_chegam_ao_modulo(conn, dados_falso, nome, params):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, nome, params)
    assert (e.value.status, e.value.codigo) == (400, "parametros_invalidos")
    assert FalsoDados.escritas == []


def test_acao_desconhecida(conn, dados_falso):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "tarefas.apagar_tudo", {})
    assert e.value.status == 404


def test_modulo_em_baixo_regista_o_erro(conn):
    ctx = actions.Contexto(DadosClient("http://127.0.0.1:9", FalsoDados.CHAVE, timeout=1), EMAIL, AGORA)
    with pytest.raises(ModuloIndisponivel):
        actions.executar(conn, ctx, "rto.marcar_dia", {"data": "2026-10-01", "marca": "T"})
    assert atividade(conn) == [("rto", "rto.marcar_dia", "ui", "erro", "modulo_indisponivel")]


def test_acao_sensivel_exige_confirmacao(conn, dados_falso, monkeypatch):
    ran = []
    monkeypatch.setitem(actions.ACOES, "teste.apagar", actions.Acao("teste.apagar", "teste", "sensitive_action", "x",
                        actions.LancamentoIn, lambda c, p: (ran.append(1) or {}, "")))
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "teste.apagar", {"lancamento": 1})
    assert e.value.codigo == "confirmacao_necessaria" and ran == []
    correr(conn, dados_falso, "teste.apagar", {"lancamento": 1}, confirmado=True)
    assert ran == [1]


def test_origem_ia_fica_registada(conn, dados_falso):
    correr(conn, dados_falso, "rto.marcar_dia", {"data": "2026-10-01", "marca": "C"}, origem="ia")
    assert atividade(conn)[0][2] == "ia"


# --- endpoint -------------------------------------------------------------------------------------------------------

@pytest.fixture
def app_cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s)
    app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        yield c


H = {"X-Pulse-Client": "web"}


def entrar(c):
    assert c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"}).status_code == 200


def test_endpoint_exige_sessao_e_csrf(app_cliente):
    assert app_cliente.post("/api/v1/actions/tarefas.concluir", json={"params": {"instancia": "I1"}}).status_code == 401
    entrar(app_cliente)
    r = app_cliente.post("/api/v1/actions/tarefas.concluir", json={"params": {"instancia": "I1"}})
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "csrf"
    assert FalsoDados.escritas == []


def test_endpoint_executa_e_devolve_o_resultado(app_cliente):
    entrar(app_cliente)
    FalsoDados.respostas["PUT /tarefas/instancias/I1"] = (200, {"instancia": {"id": "I1", "estado": "Feita"}})
    r = app_cliente.post("/api/v1/actions/tarefas.concluir", json={"params": {"instancia": "I1"}}, headers=H)
    assert r.status_code == 200 and r.json() == {"resultado": {"instancia": {"id": "I1", "estado": "Feita"}}}
    assert FalsoDados.escritas[0][3] == EMAIL


def test_endpoint_traduz_erros(app_cliente):
    entrar(app_cliente)
    FalsoDados.respostas["PUT /tarefas/instancias/I1"] = (409, {"erro": {"codigo": "conflito", "mensagem": "já existe"}})
    r = app_cliente.post("/api/v1/actions/tarefas.adiar", json={"params": {"instancia": "I1"}}, headers=H)
    assert (r.status_code, r.json()["erro"]["codigo"]) == (409, "conflito")
    r = app_cliente.post("/api/v1/actions/peso.registar", json={"params": {"peso": -3}}, headers=H)
    assert (r.status_code, r.json()["erro"]["codigo"]) == (400, "parametros_invalidos")
    assert app_cliente.post("/api/v1/actions/nao.existe", json={}, headers=H).status_code == 404
    assert app_cliente.post("/api/v1/actions/rto.marcar_dia", json={"params": "lixo"}, headers=H).status_code == 400


def test_endpoint_lista_o_catalogo(app_cliente):
    entrar(app_cliente)
    r = app_cliente.get("/api/v1/actions")
    assert r.status_code == 200 and len(r.json()["acoes"]) == 7


def test_conta_por_configurar_nao_executa_acoes(app_cliente):
    k = app_cliente.app.state.db(); k.execute("UPDATE pulse_users SET must_change_password=1"); k.close()
    entrar(app_cliente)
    r = app_cliente.post("/api/v1/actions/rto.marcar_dia", json={"params": {"data": "2026-10-01", "marca": "T"}}, headers=H)
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "mudar_password" and FalsoDados.escritas == []
