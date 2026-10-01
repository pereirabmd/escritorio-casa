import base64
import json
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from pulse import accounts, actions, config, db
from pulse import google_api as g
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import calendario, contas_google, correio
from tests.conftest import FalsoDados

TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=TZ)
BRUNO, CAMILA = "pereirabmd@gmail.com", "camila@exemplo.pt"
H = {"X-Pulse-Client": "web"}
CFG = g.GoogleConfig("cid.apps.googleusercontent.com", "segredo", "https://exemplo.pt/pulse/api/v1/google/callback", Fernet.generate_key().decode())


class GoogleFalso:
    """Imita a Google: `rotas[(metodo, caminho sem query)]` = (status, corpo) ou função `(query, corpo_json|form) -> (status, corpo)`."""

    def __init__(self):
        self.rotas, self.chamadas, self.n_tokens = {}, [], 0
        self.rotas[("POST", g.TOKEN_URL)] = self._token
        self.rotas[("POST", g.REVOKE_URL)] = (200, {})

    def _token(self, query, form):
        if form.get("grant_type") == "refresh_token":
            self.n_tokens += 1
            if form["refresh_token"].startswith("morto"):
                return 400, {"error": "invalid_grant"}
            return 200, {"access_token": f"at-{self.n_tokens}", "expires_in": 3600}
        return self.rotas.get("codigo", (400, {"error": "invalid_grant"})) if not callable(self.rotas.get("codigo")) else self.rotas["codigo"](query, form)

    def __call__(self, metodo, url, cab, corpo):
        caminho, _, qs = url.partition("?")
        query = {k: v if len(v) > 1 else v[0] for k, v in parse_qs(qs).items()}
        dados = None
        if corpo:
            dados = dict((k, v[0]) for k, v in parse_qs(corpo.decode()).items()) if cab.get("Content-Type", "").startswith("application/x-www-form") else json.loads(corpo)
        self.chamadas.append((metodo, caminho, query, dados, cab.get("Authorization", "")))
        r = self.rotas.get((metodo, caminho))
        if r is None:
            return 404, json.dumps({"error": {"message": f"sem rota {metodo} {caminho}"}}).encode()
        status, obj = r(query, dados) if callable(r) else r
        return status, json.dumps(obj).encode() if obj is not None else b""

    def chamadas_a(self, metodo, sufixo):
        return [c for c in self.chamadas if c[0] == metodo and c[1].endswith(sufixo)]


@pytest.fixture
def fake():
    return GoogleFalso()


@pytest.fixture
def api(fake):
    return g.GoogleApi(CFG, g.criar_cofre(CFG.chave), fake, agora=lambda: 1000.0)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-g.db"); db.migrate(c)
    c.execute("PRAGMA foreign_keys=ON")
    yield c
    c.close()


UID = {}


@pytest.fixture(autouse=True)
def utilizadores(conn):
    UID.clear()
    for e in (BRUNO, CAMILA):
        UID[e] = accounts.criar_utilizador(conn, e, "1234qweR", must_change=False)


def ligar(conn, api, uid, email, servicos="gmail,calendar", refresh=None, estado="ok"):
    return conn.execute("INSERT INTO google_accounts (user_id, email, nome, refresh_token, servicos, estado, criado, atualizado) VALUES (?,?,?,?,?,?,1,1)",
                        (uid, email, email.split("@")[0], api.cofre.cifrar(refresh or f"refresh-{email}"), servicos, estado)).lastrowid


# --- OAuth ----------------------------------------------------------------------------------------------------------------------

def test_url_de_autorizacao_tem_pkce_offline_state_e_so_os_scopes_pedidos(conn, api):
    url = contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], agora=100)
    q = parse_qs(urlparse(url).query)
    assert url.startswith(g.AUTH_URL) and q["client_id"] == [CFG.client_id] and q["redirect_uri"] == [CFG.redirect_uri]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["select_account consent"] and q["code_challenge_method"] == ["S256"]
    assert "login_hint" not in q          # nada de pré-selecionar a conta do Pulse: senão não se consegue ligar outra conta Google
    assert set(q["scope"][0].split()) == {"openid", "email", "profile", "https://www.googleapis.com/auth/gmail.modify"}      # sem Calendar
    r = conn.execute("SELECT * FROM google_oauth_states").fetchone()
    assert q["state"] == [r["state"]] and r["user_id"] == UID[BRUNO] and len(r["code_verifier"]) >= 43
    import hashlib
    assert q["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(r["code_verifier"].encode()).digest()).rstrip(b"=").decode()]


def test_servicos_invalidos(conn, api):
    for mau in ([], ["drive"], ["gmail", "x"]):
        with pytest.raises(ContaErro) as e:
            contas_google.iniciar(conn, api, UID[BRUNO], mau)
        assert e.value.codigo == "servicos_invalidos"


def _codigo(fake, scope, refresh="refresh-novo", email="ele@gmail.com"):
    fake.rotas["codigo"] = lambda q, f: (200, {"access_token": "at-x", "refresh_token": refresh, "scope": scope, "expires_in": 3600} if refresh else
                                        {"access_token": "at-x", "scope": scope, "expires_in": 3600})
    fake.rotas[("GET", g.USERINFO_URL)] = (200, {"email": email, "name": "Ele"})


GMAIL, CAL = "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly"


def test_concluir_guarda_a_conta_com_o_refresh_cifrado_e_usa_o_verificador(conn, api, fake):
    url = contas_google.iniciar(conn, api, UID[BRUNO], ["gmail", "calendar"], "", 100)
    state = parse_qs(urlparse(url).query)["state"][0]
    verificador = conn.execute("SELECT code_verifier FROM google_oauth_states").fetchone()[0]
    _codigo(fake, f"openid email profile {GMAIL} {CAL}")
    r = contas_google.concluir(conn, api, state, "codigo-123", 200)
    assert (r["email"], r["servicos"], r["user_id"]) == ("ele@gmail.com", ["gmail", "calendar"], UID[BRUNO])
    troca = fake.chamadas_a("POST", "/token")[0][3]
    assert troca["code"] == "codigo-123" and troca["code_verifier"] == verificador and troca["grant_type"] == "authorization_code"
    guardado = conn.execute("SELECT refresh_token FROM google_accounts").fetchone()[0]
    assert guardado != "refresh-novo" and "refresh-novo" not in guardado and api.cofre.decifrar(guardado) == "refresh-novo"        # cifrado em repouso
    assert contas_google.listar(conn, UID[BRUNO]) == [{"id": r["conta"], "email": "ele@gmail.com", "nome": "Ele", "servicos": ["gmail", "calendar"], "estado": "ok"}]
    assert "refresh" not in json.dumps(contas_google.listar(conn, UID[BRUNO]))                                                       # nunca sai
    assert contas_google.listar(conn, UID[CAMILA]) == []


def test_o_state_so_serve_uma_vez_e_expira(conn, api, fake):
    _codigo(fake, f"openid {GMAIL}")
    s1 = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 100)).query)["state"][0]
    contas_google.concluir(conn, api, s1, "c", 150)
    with pytest.raises(ContaErro) as e:
        contas_google.concluir(conn, api, s1, "c", 151)
    assert e.value.codigo == "estado_invalido"
    s2 = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 100)).query)["state"][0]
    with pytest.raises(ContaErro):
        contas_google.concluir(conn, api, s2, "c", 100 + g.ESTADO_TTL_S + 1)
    with pytest.raises(ContaErro):
        contas_google.concluir(conn, api, "inventado" * 4, "c", 100)


def test_permissoes_parciais_e_sem_permissoes(conn, api, fake):
    _codigo(fake, f"openid {GMAIL}")                                                            # pediu os dois; só concedeu o Gmail
    s = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail", "calendar"], "", 1)).query)["state"][0]
    assert contas_google.concluir(conn, api, s, "c", 2)["servicos"] == ["gmail"]
    _codigo(fake, "openid email", email="outra@gmail.com")
    s = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 1)).query)["state"][0]
    with pytest.raises(ContaErro) as e:
        contas_google.concluir(conn, api, s, "c", 2)
    assert e.value.codigo == "sem_permissoes"


def test_sem_refresh_token_falha_a_menos_que_a_conta_ja_exista(conn, api, fake):
    _codigo(fake, f"openid {GMAIL}", refresh=None)
    s = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 1)).query)["state"][0]
    with pytest.raises(ContaErro) as e:
        contas_google.concluir(conn, api, s, "c", 2)
    assert e.value.codigo == "sem_refresh_token"
    ligar(conn, api, UID[BRUNO], "ele@gmail.com", "gmail", "guardado", "reautorizar")
    s = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 1)).query)["state"][0]
    contas_google.concluir(conn, api, s, "c", 2)                                                # religa: mantém o token e volta a «ok»
    r = conn.execute("SELECT * FROM google_accounts").fetchone()
    assert api.cofre.decifrar(r["refresh_token"]) == "guardado" and r["estado"] == "ok"


def test_a_google_recusa_o_codigo(conn, api, fake):
    s = parse_qs(urlparse(contas_google.iniciar(conn, api, UID[BRUNO], ["gmail"], "", 1)).query)["state"][0]
    with pytest.raises(ContaErro) as e:
        contas_google.concluir(conn, api, s, "mau", 2)
    assert e.value.codigo == "google_recusou" and conn.execute("SELECT COUNT(*) FROM google_accounts").fetchone()[0] == 0


def test_remover_revoga_e_apaga_e_so_a_propria(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    with pytest.raises(ContaErro) as e:
        contas_google.remover(conn, api, UID[CAMILA], c)
    assert e.value.status == 404
    contas_google.remover(conn, api, UID[BRUNO], c)
    assert fake.chamadas_a("POST", "/revoke")[0][3]["token"] == "refresh-ele@gmail.com" and contas_google.listar(conn, UID[BRUNO]) == []


def test_refresh_token_e_reutilizado_e_invalid_grant_pede_reautorizar(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    cifrado = conn.execute("SELECT refresh_token FROM google_accounts").fetchone()[0]
    a1, a2 = api.access_token(c, cifrado), api.access_token(c, cifrado)
    assert a1 == a2 and fake.n_tokens == 1                                                       # guarda o access token em memória
    morta = ligar(conn, api, UID[BRUNO], "morta@gmail.com", refresh="morto")
    with pytest.raises(g.GoogleErro) as e:
        api.access_token(morta, api.cofre.cifrar("morto"))
    assert e.value.reautorizar


def test_um_401_renova_o_acesso_uma_vez(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    cifrado = conn.execute("SELECT refresh_token FROM google_accounts").fetchone()[0]
    respostas = iter([(401, {"error": {"message": "expirado"}}), (200, {"ok": True})])
    fake.rotas[("GET", "https://exemplo/x")] = lambda q, b: next(respostas)
    assert api.pedir(c, cifrado, "GET", "https://exemplo/x")[1] == {"ok": True} and fake.n_tokens == 2
    fake.rotas[("GET", "https://exemplo/y")] = (401, {"error": {"message": "revogado"}})
    with pytest.raises(g.GoogleErro) as e:
        api.pedir(c, cifrado, "GET", "https://exemplo/y")
    assert e.value.reautorizar


# --- Calendar -------------------------------------------------------------------------------------------------------------------

def cal_lista(fake, itens):
    fake.rotas[("GET", f"{g.CALENDAR}/users/me/calendarList")] = (200, {"items": itens})


PRINCIPAL = {"id": "ele@gmail.com", "summary": "Ele", "primary": True, "selected": True, "accessRole": "owner", "backgroundColor": "#039be5"}
FERIAS = {"id": "familia@group", "summary": "Família", "selected": True, "accessRole": "reader", "backgroundColor": "#7986cb"}
ESCONDIDO = {"id": "esc@group", "summary": "Escondido", "selected": False, "accessRole": "owner"}


@pytest.fixture(autouse=True)
def limpar_cache():
    calendario._calendarios_cache.clear()


def eventos(fake, cal, itens, status=200):
    fake.rotas[("GET", f"{g.CALENDAR}/calendars/{cal.replace('@', '%40')}/events")] = (status, {"items": itens})


def test_agenda_normaliza_dia_inteiro_varios_dias_fusos_cancelados_e_recusados(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    cal_lista(fake, [PRINCIPAL, ESCONDIDO])
    eventos(fake, "ele@gmail.com", [
        {"id": "a", "summary": "Reunião", "start": {"dateTime": "2026-09-30T09:00:00+01:00"}, "end": {"dateTime": "2026-09-30T10:30:00+01:00"}, "location": "Sala 1"},
        {"id": "b", "summary": "Feriado", "start": {"date": "2026-10-05"}, "end": {"date": "2026-10-06"}},
        {"id": "c", "summary": "Férias", "start": {"date": "2026-09-30"}, "end": {"date": "2026-10-03"}},                        # 30/09, 01/10, 02/10 (o fim é exclusivo)
        {"id": "d", "summary": "UTC", "start": {"dateTime": "2026-10-01T22:30:00Z"}, "end": {"dateTime": "2026-10-01T23:30:00Z"}},   # 23:30-00:30 em Lisboa
        {"id": "e", "summary": "Cancelado", "status": "cancelled", "start": {"date": "2026-09-30"}, "end": {"date": "2026-10-01"}},
        {"id": "f", "summary": "Recusado", "start": {"dateTime": "2026-09-30T12:00:00+01:00"}, "end": {"dateTime": "2026-09-30T13:00:00+01:00"}, "attendees": [{"self": True, "responseStatus": "declined"}]},
        {"id": "g", "start": {"dateTime": "2026-09-30T08:00:00+01:00"}, "end": {"dateTime": "2026-09-30T08:15:00+01:00"}},
        {"id": "h", "summary": "Meia-noite", "start": {"dateTime": "2026-09-30T22:00:00+01:00"}, "end": {"dateTime": "2026-10-01T00:00:00+01:00"}}])
    r = calendario.agenda(api, contas_google.com_servico(conn, UID[BRUNO], "calendar"), date(2026, 9, 30), date(2026, 10, 5), TZ)
    por_dia = {d["data"]: [(e["id"], e["inicio"], e["fim"]) for e in d["eventos"]] for d in r["dias"]}
    assert por_dia["2026-09-30"] == [("c", None, None), ("g", "08:00", "08:15"), ("a", "09:00", "10:30"), ("h", "22:00", "00:00")]     # dia inteiro primeiro; o de meia-noite não passa para 01/10
    assert [i for i, _, _ in por_dia["2026-10-01"]] == ["c", "d"] and por_dia["2026-10-01"][1][1:] == ("23:30", "00:30")
    assert [i for i, _, _ in por_dia["2026-10-02"]] == ["c", "d"] and por_dia["2026-10-03"] == []                     # o «UTC» acaba às 00:30 do dia 2 and [i for i, _, _ in por_dia["2026-10-05"]] == ["b"]
    a = next(e for d in r["dias"] for e in d["eventos"] if e["id"] == "a")
    assert (a["titulo"], a["local"], a["calendarioNome"], a["cor"], a["podeEditar"], a["diaInteiro"]) == ("Reunião", "Sala 1", "Ele", "#039be5", True, False)
    g_ = next(e for d in r["dias"] for e in d["eventos"] if e["id"] == "g")
    assert g_["titulo"] == "(sem título)"
    assert next(e for d in r["dias"] for e in d["eventos"] if e["id"] == "c")["dataFim"] == "2026-10-02"
    assert [x["nome"] for x in r["calendarios"]] == ["Ele"] and r["contas"] == [{"id": c, "email": "ele@gmail.com", "estado": "ok"}]        # o calendário desmarcado não entra


def test_agenda_junta_contas_e_uma_que_falha_nao_derruba_as_outras(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    ligar(conn, api, UID[BRUNO], "morta@gmail.com", refresh="morto")
    ligar(conn, api, UID[BRUNO], "reauth@gmail.com", estado="reautorizar")
    cal_lista(fake, [PRINCIPAL])
    eventos(fake, "ele@gmail.com", [{"id": "a", "summary": "Boa", "start": {"date": "2026-09-30"}, "end": {"date": "2026-10-01"}}])
    r = calendario.agenda(api, contas_google.com_servico(conn, UID[BRUNO], "calendar"), date(2026, 9, 30), date(2026, 9, 30), TZ)
    assert [e["titulo"] for e in r["dias"][0]["eventos"]] == ["Boa"]
    est = {c["email"]: c["estado"] for c in r["contas"]}
    assert est == {"ele@gmail.com": "ok", "morta@gmail.com": "reautorizar", "reauth@gmail.com": "reautorizar"}


def test_agenda_intervalo_invalido(conn, api):
    for de, ate in ((date(2026, 10, 2), date(2026, 10, 1)), (date(2026, 1, 1), date(2026, 12, 31))):
        with pytest.raises(ContaErro) as e:
            calendario.agenda(api, [], de, ate, TZ)
        assert e.value.codigo == "intervalo_invalido"


def test_hoje_limita_e_conta(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    cal_lista(fake, [PRINCIPAL])
    eventos(fake, "ele@gmail.com", [{"id": str(i), "summary": f"E{i}", "start": {"dateTime": f"2026-09-30T{8 + i:02d}:00:00+01:00"}, "end": {"dateTime": f"2026-09-30T{9 + i:02d}:00:00+01:00"}} for i in range(7)])
    h = calendario.hoje(api, contas_google.com_servico(conn, UID[BRUNO], "calendar"), date(2026, 9, 30), TZ, agora=datetime(2026, 9, 30, 0, 0, tzinfo=TZ))
    assert h["total"] == 7 and len(h["eventos"]) == 5 and h["eventos"][0]["titulo"] == "E0" and h["comProblemas"] == []
    assert fake.chamadas_a("GET", "/events")[0][2]["timeMin"] == "2026-09-30T00:00:00+01:00" and fake.chamadas_a("GET", "/events")[0][2]["timeMax"] == "2026-10-14T00:00:00+01:00"


def test_hoje_proximos_sem_os_que_ja_acabaram_e_com_a_data(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    cal_lista(fake, [PRINCIPAL])
    eventos(fake, "ele@gmail.com", [
        {"id": "a", "summary": "Já acabou", "start": {"dateTime": "2026-09-30T08:00:00+01:00"}, "end": {"dateTime": "2026-09-30T09:00:00+01:00"}},
        {"id": "b", "summary": "Em curso", "start": {"dateTime": "2026-09-30T09:30:00+01:00"}, "end": {"dateTime": "2026-09-30T11:00:00+01:00"}},
        {"id": "c", "summary": "Viagem", "start": {"date": "2026-10-02"}, "end": {"date": "2026-10-05"}}])
    h = calendario.hoje(api, contas_google.com_servico(conn, UID[BRUNO], "calendar"), date(2026, 9, 30), TZ, agora=datetime(2026, 9, 30, 10, 0, tzinfo=TZ))
    assert [(e["titulo"], e["data"]) for e in h["eventos"]] == [("Em curso", "2026-09-30"), ("Viagem", "2026-10-02")]     # sem repetir a viagem nos dias seguintes


def test_criar_editar_apagar_evento(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    conta = contas_google.obter(conn, UID[BRUNO], c, "calendar")
    cal_lista(fake, [PRINCIPAL, FERIAS])
    base = f"{g.CALENDAR}/calendars/ele%40gmail.com/events"
    fake.rotas[("POST", base)] = lambda q, b: (200, {"id": "novo", "summary": b["summary"], "start": b["start"], "end": b["end"]})
    e = calendario.criar(api, conta, TZ, "primary", "  Dentista ", date(2026, 10, 2), None, "15:00", "16:00", "Aveiro", None)
    corpo = fake.chamadas_a("POST", "/events")[0][3]
    assert corpo == {"summary": "Dentista", "location": "Aveiro", "start": {"dateTime": "2026-10-02T15:00:00", "timeZone": "Europe/Lisbon"}, "end": {"dateTime": "2026-10-02T16:00:00", "timeZone": "Europe/Lisbon"}}
    assert (e["id"], e["inicio"], e["fim"]) == ("novo", "15:00", "16:00")
    calendario.criar(api, conta, TZ, "primary", "Viagem", date(2026, 10, 2), date(2026, 10, 4), None, None, None, None)
    assert fake.chamadas_a("POST", "/events")[1][3]["start"] == {"date": "2026-10-02"} and fake.chamadas_a("POST", "/events")[1][3]["end"] == {"date": "2026-10-05"}   # fim exclusivo
    for mau in (dict(inicio="15:00", fim=None), dict(inicio="16:00", fim="15:00"), dict(data_fim=date(2026, 10, 1))):
        with pytest.raises(ContaErro):
            args = dict(data_fim=None, inicio=None, fim=None); args.update(mau)
            calendario.criar(api, conta, TZ, "primary", "X", date(2026, 10, 2), args["data_fim"], args["inicio"], args["fim"], None, None)
    with pytest.raises(ContaErro) as e:
        calendario.criar(api, conta, TZ, "familia@group", "X", date(2026, 10, 2), None, None, None, None, None)
    assert e.value.codigo == "calendario_so_leitura"
    with pytest.raises(ContaErro) as e:
        calendario.criar(api, conta, TZ, "nao-existe", "X", date(2026, 10, 2), None, None, None, None, None)
    assert e.value.status == 404
    fake.rotas[("PATCH", f"{base}/ev1")] = lambda q, b: (200, {"id": "ev1", "summary": b.get("summary", "?"), "start": {"date": "2026-10-02"}, "end": {"date": "2026-10-03"}})
    calendario.editar(api, conta, TZ, "primary", "ev1", "Novo título", None, None, None, None, None, None)
    assert fake.chamadas_a("PATCH", "/ev1")[0][3] == {"summary": "Novo título"}                    # só o que mudou
    with pytest.raises(ContaErro):
        calendario.editar(api, conta, TZ, "primary", "ev1", None, None, None, None, None, None, None)
    fake.rotas[("GET", f"{base}/ev1")] = (200, {"id": "ev1", "summary": "Apagar", "start": {"date": "2026-10-02"}, "end": {"date": "2026-10-03"}})
    fake.rotas[("DELETE", f"{base}/ev1")] = (204, None)
    antes = calendario.apagar(api, conta, TZ, "primary", "ev1")
    assert antes["titulo"] == "Apagar" and fake.chamadas_a("DELETE", "/ev1")


# --- Gmail ----------------------------------------------------------------------------------------------------------------------

def msg(i, assunto, de="Ana <ana@x.pt>", labels=("INBOX", "UNREAD"), ms=1_790_000_000_000, snippet="olá &amp; adeus"):
    return {"id": i, "threadId": "t" + i, "labelIds": list(labels), "snippet": snippet, "internalDate": str(ms),
            "payload": {"headers": [{"name": "From", "value": de}, {"name": "Subject", "value": assunto}, {"name": "Date", "value": "x"}]}}


def caixa_falsa(fake, mensagens, q=None):
    fake.rotas[("GET", f"{g.GMAIL}/messages")] = lambda query, b: (200, {"messages": [{"id": m["id"]} for m in mensagens], "resultSizeEstimate": len(mensagens)})
    for m in mensagens:
        fake.rotas[("GET", f"{g.GMAIL}/messages/{m['id']}")] = (200, m)


def test_caixa_normaliza_cabecalhos_codificados_ordem_e_estado(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    assunto = "=?UTF-8?B?" + base64.b64encode("Reunião às 10h".encode()).decode() + "?="
    caixa_falsa(fake, [msg("m1", assunto, ms=1_790_000_000_000), msg("m2", "Recente", de="bob@y.pt", labels=("INBOX", "IMPORTANT", "STARRED"), ms=1_790_000_900_000)])
    r = correio.caixa(api, contas_google.com_servico(conn, UID[BRUNO], "gmail"), "importantes", TZ)
    assert [m["id"] for m in r["mensagens"]] == ["m2", "m1"]                                      # mais recente primeiro
    m1 = next(m for m in r["mensagens"] if m["id"] == "m1")
    assert (m1["assunto"], m1["de"], m1["deEmail"], m1["lida"], m1["estrela"], m1["resumo"]) == ("Reunião às 10h", "Ana", "ana@x.pt", False, False, "olá & adeus")
    m2 = next(m for m in r["mensagens"] if m["id"] == "m2")
    assert (m2["de"], m2["lida"], m2["estrela"], m2["importante"]) == ("bob@y.pt", True, True, True)
    assert fake.chamadas_a("GET", "/messages")[0][2]["q"] == "in:inbox is:important"
    with pytest.raises(ContaErro):
        correio.caixa(api, [], "tudo", TZ)


def test_caixa_junta_contas_e_falhas_de_mensagens_soltas_nao_estragam(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    ligar(conn, api, UID[BRUNO], "morta@gmail.com", refresh="morto")
    caixa_falsa(fake, [msg("m1", "Um")])
    fake.rotas[("GET", f"{g.GMAIL}/messages")] = lambda q, b: (200, {"messages": [{"id": "m1"}, {"id": "desaparecida"}], "resultSizeEstimate": 2})
    r = correio.caixa(api, contas_google.com_servico(conn, UID[BRUNO], "gmail"), "entrada", TZ)
    assert [m["id"] for m in r["mensagens"]] == ["m1"]
    assert r["mensagens"][0]["link"] == "https://mail.google.com/mail/u/ele@gmail.com/#all/m1"         # abre a mensagem certa, na conta certa
    assert {c["email"]: c["estado"] for c in r["contas"]} == {"ele@gmail.com": "ok", "morta@gmail.com": "reautorizar"}


def test_importantes_hoje_so_conta_as_por_ler(conn, api, fake):
    ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    caixa_falsa(fake, [msg("a", "A"), msg("b", "B", labels=("INBOX", "IMPORTANT")), msg("c", "C"), msg("d", "D"), msg("e", "E")])
    h = correio.importantes_hoje(api, contas_google.com_servico(conn, UID[BRUNO], "gmail"), TZ)
    assert h["porLer"] == 4 and len(h["mensagens"]) == 3 and all(not m["lida"] for m in h["mensagens"])


def b64(t):
    return base64.urlsafe_b64encode(t.encode()).rstrip(b"=").decode()


def test_detalhe_texto_simples_html_e_anexos(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    conta = contas_google.obter(conn, UID[BRUNO], c, "gmail")
    completo = msg("m1", "Assunto")
    completo["payload"]["mimeType"] = "multipart/mixed"
    completo["payload"]["parts"] = [
        {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/plain", "body": {"data": b64("Olá,\nisto é texto.")}}, {"mimeType": "text/html", "body": {"data": b64("<p>ignorado</p>")}}]},
        {"mimeType": "application/pdf", "filename": "fatura.pdf", "body": {"attachmentId": "x"}}]
    fake.rotas[("GET", f"{g.GMAIL}/messages/m1")] = (200, completo)
    d = correio.detalhe(api, conta, "m1", TZ)
    assert d["corpo"] == "Olá,\nisto é texto." and d["temAnexos"] is True and d["assunto"] == "Assunto"
    so_html = msg("m2", "H")
    so_html["payload"].update({"mimeType": "text/html", "body": {"data": b64("<style>x{}</style><script>alert(1)</script><div>Linha 1<br>Linha&nbsp;2 &amp; mais</div><p>Fim</p>")}})
    fake.rotas[("GET", f"{g.GMAIL}/messages/m2")] = (200, so_html)
    corpo = correio.detalhe(api, conta, "m2", TZ)["corpo"]
    assert "alert" not in corpo and "<" not in corpo and "Linha 1" in corpo and "& mais" in corpo
    enorme = msg("m3", "G")
    enorme["payload"].update({"mimeType": "text/plain", "body": {"data": b64("x" * 50000)}})
    fake.rotas[("GET", f"{g.GMAIL}/messages/m3")] = (200, enorme)
    assert len(correio.detalhe(api, conta, "m3", TZ)["corpo"]) == correio.MAX_CORPO


def test_organizar_muda_so_as_etiquetas_certas(conn, api, fake):
    c = ligar(conn, api, UID[BRUNO], "ele@gmail.com")
    conta = contas_google.obter(conn, UID[BRUNO], c, "gmail")
    fake.rotas[("POST", f"{g.GMAIL}/messages/m1/modify")] = lambda q, b: (200, {"id": "m1", "labelIds": ["INBOX"] if "UNREAD" in b["removeLabelIds"] else ["INBOX", "UNREAD"]})
    corpos = lambda: [x[3] for x in fake.chamadas_a("POST", "/modify")]
    assert correio.marcar_lida(api, conta, "m1", True, TZ)["lida"] is True
    correio.marcar_lida(api, conta, "m1", False, TZ); correio.arquivar(api, conta, "m1", True, TZ); correio.arquivar(api, conta, "m1", False, TZ)
    correio.estrela(api, conta, "m1", True, TZ); correio.estrela(api, conta, "m1", False, TZ)
    assert corpos() == [{"addLabelIds": [], "removeLabelIds": ["UNREAD"]}, {"addLabelIds": ["UNREAD"], "removeLabelIds": []},
                        {"addLabelIds": [], "removeLabelIds": ["INBOX"]}, {"addLabelIds": ["INBOX"], "removeLabelIds": []},
                        {"addLabelIds": ["STARRED"], "removeLabelIds": []}, {"addLabelIds": [], "removeLabelIds": ["STARRED"]}]
    assert not [c for c in fake.chamadas if c[1].endswith("/send") or c[0] == "DELETE"]           # nunca envia nem apaga


# --- API e ações ----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, dados_falso, fake):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SERVICE_KEY": FalsoDados.CHAVE,
                     "PULSE_WEB_BASE_PATH": "/", "PULSE_SCHEDULER_S": "0"})
    a = create_app(s, google=g.GoogleApi(CFG, g.criar_cofre(CFG.chave), fake, agora=lambda: 1000.0)); a.state.agora = lambda: AGORA
    with TestClient(a):
        k = a.state.db()
        accounts.criar_utilizador(k, BRUNO, "1234qweR", must_change=False, admin=True); accounts.criar_utilizador(k, CAMILA, "1234qweR", must_change=False)
        k.close()
        yield a


def entrar(app, email=BRUNO):
    c = TestClient(app, follow_redirects=False)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "1234qweR"}).status_code == 200
    return c


def ligar_via_api(app, email, servicos="gmail,calendar", refresh=None, estado="ok"):
    k = app.state.db()
    uid = k.execute("SELECT id FROM pulse_users WHERE email = ?", (email,)).fetchone()[0]
    r = ligar(k, app.state.google, uid, email.replace("@", "+g@"), servicos, refresh, estado)
    k.close()
    return r


def test_api_sem_configuracao_diz_que_esta_desligado(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SCHEDULER_S": "0", "PULSE_WEB_BASE_PATH": "/"})
    with TestClient(create_app(s)) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, BRUNO, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": BRUNO, "password": "1234qweR"})
        assert c.get("/api/v1/google/accounts").json() == {"configurado": False, "servicos": ["gmail", "calendar"], "contas": []}
        assert c.post("/api/v1/google/connect", json={"servicos": ["gmail"]}, headers=H).status_code == 503
        r = c.get("/api/v1/calendar?de=2026-09-30&ate=2026-09-30").json()
        assert r["ligado"] is False and r["configurado"] is False
        assert c.get("/api/v1/mail").json()["ligado"] is False


def test_api_ligar_callback_e_remover(app, fake):
    b = entrar(app)
    assert entrar(app, CAMILA).get("/api/v1/google/accounts").json()["contas"] == []
    url = b.post("/api/v1/google/connect", json={"servicos": ["gmail", "calendar"]}, headers=H).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    _codigo(fake, f"openid {GMAIL} {CAL}")
    r = b.get(f"/api/v1/google/callback?code=abc&state={state}")                                  # o Google regressa sem cabeçalho X-Pulse-Client
    assert r.status_code == 303 and r.headers["location"] == "/definicoes?google=ok"
    contas = b.get("/api/v1/google/accounts").json()["contas"]
    assert [(c["email"], c["servicos"]) for c in contas] == [("ele@gmail.com", ["gmail", "calendar"])]
    again = b.get(f"/api/v1/google/callback?code=abc&state={state}")
    assert again.headers["location"] == "/definicoes?google=erro&motivo=estado_invalido"    # o state só serve uma vez
    assert b.get("/api/v1/google/callback?error=access_denied&state=x").headers["location"].endswith("?google=erro&motivo=recusado")
    assert b.get("/api/v1/google/callback").headers["location"].endswith("?google=erro&motivo=invalido")
    assert entrar(app, CAMILA).delete(f"/api/v1/google/accounts/{contas[0]['id']}", headers=H).status_code == 404
    assert b.delete(f"/api/v1/google/accounts/{contas[0]['id']}", headers=H).status_code == 200
    assert b.get("/api/v1/google/accounts").json()["contas"] == []
    k = app.state.db()
    assert [tuple(r) for r in k.execute("SELECT acao FROM pulse_activity WHERE acao LIKE 'google.%' ORDER BY id")] == [("google.ligar",), ("google.remover",)]
    k.close()


def test_api_ligar_pelo_android_regressa_ao_link_da_app(app, fake):
    b = entrar(app)
    url = b.post("/api/v1/google/connect", json={"servicos": ["calendar"], "cliente": "android"}, headers=H).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    _codigo(fake, f"openid {CAL}")
    r = b.get(f"/api/v1/google/callback?code=abc&state={state}")
    assert r.status_code == 200 and "pulse://google?resultado=ok" in r.text                        # ponte sem scripts para a app
    assert [c["email"] for c in b.get("/api/v1/google/accounts").json()["contas"]] == ["ele@gmail.com"]
    depois = b.get(f"/api/v1/google/callback?code=abc&state={state}")                                # já gasto: o erro vai para a Web
    assert depois.status_code == 303 and depois.headers["location"].endswith("motivo=estado_invalido")
    url2 = b.post("/api/v1/google/connect", json={"servicos": ["calendar"], "cliente": "android"}, headers=H).json()["url"]
    recusado = b.get(f"/api/v1/google/callback?error=access_denied&state={parse_qs(urlparse(url2).query)['state'][0]}")
    assert "pulse://google?resultado=erro&amp;motivo=recusado" in recusado.text or "pulse://google?resultado=erro&motivo=recusado" in recusado.text
    assert b.post("/api/v1/google/connect", json={"servicos": ["calendar"], "cliente": "ios"}, headers=H).status_code in (400, 422)


def test_api_calendario_marca_a_conta_que_pede_reautorizacao(app, fake):
    b = entrar(app)
    ligar_via_api(app, BRUNO, "calendar", refresh="morto")
    r = b.get("/api/v1/calendar?de=2026-09-30&ate=2026-09-30").json()
    assert r["ligado"] is True and r["contas"][0]["estado"] == "reautorizar"
    assert b.get("/api/v1/google/accounts").json()["contas"][0]["estado"] == "reautorizar"          # ficou registado
    assert b.get("/api/v1/calendar?de=2026-09-30&ate=2026-12-31").status_code == 400
    assert b.get("/api/v1/calendar").status_code in (400, 422)


def test_api_email_lista_e_detalhe_so_da_propria_conta(app, fake):
    b = entrar(app)
    conta = ligar_via_api(app, BRUNO, "gmail")
    caixa_falsa(fake, [msg("m1", "Olá")])
    r = b.get("/api/v1/mail?filtro=por_ler").json()
    assert r["ligado"] is True and r["mensagens"][0]["assunto"] == "Olá"
    completo = msg("m1", "Olá"); completo["payload"].update({"mimeType": "text/plain", "body": {"data": b64("corpo")}})
    fake.rotas[("GET", f"{g.GMAIL}/messages/m1")] = (200, completo)
    assert b.get(f"/api/v1/mail/{conta}/m1").json()["corpo"] == "corpo"
    assert entrar(app, CAMILA).get(f"/api/v1/mail/{conta}/m1").status_code == 404                 # a conta é de outro utilizador
    assert b.get("/api/v1/mail?filtro=x").status_code in (400, 422)
    assert b.get("/api/v1/mail?conta=999").json()["ligado"] is False


def test_api_modulo_desativado_bloqueia_calendario_e_email(app):
    b = entrar(app)
    b.put("/api/v1/admin/modules", json={"modulos": {"calendario": False, "email": False}}, headers=H)
    for rota in ("/calendar?de=2026-09-30&ate=2026-09-30", "/mail"):
        r = b.get("/api/v1" + rota)
        assert (r.status_code, r.json()["erro"]["codigo"]) == (403, "modulo_desativado")


@pytest.fixture
def ctx_acao(app, fake):
    k = app.state.db()
    yield lambda email: actions.Contexto(DadosClient("http://x", "k"), email, AGORA, google=app.state.google), k
    k.close()


def correr(k, ctx, nome, params, **kw):
    return actions.executar(k, ctx, nome, params, **kw)


def test_acoes_de_calendario_e_email_em_nome_do_dono(app, fake, ctx_acao):
    c_bruno = ligar_via_api(app, BRUNO)
    mk, k = ctx_acao
    cal_lista(fake, [PRINCIPAL])
    base = f"{g.CALENDAR}/calendars/ele%40gmail.com/events"
    fake.rotas[("POST", base)] = lambda q, b: (200, {"id": "novo", "summary": b["summary"], "start": b["start"], "end": b["end"]})
    r = correro = correr(k, mk(BRUNO), "calendario.criar", {"conta": c_bruno, "titulo": "Dentista", "data": "2026-10-02", "inicio": "15:00", "fim": "16:00"})
    assert r["id"] == "novo" and fake.chamadas_a("POST", "/events")
    with pytest.raises(ContaErro) as e:                                                          # a conta do Bruno não é da Camila
        correr(k, mk(CAMILA), "calendario.criar", {"conta": c_bruno, "titulo": "X", "data": "2026-10-02"})
    assert e.value.status == 404
    with pytest.raises(ContaErro) as e:
        correr(k, mk(BRUNO), "calendario.apagar", {"conta": c_bruno, "evento": "novo"})
    assert e.value.codigo == "confirmacao_necessaria"
    fake.rotas[("POST", f"{g.GMAIL}/messages/mensagem1/modify")] = (200, {"id": "mensagem1", "labelIds": ["INBOX"]})
    assert correr(k, mk(BRUNO), "email.lida", {"conta": c_bruno, "mensagem": "mensagem1", "lida": True})["lida"] is True
    for mau in ({"conta": c_bruno, "mensagem": "x"}, {"conta": c_bruno, "mensagem": "mensagem1"}, {"conta": c_bruno, "mensagem": "a/b/c/d/e", "lida": True}):
        with pytest.raises(ContaErro) as e:
            correr(k, mk(BRUNO), "email.lida", mau)
        assert e.value.codigo == "parametros_invalidos"


def test_acao_com_reautorizacao_marca_a_conta_e_diz_porque(app, fake, ctx_acao):
    conta = ligar_via_api(app, BRUNO, refresh="morto")
    mk, k = ctx_acao
    with pytest.raises(ContaErro) as e:
        correr(k, mk(BRUNO), "email.estrela", {"conta": conta, "mensagem": "mensagem1", "estrela": True})
    assert (e.value.status, e.value.codigo) == (409, "reautorizar")
    assert k.execute("SELECT estado FROM google_accounts").fetchone()[0] == "reautorizar"
    assert [tuple(r) for r in k.execute("SELECT acao, resultado, detalhe FROM pulse_activity")] == [("email.estrela", "erro", "reautorizar")]


def test_acoes_sem_google_configurado_dizem_desligado(tmp_path, dados_falso):
    c = db.connect(tmp_path / "teste-x.db"); db.migrate(c)
    accounts.criar_utilizador(c, BRUNO, "1234qweR", must_change=False)
    with pytest.raises(ContaErro) as e:
        actions.executar(c, actions.Contexto(DadosClient("http://x", "k"), BRUNO, AGORA), "email.lida", {"conta": 1, "mensagem": "mensagem1", "lida": True})
    assert (e.value.status, e.value.codigo) == (503, "google_desligado")
    c.close()


def test_hoje_calendario_e_email(app, fake):
    b = entrar(app)
    FalsoDados.respostas = {}
    d = b.get("/api/v1/dashboard/today").json()["modulos"]
    assert d["calendario"] == {"estado": "nao_ligado", "dados": None} and d["email"] == {"estado": "nao_ligado", "dados": None}
    ligar_via_api(app, BRUNO)
    cal_lista(fake, [PRINCIPAL])
    eventos(fake, "ele@gmail.com", [{"id": "a", "summary": "Reunião", "start": {"dateTime": "2026-09-30T22:00:00+01:00"}, "end": {"dateTime": "2026-09-30T23:30:00+01:00"}}])
    caixa_falsa(fake, [msg("m1", "Urgente", labels=("INBOX", "IMPORTANT", "UNREAD"))])
    d = b.get("/api/v1/dashboard/today").json()["modulos"]
    assert d["calendario"]["estado"] == "ok" and d["calendario"]["dados"]["eventos"][0]["titulo"] == "Reunião" and d["calendario"]["dados"]["total"] == 1
    assert d["email"]["estado"] == "ok" and d["email"]["dados"]["porLer"] == 1 and d["email"]["dados"]["mensagens"][0]["assunto"] == "Urgente"
    b.put("/api/v1/admin/modules", json={"modulos": {"email": False}}, headers=H)
    assert b.get("/api/v1/dashboard/today").json()["modulos"]["email"] == {"estado": "desativado", "dados": None}


def test_hoje_com_conta_a_pedir_reautorizacao_avisa_no_cartao(app, fake):
    b = entrar(app)
    ligar_via_api(app, BRUNO, refresh="morto")
    d = b.get("/api/v1/dashboard/today").json()["modulos"]["calendario"]
    assert d["estado"] == "ok" and d["dados"]["eventos"] == [] and d["dados"]["comProblemas"][0]["estado"] == "reautorizar"


def test_configuracao_google_so_liga_com_tudo_e_com_chave_valida(tmp_path, dados_falso):
    base = {"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SCHEDULER_S": "0"}
    completo = {"PULSE_GOOGLE_CLIENT_ID": "a", "PULSE_GOOGLE_CLIENT_SECRET": "b", "PULSE_GOOGLE_REDIRECT_URI": "https://x/cb", "PULSE_GOOGLE_KEY": Fernet.generate_key().decode()}
    assert create_app(config.load({**base, **completo})).state.google is not None
    assert create_app(config.load(base)).state.google is None
    for falta in completo:
        assert create_app(config.load({**base, **{k: v for k, v in completo.items() if k != falta}})).state.google is None
    assert create_app(config.load({**base, **completo, "PULSE_GOOGLE_KEY": "chave-invalida"})).state.google is None


def test_hoje_serve_o_google_em_cache_velho_e_atualiza_em_segundo_plano(app, fake, monkeypatch):
    """Passado 1 min o Hoje não espera pelo Google: serve o que tem em cache (até 15 min) e atualiza para a próxima vez."""
    import time as _t
    from pulse.api.v1 import dashboard as dash
    b = entrar(app)
    ligar_via_api(app, BRUNO)
    cal_lista(fake, [PRINCIPAL])
    eventos(fake, "ele@gmail.com", [{"id": "a", "summary": "Reunião", "start": {"dateTime": "2026-09-30T22:00:00+01:00"}, "end": {"dateTime": "2026-09-30T23:30:00+01:00"}}])
    caixa_falsa(fake, [msg("m1", "Urgente", labels=("INBOX", "IMPORTANT", "UNREAD"))])
    assert b.get("/api/v1/dashboard/today").json()["modulos"]["calendario"]["dados"]["eventos"][0]["titulo"] == "Reunião"
    eventos(fake, "ele@gmail.com", [{"id": "b", "summary": "Dentista", "start": {"dateTime": "2026-09-30T22:00:00+01:00"}, "end": {"dateTime": "2026-09-30T23:30:00+01:00"}}])
    agora = _t.monotonic()
    monkeypatch.setattr(dash.time, "monotonic", lambda: agora + dash.CACHE_GOOGLE_S + 5)            # passou 1 min: a cache já é «velha», mas serve-se
    velho = b.get("/api/v1/dashboard/today").json()["modulos"]["calendario"]["dados"]["eventos"][0]["titulo"]
    assert velho == "Reunião"                                                                        # não esperou pelo Google
    for _ in range(100):                                                                              # a atualização corre em segundo plano
        if not app.state.google_a_refrescar:
            break
        _t.sleep(0.05)
    monkeypatch.setattr(dash.time, "monotonic", lambda: agora + dash.CACHE_GOOGLE_S + 6)
    assert b.get("/api/v1/dashboard/today").json()["modulos"]["calendario"]["dados"]["eventos"][0]["titulo"] == "Dentista"
