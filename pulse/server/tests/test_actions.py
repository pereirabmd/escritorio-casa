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
    assert set(c) == {"tarefas.concluir", "tarefas.reabrir", "tarefas.saltar", "tarefas.criar", "tarefas.editar", "tarefas.apagar", "tarefas.adiar", "tarefas.lembrar_mais_tarde", "tarefas.piscina_registar", "tarefas.piscina_repor", "tarefas.avisos_horario", "tarefas.preferencias", "tarefas.pessoa_adicionar", "tarefas.pessoa_editar", "tarefas.pessoa_remover", "tarefas.reatribuir", "tarefas.admin", "tarefas.gerar", "peso.registar", "peso.editar", "peso.eliminar",
                      "peso.configurar", "rto.marcar_dia", "rto.ferias_dia", "rto.nota_criar", "rto.nota_editar", "rto.nota_eliminar",
                      "rto.nota_restaurar", "rto.gerar_validacoes", "calendario.criar", "calendario.editar", "calendario.apagar", "email.lida", "email.arquivar", "email.estrela",
                      "compras.adicionar", "compras.remover", "compras.comprado", "compras.detalhes", "compras.mover", "compras.limpar_comprados", "compras.restaurar", "compras.ultima_chamada", "compras.favorito", "compras.ocultar", "compras.sugestao_ignorar", "compras.categoria_ocultar", "compras.produto_criar", "compras.produto_editar", "compras.produto_apagar", "compras.lista_criar", "compras.lista_editar", "compras.lista_apagar",
                      "bilhetes.semana", "bilhetes.passe", "bilhetes.cp_cancelar", "bilhetes.pedido_repetir", "bilhetes.pedido_forcar",
                      "financas.pagar", "financas.anular_pagamento", "financas.criar", "financas.editar", "financas.apagar", "financas.preparar_mes",
                      "financas.categoria_criar", "financas.categoria_editar", "financas.categoria_eliminar", "financas.lembrete_criar", "financas.lembrete_editar", "financas.lembrete_eliminar"}
    assert all(c[n]["nivel"] == "sensitive_action" for n in ("peso.eliminar", "rto.nota_eliminar", "tarefas.apagar", "tarefas.pessoa_remover", "tarefas.reatribuir", "tarefas.admin", "financas.apagar", "financas.categoria_eliminar", "financas.lembrete_eliminar",
                                                            "compras.limpar_comprados", "compras.produto_apagar", "compras.lista_apagar", "calendario.apagar", "bilhetes.cp_cancelar"))
    assert all(a["nivel"] in ("read", "safe_action", "sensitive_action") and a["descricao"] for a in c.values())


def dados_tarefas(*instancias):
    FalsoDados.respostas["/tarefas/dados"] = (200, {"tarefas": [], "config": [], "piscina": [], "instancias": [
        {"id": i, "tarefaId": t, "data": d, "pessoa": "Bruno", "estado": e, "dataConclusao": ""} for i, t, d, e in instancias]})


def test_concluir_escreve_no_modulo_em_nome_do_utilizador(conn, dados_falso):
    dados_tarefas(("I0042", "T001", "2026-09-30", "Pendente"))
    r = correr(conn, dados_falso, "tarefas.concluir", {"instancia": "I0042"})
    assert r["tambem"] == []
    assert FalsoDados.escritas == [("PUT", "/tarefas/instancias/I0042", {"estado": "Feita", "dataConclusao": "2026-09-30 10:05"}, EMAIL)]
    assert atividade(conn) == [("tarefas", "tarefas.concluir", "ui", "ok", "I0042")]


def test_concluir_atrasada_conclui_as_atrasadas_anteriores_da_mesma_tarefa_de_uma_vez(conn, dados_falso):
    dados_tarefas(("I1", "T001", "2026-09-27", "Atrasada"), ("I2", "T001", "2026-09-28", "Atrasada"), ("I3", "T001", "2026-09-29", "Atrasada"),
                  ("I4", "T002", "2026-09-29", "Atrasada"), ("I5", "T001", "2026-09-26", "Feita"), ("I6", "T001", "2026-09-30", "Pendente"))
    r = correr(conn, dados_falso, "tarefas.concluir", {"instancia": "I3"})
    assert r["tambem"] == ["I1", "I2"]
    assert FalsoDados.escritas == [("PUT", "/tarefas/instancias", {"atualizacoes": [
        {"id": i, "estado": "Feita", "dataConclusao": "2026-09-30 10:05"} for i in ("I3", "I1", "I2")]}, EMAIL)]      # só as atrasadas da MESMA tarefa
    assert atividade(conn) == [("tarefas", "tarefas.concluir", "ui", "ok", "I3 (+2 atrasadas)")]


def test_concluir_pendente_nao_mexe_nas_atrasadas(conn, dados_falso):
    dados_tarefas(("I1", "T001", "2026-09-28", "Atrasada"), ("I6", "T001", "2026-09-30", "Pendente"))
    correr(conn, dados_falso, "tarefas.concluir", {"instancia": "I6"})
    assert [w[1] for w in FalsoDados.escritas] == ["/tarefas/instancias/I6"]


def test_concluir_instancia_inexistente_e_404_e_nao_escreve(conn, dados_falso):
    dados_tarefas(("I1", "T001", "2026-09-30", "Pendente"))
    with pytest.raises(ErroDoModulo) as e:
        correr(conn, dados_falso, "tarefas.concluir", {"instancia": "I99"})
    assert e.value.status == 404 and FalsoDados.escritas == []


def test_reabrir_varias_e_saltar(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.reabrir", {"instancia": "I3", "tambem": ["I1", "I2"]})
    assert FalsoDados.escritas[0][2] == {"atualizacoes": [{"id": i, "estado": "Pendente", "dataConclusao": ""} for i in ("I3", "I1", "I2")]}
    correr(conn, dados_falso, "tarefas.saltar", {"instancia": "I9"})
    assert FalsoDados.escritas[1] == ("PUT", "/tarefas/instancias/I9", {"estado": "Saltada"}, EMAIL)


TAREFA = {"nome": " Limpar WC ", "categoria": "Limpeza", "recorrencia": "Semanal", "dias": ["Seg", "Qua"], "hora": "09:00", "pessoa": "Bruno",
          "prioridade": "Alta", "rotacao": ["Bruno", "Camila"], "dependeDe": "T002"}


def test_tarefa_criar_mapeia_para_o_formato_do_modulo(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.criar", {**TAREFA, "cid": "tarefa-cid-01"})
    assert FalsoDados.escritas == [("POST", "/tarefas/tarefas", {"nome": "Limpar WC", "categoria": "Limpeza", "recorrencia": "Semanal", "diasSemana": "Seg,Qua", "diaMes": None,
        "horaNotificacao": "09:00", "pessoaPadrao": "Bruno", "prioridade": "Alta", "rotacaoPessoas": "Bruno,Camila", "dependeDe": "T002", "cid": "tarefa-cid-01"}, EMAIL)]


def test_tarefa_criar_por_tipo_de_recorrencia(conn, dados_falso):
    base = {"nome": "X", "categoria": "Casa"}
    correr(conn, dados_falso, "tarefas.criar", {**base, "recorrencia": "Diaria", "dias": ["Seg"], "diaMes": 3, "data": "2026-10-01"})     # o que não se aplica é ignorado
    correr(conn, dados_falso, "tarefas.criar", {**base, "recorrencia": "Mensal", "diaMes": 15})
    correr(conn, dados_falso, "tarefas.criar", {**base, "recorrencia": "Trimestral", "data": "2026-10-01"})
    correr(conn, dados_falso, "tarefas.criar", {**base, "recorrencia": "Pontual", "data": "2026-10-05"})
    corpos = [w[2] for w in FalsoDados.escritas]
    assert [(c["recorrencia"], c["diasSemana"], c["diaMes"]) for c in corpos] == [("Diaria", "", None), ("Mensal", "", 15), ("Trimestral", "2026-10-01", None), ("Pontual", "2026-10-05", None)]


def test_tarefa_editar_e_apagar(conn, dados_falso):
    correr(conn, dados_falso, "tarefas.editar", {**TAREFA, "tarefa": "T007"})
    assert FalsoDados.escritas[0][:2] == ("PUT", "/tarefas/tarefas/T007")
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "tarefas.apagar", {"tarefa": "T007"})
    assert e.value.codigo == "confirmacao_necessaria" and len(FalsoDados.escritas) == 1
    correr(conn, dados_falso, "tarefas.apagar", {"tarefa": "T007"}, confirmado=True)
    assert FalsoDados.escritas[1] == ("DELETE", "/tarefas/tarefas/T007", None, EMAIL)


@pytest.mark.parametrize("params", [
    {"nome": "X", "categoria": "Casa", "recorrencia": "Semanal"}, {"nome": "X", "categoria": "Casa", "recorrencia": "Dias especificos", "dias": []},
    {"nome": "X", "categoria": "Casa", "recorrencia": "Mensal"}, {"nome": "X", "categoria": "Casa", "recorrencia": "Mensal", "diaMes": 32},
    {"nome": "X", "categoria": "Casa", "recorrencia": "Pontual"}, {"nome": "X", "categoria": "Casa", "recorrencia": "Semestral"},
    {"nome": "", "categoria": "Casa", "recorrencia": "Diaria"}, {"nome": "X", "categoria": "", "recorrencia": "Diaria"},
    {"nome": "X", "categoria": "Casa", "recorrencia": "Anual"}, {"nome": "X", "categoria": "Casa", "recorrencia": "Diaria", "hora": "25:00"},
    {"nome": "X", "categoria": "Casa", "recorrencia": "Diaria", "prioridade": "Urgente"}, {"nome": "X", "categoria": "Casa", "recorrencia": "Semanal", "dias": ["Seg", "Xpto"]},
    {"nome": "X", "categoria": "Casa", "recorrencia": "Diaria", "extra": 1}])
def test_tarefa_criar_valida_antes_de_escrever(conn, dados_falso, params):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "tarefas.criar", params)
    assert e.value.status == 400 and FalsoDados.escritas == []


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


def test_peso_registar_com_data_original_para_o_desfazer(conn, dados_falso):
    correr(conn, dados_falso, "peso.registar", {"peso": 80, "quando": "2026-09-20 07:30:00"})
    assert FalsoDados.escritas[0][2] == {"peso": 80, "nota": "", "quando": "2026-09-20 07:30:00"}
    with pytest.raises(ContaErro):
        correr(conn, dados_falso, "peso.registar", {"peso": 80, "quando": "20/09/2026"})


def test_peso_editar_envia_o_registo_todo(conn, dados_falso):
    correr(conn, dados_falso, "peso.editar", {"registo": 5, "quando": "2026-09-20 07:30:00", "peso": 79.5, "nota": "jejum"})
    assert FalsoDados.escritas == [("PUT", "/peso/registos/5", {"quando": "2026-09-20 07:30:00", "peso": 79.5, "nota": "jejum"}, EMAIL)]
    assert atividade(conn) == [("peso", "peso.editar", "ui", "ok", "registo 5")]


def test_peso_eliminar_e_sensivel_e_devolve_o_registo_apagado(conn, dados_falso):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "peso.eliminar", {"registo": 5})
    assert e.value.codigo == "confirmacao_necessaria" and FalsoDados.escritas == []
    FalsoDados.respostas["DELETE /peso/registos/5"] = (200, {"id": 5, "quando": "2026-09-20 07:30:00", "peso": 79.5, "nota": ""})
    r = correr(conn, dados_falso, "peso.eliminar", {"registo": 5}, confirmado=True)
    assert r["peso"] == 79.5 and FalsoDados.escritas == [("DELETE", "/peso/registos/5", None, EMAIL)]
    assert "79" not in str(atividade(conn))


def test_peso_configurar_so_envia_o_que_foi_indicado_e_null_apaga(conn, dados_falso):
    correr(conn, dados_falso, "peso.configurar", {"altura": 180, "sexo": "M", "nascimento": "1990-10-01", "pesoAlvo": None})
    assert FalsoDados.escritas[0][2] == {"altura": 180.0, "sexo": "M", "nascimento": "1990-10-01", "pesoAlvo": None}


@pytest.mark.parametrize("params", [{}, {"altura": 10}, {"altura": 300}, {"sexo": "X"}, {"atividade": 5}, {"diaControlo": 7},
                                    {"nascimento": "01/10/1990"}, {"pesoMin": 100, "pesoMax": 90}, {"desconhecido": 1}])
def test_peso_configurar_valida_antes_de_escrever(conn, dados_falso, params):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "peso.configurar", params)
    assert e.value.status == 400 and FalsoDados.escritas == []


@pytest.mark.parametrize("nome,params", [
    ("rto.nota_criar", {}), ("rto.nota_criar", {"inicio": "2026-10-10", "fim": "2026-10-01"}), ("rto.nota_criar", {"inicio": "10/10/2026"}),
    ("rto.nota_criar", {"categoria": "Férias", "inicio": "2026-09-01"}),                        # passado, sem modo administrador
    ("rto.nota_criar", {"categoria": "x" * 101}), ("rto.nota_editar", {"categoria": "x"}), ("rto.nota_eliminar", {}),
    ("rto.gerar_validacoes", {"referencia": "2026-10-10", "ate": "2026-10-01"}),
    ("rto.gerar_validacoes", {"referencia": "2026-01-01", "ate": "2050-01-01"}), ("rto.gerar_validacoes", {"referencia": "2026-01-01", "ate": "2026-03-01", "tipo": "Outra"}),
    ("rto.ferias_dia", {}), ("rto.ferias_dia", {"data": "amanhã"})])
def test_rto_notas_validam_antes_de_escrever(conn, dados_falso, nome, params):
    with pytest.raises((ContaErro, ErroDoModulo)) as e:
        correr(conn, dados_falso, nome, params, confirmado=True)
    assert e.value.status in (400, 404) and not [w for w in FalsoDados.escritas if w[0] != "GET"]


def test_rto_nota_criar_com_modo_administrador_aceita_o_passado(conn, dados_falso):
    correr(conn, dados_falso, "rto.nota_criar", {"categoria": " Férias ", "inicio": "2026-09-01", "fim": "2026-09-02", "admin": True, "cid": "nota-cid-0001"})
    assert FalsoDados.escritas[0][1:3] == ("/rto/notas", {"dataInicio": "2026-09-01", "dataFim": "2026-09-02", "categoria": "Férias", "descricao": "", "cid": "nota-cid-0001"})


def test_rto_nota_eliminar_e_sensivel(conn, dados_falso):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "rto.nota_eliminar", {"nota": 3})
    assert e.value.codigo == "confirmacao_necessaria" and FalsoDados.escritas == []


def test_rto_dias_bloqueados_no_modo_normal_e_livres_em_administrador(conn, dados_falso):
    # AGORA = quarta 30/09/2026: sábado 03/10, domingo 04/10 e ontem estão bloqueados; hoje e sexta 02/10 não
    for d in ("2026-10-03", "2026-10-04", "2026-09-29"):
        for nome, params in (("rto.marcar_dia", {"data": d, "marca": "T"}), ("rto.ferias_dia", {"data": d})):
            with pytest.raises(ContaErro) as e:
                correr(conn, dados_falso, nome, params)
            assert e.value.codigo == "dia_bloqueado"
    assert not [w for w in FalsoDados.escritas if w[0] != "GET"]
    for d in ("2026-09-30", "2026-10-02"):
        correr(conn, dados_falso, "rto.marcar_dia", {"data": d, "marca": "T"})
    correr(conn, dados_falso, "rto.marcar_dia", {"data": "2026-10-03", "marca": "C", "admin": True})
    correr(conn, dados_falso, "rto.marcar_dia", {"data": "2026-09-01", "marca": "C", "admin": True})
    assert [w[1] for w in FalsoDados.escritas] == ["/rto/dias/2026-09-30", "/rto/dias/2026-10-02", "/rto/dias/2026-10-03", "/rto/dias/2026-09-01"]
    assert all("admin" not in (w[2] or {}) for w in FalsoDados.escritas)                        # o modo administrador não vai para o módulo


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
    dados_tarefas(("I1", "T001", "2026-09-30", "Pendente"))
    FalsoDados.respostas["PUT /tarefas/instancias/I1"] = (200, {"instancia": {"id": "I1", "estado": "Feita"}})
    r = app_cliente.post("/api/v1/actions/tarefas.concluir", json={"params": {"instancia": "I1"}}, headers=H)
    assert r.status_code == 200 and r.json() == {"resultado": {"instancia": {"id": "I1", "estado": "Feita"}, "tambem": []}}
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
    assert r.status_code == 200 and len(r.json()["acoes"]) == 70


def test_conta_por_configurar_nao_executa_acoes(app_cliente):
    k = app_cliente.app.state.db(); k.execute("UPDATE pulse_users SET must_change_password=1"); k.close()
    entrar(app_cliente)
    r = app_cliente.post("/api/v1/actions/rto.marcar_dia", json={"params": {"data": "2026-10-01", "marca": "T"}}, headers=H)
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "mudar_password" and FalsoDados.escritas == []


def test_lembrar_mais_tarde_chama_o_servidor_das_tarefas(conn, dados_falso):
    class Falso:
        chamadas = []
        def lembrar_mais_tarde(self, u, i, m):
            self.chamadas.append((u, i, m)); return {"ok": True, "ate": "2026-09-30T21:00:00+01:00"}
    api = Falso()
    ctx = actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), EMAIL, AGORA, tarefas_api=api)
    assert actions.executar(conn, ctx, "tarefas.lembrar_mais_tarde", {"instancia": "I0042"}) == {"ate": "2026-09-30T21:00:00+01:00"}
    assert api.chamadas == [(EMAIL, "I0042", 60)]
    with pytest.raises(ContaErro):
        actions.executar(conn, ctx, "tarefas.lembrar_mais_tarde", {"instancia": "I0042", "minutos": 1})       # menos de 5 min: recusado
