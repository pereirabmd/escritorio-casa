from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, config, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import modulos
from tests.conftest import FalsoDados

ADMIN, OUTRO = "pereirabmd@gmail.com", "camila@exemplo.pt"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
H = {"X-Pulse-Client": "web"}


@pytest.fixture
def app(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    a = create_app(s); a.state.agora = lambda: AGORA
    with TestClient(a):
        k = a.state.db()
        accounts.criar_utilizador(k, ADMIN, "1234qweR", must_change=False, admin=True)
        accounts.criar_utilizador(k, OUTRO, "1234qweR", must_change=False)
        k.close()
        yield a


def entrar(app, email):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "1234qweR"}).status_code == 200
    return c


def test_por_omissao_todos_os_modulos_estao_ativos_e_disponiveis(app):
    j = entrar(app, OUTRO).get("/api/v1/modules").json()["modulos"]
    assert [m["id"] for m in j] == ["tarefas", "bilhetes", "rto", "peso", "financas", "compras", "calendario", "email"]
    assert all(m["ativo"] and m["disponivel"] for m in j)                      # já não há módulos «Em breve»


def test_so_o_administrador_altera(app):
    assert entrar(app, OUTRO).put("/api/v1/admin/modules", json={"modulos": {"peso": False}}, headers=H).status_code == 403
    assert entrar(app, ADMIN).put("/api/v1/admin/modules", json={"modulos": {"peso": False}}, headers=H).status_code == 200
    assert next(m for m in entrar(app, OUTRO).get("/api/v1/modules").json()["modulos"] if m["id"] == "peso")["ativo"] is False   # vale para todos


@pytest.mark.parametrize("mau", [{"modulos": {}}, {"modulos": {"inexistente": False}}, {"modulos": {"peso": "nao"}}, {"peso": False}])
def test_pedidos_invalidos(app, mau):
    assert entrar(app, ADMIN).put("/api/v1/admin/modules", json=mau, headers=H).status_code == 400


def test_modulo_desativado_e_recusado_na_api_e_nas_acoes(app):
    adm = entrar(app, ADMIN)
    adm.put("/api/v1/admin/modules", json={"modulos": {"peso": False, "financas": False, "bilhetes": False, "rto": False, "tarefas": False}}, headers=H)
    for rota in ("/weight", "/finance", "/tickets", "/rto", "/tasks", "/tasks/pool", "/finance/reports?de=2026-01&ate=2026-02"):
        r = adm.get("/api/v1" + rota)
        assert (r.status_code, r.json()["erro"]["codigo"]) == (403, "modulo_desativado"), rota
    r = adm.post("/api/v1/actions/peso.registar", json={"params": {"peso": 90}}, headers=H)
    assert (r.status_code, r.json()["erro"]["codigo"]) == (403, "modulo_desativado") and FalsoDados.escritas == []
    adm.put("/api/v1/admin/modules", json={"modulos": {"peso": True}}, headers=H)
    assert adm.get("/api/v1/weight").status_code != 403


def test_hoje_nao_pede_nada_aos_modulos_desativados(app):
    adm = entrar(app, ADMIN)
    adm.put("/api/v1/admin/modules", json={"modulos": {"financas": False, "bilhetes": False}}, headers=H)
    FalsoDados.pedidos.clear()
    j = adm.get("/api/v1/dashboard/today").json()
    assert j["modulos"]["financas"] == {"estado": "desativado", "dados": None} and j["modulos"]["bilhetes"]["estado"] == "desativado"
    assert not any(p.startswith(("/financas", "/bilhetes")) for p, _ in FalsoDados.pedidos)
    assert any(p.startswith("/rto") for p, _ in FalsoDados.pedidos)


def test_alteracoes_ficam_no_centro_de_atividade_e_sem_mudanca_nao_regista(app):
    adm = entrar(app, ADMIN)
    adm.put("/api/v1/admin/modules", json={"modulos": {"peso": False}}, headers=H)
    adm.put("/api/v1/admin/modules", json={"modulos": {"peso": False}}, headers=H)          # já estava
    k = app.state.db()
    rows = [tuple(r) for r in k.execute("SELECT utilizador, acao, detalhe FROM pulse_activity WHERE acao LIKE 'modulo.%'")]
    k.close()
    assert rows == [(ADMIN, "modulo.desativar", "peso")]


def test_servico_guarda_so_o_que_esta_desativado(tmp_path):
    c = db.connect(tmp_path / "teste-m.db"); db.migrate(c)
    modulos.alterar(c, {"peso": False, "rto": False})
    modulos.alterar(c, {"peso": True})
    assert modulos.desativados(c) == {"rto"}
    with pytest.raises(ContaErro):
        modulos.exigir(c, "rto")
    modulos.exigir(c, "peso")
    c.execute("UPDATE pulse_settings SET valor = 'rto,lixo,inexistente' WHERE chave = ?", (modulos.CHAVE,))
    assert modulos.desativados(c) == {"rto"}                                                # valores estranhos ignoram-se
    c.close()
