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
        yield c


def test_exige_sessao(cliente):
    assert cliente.get("/api/v1/weight").status_code == 401


def test_devolve_registos_config_e_resumo(cliente):
    FalsoDados.respostas["/peso/registos"] = (200, {"registos": [{"id": 1, "quando": "2026-09-01 08:00:00", "peso": 110, "nota": ""},
                                                                 {"id": 2, "quando": "2026-09-30 08:00:00", "peso": 100, "nota": "x"}]})
    FalsoDados.respostas["/peso/config"] = (200, {"altura": 180.0, "pesoAlvo": 90.0})
    cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    r = cliente.get("/api/v1/weight")
    assert r.status_code == 200
    j = r.json()
    assert len(j["registos"]) == 2 and j["config"]["altura"] == 180.0
    assert j["resumo"]["ultimo"]["peso"] == 100 and j["resumo"]["progresso"]["pct"] == 50.0 and j["resumo"]["imc"]["classe"] == "Obesidade grau I"
    assert {p[1] for p in FalsoDados.pedidos} == {EMAIL}


def test_modulo_em_baixo_e_503_e_sem_acesso_e_403(cliente):
    cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    FalsoDados.respostas["/peso/registos"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    assert cliente.get("/api/v1/weight").status_code == 503
    FalsoDados.respostas["/peso/registos"] = (403, {"erro": {"codigo": "sem_acesso", "mensagem": "sem acesso a esta aplicação"}})
    r = cliente.get("/api/v1/weight")
    assert (r.status_code, r.json()["erro"]["codigo"]) == (403, "sem_acesso")
