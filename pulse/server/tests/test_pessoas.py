"""Acesso por pessoa e «Hoje» por pessoa (ADR-063)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from pulse.services import modulos
from tests.conftest import FalsoDados
from tests.test_dashboard import preparar

ADMIN, CAMILA = "pereirabmd@gmail.com", "camila@exemplo.pt"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
H = {"X-Pulse-Client": "web"}


@pytest.fixture
def app(tmp_path, dados_falso):
    preparar()
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    a = create_app(s); a.state.agora = lambda: AGORA
    with TestClient(a):
        k = a.state.db()
        accounts.criar_utilizador(k, ADMIN, "1234qweR", must_change=False, admin=True)
        k.close()
        yield a


def entrar(app, email, password="1234qweR"):
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def criar_camila(admin, modulos_=("compras", "tarefas")):
    r = admin.post("/api/v1/admin/users", json={"email": CAMILA, "nome": "Camila", "password": "provisoria1", "modulos": list(modulos_)}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def test_so_administradores_gerem_pessoas(app):
    admin = entrar(app, ADMIN)
    criar_camila(admin)
    camila = entrar(app, CAMILA, "provisoria1")
    assert camila.get("/api/v1/admin/users").status_code in (403,)                 # tem de mudar a palavra-passe primeiro
    camila.post("/api/v1/auth/password", json={"atual": "provisoria1", "nova": "MinhaSenha#2031x"}, headers=H)
    assert camila.get("/api/v1/admin/users").json()["erro"]["codigo"] == "sem_permissao"
    assert camila.post("/api/v1/admin/users", json={"email": "x@y.pt", "password": "provisoria1"}, headers=H).status_code == 403


def test_conta_nova_so_tem_os_modulos_dados_e_a_api_recusa_o_resto(app):
    admin = entrar(app, ADMIN)
    p = criar_camila(admin)
    assert p["modulos"] == ["compras", "tarefas"] and p["mudarPassword"] is True
    camila = entrar(app, CAMILA, "provisoria1")
    camila.post("/api/v1/auth/password", json={"atual": "provisoria1", "nova": "MinhaSenha#2031x"}, headers=H)
    mods = {m["id"]: m for m in camila.get("/api/v1/modules").json()["modulos"]}
    assert [i for i, m in mods.items() if m["ativo"]] == ["tarefas", "compras"]
    assert mods["peso"]["ativo"] is False and mods["peso"]["ativoGlobal"] is True and mods["peso"]["permitido"] is False
    r = camila.get("/api/v1/weight")
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "sem_acesso"
    assert camila.post("/api/v1/actions/peso.registar", json={"params": {"peso": 80}}, headers=H).json()["erro"]["codigo"] == "sem_acesso"
    assert admin.get("/api/v1/modules").json()["modulos"][3]["ativo"] is True        # o administrador continua com tudo


def test_dar_e_tirar_modulos(app):
    admin = entrar(app, ADMIN)
    p = criar_camila(admin)
    r = admin.put(f"/api/v1/admin/users/{p['id']}/modules", json={"modulos": ["peso"]}, headers=H)
    assert r.json()["modulos"] == ["peso"]
    assert admin.put(f"/api/v1/admin/users/{p['id']}/modules", json={"modulos": ["nao_existe"]}, headers=H).status_code == 400
    assert admin.put("/api/v1/admin/users/999/modules", json={"modulos": []}, headers=H).status_code == 404


def test_hoje_so_pede_os_modulos_da_pessoa(app):
    admin = entrar(app, ADMIN)
    criar_camila(admin, ("compras",))
    camila = entrar(app, CAMILA, "provisoria1")
    camila.post("/api/v1/auth/password", json={"atual": "provisoria1", "nova": "MinhaSenha#2031x"}, headers=H)
    FalsoDados.pedidos.clear()
    j = camila.get("/api/v1/dashboard/today").json()
    assert j["modulos"]["tarefas"]["estado"] == "desativado" and j["modulos"]["compras"]["estado"] != "desativado"
    assert [p for p in FalsoDados.pedidos if not p[0].startswith("/compras")] == []          # nada foi pedido aos módulos sem acesso
    d = camila.get("/api/v1/dashboard/order").json()
    assert d["disponiveis"] == ["compras"]


def test_esconder_cartoes_do_hoje(app):
    admin = entrar(app, ADMIN)
    assert admin.get("/api/v1/dashboard/order").json()["ocultos"] == []
    r = admin.put("/api/v1/dashboard/order", json={"ocultos": ["peso", "rto"]}, headers=H).json()
    assert r["ocultos"] == ["peso", "rto"] and r["ordem"][0] == "calendario"               # a ordem não mudou
    FalsoDados.pedidos.clear()
    j = admin.get("/api/v1/dashboard/today").json()
    assert j["modulos"]["peso"]["estado"] == "desativado" and j["modulos"]["tarefas"]["estado"] == "ok" and j["ocultos"] == ["peso", "rto"]
    assert not [p for p in FalsoDados.pedidos if p[0].startswith("/peso") or p[0].startswith("/rto")]       # escondido = nem se pede
    assert admin.put("/api/v1/dashboard/order", json={"ocultos": ["peso", "peso"]}, headers=H).status_code == 422
    assert admin.put("/api/v1/dashboard/order", json={"ocultos": []}, headers=H).json()["ocultos"] == []


def test_desativar_termina_as_sessoes_e_nao_se_desativa_a_propria(app):
    admin = entrar(app, ADMIN)
    p = criar_camila(admin)
    camila = entrar(app, CAMILA, "provisoria1")
    assert admin.put(f"/api/v1/admin/users/{p['id']}/active", json={"ativo": False}, headers=H).json()["ativo"] is False
    assert camila.get("/api/v1/auth/me").status_code == 401
    eu = admin.get("/api/v1/admin/users").json()["pessoas"][0]["id"]
    assert admin.put(f"/api/v1/admin/users/{eu}/active", json={"ativo": False}, headers=H).json()["erro"]["codigo"] == "a_propria"


def test_repor_password_provisoria(app):
    admin = entrar(app, ADMIN)
    p = criar_camila(admin)
    assert admin.post(f"/api/v1/admin/users/{p['id']}/password", json={"password": "outraprovisoria"}, headers=H).json() == {"ok": True}
    entrar(app, CAMILA, "outraprovisoria")
    assert TestClient(app).post("/api/v1/auth/login", json={"email": CAMILA, "password": "provisoria1"}).status_code == 401


def test_contas_criadas_pela_linha_de_comandos_ficam_com_todos_os_modulos(app):
    k = app.state.db()
    uid = accounts.criar_utilizador(k, "x@y.pt", "1234qweR")
    assert modulos.permitidos(k, uid) == modulos.DISPONIVEIS
    k.close()
