import json
import time
from datetime import datetime
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config, db, notifications
from pulse.main import create_app
from pulse.notifications import Erro, Evento, FcmCanal
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
CHAVE = FalsoDados.CHAVE
TOKEN = "t" * 40
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


class CanalFalso:
    nome = "falso"

    def __init__(self, comportamento=None):
        self.enviados, self.comportamento = [], comportamento

    def enviar(self, token, evento):
        if self.comportamento:
            self.comportamento(token)
        self.enviados.append((token, evento.titulo))


def montar(tmp_path, dados_falso, canais):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s, canais=canais); app.state.agora = lambda: AGORA
    return app


@pytest.fixture
def canal():
    return CanalFalso()


@pytest.fixture
def cliente(tmp_path, dados_falso, canal):
    app = montar(tmp_path, dados_falso, [canal])
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


SERVICO = {"X-Pulse-Key": CHAVE, "X-Pulse-User": EMAIL}
EVENTO = {"modulo": "bilhetes", "tipo": "bilhetes.comprado", "titulo": "Comprado — Aveiro → Lisboa", "corpo": "Carruagem 21, lugar 53", "dados": {"link": "pulse://bilhetes"}, "chave": "abcdef12"}


def registar(c, token=TOKEN):
    return c.post("/api/v1/devices", json={"token": token, "nome": "Telemóvel"}, headers={"X-Pulse-Client": "web"})


# --- dispositivos ---------------------------------------------------------------------------------------------------------------

def test_dispositivos_exigem_sessao_e_registo_e_idempotente(cliente):
    r1, r2 = registar(cliente), registar(cliente)
    assert r1.status_code == 201 and r1.json() == r2.json()
    cliente.cookies.clear()
    assert registar(cliente).status_code == 401


def test_token_invalido_e_recusado(cliente):
    for mau in ("curto", "com espaços " * 3, "x" * 5000):
        assert cliente.post("/api/v1/devices", json={"token": mau}, headers={"X-Pulse-Client": "web"}).status_code == 400


def test_remover_so_o_proprio(cliente, tmp_path):
    i = registar(cliente).json()["id"]
    assert cliente.delete(f"/api/v1/devices/{i}", headers={"X-Pulse-Client": "web"}).status_code == 200
    assert cliente.delete(f"/api/v1/devices/{i}", headers={"X-Pulse-Client": "web"}).status_code == 404


# --- entrada de eventos ---------------------------------------------------------------------------------------------------------

def test_evento_e_entregue_ao_dispositivo_do_dono(cliente, canal):
    registar(cliente)
    r = cliente.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO)
    assert r.status_code == 201 and r.json()["estado"] == "enviado" and r.json()["novo"] is True
    assert canal.enviados == [(TOKEN, "Comprado — Aveiro → Lisboa")]


def test_evento_repetido_com_a_mesma_chave_nao_reenvia(cliente, canal):
    registar(cliente)
    a = cliente.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO).json()
    b = cliente.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO).json()
    assert (b["id"], b["novo"], b["estado"]) == (a["id"], False, "enviado") and len(canal.enviados) == 1


def test_sem_dispositivo_fica_na_caixa_e_aparece_na_lista(cliente, canal):
    r = cliente.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO)
    assert r.json()["estado"] == "sem_canal" and canal.enviados == []
    j = cliente.get("/api/v1/notifications").json()
    assert j["naoLidas"] == 1 and j["eventos"][0]["titulo"].startswith("Comprado") and j["eventos"][0]["dados"] == {"link": "pulse://bilhetes"}
    assert cliente.get(f"/api/v1/notifications?desde={j['eventos'][0]['id']}").json()["eventos"] == []
    cliente.post("/api/v1/notifications/read", json={}, headers={"X-Pulse-Client": "web"})
    assert cliente.get("/api/v1/notifications").json()["naoLidas"] == 0


def test_sem_canais_configurados_guarda_como_sem_canal(tmp_path, dados_falso):
    app = montar(tmp_path, dados_falso, [])
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        k = app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        assert c.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO).json()["estado"] == "sem_canal"


def test_entrada_interna_exige_chave_loopback_direto_e_utilizador(cliente):
    post = lambda h, corpo=EVENTO: cliente.post("/api/v1/internal/events", json=corpo, headers=h).status_code
    assert post({}) == 401
    assert post({**SERVICO, "X-Pulse-Key": "x" * 40}) == 401
    assert post({**SERVICO, "X-Real-IP": "8.8.8.8"}) == 401              # veio pelo nginx = Internet: nunca
    assert post({**SERVICO, "X-Forwarded-For": "8.8.8.8"}) == 401
    assert post({**SERVICO, "X-Pulse-User": "ninguem@x.pt"}) == 403
    assert post(SERVICO, {**EVENTO, "extra": 1}) == 400
    assert post(SERVICO, {**EVENTO, "modulo": "Maiúsculas"}) == 400
    assert post(SERVICO, {**EVENTO, "dados": {"k": "v" * 2000}}) == 400


def test_chave_de_servico_curta_desliga_a_entrada(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SERVICE_KEY": "curta"})
    with TestClient(create_app(s, canais=[]), client=("127.0.0.1", 50000)) as c:
        assert c.post("/api/v1/internal/events", json=EVENTO, headers={"X-Pulse-Key": "curta", "X-Pulse-User": EMAIL}).status_code == 401


def test_so_o_dono_ve_os_eventos(cliente, tmp_path):
    cliente.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO)
    k = cliente.app.state.db(); accounts.criar_utilizador(k, "outra@x.pt", "1234qweR", must_change=False); k.close()
    cliente.cookies.clear()
    cliente.post("/api/v1/auth/login", json={"email": "outra@x.pt", "password": "1234qweR"})
    assert cliente.get("/api/v1/notifications").json() == {"eventos": [], "naoLidas": 0}


# --- despacho -------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-n.db"); db.migrate(c)
    accounts.criar_utilizador(c, EMAIL, "1234qweR", must_change=False)
    yield c
    c.close()


def _com_aparelho(conn, token=TOKEN):
    uid = conn.execute("SELECT id FROM pulse_users").fetchone()[0]
    conn.execute("INSERT INTO pulse_devices (user_id, fcm_token, criado, ultimo_uso) VALUES (?,?,1,1)", (uid, token))
    return uid


def test_token_desregistado_desativa_o_dispositivo(conn):
    uid = _com_aparelho(conn)
    def falha(_):
        raise Erro("UNREGISTERED", token_invalido=True)
    i, _ = notifications.guardar(conn, uid, "bilhetes", "x", "Título", chave="chave-001")
    notifications.despachar(conn, i, [CanalFalso(falha)])
    assert conn.execute("SELECT ativo FROM pulse_devices").fetchone()[0] == 0


def test_falha_temporaria_repete_ate_ao_limite_e_depois_da_erro(conn):
    uid = _com_aparelho(conn)
    def falha(_):
        raise Erro("503", temporario=True)
    canal = CanalFalso(falha)
    i, _ = notifications.guardar(conn, uid, "bilhetes", "x", "Título", chave="chave-002")
    estados = [notifications.despachar(conn, i, [canal]) for _ in range(notifications.MAX_TENTATIVAS)]
    assert estados == ["novo"] * (notifications.MAX_TENTATIVAS - 1) + ["erro"]
    canal.comportamento = None
    assert notifications.despachar(conn, i, [canal]) == "erro"          # um evento em erro não volta a ser tentado sozinho


def test_pendentes_sao_repetidos_quando_o_canal_recupera(conn):
    uid = _com_aparelho(conn)
    canal = CanalFalso(lambda _: (_ for _ in ()).throw(Erro("x", temporario=True)))
    i, _ = notifications.guardar(conn, uid, "bilhetes", "x", "Título", chave="chave-003")
    assert notifications.despachar(conn, i, [canal]) == "novo"
    canal.comportamento = None
    assert notifications.repetir_pendentes(conn, [canal]) == 1
    assert conn.execute("SELECT estado FROM pulse_events WHERE id=?", (i,)).fetchone()[0] == "enviado" and len(canal.enviados) == 1


# --- FCM (transporte simulado) --------------------------------------------------------------------------------------------------

class GoogleFalso:
    def __init__(self):
        self.pedidos, self.respostas = [], {}

    def __call__(self, metodo, url, cab, corpo):
        self.pedidos.append((metodo, url, cab, corpo))
        if "oauth2" in url:
            return 200, json.dumps({"access_token": "AT", "expires_in": 3600}).encode()
        return self.respostas.get("fcm", (200, b'{"name":"m"}'))


@pytest.fixture
def fcm(monkeypatch):
    g = GoogleFalso()
    monkeypatch.setattr(FcmCanal, "_assinar", lambda self, m: b"assinatura")
    c = FcmCanal({"client_email": "sa@p.iam", "private_key": "x", "project_id": "proj"}, transporte=g, agora=lambda: 1000.0)
    return c, g


EV = Evento(7, "bilhetes", "bilhetes.comprado", "Título", "Corpo", {"link": "pulse://bilhetes"})


def test_fcm_troca_o_jwt_e_envia_com_prioridade_alta(fcm):
    canal, g = fcm
    canal.enviar(TOKEN, EV); canal.enviar(TOKEN, EV)
    oauth = [p for p in g.pedidos if "oauth2" in p[1]]
    assert len(oauth) == 1                                           # o access token fica em memória
    form = parse_qs(oauth[0][3].decode())
    jwt = form["assertion"][0].split(".")
    assert json.loads(__import__("base64").urlsafe_b64decode(jwt[1] + "==")) == {"iss": "sa@p.iam", "scope": notifications.FCM_SCOPE, "aud": "https://oauth2.googleapis.com/token", "iat": 1000, "exp": 4600}
    envio = [p for p in g.pedidos if "fcm.googleapis" in p[1]][0]
    assert envio[1] == "https://fcm.googleapis.com/v1/projects/proj/messages:send" and envio[2]["Authorization"] == "Bearer AT"
    m = json.loads(envio[3])["message"]
    assert m["token"] == TOKEN and m["android"]["priority"] == "HIGH" and m["notification"] == {"title": "Título", "body": "Corpo"}
    assert m["data"] == {"link": "pulse://bilhetes", "evento": "7", "modulo": "bilhetes", "tipo": "bilhetes.comprado", "titulo": "Título", "corpo": "Corpo"}


def test_fcm_so_dados_para_a_app_desenhar_o_aviso(fcm):
    canal, g = fcm
    canal.so_dados = True
    canal.enviar(TOKEN, Evento(8, "tarefas", "tarefas.inst", "Lixo", "Bruno: é a vez", {"instancia": "I1", "link": "pulse://tarefas/hoje"}))
    m = json.loads([p for p in g.pedidos if "fcm.googleapis" in p[1]][-1][3])["message"]
    assert "notification" not in m and m["android"]["priority"] == "HIGH"
    assert m["data"]["instancia"] == "I1" and m["data"]["titulo"] == "Lixo" and m["data"]["corpo"] == "Bruno: é a vez"


def test_fcm_classifica_os_erros(fcm):
    canal, g = fcm
    g.respostas["fcm"] = (404, json.dumps({"error": {"status": "NOT_FOUND"}}).encode())
    with pytest.raises(Erro) as e:
        canal.enviar(TOKEN, EV)
    assert e.value.token_invalido
    g.respostas["fcm"] = (503, b"{}")
    with pytest.raises(Erro) as e:
        canal.enviar(TOKEN, EV)
    assert e.value.temporario and not e.value.token_invalido
    g.respostas["fcm"] = (400, json.dumps({"error": {"status": "INVALID_ARGUMENT"}}).encode())
    with pytest.raises(Erro) as e:
        canal.enviar(TOKEN, EV)
    assert not e.value.temporario and not e.value.token_invalido


def test_fcm_exige_credenciais_completas():
    with pytest.raises(ValueError):
        FcmCanal({"client_email": "a"})


def test_arranque_sem_credenciais_validas_nao_liga_fcm(tmp_path, dados_falso):
    (tmp_path / "sa.json").write_text("{}")
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_FCM_CREDENTIALS": str(tmp_path / "sa.json")})
    assert create_app(s).state.canais == []
    s2 = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_FCM_CREDENTIALS": str(tmp_path / "nao-existe.json")})
    assert create_app(s2).state.canais == []


def test_cliente_que_nao_e_loopback_e_recusado(tmp_path, dados_falso):
    with TestClient(montar(tmp_path, dados_falso, [CanalFalso()]), client=("203.0.113.5", 50000)) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        assert c.post("/api/v1/internal/events", json=EVENTO, headers=SERVICO).status_code == 401


# --- agendamento (o FCM não agenda: o Pulse espera) ------------------------------------------------------------------------------

def test_evento_agendado_nao_sai_nem_aparece_ate_chegar_a_hora(cliente, canal):
    import time
    registar(cliente)
    quando = int(time.time()) + 3600
    r = cliente.post("/api/v1/internal/events", json={**EVENTO, "chave": "agendado1", "entregarEm": quando}, headers=SERVICO).json()
    assert r["estado"] == "agendado" and canal.enviados == []
    assert cliente.get("/api/v1/notifications").json() == {"eventos": [], "naoLidas": 0}
    k = cliente.app.state.db()
    assert notifications.despachar_vencidos(k, [canal], agora=quando - 1) == 0 and canal.enviados == []
    assert notifications.despachar_vencidos(k, [canal], agora=quando + 1) == 1
    assert canal.enviados == [(TOKEN, "Comprado — Aveiro → Lisboa")]
    assert notifications.despachar_vencidos(k, [canal], agora=quando + 2) == 0          # não volta a sair
    k.close()
    assert cliente.get("/api/v1/notifications").json()["eventos"][0]["estado"] == "enviado"


def test_hora_no_passado_entrega_logo(cliente, canal):
    registar(cliente)
    r = cliente.post("/api/v1/internal/events", json={**EVENTO, "chave": "passado01", "entregarEm": 1000}, headers=SERVICO).json()
    assert r["estado"] == "enviado" and len(canal.enviados) == 1


def test_agendador_de_fundo_entrega_sozinho(tmp_path, dados_falso):
    import time
    canal = CanalFalso()
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": CHAVE, "PULSE_WEB_BASE_PATH": "/", "PULSE_SCHEDULER_S": "1"})
    with TestClient(create_app(s, canais=[canal]), client=("127.0.0.1", 50000)) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"}); registar(c)
        c.post("/api/v1/internal/events", json={**EVENTO, "chave": "fundo0001", "entregarEm": int(time.time()) + 1}, headers=SERVICO)
        for _ in range(60):
            if canal.enviados:
                break
            time.sleep(0.1)
    assert len(canal.enviados) == 1


def test_fcm_assina_o_jwt_com_rsa_de_verdade():
    """Sem simular a assinatura: gera uma chave RSA, deixa o canal assinar e verifica a assinatura com a chave pública."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    g = GoogleFalso()
    canal = FcmCanal({"client_email": "sa@p.iam", "private_key": pem, "project_id": "proj"}, transporte=g, agora=lambda: 1000.0)
    canal.enviar(TOKEN, EV)
    jwt = parse_qs(next(p for p in g.pedidos if "oauth2" in p[1])[3].decode())["assertion"][0]
    cab, pl, sig = jwt.split(".")
    dec = lambda b: __import__("base64").urlsafe_b64decode(b + "=" * (-len(b) % 4))
    chave.public_key().verify(dec(sig), f"{cab}.{pl}".encode(), padding.PKCS1v15(), hashes.SHA256())        # levanta se a assinatura for inválida
    assert json.loads(dec(cab)) == {"alg": "RS256", "typ": "JWT"}


def test_notificacao_de_teste(cliente, canal):
    assert cliente.post("/api/v1/notifications/test", headers={"X-Pulse-Client": "web"}).json()["erro"]["codigo"] == "sem_dispositivo"
    registar(cliente)
    r = cliente.post("/api/v1/notifications/test", headers={"X-Pulse-Client": "web"})
    assert r.status_code == 200 and r.json()["estado"] == "enviado" and r.json()["dispositivos"] == 1
    assert canal.enviados == [(TOKEN, "Notificação de teste")]


def test_cancelar_aviso_agendado_so_enquanto_agendado(cliente, canal):
    registar(cliente)
    futuro = int(time.time()) + 3600
    r = cliente.post("/api/v1/internal/events", json={**EVENTO, "chave": "tar-agendado-1", "entregarEm": futuro}, headers=SERVICO)
    assert r.json()["estado"] == "agendado"
    assert cliente.delete("/api/v1/internal/events/tar-agendado-1", headers=SERVICO).json() == {"cancelado": True}
    assert cliente.delete("/api/v1/internal/events/tar-agendado-1", headers=SERVICO).json() == {"cancelado": False}      # repetir é inofensivo
    cliente.post("/api/v1/internal/events", json={**EVENTO, "chave": "tar-enviado-01"}, headers=SERVICO)                  # este sai já
    assert cliente.delete("/api/v1/internal/events/tar-enviado-01", headers=SERVICO).json() == {"cancelado": False}      # enviado: não se toca
    assert cliente.delete("/api/v1/internal/events/tar-agendado-1").status_code == 401                                  # exige a chave de serviço


def test_contar_dispositivos_ativos_para_a_pausa_do_ntfy(cliente):
    assert cliente.get("/api/v1/internal/devices/count", headers=SERVICO).json() == {"ativos": 0}
    registar(cliente)
    assert cliente.get("/api/v1/internal/devices/count", headers=SERVICO).json() == {"ativos": 1}
    assert cliente.get("/api/v1/internal/devices/count").status_code == 401                       # exige a chave de serviço
