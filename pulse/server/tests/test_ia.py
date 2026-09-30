import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from pulse.services import ia
from tests.conftest import FalsoDados

AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
BRUNO = "pereirabmd@gmail.com"


class ModeloFalso:
    """Responde com os passos combinados e guarda o que recebeu (ferramentas e mensagens)."""

    def __init__(self, *passos, estado=200):
        self.passos, self.pedidos, self.estado = list(passos), [], estado

    def __call__(self, url, cabecalhos, corpo):
        self.pedidos.append(json.loads(corpo))
        return self.estado, json.dumps(self.passos.pop(0) if self.passos else {"content": [{"type": "text", "text": "ok"}]}).encode()


def uso(id_, ferramenta, **entrada):
    return {"type": "tool_use", "id": id_, "name": ferramenta, "input": entrada}


def texto(t):
    return {"content": [{"type": "text", "text": t}]}


@pytest.fixture
def montar(tmp_path, dados_falso):
    n = [0]

    def _montar(modelo, chave="k-teste"):
        n[0] += 1
        s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / f"teste-ia{n[0]}.db"), "PULSE_DADOS_URL": dados_falso,
                         "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
        app = create_app(s, ia_agente=ia.Agente(chave, transporte=modelo)); app.state.agora = lambda: AGORA
        c = TestClient(app, headers={"X-Pulse-Client": "web"}).__enter__()
        k = c.app.state.db(); accounts.criar_utilizador(k, BRUNO, "1234qweR", must_change=False, admin=True); k.close()
        assert c.post("/api/v1/auth/login", json={"email": BRUNO, "password": "1234qweR"}).status_code == 200
        return c
    return _montar


def pedir(c, *frases):
    return c.post("/api/v1/ai/command", json={"mensagens": [{"papel": "utilizador", "texto": f} for f in frases]})


def test_adicionar_pao_e_cebolas_propoe_e_so_escreve_depois_de_confirmar(montar):
    modelo = ModeloFalso({"content": [uso("t1", "compras_procurar", texto="pão")]},
                         {"content": [uso("t2", "compras__adicionar", lista=1, nome="Pão", categoria="padaria"), uso("t3", "compras__adicionar", lista=1, nome="Cebola", categoria="frutas-legumes")]},
                         texto("Vou adicionar pão e cebolas à lista Casa. Confirmas?"))
    c = montar(modelo)
    r = pedir(c, "adiciona à lista de compras pão e cebolas").json()
    assert r["texto"].startswith("Vou adicionar") and [p["acao"] for p in r["propostas"]] == ["compras.adicionar"] * 2
    assert c.get("/api/v1/shopping").json()["pendentes"] == 0                      # nada foi escrito ainda
    resultados = c.post("/api/v1/ai/confirm", json={"propostas": [{"acao": p["acao"], "params": p["params"]} for p in r["propostas"]]}).json()["resultados"]
    assert all(x["ok"] for x in resultados)
    assert c.get("/api/v1/shopping").json()["pendentes"] == 2
    ferramentas = {t["name"] for t in modelo.pedidos[0]["tools"]}
    assert {"consultar_hoje", "compras_procurar", "compras__adicionar"} <= ferramentas
    ativ = c.app.state.db().execute("SELECT origem FROM pulse_activity WHERE acao = 'compras.adicionar'").fetchall()
    assert [a[0] for a in ativ] == ["ia", "ia"]                                     # auditado como origem IA


def test_parametros_invalidos_voltam_ao_modelo_que_corrige(montar):
    modelo = ModeloFalso({"content": [uso("t1", "compras__adicionar", lista="x")]}, texto("Em que lista?"))
    c = montar(modelo)
    r = pedir(c, "adiciona leite").json()
    assert r["propostas"] == [] and r["texto"] == "Em que lista?"
    assert modelo.pedidos[1]["messages"][-1]["content"][0]["is_error"] is True


def test_sem_chave_desligado_e_limite_e_conversa_invalida(montar):
    c = montar(ModeloFalso(), chave="")
    assert c.get("/api/v1/ai/status").json() == {"ativo": False}
    assert pedir(c, "olá").status_code == 503
    c2 = montar(ModeloFalso(*[texto("ok")] * 30))
    assert c2.get("/api/v1/ai/status").json() == {"ativo": True}
    codigos = [pedir(c2, "olá").status_code for _ in range(ia.LIMITE_POR_MINUTO + 1)]
    assert codigos[:-1] == [200] * ia.LIMITE_POR_MINUTO and codigos[-1] == 429
    assert c2.post("/api/v1/ai/command", json={"mensagens": [{"papel": "assistente", "texto": "x"}]}).status_code == 400


def test_confirmar_uma_acao_que_falha_nao_impede_as_outras_e_modelo_em_erro_da_502(montar):
    c = montar(ModeloFalso(estado=500))
    assert pedir(c, "olá").status_code == 502
    r = c.post("/api/v1/ai/confirm", json={"propostas": [{"acao": "compras.adicionar", "params": {"lista": 999, "nome": "X", "categoria": "outros"}},
                                                          {"acao": "compras.adicionar", "params": {"lista": 1, "nome": "Sal", "categoria": "mercearia"}}]}).json()["resultados"]
    assert [x["ok"] for x in r] == [False, True]


def test_propostas_trazem_resumo_sem_ids(montar):
    modelo = ModeloFalso({"content": [uso("t1", "compras__adicionar", lista=1, produto=1), uso("t2", "compras__adicionar", lista=1, nome="Cebola", categoria="frutas-legumes")]},
                         texto("Vou adicionar pão e cebolas à lista Casa. Confirmas?"))
    c = montar(modelo)
    r = pedir(c, "adiciona pão e cebolas").json()
    resumos = [p["resumo"] for p in r["propostas"]]
    assert resumos[1] == "Adicionar «Cebola» à lista «Casa»"
    assert resumos[0].startswith("Adicionar «") and resumos[0].endswith("à lista «Casa»")
    assert not any(ch.isdigit() for ch in " ".join(resumos))                         # nenhum id à vista
    assert "NUNCA escrevas ids" in modelo.pedidos[0]["system"][0]["text"]
