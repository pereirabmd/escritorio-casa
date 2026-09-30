from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, config, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import bilhetes_favoritos as fav
from tests.conftest import FalsoDados
from tests.test_bilhetes_module import DADOS, V

EMAIL, OUTRO = "pereirabmd@gmail.com", "camila@exemplo.pt"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
UID: dict[str, int] = {}                                    # e-mail -> id, preenchido pela fixture `conn`


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-f.db"); db.migrate(c)
    UID.clear(); UID.update({e: accounts.criar_utilizador(c, e, "1234qweR", must_change=False, admin=(e == EMAIL)) for e in (EMAIL, OUTRO)})
    yield c
    c.close()


def correr(conn, dados_falso, nome, params, email=EMAIL):
    return actions.executar(conn, actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), email, AGORA), nome, params, origem="ui")


def test_guardar_nao_duplica_atualiza_o_apelido_e_e_por_conta(conn):
    u, o = UID[EMAIL], UID[OUTRO]
    a = fav.guardar(conn, u, 520, "06:45", "Aveiro", "Lisboa Oriente")
    b = fav.guardar(conn, u, 520, "06:45", "Aveiro", "Lisboa Oriente", "Manhã")
    assert a["id"] == b["id"] and b["apelido"] == "Manhã" and len(fav.listar(conn, u)) == 1
    assert fav.guardar(conn, u, 520, "06:45", "Aveiro", "Lisboa Oriente")["apelido"] == "Manhã"      # sem apelido novo, o que havia mantém-se
    assert fav.listar(conn, o) == []
    with pytest.raises(ContaErro) as e:
        fav.apagar(conn, o, a["id"])                                                                 # o favorito de outra conta não existe
    assert e.value.codigo == "nao_encontrado"
    with pytest.raises(ContaErro):
        fav.guardar(conn, u, 520, "07:00", "Aveiro", "aveiro")
    fav.apagar(conn, u, a["id"])
    assert fav.listar(conn, u) == []


def test_acoes_guardar_e_apagar(conn, dados_falso):
    r = correr(conn, dados_falso, "bilhetes.favorito_guardar", {"comboio": 731, "hora": "17:30", "origem": "Lisboa Oriente", "destino": "Aveiro", "apelido": "Tarde"})
    assert r["apelido"] == "Tarde"
    assert correr(conn, dados_falso, "bilhetes.favorito_apagar", {"favorito": r["id"]})["comboio"] == 731
    assert fav.listar(conn, UID[EMAIL]) == []


def test_marcar_favorito_acrescenta_sem_apagar_as_outras_viagens_e_por_semana(conn, dados_falso):
    f = fav.guardar(conn, UID[EMAIL], 520, "07:00", "Aveiro", "Lisboa Oriente")
    FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)                      # semana de 05/10 já tem as viagens 6 (525, seg) e 7 (525, ter)
    FalsoDados.respostas["PUT /bilhetes/semana"] = (200, {"viagens": []})
    r = correr(conn, dados_falso, "bilhetes.marcar_favorito", {"favorito": f["id"], "datas": ["2026-10-07", "2026-10-08", "2026-10-13"]})
    assert r["marcadas"] == 3 and r["jaExistiam"] == 0
    puts = [e for e in FalsoDados.escritas if e[1] == "/bilhetes/semana"]
    assert [p[2]["inicio"] for p in puts] == ["2026-10-05", "2026-10-12"]
    primeira = {(v["data"], v["comboio"]) for v in puts[0][2]["viagens"]}
    assert primeira == {("2026-10-05", 525), ("2026-10-06", 525), ("2026-10-07", 520), ("2026-10-08", 520)}      # as que já lá estavam mantêm-se
    assert {(v["data"], v["comboio"]) for v in puts[1][2]["viagens"]} == {("2026-10-13", 520)}


def test_marcar_favorito_que_ja_existe_nao_repete(conn, dados_falso):
    f = fav.guardar(conn, UID[EMAIL], 525, "07:27", "Aveiro", "Lisboa Oriente")
    FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)
    r = correr(conn, dados_falso, "bilhetes.marcar_favorito", {"favorito": f["id"], "datas": ["2026-10-06"]})
    assert r["marcadas"] == 0 and r["jaExistiam"] == 1 and not [e for e in FalsoDados.escritas if e[0] == "PUT"]


def test_api_tickets_traz_favoritos_e_semeia_uma_so_vez(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app, headers={"X-Pulse-Client": "web"}) as c:
        k = app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False, admin=True); k.close()
        assert c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"}).status_code == 200
        FalsoDados.respostas["/bilhetes/dados"] = (200, DADOS)
        j = c.get("/api/v1/tickets").json()
        assert len(j["favoritos"]) > 0 and {"id", "apelido", "comboio", "hora", "origem", "destino"} <= set(j["favoritos"][0])
        c.post("/api/v1/actions/bilhetes.favorito_apagar", json={"params": {"favorito": j["favoritos"][0]["id"]}})
        assert len(c.get("/api/v1/tickets").json()["favoritos"]) == len(j["favoritos"]) - 1       # o que apagou não volta a aparecer
