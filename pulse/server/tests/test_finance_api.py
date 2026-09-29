from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from pulse.services import financas
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 15, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
CATS = [{"id": 1, "nome": "Casa", "cor": "#111111"}, {"id": 2, "nome": "Rendimentos", "cor": "#222222"}]


def L(i, tipo, valor, venc, pago=None, cat=1, mes=None):
    return {"id": i, "tipo": tipo, "descricao": f"d{i}", "valor": valor, "categoria_id": cat, "categoria": "Casa" if cat == 1 else "Rendimentos",
            "data_vencimento": venc, "data_pagamento": pago, "recorrente": False, "mes_referencia": mes or venc[:7]}


@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


def test_estado_derivado():
    hoje = AGORA.date()
    assert financas.estado(L(1, "despesa", 1, "2026-09-14"), hoje) == "vencido"
    assert financas.estado(L(1, "despesa", 1, "2026-09-15"), hoje) == "hoje"
    assert financas.estado(L(1, "despesa", 1, "2026-09-16"), hoje) == "pendente"
    assert financas.estado(L(1, "despesa", 1, "2026-09-01", pago="2026-09-02"), hoje) == "pago"


def test_janelas():
    hoje = AGORA.date()
    assert financas.janela("mes", "2026-02", hoje) == ("2026-02-01", "2026-02-28")
    assert financas.janela("30d", "2026-02", hoje) == ("2026-09-15", "2026-10-14")


def test_exige_sessao(cliente):
    cliente.cookies.clear()
    assert cliente.get("/api/v1/finance").status_code == 401


def test_visao_calcula_saldo_e_vencidas(cliente):
    FalsoDados.respostas["/financas/categorias"] = (200, {"categorias": CATS})
    do_mes = [L(1, "rendimento", 2000, "2026-09-26", cat=2), L(2, "despesa", 300, "2026-09-20"), L(3, "despesa", 100.5, "2026-09-05", pago="2026-09-05"),
              L(4, "despesa", 50, "2026-09-10")]
    FalsoDados.respostas["/financas/lancamentos?mes=2026-09"] = (200, {"lancamentos": do_mes})
    FalsoDados.respostas["/financas/lancamentos?de=2026-09-01&ate=2026-09-30"] = (200, {"lancamentos": do_mes})
    FalsoDados.respostas["/financas/lancamentos?pendentes=1&tipo=despesa&ate=2026-09-14"] = (200, {"lancamentos": [do_mes[3]]})
    r = cliente.get("/api/v1/finance?mes=2026-09")
    assert r.status_code == 200
    j = r.json()
    assert j["totaisMes"] == {"rendimento": 2000.0, "despesas": 450.5, "porPagar": 350.0}
    assert [x["id"] for x in j["lancamentos"]] == [3, 4, 2, 1] and {x["id"]: x["estado"] for x in j["lancamentos"]} == {1: "pendente", 2: "pendente", 3: "pago", 4: "vencido"}
    assert j["janela"] == {"modo": "mes", "de": "2026-09-01", "ate": "2026-09-30"}
    assert j["resumo"]["saldo"] == 1650.0 and j["resumo"]["porPagar"] == 350.0 and j["resumo"]["emAtraso"] == 0.0
    assert j["atrasadas"]["total"] == 50.0 and j["atrasadas"]["itens"][0]["estado"] == "vencido"
    assert j["resumo"]["porCategoria"][0]["nome"] == "Casa" and j["resumo"]["porCategoria"][0]["total"] == 450.5


def test_vencidas_antes_da_janela_entram_no_saldo_com_atraso(cliente):
    FalsoDados.respostas["/financas/categorias"] = (200, {"categorias": CATS})
    FalsoDados.respostas["/financas/lancamentos?mes=2026-10"] = (200, {"lancamentos": []})
    FalsoDados.respostas["/financas/lancamentos?de=2026-09-15&ate=2026-10-14"] = (200, {"lancamentos": [L(1, "rendimento", 1000, "2026-10-01", cat=2), L(2, "despesa", 300, "2026-09-20")]})
    FalsoDados.respostas["/financas/lancamentos?pendentes=1&tipo=despesa&ate=2026-09-14"] = (200, {"lancamentos": [L(9, "despesa", 200, "2026-08-30"), L(8, "despesa", 20, "2026-09-14")]})
    j = cliente.get("/api/v1/finance?mes=2026-10&janela=30d").json()
    assert j["janela"] == {"modo": "30d", "de": "2026-09-15", "ate": "2026-10-14"}
    assert (j["resumo"]["saldo"], j["resumo"]["emAtraso"], j["resumo"]["saldoComAtraso"]) == (700.0, 220.0, 480.0)


def test_pedidos_invalidos(cliente):
    assert cliente.get("/api/v1/finance?mes=2026-13").status_code in (400, 422)
    assert cliente.get("/api/v1/finance?janela=x").status_code in (400, 422)
    assert cliente.get("/api/v1/finance/reports?de=2026-05&ate=2026-01").status_code == 400
    assert cliente.get("/api/v1/finance/reports?de=2020-01&ate=2026-01").status_code == 400


def test_relatorio_soma_por_mes_e_categoria(cliente):
    FalsoDados.respostas["/financas/categorias"] = (200, {"categorias": CATS})
    FalsoDados.respostas["/financas/agregado"] = (200, {"linhas": [
        {"mes": "2026-08", "tipo": "despesa", "categoria_id": 1, "categoria": "Casa", "descricao": "Luz", "total": 40.0, "n": 1},
        {"mes": "2026-09", "tipo": "despesa", "categoria_id": 1, "categoria": "Casa", "descricao": "Luz", "total": 50.5, "n": 1},
        {"mes": "2026-09", "tipo": "rendimento", "categoria_id": 2, "categoria": "Rendimentos", "descricao": "Salário", "total": 1500.0, "n": 1}]})
    j = cliente.get("/api/v1/finance/reports?de=2026-08&ate=2026-09").json()
    assert [(m["mes"], m["despesas"], m["rendimento"], m["saldo"]) for m in j["meses"]] == [("2026-08", 40.0, 0.0, -40.0), ("2026-09", 50.5, 1500.0, 1449.5)]
    assert j["categorias"][0]["total"] == 90.5 and j["categorias"][0]["meses"] == {"2026-08": 40.0, "2026-09": 50.5}
    assert j["totais"] == {"rendimento": 1500.0, "despesas": 90.5}


def test_lembretes(cliente):
    FalsoDados.respostas["/financas/lembretes"] = (200, {"lembretes": [{"id": 1, "titulo": "IRS"}]})
    assert cliente.get("/api/v1/finance/reminders").json() == {"lembretes": [{"id": 1, "titulo": "IRS"}]}
