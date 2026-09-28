import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config, db
from pulse.main import create_app

EMAIL, PW, NOVA = "pereirabmd@gmail.com", "1234qweR", "Outra-Palavra-Segura-7"


@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_WEB_BASE_PATH": "/"})   # o cliente de teste não tem o prefixo /pulse/ do nginx, senão não reenviava o cookie
    with TestClient(create_app(s)) as c:
        conn = c.app.state.db()
        accounts.criar_utilizador(conn, EMAIL, PW, "Bruno", admin=True); conn.close()
        yield c


def login(c, pw=PW, cliente_="web", email=EMAIL):
    return c.post("/api/v1/auth/login", json={"email": email, "password": pw, "cliente": cliente_})


def test_login_web_da_cookie_httponly_e_nao_devolve_token(cliente):
    r = login(cliente)
    assert r.status_code == 200 and "token" not in r.json()
    assert r.json()["utilizador"] == {"id": 1, "email": EMAIL, "nome": "Bruno", "admin": True, "mudarPassword": True}
    sc = r.headers["set-cookie"].lower()
    assert "pulse_session=" in sc and "httponly" in sc and "samesite=lax" in sc and "path=/;" in sc + ";"
    assert cliente.get("/api/v1/auth/me").status_code == 200


def test_login_android_devolve_token_bearer_e_nao_poe_cookie(cliente):
    r = login(cliente, cliente_="android")
    assert "set-cookie" not in r.headers
    token = r.json()["token"]
    cliente.cookies.clear()
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["utilizador"]["email"] == EMAIL


def test_credenciais_erradas_401_generico(cliente):
    for email, pw in ((EMAIL, "errada"), ("nao@existe.pt", PW)):
        r = login(cliente, pw=pw, email=email)
        assert r.status_code == 401 and r.json()["erro"]["codigo"] == "credenciais_invalidas"
    assert cliente.get("/api/v1/auth/me").status_code == 401


def test_pedido_mal_formado_e_400_no_formato_do_pulse(cliente):
    r = cliente.post("/api/v1/auth/login", json={"email": EMAIL})
    assert r.status_code == 400 and r.json()["erro"]["codigo"] == "pedido_invalido"


def test_must_change_password_limita_o_que_se_pode_fazer(cliente):
    login(cliente)
    r = cliente.get("/api/v1/auth/sessions")
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "mudar_password"
    assert cliente.get("/api/v1/auth/me").status_code == 200
    r = cliente.post("/api/v1/auth/password", json={"atual": PW, "nova": NOVA}, headers={"X-Pulse-Client": "web"})
    assert r.status_code == 200
    assert cliente.get("/api/v1/auth/sessions").status_code == 200


def test_csrf_cookie_exige_cabecalho_nos_pedidos_que_alteram(cliente):
    login(cliente)
    r = cliente.post("/api/v1/auth/password", json={"atual": PW, "nova": NOVA})
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "csrf"


def test_password_fraca_e_atual_errada(cliente):
    login(cliente); h = {"X-Pulse-Client": "web"}
    assert cliente.post("/api/v1/auth/password", json={"atual": PW, "nova": "curta"}, headers=h).json()["erro"]["codigo"] == "password_fraca"
    assert cliente.post("/api/v1/auth/password", json={"atual": "x", "nova": NOVA}, headers=h).json()["erro"]["codigo"] == "password_atual_errada"


def test_logout_revoga_a_sessao(cliente):
    login(cliente)
    assert cliente.post("/api/v1/auth/logout", headers={"X-Pulse-Client": "web"}).status_code == 200
    assert cliente.get("/api/v1/auth/me").status_code == 401


def test_mudar_password_termina_as_outras_sessoes(cliente):
    token = login(cliente, cliente_="android").json()["token"]
    cliente.cookies.clear()
    login(cliente)
    cliente.post("/api/v1/auth/password", json={"atual": PW, "nova": NOVA}, headers={"X-Pulse-Client": "web"})
    assert cliente.get("/api/v1/auth/me").status_code == 200
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", "Cookie": ""}).status_code == 401


def test_listar_e_terminar_sessoes_so_as_proprias(cliente):
    login(cliente); h = {"X-Pulse-Client": "web"}
    cliente.post("/api/v1/auth/password", json={"atual": PW, "nova": NOVA}, headers=h)
    outra = login(cliente, pw=NOVA, cliente_="android").json()["token"]
    ss = cliente.get("/api/v1/auth/sessions").json()["sessoes"]
    assert len(ss) == 2 and sum(s["atual"] for s in ss) == 1
    alheio = next(s["id"] for s in ss if not s["atual"])
    assert cliente.delete(f"/api/v1/auth/sessions/{alheio}", headers=h).status_code == 200
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {outra}"}).status_code == 401
    assert cliente.delete("/api/v1/auth/sessions/9999", headers=h).status_code == 404


def test_limite_de_tentativas_por_ip(cliente):
    cliente.app.state.limite_login.limite = 3
    codigos = [login(cliente, pw="errada").status_code for _ in range(5)]
    assert codigos[:3] == [401, 401, 401] and codigos[3:] == [429, 429]


def test_bloqueio_da_conta_apos_falhas_seguidas(cliente):
    cliente.app.state.limite_login.limite = 100
    for _ in range(accounts.MAX_FALHAS):
        login(cliente, pw="errada")
    r = login(cliente)
    assert r.status_code == 429 and r.json()["erro"]["codigo"] == "conta_bloqueada"


def test_atividade_regista_login_ok_e_falhado_sem_passwords(cliente):
    login(cliente, pw="errada"); login(cliente)
    conn = cliente.app.state.db()
    linhas = conn.execute("SELECT acao, resultado, detalhe FROM pulse_activity ORDER BY id").fetchall()
    conn.close()
    assert [(l["acao"], l["resultado"]) for l in linhas] == [("login", "erro"), ("login", "ok")]
    assert "errada" not in str([tuple(l) for l in linhas]) and PW not in str([tuple(l) for l in linhas])


def test_token_nunca_fica_guardado_em_claro(cliente):
    token = login(cliente, cliente_="android").json()["token"]
    conn = cliente.app.state.db()
    guardado = conn.execute("SELECT token_hash FROM pulse_sessions").fetchone()[0]
    conn.close()
    assert guardado != token and token not in guardado


def test_cookie_usa_o_caminho_base_da_web_por_omissao(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-p.db"), "PULSE_DADOS_URL": dados_falso})
    with TestClient(create_app(s)) as c:
        conn = c.app.state.db(); accounts.criar_utilizador(conn, EMAIL, PW); conn.close()
        assert "path=/pulse/" in login(c).headers["set-cookie"].lower()
