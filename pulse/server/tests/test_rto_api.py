from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


def test_exige_sessao(cliente):
    cliente.cookies.clear()
    assert cliente.get("/api/v1/rto").status_code == 401


def test_devolve_visao_do_ano_pedido(cliente):
    FalsoDados.respostas["/rto/dias"] = (200, {"dias": {"2026-01-05": "C", "2026-01-06": "T", "2025-12-01": "C", "2024-05-01": "T"}})
    FalsoDados.respostas["/rto/notas"] = (200, {"notas": [{"id": 1, "dataInicio": "2026-09-28", "dataFim": "2026-10-02", "categoria": "Férias", "descricao": ""}]})
    r = cliente.get("/api/v1/rto")
    assert r.status_code == 200
    j = r.json()
    assert j["ano"] == 2026 and j["totais"]["C"] == 1 and j["totais"]["T"] == 1 and j["hoje"]["estado"] == "ferias"
    assert set(j["dias"]) == {"2026-01-05", "2026-01-06", "2025-12-01"}          # só o ano pedido e os vizinhos (2024 fica de fora)
    assert "2027-03-26" in j["feriados"] and "2025-04-18" in j["feriados"] and "2026-04-03" in j["feriados"]
    assert len(j["notas"]) == 1 and j["ferias"][0] == "2026-09-28" and j["dezembroAnterior"] == {"t": 0, "c": 1}
    assert cliente.get("/api/v1/rto?ano=2025").json()["totais"]["C"] == 1


@pytest.mark.parametrize("ano", ["1999", "2101", "abc"])
def test_ano_invalido(cliente, ano):
    assert cliente.get(f"/api/v1/rto?ano={ano}").status_code == 400


def test_modulo_em_baixo_e_503(cliente):
    FalsoDados.respostas["/rto/dias"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    assert cliente.get("/api/v1/rto").status_code == 503
