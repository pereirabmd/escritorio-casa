from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, config, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import bilhetes
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))     # quarta-feira


def V(i, data, hora, comboio=520, ativo="SIM", origem="Aveiro", destino="Lisboa Oriente"):
    return {"id": i, "data": data, "hora": hora, "origem": origem, "destino": destino, "comboio": comboio, "ativo": ativo}


def C(i, data, hora, comboio=520, carruagem="21", lugar="53"):
    return {"id": i, "data": data, "hora": hora, "comboio": comboio, "origem": "Aveiro", "destino": "Lisboa Oriente", "carruagem": carruagem, "lugar": lugar, "referencia": f"R{i}"}


def P(i, data, estado="ESGOTADO", retry="NAO"):
    return {"id": i, "data": data, "hora": "07:00", "origem": "Aveiro", "destino": "Lisboa Oriente", "comboio": 520, "ativo": "SIM", "retry": retry,
            "intervaloMinutos": 15, "forcar": "NAO", "estado": estado, "ultimaTentativa": None, "referencia": None, "mensagem": "sem lugares"}


DADOS = {
    "passe": {"dataUltimaCompra": "2026-09-05", "validadeDias": 29, "dataExpira": "2026-10-05", "diasRestantes": 5},
    "viagens": [V(1, "2026-09-29", "07:00"), V(2, "2026-09-30", "06:00", 521), V(3, "2026-09-30", "09:00", 522), V(4, "2026-09-30", "18:00", 523),
                V(5, "2026-10-01", "07:00", 524, "NAO"), V(6, "2026-10-05", "07:27", 525, origem="Coimbra-B"), V(7, "2026-10-06", "07:27", 525)],
    "compras": [C(1, "2026-09-29", "07:00"), C(2, "2026-09-30", "09:00", 522, "5", "12"), C(3, "2026-10-05", "07:27", 525)],
    "pedidos": [P(1, "2026-10-06"), P(2, "2026-09-01"), P(3, "2026-10-07", "CONFIRMADO"), P(4, "2026-10-08", "PENDENTE", "SIM")],
    "logs": [{"ts": "2026-09-29 06:00:00", "tipo": "COMPRA", "resultado": "CONFIRMED"}, {"ts": "2026-09-30 06:00:00", "tipo": "ERRO", "resultado": "FALHA"}],
}


def test_estado_de_cada_viagem():
    j = bilhetes.visao(DADOS, AGORA)
    e = {v["id"]: v["estado"] for v in j["semana"]["viagens"] + [v for v in j["proximas"]] + [x for x in bilhetes.visao(DADOS, AGORA, date(2026, 9, 28))["semana"]["viagens"]]}
    assert e[1] == "passada"                 # ontem
    assert e[2] == "passada"                 # 07:00 + 3 h < 10:00
    assert e[3] == "em_curso"                # partiu às 09:00, chega ~12:00
    assert e[4] == "por_comprar"
    assert e[5] == "inativa"


def test_em_curso_com_bilhete_mantem_o_bilhete_e_a_chegada_estimada():
    p = bilhetes.visao(DADOS, AGORA)["proxima"]
    assert (p["id"], p["estado"], p["fimEstimado"]) == (3, "em_curso", "12:00")
    assert p["compra"] == {"carruagem": "5", "lugar": "12", "referencia": "R2"}


def test_a_proxima_passa_a_seguinte_so_depois_da_chegada_estimada():
    depois = datetime(2026, 9, 30, 12, 1, tzinfo=ZoneInfo("Europe/Lisbon"))
    assert bilhetes.visao(DADOS, depois)["proxima"]["id"] == 4


def test_semana_por_omissao_e_a_seguinte_e_conta_ativas():
    j = bilhetes.visao(DADOS, AGORA)
    assert j["semana"]["inicio"] == "2026-10-05" and j["semanaSeguinte"] == {"inicio": "2026-10-05", "ativas": 2}
    assert [v["id"] for v in j["semana"]["viagens"]] == [6, 7]
    assert len(j["semana"]["dias"]) == 7 and j["semana"]["dias"][0] == "2026-10-05"
    assert bilhetes.visao(DADOS, AGORA, date(2026, 9, 28))["semana"]["inicio"] == "2026-09-28"


def test_bilhetes_pedidos_passe_registo_e_estacoes():
    j = bilhetes.visao(DADOS, AGORA)
    assert [b["id"] for b in j["bilhetes"]["proximos"]] == [2, 3] and [b["id"] for b in j["bilhetes"]["anteriores"]] == [1]
    assert [p["id"] for p in j["pedidos"]] == [1, 4]                       # sem o confirmado nem o que já passou
    assert j["pedidos"][1]["retry"] is True and j["pedidos"][0]["retry"] is False and j["pedidos"][0]["forcar"] is False
    assert j["passe"]["estado"] == "ok" and j["passe"]["diasRestantes"] == 5
    assert j["registo"][0]["resultado"] == "FALHA"                           # o mais recente primeiro
    assert j["estacoes"] == ["Aveiro", "Lisboa Oriente", "Coimbra-B"]
    assert j["historico"][0]["comboio"] == 525 and len(j["historico"]) == 7


@pytest.mark.parametrize("dias,estado", [(None, "sem_data"), (-1, "expirado"), (0, "hoje"), (3, "a_expirar"), (4, "ok")])
def test_estados_do_passe(dias, estado):
    assert bilhetes._passe({"diasRestantes": dias, "validadeDias": 29}, AGORA.date())["estado"] == estado


# --- API ------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


def test_api_exige_sessao_e_devolve_a_visao(cliente):
    FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)
    j = cliente.get("/api/v1/tickets?semana=2026-09-30").json()
    assert j["semana"]["inicio"] == "2026-09-28" and j["proxima"]["id"] == 3
    assert cliente.get("/api/v1/tickets?semana=2026-13-45").status_code in (400, 422)
    assert cliente.get("/api/v1/tickets?semana=x").status_code in (400, 422)
    cliente.cookies.clear()
    assert cliente.get("/api/v1/tickets").status_code == 401


def test_api_modulo_em_baixo_e_sem_acesso(cliente):
    FalsoDados.respostas["/bilhetes/dados"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    assert cliente.get("/api/v1/tickets").status_code == 503
    FalsoDados.respostas["/bilhetes/dados"] = (403, {"erro": {"codigo": "sem_acesso", "mensagem": "sem acesso a esta aplicação"}})
    assert cliente.get("/api/v1/tickets").status_code == 403


# --- ações ----------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-b.db"); db.migrate(c)
    yield c
    c.close()


def correr(conn, dados_falso, nome, params, **kw):
    return actions.executar(conn, actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), EMAIL, AGORA), nome, params, **kw)


VIAGEM = {"data": "2026-10-06", "origem": "Aveiro", "destino": "Lisboa Oriente", "comboio": 525, "hora": "07:27"}


def test_semana_grava_e_devolve_o_que_la_estava_para_o_desfazer(conn, dados_falso):
    FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)
    FalsoDados.respostas["PUT /bilhetes/semana"] = (200, {"viagens": []})
    r = correr(conn, dados_falso, "bilhetes.semana", {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "ativo": False}]})
    assert [(v["data"], v["comboio"]) for v in r["anteriores"]] == [("2026-10-05", 525), ("2026-10-06", 525)]
    assert FalsoDados.escritas == [("PUT", "/bilhetes/semana", {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "ativo": "NAO"}]}, EMAIL)]


@pytest.mark.parametrize("mau", [
    {"inicio": "2026-10-06", "viagens": []},                                                                   # não é segunda-feira
    {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "data": "2026-10-12"}]},                                   # fora da semana
    {"inicio": "2026-10-05", "viagens": [VIAGEM, VIAGEM]},                                                     # repetida
    {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "destino": " aveiro "}]},                                  # origem = destino
    {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "hora": "7:27"}]},
    {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "comboio": 0}]},
])
def test_semana_recusa_dados_invalidos(conn, dados_falso, mau):
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "bilhetes.semana", mau)
    assert e.value.codigo == "parametros_invalidos" and FalsoDados.escritas == []


def test_passe_pedidos(conn, dados_falso):
    correr(conn, dados_falso, "bilhetes.passe", {"dataUltimaCompra": "2026-09-30"})
    correr(conn, dados_falso, "bilhetes.passe", {"dataUltimaCompra": "2026-09-30", "validadeDias": 30})
    correr(conn, dados_falso, "bilhetes.pedido_repetir", {"pedido": 4, "retry": True, "intervaloMinutos": 20})
    correr(conn, dados_falso, "bilhetes.pedido_forcar", {"pedido": 4})
    assert [(m, c, b) for m, c, b, _ in FalsoDados.escritas] == [
        ("PUT", "/bilhetes/passe", {"dataUltimaCompra": "2026-09-30"}), ("PUT", "/bilhetes/passe", {"dataUltimaCompra": "2026-09-30", "validadeDias": 30}),
        ("PUT", "/bilhetes/pedidos/4", {"retry": True, "intervaloMinutos": 20}), ("POST", "/bilhetes/pedidos/4/forcar", None)]
    with pytest.raises(ContaErro):
        correr(conn, dados_falso, "bilhetes.pedido_repetir", {"pedido": 4, "retry": True, "intervaloMinutos": 0})


def test_marcar_para_outra_pessoa_leva_o_utilizador_ao_dados_api(conn, dados_falso):
    """O Bruno marca no Pulse para a Camila (utilizador 2): a semana lê-se e grava-se como dela, e o «Desfazer» repõe a dela."""
    FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)
    FalsoDados.respostas["PUT /bilhetes/semana"] = (200, {"viagens": []})
    FalsoDados.pedidos.clear()
    r = correr(conn, dados_falso, "bilhetes.semana", {"inicio": "2026-10-05", "utilizador": 2, "viagens": [VIAGEM]})
    assert any(p[0].startswith("/bilhetes/dados?utilizador=2") for p in FalsoDados.pedidos)             # as «anteriores» lêem-se da Camila
    assert FalsoDados.escritas == [("PUT", "/bilhetes/semana", {"inicio": "2026-10-05", "viagens": [{**VIAGEM, "ativo": "SIM"}], "utilizadorId": 2}, EMAIL)]
    assert "anteriores" in r
    FalsoDados.escritas.clear()
    correr(conn, dados_falso, "bilhetes.passe", {"dataUltimaCompra": "2026-09-30", "utilizador": 2})
    assert FalsoDados.escritas[0][2] == {"dataUltimaCompra": "2026-09-30", "utilizadorId": 2}


def test_visao_traz_a_pessoa_e_as_pessoas_por_quem_se_pode_marcar():
    j = bilhetes.visao({**DADOS, "utilizador": {"id": 2, "nome": "Camila", "eu": False}, "pessoas": [{"id": 1, "nome": "Bruno"}, {"id": 2, "nome": "Camila"}]}, AGORA)
    assert j["utilizador"]["nome"] == "Camila" and [p["nome"] for p in j["pessoas"]] == ["Bruno", "Camila"]
    assert bilhetes.visao(DADOS, AGORA)["pessoas"] == []               # um dados-api antigo: sem seletor


def test_api_passa_o_utilizador_pedido(cliente):
    cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    FalsoDados.pedidos.clear()
    assert cliente.get("/api/v1/tickets?utilizador=2").status_code == 200
    assert any(p[0] == "/bilhetes/dados?utilizador=2" for p in FalsoDados.pedidos)
    assert cliente.get("/api/v1/tickets?utilizador=0").status_code in (400, 422)


def test_cancelar_bilhete_na_cp_e_sensivel_e_leva_a_venda_e_a_pessoa(conn, dados_falso):
    FalsoDados.respostas["POST /bilhetes/cp/cancelar"] = (200, {"venda": 77, "estado": "CONFIRMED"})
    FalsoDados.escritas.clear()
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "bilhetes.cp_cancelar", {"venda": 77})
    assert e.value.codigo == "confirmacao_necessaria" and FalsoDados.escritas == []                   # nunca cancela sem confirmação
    correr(conn, dados_falso, "bilhetes.cp_cancelar", {"venda": 77, "utilizador": 2}, confirmado=True)
    assert FalsoDados.escritas == [("POST", "/bilhetes/cp/cancelar", {"venda": 77, "utilizadorId": 2}, EMAIL)]



def test_api_cp_futuros_e_passe_passam_pelo_dados_api(cliente):
    FalsoDados.respostas["/bilhetes/cp/futuros"] = (200, {"utilizadorId": 1, "bilhetes": [{"venda": 77, "origem": "Aveiro"}]})
    FalsoDados.respostas["/bilhetes/cp/passe"] = (200, {"utilizadorId": 1, "passes": [{"validade": "2026-10-20", "diasRestantes": 20}]})
    FalsoDados.pedidos.clear()
    assert cliente.get("/api/v1/tickets/cp/futuros?utilizador=2").json()["bilhetes"][0]["venda"] == 77
    assert cliente.get("/api/v1/tickets/cp/passe").json()["passes"][0]["validade"] == "2026-10-20"
    assert [p[0] for p in FalsoDados.pedidos] == ["/bilhetes/cp/futuros?utilizador=2", "/bilhetes/cp/passe"]
    FalsoDados.respostas["/bilhetes/cp/futuros"] = (409, {"erro": {"codigo": "cp_credenciais", "mensagem": "faltam dados de Davi: NIF"}})
    r = cliente.get("/api/v1/tickets/cp/futuros")
    assert r.status_code == 409 and "faltam dados" in r.text                                          # a mensagem da CP chega à interface
    cliente.cookies.clear()
    assert cliente.get("/api/v1/tickets/cp/passe").status_code == 401


def test_viagem_com_a_hora_da_venda_diferente_da_de_embarque_conta_como_comprada():
    # a viagem é das 06:45 (abre a venda) e a compra guardou 07:27 (embarque): é o mesmo bilhete (ADR-068)
    d = {"viagens": [V(111, "2026-10-02", "06:45", 520), V(112, "2026-10-02", "17:30", 731, origem="Lisboa Oriente", destino="Aveiro")],
         "compras": [{**C(9, "2026-10-02", "07:27", 520), "origem": "Aveiro", "destino": "Lisboa Oriente"},
                     {**C(10, "2026-10-02", "17:39", 731), "origem": "Aveiro", "destino": "Lisboa Oriente"}], "passe": {}, "pedidos": [], "logs": []}
    j = bilhetes.visao(d, datetime(2026, 10, 1, 18, 0), None)
    estados = {v["id"]: v["estado"] for v in j["semana"]["viagens"] + j["proximas"]}
    assert estados[111] == "comprado"                    # mesmo comboio, dia e percurso, hora diferente
    assert estados[112] == "por_comprar"                 # o 731 comprado é no sentido contrário: não conta


def test_troca_armar_e_desarmar_passam_pelo_dados_api(conn, dados_falso):
    FalsoDados.respostas["POST /bilhetes/trocas"] = (201, {"id": 104, "comboio": 731, "trocaVenda": 77})
    FalsoDados.respostas["DELETE /bilhetes/trocas/104"] = (200, {"id": 104, "estado": "DESARMADO"})
    r = correr(conn, dados_falso, "bilhetes.troca_armar", {"venda": 77, "comboio": 731, "hora": "17:30"}, confirmado=True)
    assert r["trocaVenda"] == 77
    assert ("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"}, EMAIL) in FalsoDados.escritas
    assert correr(conn, dados_falso, "bilhetes.troca_desarmar", {"pedido": 104})["estado"] == "DESARMADO"
    with pytest.raises(ContaErro) as e:                                                       # cancela um bilhete: pede confirmação
        correr(conn, dados_falso, "bilhetes.troca_armar", {"venda": 77, "comboio": 731, "hora": "17:30"})
    assert e.value.codigo == "confirmacao_necessaria"


def test_pedidos_desarmados_nao_aparecem_mas_o_expirado_sim_com_os_campos_da_troca():
    d = {"viagens": [], "compras": [], "passe": {}, "logs": [], "pedidos": [
        {**P(1, "2026-10-06"), "trocaVenda": 77, "trocaReferencia": "CP-X", "trocaAntecedenciaMin": 30},
        {**P(2, "2026-10-06", estado="DESARMADO"), "trocaVenda": 77},
        {**P(3, "2026-10-06", estado="EXPIRADO"), "trocaVenda": 78, "mensagem": "Sem lugar até 30 min antes."}]}
    j = bilhetes.visao(d, datetime(2026, 10, 1, 18, 0), None)
    assert [(p["id"], p["trocaVenda"]) for p in j["pedidos"]] == [(1, 77), (3, 78)]
