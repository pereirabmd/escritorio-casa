"""Verificação do horário da CP no editor dos Bilhetes (ADR-068), com a CP simulada."""
from datetime import date

import pytest

from pulse.services.cp_horarios import CpHorarios, verificar

D = date(2026, 10, 1)
AV, LO = "94-38000", "94-31039"
PARAGENS_731 = [
    {"station": {"code": "94-31039", "designation": "Lisboa Oriente"}, "departure": "17:30:00"},
    {"station": {"code": "94-99999", "designation": "Entroncamento"}, "arrival": "18:20:00", "departure": "18:22:00"},
    {"station": {"code": AV, "designation": "Aveiro"}, "arrival": "19:39:00"},
]


class CpFalsa:
    """Transporte simulado: regista os pedidos e responde pelo que se lhe der."""
    def __init__(self, tt=(200, {"trainStops": PARAGENS_731}), jn=(200, {"outwardTrip": []})):
        self.tt, self.jn, self.pedidos = tt, jn, []

    def __call__(self, metodo, url, cab, corpo):
        self.pedidos.append((metodo, url, cab, corpo))
        return self.tt if "timetable" in url else self.jn


def cp(transporte=None, chaves=("i", "s", "k")):
    return CpHorarios(*chaves, transporte=transporte or CpFalsa())


def test_desligado_sem_chaves():
    assert verificar(cp(chaves=("", "", "")), 731, D, "Lisboa Oriente", "Aveiro", "17:30")["estado"] == "desligado"


def test_confirma_a_hora_da_primeira_estacao_e_a_de_embarque():
    r = verificar(cp(), 731, D, "Lisboa Oriente", "Aveiro", "17:30")
    assert r["estado"] == "confirmado" and r["chegada"] == "19:39" and r["primeira"] == {"estacao": "Lisboa Oriente", "hora": "17:30"}
    assert "Confirmado pela CP" in r["mensagem"]


def test_preenche_a_hora_quando_falta():
    r = verificar(cp(), 731, D, "Lisboa Oriente", "Aveiro", None)
    assert (r["estado"], r["sugestaoHora"]) == ("preenchido", "17:30")


def test_hora_errada_avisa_e_sugere_a_da_primeira_estacao():
    r = verificar(cp(), 731, D, "Lisboa Oriente", "Aveiro", "17:45")
    assert r["estado"] == "aviso" and r["sugestaoHora"] == "17:30" and "tens 17:45" in r["mensagem"]


def test_comboio_que_nao_existe_nessa_data():
    r = verificar(cp(CpFalsa(tt=(404, None))), 731, D, "Lisboa Oriente", "Aveiro", "17:30")
    assert r["estado"] == "aviso" and "não tem o comboio 731 em 01/10" in r["mensagem"]


def test_sentido_contrario_ou_estacao_em_falta_recorre_a_pesquisa_de_viagens():
    # Aveiro → Lisboa Oriente no 731 (que vai ao contrário): a pesquisa também não o encontra
    r = verificar(cp(), 731, D, "Aveiro", "Lisboa Oriente", "19:39")
    assert r["estado"] == "aviso" and "não segue de Aveiro para Lisboa Oriente" in r["mensagem"]
    # o comboio não passa na origem e a pesquisa também não o tem
    r = verificar(cp(CpFalsa(tt=(200, {"trainStops": PARAGENS_731[:2]}))), 731, D, "Aveiro", "Lisboa Oriente", "10:00")
    assert r["estado"] == "aviso" and "não para em Aveiro" in r["mensagem"]


def test_transbordo_pela_pesquisa_de_viagens():
    viagem = {"travelSections": [
        {"trainNumber": 511, "departureTime": "07:10:00", "departureStation": {"designation": "Lisboa Oriente"}, "arrivalTime": "08:00:00"},
        {"trainNumber": 4609, "departureTime": "08:10:00", "departureStation": {"designation": "Pampilhosa"}, "arrivalTime": "08:40:00"}]}
    # o 511 só chega a Pampilhosa: não tem Aveiro nas paragens, a pesquisa dá a viagem com transbordo
    paragens = [{"station": {"code": "94-31039", "designation": "Lisboa Oriente"}, "departure": "07:10:00"}, {"station": {"code": "94-77777", "designation": "Pampilhosa"}, "arrival": "08:00:00"}]
    r = verificar(cp(CpFalsa(tt=(200, {"trainStops": paragens}), jn=(200, {"outwardTrip": [viagem]}))), 511, D, "Lisboa Oriente", "Aveiro", "07:10")
    assert r["estado"] == "confirmado" and r["transbordo"] is True and "(com transbordo)" in r["mensagem"] and r["chegada"] == "08:40"


def test_falha_da_cp_nunca_levanta_e_nao_fica_em_cache():
    falso = CpFalsa(tt=(0, None))
    c = cp(falso)
    assert verificar(c, 731, D, "Lisboa Oriente", "Aveiro", "17:30")["estado"] == "sem_informacao"
    falso.tt = (200, {"trainStops": PARAGENS_731})
    assert verificar(c, 731, D, "Lisboa Oriente", "Aveiro", "17:30")["estado"] == "confirmado"          # a falha não ficou guardada


def test_estacao_desconhecida_nao_se_sabe_confirmar():
    assert verificar(cp(), 731, D, "Coimbra", "Aveiro", "17:30")["estado"] == "sem_informacao"


def test_cache_evita_repetir_o_pedido_e_as_chaves_vao_nos_cabecalhos():
    falso = CpFalsa()
    c = cp(falso)
    verificar(c, 731, D, "Lisboa Oriente", "Aveiro", "17:30"); verificar(c, 731, D, "Lisboa Oriente", "Aveiro", "17:45")
    assert len(falso.pedidos) == 1
    _, url, cab, _ = falso.pedidos[0]
    assert url.endswith("/travel-api/trains/731/timetable/2026-10-01") and cab["X-Api-Key"] == "k" and cab["x-cp-connect-id"] == "i" and cab["x-cp-connect-secret"] == "s"


def test_endpoint_exige_sessao_e_valida_parametros(tmp_path, dados_falso):
    from fastapi.testclient import TestClient
    from pulse import accounts, config
    from pulse.main import create_app
    from tests.conftest import FalsoDados
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s)
    app.state.cp = cp()
    with TestClient(app) as c:
        k = app.state.db(); accounts.criar_utilizador(k, "a@b.pt", "1234qweR", must_change=False); k.close()
        q = "/api/v1/tickets/timetable?comboio=731&data=2026-10-01&origem=Lisboa%20Oriente&destino=Aveiro&hora=17:30"
        assert c.get(q).status_code == 401
        c.post("/api/v1/auth/login", json={"email": "a@b.pt", "password": "1234qweR"})
        assert c.get(q).json()["estado"] == "confirmado"
        assert c.get(q.replace("comboio=731", "comboio=abc")).status_code in (400, 422)
        assert c.get(q.replace("2026-10-01", "2026-13-45")).status_code == 400
