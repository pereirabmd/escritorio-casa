from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import dashboard
from tests.conftest import FalsoDados

H = {"X-Pulse-Client": "web"}
EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))   # quarta-feira; a semana vai de 28/09 a 04/10

TAREFAS = {
    "tarefas": [
        {"id": "T001", "nome": "Limpar WC", "categoria": "Limpeza", "icone": "wc", "prioridade": "Media", "horaNotificacao": "09:00", "ativa": True},
        {"id": "T002", "nome": "Lixo", "categoria": "Casa", "icone": "", "prioridade": "Alta", "horaNotificacao": "", "ativa": True},
        {"id": "T003", "nome": "Desativada", "categoria": "", "icone": "", "prioridade": "Baixa", "horaNotificacao": "", "ativa": False}],
    "instancias": [
        {"id": "I1", "tarefaId": "T001", "data": "2026-09-30", "pessoa": "Bruno", "estado": "Pendente"},
        {"id": "I2", "tarefaId": "T002", "data": "2026-09-30", "pessoa": "", "estado": "Pendente"},
        {"id": "I3", "tarefaId": "T001", "data": "2026-09-29", "pessoa": "Bruno", "estado": "Atrasada"},
        {"id": "I4", "tarefaId": "T002", "data": "2026-09-30", "pessoa": "", "estado": "Feita"},
        {"id": "I5", "tarefaId": "T001", "data": "2026-09-30", "pessoa": "Camila", "estado": "Pendente"},
        {"id": "I6", "tarefaId": "T003", "data": "2026-09-30", "pessoa": "", "estado": "Pendente"}],
    "config": [{"chave": "Pessoa1_Nome", "valor": "Bruno"}, {"chave": "Pessoa1_Email", "valor": "PereiraBMD@gmail.com"},
               {"chave": "Pessoa2_Nome", "valor": "Camila"}, {"chave": "Pessoa2_Email", "valor": "camila@exemplo.pt"}],
}
BILHETE = {"proximo": {"id": 1, "data": "2026-10-01", "hora": "07:27", "compra": None}, "passe": {"diasRestantes": 20}}


def preparar(respostas=None):
    FalsoDados.respostas = {
        "/tarefas/dados": (200, TAREFAS), "/bilhetes/proximo": (200, BILHETE),
        "/rto/dias": (200, {"dias": {"2026-09-28": "T", "2026-09-29": "C", "2026-09-30": "T"}}),
        "/peso/registos": (200, {"registos": [{"quando": "2026-09-20 08:00:00", "peso": 81.2},
                                              {"quando": "2026-09-30 07:30:00", "peso": 80.6}]}),
        "/financas/lancamentos": (200, {"lancamentos": [
            {"id": 2, "descricao": "Luz", "valor": 60.5, "categoria": "Habitação", "data_vencimento": "2026-10-05"},
            {"id": 1, "descricao": "Água", "valor": 20, "categoria": "Habitação", "data_vencimento": "2026-09-25"}]}),
        **(respostas or {})}


def cliente(dados_falso):
    return DadosClient(dados_falso, FalsoDados.CHAVE)


def test_agregado_completo(dados_falso):
    preparar()
    r = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)
    assert r["estado"] == "ok" and r["data"] == "2026-09-30" and r["resumo"] is None
    assert set(r["modulos"]) == {"tarefas", "bilhetes", "rto", "peso", "financas", "calendario", "email"}
    assert r["modulos"]["calendario"] == {"estado": "nao_ligado", "dados": None}
    assert r["modulos"]["bilhetes"]["dados"] == BILHETE
    assert {p[1] for p in FalsoDados.pedidos} == {EMAIL}           # sempre em nome do utilizador


def test_rto_semana_atual(dados_falso):
    preparar()
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["rto"]["dados"]
    assert d["semana"] == {"inicio": "2026-09-28", "fim": "2026-10-04"}
    assert [x["marca"] for x in d["dias"]] == ["T", "C", "T", "", "", "", ""]
    assert [x["diaSemana"] for x in d["dias"]] == [1, 2, 3, 4, 5, 6, 7] and d["dias"][2]["hoje"] and not d["dias"][1]["hoje"]
    assert d["contagem"] == {"T": 2, "C": 1}
    assert ("/rto/dias?desde=2026-09-28&ate=2026-10-04", EMAIL) in FalsoDados.pedidos


def test_peso_sugere_o_ultimo_e_sabe_se_ja_registou_hoje(dados_falso):
    preparar()
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["peso"]["dados"]
    assert d == {"ultimo": {"quando": "2026-09-30 07:30:00", "peso": 80.6}, "registadoHoje": True, "sugestao": 80.6}
    preparar({"/peso/registos": (200, {"registos": [{"quando": "2026-09-20 08:00:00", "peso": 81.2}]})})
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["peso"]["dados"]
    assert (d["registadoHoje"], d["sugestao"]) == (False, 81.2)


def test_peso_sem_registos_recentes_procura_o_historico_todo(dados_falso):
    preparar({"/peso/registos": (200, {"registos": []})})
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["peso"]["dados"]
    assert d == {"ultimo": None, "registadoHoje": False, "sugestao": None}
    pesos = [p[0] for p in FalsoDados.pedidos if p[0].startswith("/peso")]
    assert pesos == ["/peso/registos?desde=2026-07-02", "/peso/registos"]


def test_contas_ordenadas_com_vencidas_e_total(dados_falso):
    preparar()
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["financas"]["dados"]
    assert [c["descricao"] for c in d["proximas"]] == ["Água", "Luz"]
    assert d["proximas"][0]["vencida"] and d["proximas"][0]["diasAte"] == -5 and d["proximas"][1]["diasAte"] == 5
    assert (d["vencidas"], d["total"], d["valorTotal"]) == (1, 2, 80.5)
    q = next(p[0] for p in FalsoDados.pedidos if p[0].startswith("/financas"))
    assert "pendentes=1" in q and "tipo=despesa" in q and "ate=2026-10-30" in q


def test_tarefas_do_utilizador_ordenadas_e_sem_as_de_outros(dados_falso):
    preparar()
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["tarefas"]["dados"]
    assert d["pessoa"] == "Bruno"
    assert [t["id"] for t in d["hoje"]] == ["I1", "I2"]            # 09:00 antes do sem hora; a da Camila e a desativada ficam fora
    assert (d["atrasadas"], d["feitasHoje"], d["totalHoje"]) == (1, 1, 3)


def test_tarefas_incluem_a_piscina_do_dia_ou_atrasada_e_a_saida_do_bruno(dados_falso):
    from pulse.services import piscina as regras
    ids = [i["id"] for i in regras.CATALOGO if i.get("tipo") != "log"]
    piscina = [{"id": ids[0], "ultimaData": "2026-09-27", "proximaData": "2026-09-30"},          # sugerida para hoje
               {"id": ids[1], "ultimaData": "2026-09-27", "proximaData": "2026-10-05"},          # ainda não é a vez
               {"id": ids[2], "ultimaData": "2026-05-01", "proximaData": "2026-05-04"}]          # já passou há muito
    aulas = [{"aluno": "Bruno", "anoLetivo": "2026/2027", "diaSemana": 3, "horaInicio": "08:30", "horaFim": "09:15", "disciplina": "Matemática", "sala": "A1"},
             {"aluno": "Bruno", "anoLetivo": "2026/2027", "diaSemana": 3, "horaInicio": "15:30", "horaFim": "16:15", "disciplina": "Inglês", "sala": "B2"},
             {"aluno": "Bruno", "anoLetivo": "2026/2027", "diaSemana": 4, "horaInicio": "08:30", "horaFim": "12:00", "disciplina": "Português", "sala": "A1"},
             {"aluno": "Outra", "anoLetivo": "2026/2027", "diaSemana": 3, "horaInicio": "08:30", "horaFim": "17:00", "disciplina": "Arte", "sala": "C3"}]
    preparar({"/tarefas/dados": (200, {**TAREFAS, "piscina": piscina}), "/tarefas/horario": (200, {"aulas": aulas})})
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["tarefas"]["dados"]
    assert {k["id"] for k in d["piscina"]} == {ids[0], ids[2]}                                   # a que só é daqui a 5 dias fica de fora
    assert {"estado", "nome", "diasDesde", "proxima"} <= set(d["piscina"][0])
    assert d["horario"] == {"aluno": "Bruno", "entra": "08:30", "sai": "16:15", "aviso": "15:45"}    # quarta-feira; a 4.ª de outro dia e a «Outra» não contam


def test_sem_horario_do_bruno_ou_sem_aulas_hoje_nao_ha_saida(dados_falso):
    preparar()                                                                 # o dados-api não responde ao horário
    d = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["tarefas"]["dados"]
    assert d["horario"] is None and d["piscina"] == []
    aulas = [{"aluno": "Bruno", "anoLetivo": "2026/2027", "diaSemana": 4, "horaInicio": "08:30", "horaFim": "12:00", "disciplina": "Português", "sala": "A1"}]
    preparar({"/tarefas/horario": (200, {"aulas": aulas})})
    assert dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)["modulos"]["tarefas"]["dados"]["horario"] is None


def test_tarefas_sem_pessoa_associada_mostra_todas(dados_falso):
    preparar()
    d = dashboard.hoje(cliente(dados_falso), "outro@exemplo.pt", AGORA)["modulos"]["tarefas"]["dados"]
    assert d["pessoa"] is None and {t["id"] for t in d["hoje"]} == {"I1", "I2", "I5"}


def test_um_modulo_a_falhar_nao_derruba_os_outros(dados_falso):
    preparar({"/rto/dias": (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})})
    r = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)
    assert r["estado"] == "degradado"
    assert r["modulos"]["rto"]["estado"] == "indisponivel"
    assert all(r["modulos"][m]["estado"] == "ok" for m in ("tarefas", "bilhetes", "peso", "financas"))


def test_sem_acesso_a_um_modulo_nao_e_degradado(dados_falso):
    preparar({"/financas/lancamentos": (403, {"erro": {"codigo": "sem_acesso", "mensagem": "sem acesso a esta aplicação"}})})
    r = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)
    assert r["modulos"]["financas"]["estado"] == "sem_acesso" and r["estado"] == "ok"


def test_resposta_inesperada_e_erro_do_modulo_e_nao_500(dados_falso):
    preparar({"/tarefas/dados": (200, {"tarefas": [{"id": "T1", "ativa": True}], "instancias": [{"tarefaId": "T1", "data": "x"}]}),
              "/rto/dias": (200, {"dias": []})})
    r = dashboard.hoje(cliente(dados_falso), EMAIL, AGORA)
    assert r["modulos"]["tarefas"]["estado"] == "erro" and r["modulos"]["tarefas"]["erro"]["codigo"] == "resposta_inesperada"
    assert r["modulos"]["rto"]["estado"] == "erro"
    assert r["estado"] == "degradado" and r["modulos"]["peso"]["estado"] == "ok"


def test_dados_api_em_baixo_todos_indisponiveis(tmp_path):
    c = DadosClient("http://127.0.0.1:9", FalsoDados.CHAVE, timeout=1)
    r = dashboard.hoje(c, EMAIL, AGORA)
    assert r["estado"] == "degradado"
    assert {r["modulos"][m]["estado"] for m in dashboard.MODULOS} == {"indisponivel"}


# --- endpoint -------------------------------------------------------------------------------------------------------

@pytest.fixture
def app_cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s)
    app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        conn = c.app.state.db(); accounts.criar_utilizador(conn, EMAIL, "1234qweR", must_change=False); conn.close()
        yield c


def test_endpoint_exige_sessao(app_cliente):
    r = app_cliente.get("/api/v1/dashboard/today")
    assert r.status_code == 401 and r.json()["erro"]["codigo"] == "nao_autenticado"


def test_endpoint_devolve_o_hoje_em_nome_do_utilizador(app_cliente):
    preparar()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    r = app_cliente.get("/api/v1/dashboard/today")
    assert r.status_code == 200 and r.json()["estado"] == "ok" and r.json()["modulos"]["peso"]["dados"]["sugestao"] == 80.6
    assert {p[1] for p in FalsoDados.pedidos} == {EMAIL}


def test_endpoint_recusa_conta_que_ainda_tem_de_mudar_a_password(app_cliente):
    conn = app_cliente.app.state.db(); conn.execute("UPDATE pulse_users SET must_change_password=1"); conn.close()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    r = app_cliente.get("/api/v1/dashboard/today")
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "mudar_password"
    assert FalsoDados.pedidos == []


# --- cartão das Compras (dados do próprio pulse.db) ---------------------------------------------------------------------------

def _produto(conn, nome):
    return conn.execute("SELECT id FROM shop_products WHERE nome = ?", (nome,)).fetchone()["id"]


def test_compras_no_hoje_mostra_alguns_itens_por_corredor_e_o_seguinte_entra_quando_um_e_comprado(app_cliente):
    preparar()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    vazio = app_cliente.get("/api/v1/dashboard/today").json()["modulos"]["compras"]
    assert vazio["estado"] == "ok" and vazio["dados"]["itens"] == [] and vazio["dados"]["lista"]["nome"] == "Casa" and vazio["dados"]["pendentes"] == 0
    H = {"X-Pulse-Client": "web"}
    lista = vazio["dados"]["lista"]["id"]
    ids = {}
    conn = app_cliente.app.state.db()
    for nome in ("Champô", "Bacalhau", "Arroz agulha", "Leite meio-gordo", "Maçã", "Ovos", "Fraldas"):
        ids[nome] = app_cliente.post("/api/v1/actions/compras.adicionar", json={"params": {"lista": lista, "produto": _produto(conn, nome)}}, headers=H).json()["resultado"]["id"]
    conn.close()
    d = app_cliente.get("/api/v1/dashboard/today").json()["modulos"]["compras"]["dados"]
    assert d["pendentes"] == 7 and [i["nome"] for i in d["itens"]] == ["Maçã", "Arroz agulha", "Leite meio-gordo", "Ovos", "Bacalhau"]      # 5, pela ordem dos corredores
    assert app_cliente.post("/api/v1/actions/compras.comprado", json={"params": {"item": ids["Maçã"], "comprado": True}}, headers=H).status_code == 200
    d = app_cliente.get("/api/v1/dashboard/today").json()["modulos"]["compras"]["dados"]
    assert d["pendentes"] == 6 and [i["nome"] for i in d["itens"]] == ["Arroz agulha", "Leite meio-gordo", "Ovos", "Bacalhau", "Champô"]   # a comprada saiu e entrou o seguinte


def test_compras_desativadas_nao_sao_pedidas_e_o_cartao_diz_desativado(app_cliente):
    preparar()
    conn = app_cliente.app.state.db(); conn.execute("UPDATE pulse_users SET admin = 1"); conn.close()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    app_cliente.put("/api/v1/admin/modules", json={"modulos": {"compras": False}}, headers={"X-Pulse-Client": "web"})
    assert app_cliente.get("/api/v1/dashboard/today").json()["modulos"]["compras"] == {"estado": "desativado", "dados": None}


def test_um_erro_nas_compras_nao_derruba_o_resto_do_hoje(app_cliente, monkeypatch):
    preparar()
    from pulse.services import compras
    monkeypatch.setattr(compras, "resumo_hoje", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    j = app_cliente.get("/api/v1/dashboard/today").json()
    assert j["modulos"]["compras"]["estado"] == "erro" and j["modulos"]["peso"]["estado"] == "ok" and j["estado"] == "degradado"


def test_ordem_dos_cartoes_guarda_se_por_utilizador_e_completa_se(app_cliente):
    preparar()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    origem = ["calendario", "tarefas", "email", "bilhetes", "rto", "peso", "compras", "financas"]
    assert app_cliente.get("/api/v1/dashboard/today").json()["ordem"] == origem
    r = app_cliente.put("/api/v1/dashboard/order", json={"ordem": ["peso", "tarefas"]}, headers=H)
    assert r.status_code == 200 and r.json()["ordem"][:2] == ["peso", "tarefas"] and sorted(r.json()["ordem"]) == sorted(origem)
    assert app_cliente.get("/api/v1/dashboard/today").json()["ordem"] == r.json()["ordem"]
    assert app_cliente.get("/api/v1/dashboard/order").json() == {"ordem": r.json()["ordem"]}


@pytest.mark.parametrize("ordem", [["peso", "peso"], ["nao_existe"], []])
def test_ordem_invalida_e_recusada(app_cliente, ordem):
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    assert app_cliente.put("/api/v1/dashboard/order", json={"ordem": ordem}, headers=H).status_code in (400, 422)


def test_atualizacao_parcial_so_pede_os_modulos_indicados(app_cliente):
    preparar()
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    FalsoDados.pedidos.clear()
    r = app_cliente.get("/api/v1/dashboard/today?modulos=peso")
    assert r.status_code == 200 and set(r.json()["modulos"]) == {"peso"} and r.json()["ordem"]
    assert [p[0].split("?")[0] for p in FalsoDados.pedidos] == ["/peso/registos"]      # nada mais foi pedido (nem tarefas, nem Google)
    assert set(app_cliente.get("/api/v1/dashboard/today?modulos=tarefas,rto,nao_existe").json()["modulos"]) == {"tarefas", "rto"}
    assert len(app_cliente.get("/api/v1/dashboard/today").json()["modulos"]) >= 7


def test_ecras_com_ligacao_sqlite_nao_rebentam_com_a_middleware(app_cliente):
    """Regressão: a middleware de tempos não pode mudar de thread (o `get_conn` fecha a ligação onde a abriu)."""
    app_cliente.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
    for caminho in ("/api/v1/auth/sessions", "/api/v1/dashboard/order", "/api/v1/modules"):
        assert app_cliente.get(caminho).status_code == 200, caminho
