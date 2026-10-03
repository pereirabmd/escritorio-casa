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

    def _montar(modelo, chave="k-teste", tempo=None):
        n[0] += 1
        s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / f"teste-ia{n[0]}.db"), "PULSE_DADOS_URL": dados_falso,
                         "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
        app = create_app(s, ia_agente=ia.Agente(chave, transporte=modelo), tempo=tempo); app.state.agora = lambda: AGORA
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


# --- ferramentas novas: tempo, bilhetes na CP, simular devolução e histórico (ADR-094) ---------------------------------------------

def _prev():
    from tests.test_tempo import bruto
    return bruto()


class TempoFalso:
    def __init__(self):
        self.pedidos = []

    def __call__(self, url):
        self.pedidos.append(url)
        return _prev()


def test_as_ferramentas_novas_existem_e_as_de_bilhetes_somem_sem_o_modulo(montar):
    modelo = ModeloFalso(texto("ok"), texto("ok"))
    c = montar(modelo)
    pedir(c, "olá")
    nomes = {t["name"] for t in modelo.pedidos[0]["tools"]}
    assert {"consultar_tempo", "bilhetes_na_cp", "simular_devolucao", "bilhetes_historico", "bilhetes_favoritos", "bilhetes__troca_armar"} <= nomes
    assert c.put("/api/v1/admin/modules", json={"modulos": {"bilhetes": False}}).status_code == 200            # o administrador desliga os Bilhetes
    pedir(c, "olá outra vez")
    sem = {t["name"] for t in modelo.pedidos[1]["tools"]}
    assert "consultar_tempo" in sem                                                                          # o tempo não depende de nenhum módulo
    assert not ({"bilhetes_na_cp", "simular_devolucao", "bilhetes_historico", "bilhetes_favoritos", "bilhetes__troca_armar"} & sem)


def test_consultar_tempo_usa_a_posicao_do_aparelho_e_devolve_poucas_linhas(montar):
    from pulse.services.tempo import Tempo
    t = TempoFalso()
    modelo = ModeloFalso({"content": [uso("t1", "consultar_tempo")]}, texto("Hoje vai estar nublado, 20 graus."))
    c = montar(modelo, tempo=Tempo(t))
    r = c.post("/api/v1/ai/command", json={"mensagens": [{"papel": "utilizador", "texto": "que tempo faz hoje?"}], "posicao": {"lat": 38.7412, "lon": -9.1527}}).json()
    assert r["texto"].startswith("Hoje vai estar") and "latitude=38.74" in t.pedidos[0] and "longitude=-9.15" in t.pedidos[0]      # as coordenadas do aparelho chegam ao tempo
    resultado = json.loads(modelo.pedidos[1]["messages"][-1]["content"][0]["content"])
    assert resultado["local"] == "onde o utilizador está" and resultado["hoje"]["max"] == 20 and len(resultado["dias"]) == 5
    assert "temp" in resultado["agora"] and "horas" not in resultado                        # sem as 24 horas completas


def test_consultar_tempo_sem_posicao_diz_que_e_aveiro(montar):
    from pulse.services.tempo import Tempo
    modelo = ModeloFalso({"content": [uso("t1", "consultar_tempo")]}, texto("ok"))
    c = montar(modelo, tempo=Tempo(TempoFalso()))
    pedir(c, "vai chover?")
    assert "Aveiro" in json.loads(modelo.pedidos[1]["messages"][-1]["content"][0]["content"])["local"]


def test_posicao_invalida_e_recusada(montar):
    c = montar(ModeloFalso(texto("ok")))
    assert c.post("/api/v1/ai/command", json={"mensagens": [{"papel": "utilizador", "texto": "x"}], "posicao": {"lat": 200, "lon": 0}}).status_code in (400, 422)


def test_bilhetes_na_cp_e_simular_devolucao_passam_pelo_dados_api(montar):
    FalsoDados.respostas["/bilhetes/cp/futuros"] = (200, {"bilhetes": [{"venda": 77, "data": "2026-10-02", "hora": "07:27", "origem": "Aveiro", "destino": "Lisboa Oriente", "comboio": 520,
                                                                      "carruagem": 24, "lugar": 78, "valor": 23.45, "podeCancelar": True, "referencia": "SEGREDO"}]})
    FalsoDados.respostas["/bilhetes/trocas/simular"] = (200, {"venda": 77, "cancelavel": True, "motivo": "", "valor": "€ 23,45", "referencia": "SEGREDO"})
    FalsoDados.pedidos.clear()
    modelo = ModeloFalso({"content": [uso("t1", "bilhetes_na_cp")]}, {"content": [uso("t2", "simular_devolucao", venda=77)]}, texto("Recebes 23,45 €."))
    c = montar(modelo)
    assert pedir(c, "se devolver o comboio das 07:27 quanto recebo?").json()["texto"].startswith("Recebes")
    cp = json.loads(modelo.pedidos[1]["messages"][-1]["content"][0]["content"])["bilhetes"][0]
    assert (cp["venda"], cp["comboio"], cp["podeCancelar"]) == (77, 520, True) and "referencia" not in cp                   # a referência da CP não vai ao modelo
    sim = json.loads(modelo.pedidos[2]["messages"][-1]["content"][0]["content"])
    assert sim == {"cancelavel": True, "motivo": "", "valor": "€ 23,45"}
    assert [p[0] for p in FalsoDados.pedidos] == ["/bilhetes/cp/futuros", "/bilhetes/trocas/simular?venda=77"]


def test_simular_devolucao_recusa_venda_invalida_e_o_historico_so_para_o_administrador(montar):
    FalsoDados.respostas["/bilhetes/historico"] = (403, {"erro": {"codigo": "so_administrador", "mensagem": "só o administrador vê o histórico de pedidos"}})
    modelo = ModeloFalso({"content": [uso("t1", "simular_devolucao", venda=0), uso("t2", "bilhetes_historico")]}, texto("ok"))
    c = montar(modelo)
    pedir(c, "x")
    res = modelo.pedidos[1]["messages"][-1]["content"]
    assert res[0]["is_error"] and "venda inválida" in res[0]["content"]
    assert res[1]["is_error"] and "administrador" in res[1]["content"]


def test_bilhetes_historico_resume_por_resposta_e_limita_as_linhas(montar):
    pedidos = [{"ts": f"2026-10-02T17:{m:02d}:00.100+01:00", "pessoa": "Bruno", "comboio": 731, "fase": "retencao", "resultado": "sold_out" if m % 2 else "ok", "http": 200, "detalhe": "x" * 200} for m in range(40)]
    FalsoDados.respostas["/bilhetes/historico"] = (200, {"dias": 2, "pedidos": pedidos, "desfechos": [{"ts": "2026-10-02T17:55:00+01:00", "tipo": "COMPRA", "resultado": "SOLD_OUT", "comboio": 731}]})
    modelo = ModeloFalso({"content": [uso("t1", "bilhetes_historico", dias=2)]}, texto("ok"))
    c = montar(modelo)
    pedir(c, "o que aconteceu ontem às 17:30?")
    r = json.loads(modelo.pedidos[1]["messages"][-1]["content"][0]["content"])
    assert r["total"] == 40 and r["por_resposta"] == {"ok": 20, "sold_out": 20} and len(r["recentes"]) == 20 and len(r["recentes"][0]["detalhe"]) == 80


def test_resumo_da_troca_explica_os_dois_casos_e_o_inicio():
    from pulse import actions
    a = actions.ACOES["bilhetes.troca_armar"]
    r = ia.resumo(None, a, {"venda": 77, "comboio": 520, "hora": "06:45", "inicio": "2026-10-05T08:00"})
    assert "a partir de" in r and "mesmo comboio" in r and "risco" in r and "77" not in r                   # sem ids
