from fastapi.testclient import TestClient

from pulse import config
from pulse.clients.dados import DadosClient
from pulse.main import create_app


def test_health_ok(settings):
    with TestClient(create_app(settings)) as c:
        r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok" and r.json()["componentes"] == {"base_de_dados": "ok", "dados_api": "ok"}
    assert r.json()["ambiente"] == "test"


def test_dados_api_em_baixo_e_degradado_e_nao_erro(tmp_path):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-p.db"),
                     "PULSE_DADOS_URL": "http://127.0.0.1:9", "PULSE_SERVICE_KEY": "k" * 40})
    with TestClient(create_app(s)) as c:
        r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "degradado" and r.json()["componentes"]["dados_api"] == "indisponivel"
    assert r.json()["componentes"]["base_de_dados"] == "ok"


def test_version_e_migracao_no_arranque(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/v1/version").json() == {"versao": "0.1.0"}
        conn = c.app.state.db()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        conn.close()


def test_docs_so_fora_de_producao(tmp_path):
    prod = config.load({"PULSE_ENV": "production", "PULSE_DB_PATH": str(tmp_path / "pulse.db")})
    dev = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-d.db")})
    with TestClient(create_app(prod, DadosClient("http://127.0.0.1:9", ""))) as c:
        assert c.get("/api/openapi.json").status_code == 404
    with TestClient(create_app(dev)) as c:
        assert c.get("/api/openapi.json").status_code == 200
