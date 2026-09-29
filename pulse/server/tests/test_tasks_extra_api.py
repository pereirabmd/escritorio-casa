"""GET /tasks/{calendar,schedule,pool,settings,history} e as ações de configuração (contra o dados-api falso)."""
import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, config
from pulse.clients.dados import DadosClient, ModuloIndisponivel
from pulse.main import create_app
from tests.conftest import FalsoDados
from tests.test_tasks_api import AGORA, DADOS, EMAIL
from tests.test_actions import conn, atividade                    # noqa: F401  (fixture `conn`)


class FalsoAvisos:
    def __init__(self, saude=None, gerar=None):
        self._saude, self._gerar, self.recalculos, self.geracoes = saude, gerar, [], 0

    def saude(self):
        return self._saude

    def gerar(self, utilizador):
        self.geracoes += 1
        return self._gerar

    def recalcular_em_fundo(self, utilizador):
        self.recalculos.append(utilizador)


@pytest.fixture
def avisos():
    return FalsoAvisos(saude={"ok": True, "saudavel": True, "minutosDesde": 3, "contagens": {"agendado": 2}}, gerar={"ok": True, "criadas": 4})


@pytest.fixture
def cliente(tmp_path, dados_falso, avisos):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s, avisos=avisos); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        FalsoDados.respostas["/tarefas/dados"] = (200, DADOS)
        c.headers["X-Pulse-Client"] = "web"
        yield c


def test_todas_as_rotas_exigem_sessao(cliente):
    cliente.cookies.clear()
    for caminho in ("/calendar?de=2026-09-01&ate=2026-09-30", "/schedule", "/pool", "/settings", "/history"):
        assert cliente.get("/api/v1/tasks" + caminho).status_code == 401, caminho


def test_calendario_por_intervalo(cliente):
    r = cliente.get("/api/v1/tasks/calendar", params={"de": "2026-09-28", "ate": "2026-10-04"})
    assert r.status_code == 200
    j = r.json()
    assert len(j["dias"]) == 7 and j["hoje"] == "2026-09-30" and [i["id"] for i in j["dias"][2]["itens"]] == ["I1"] and j["dias"][2]["feriado"] is None
    assert next(d for d in cliente.get("/api/v1/tasks/calendar", params={"de": "2026-10-05", "ate": "2026-10-05"}).json()["dias"])["feriado"] == "Implantação da República"
    assert cliente.get("/api/v1/tasks/calendar", params={"de": "2026-01-01", "ate": "2026-12-31"}).status_code == 400
    assert cliente.get("/api/v1/tasks/calendar", params={"de": "2026-09-30", "ate": "2026-09-01"}).status_code == 400
    assert cliente.get("/api/v1/tasks/calendar", params={"de": "x", "ate": "y"}).status_code == 400
    assert cliente.get("/api/v1/tasks/calendar").status_code == 400


def test_horario(cliente):
    FalsoDados.respostas["/tarefas/horario"] = (200, {"aulas": [{"id": 1, "aluno": "Ana", "anoLetivo": "2026/2027", "diaSemana": 3, "horaInicio": "09:00",
                                                                 "horaFim": "10:00", "disciplina": "Mat", "sala": "B1"}]})
    j = cliente.get("/api/v1/tasks/schedule").json()
    assert j["disponivel"] and j["diaHoje"] == 3 and j["alunos"][0]["dias"][0]["aviso"] == "09:30" and j["avisos"] == {"ativos": True, "minutos": 30}
    FalsoDados.respostas["/tarefas/horario"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    assert cliente.get("/api/v1/tasks/schedule").json()["disponivel"] is False                      # degradado: o resto do módulo continua


def test_piscina_completa_o_catalogo_em_falta(cliente):
    from pulse.services import piscina
    FalsoDados.respostas["POST /tarefas/piscina/catalogo"] = (200, {"criados": 12, "piscina": [
        {"id": i["id"], "nome": i["nome"], "avisoLongo": False, "ultimaData": None, "proximaData": None, "notificacaoEnviada": False, "usarIntervaloLongo": False}
        for i in piscina.CATALOGO]})
    j = cliente.get("/api/v1/tasks/pool").json()
    escrita = next(e for e in FalsoDados.escritas if e[1] == "/tarefas/piscina/catalogo")
    assert len(escrita[2]["itens"]) == len(piscina.CATALOGO) and escrita[3] == EMAIL
    assert j["estacao"] == "quente" and len(j["periodicas"]) == 9 and len(j["outras"]) == 4 and all(c["estado"] == "nunca" for c in j["periodicas"])


def test_piscina_com_catalogo_completo_nao_escreve(cliente):
    from pulse.services import piscina
    FalsoDados.respostas["/tarefas/dados"] = (200, {**DADOS, "piscina": [{"id": i["id"], "nome": i["nome"], "avisoLongo": False, "ultimaData": "2026-09-29",
                                                                         "proximaData": "2026-10-06", "notificacaoEnviada": False, "usarIntervaloLongo": False}
                                                                        for i in piscina.CATALOGO]}
    )
    j = cliente.get("/api/v1/tasks/pool").json()
    assert FalsoDados.escritas == [] and j["periodicas"][0]["estado"] == "ok"


def test_definicoes_para_admin_e_nao_admin(cliente):
    FalsoDados.respostas["/tarefas/auditoria"] = (200, {"entradas": [{"ts": "2026-09-29T10:00:00.000Z", "acao": "piscina_feita", "tarefa": "Cloro", "pessoa": "Bruno", "instanciaId": ""}]})
    j = cliente.get("/api/v1/tasks/settings").json()
    assert j["pessoas"] == [{"nome": "Bruno", "email": EMAIL}] and j["pessoaAtual"] == "Bruno" and j["categorias"] == ["Limpeza"]
    assert j["souAdmin"] is False and j["admin"] is None and j["auditoria"][0]["tarefa"] == "Cloro" and j["saude"]["minutosDesde"] == 3
    assert j["resumo"]["pessoas"] == [{"nome": "Bruno", "feitas": 0}] and j["preferencias"]["horaPadrao"] == "08:00"
    assert not any(p[0] == "/tarefas/admin" for p in FalsoDados.pedidos)                             # não pergunta o painel a quem não é admin
    FalsoDados.respostas["/tarefas/dados"] = (200, {**DADOS, "souAdmin": True})
    FalsoDados.respostas["/tarefas/admin"] = (200, {"raiz": [EMAIL], "admins": [EMAIL], "pessoas": [], "notificacoes": []})
    j = cliente.get("/api/v1/tasks/settings").json()
    assert j["souAdmin"] is True and j["admin"]["admins"] == [EMAIL]


def test_definicoes_com_auditoria_e_pi_em_baixo(cliente, avisos):
    FalsoDados.respostas["/tarefas/auditoria"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    avisos._saude = None
    j = cliente.get("/api/v1/tasks/settings").json()
    assert j["auditoria"] == [] and j["saude"] is None and j["pessoas"]


def test_historico_so_feitas_e_saltadas(cliente):
    FalsoDados.respostas["/tarefas/dados"] = (200, {**DADOS, "instancias": DADOS["instancias"] + [
        {"id": "I2", "tarefaId": "T1", "data": "2026-09-29", "pessoa": "Bruno", "estado": "Feita", "dataConclusao": "2026-09-29 10:00"},
        {"id": "I3", "tarefaId": "T1", "data": "2026-09-28", "pessoa": "Bruno", "estado": "Saltada", "dataConclusao": ""}]})
    j = cliente.get("/api/v1/tasks/history").json()
    assert [(x["data"], x["estado"], x["tarefa"]) for x in j["linhas"]] == [("2026-09-28", "Saltada", "Limpar WC"), ("2026-09-29", "Feita", "Limpar WC")]


def test_acao_de_tarefas_pede_o_recalculo_dos_avisos_e_a_de_peso_nao(cliente, avisos):
    assert cliente.post("/api/v1/actions/tarefas.avisos_horario", json={"params": {"ativos": False}}).status_code == 200
    assert avisos.recalculos == [EMAIL]
    assert cliente.post("/api/v1/actions/peso.registar", json={"params": {"peso": 80}}).status_code == 200
    assert avisos.recalculos == [EMAIL]
    e = FalsoDados.escritas[0]
    assert (e[0], e[1], e[2]) == ("PUT", "/tarefas/config", {"valores": {"HorarioAvisos": "FALSE"}})


def test_gerar_usa_o_servidor_das_tarefas_e_falha_com_clareza(cliente, avisos):
    r = cliente.post("/api/v1/actions/tarefas.gerar", json={"params": {}})
    assert r.status_code == 200 and r.json()["resultado"] == {"criadas": 4} and avisos.geracoes == 1
    avisos._gerar = None
    r = cliente.post("/api/v1/actions/tarefas.gerar", json={"params": {}})
    assert r.status_code == 503 and r.json()["erro"]["codigo"] == "modulo_indisponivel"


# --- validação e regras das ações (dados-api falso) -------------------------------------------------------------------------

def correr(conn, dados_falso, nome, params, **kw):                                                # noqa: F811
    ctx = actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), EMAIL, AGORA)
    return actions.executar(conn, ctx, nome, params, **kw)


def com_pessoas(*pessoas, instancias=(), tarefas=()):
    cfg = [{"chave": f"Pessoa{n}_{campo}", "valor": v} for n, nome, email in pessoas for campo, v in (("Nome", nome), ("Email", email)) if v]
    FalsoDados.respostas["/tarefas/dados"] = (200, {"tarefas": list(tarefas), "instancias": list(instancias), "config": cfg, "piscina": []})


@pytest.mark.parametrize("nome,params", [
    ("tarefas.avisos_horario", {"ativos": "talvez"}), ("tarefas.preferencias", {"naoIncomodarInicio": "25:00", "naoIncomodarFim": "07:00"}),
    ("tarefas.pessoa_adicionar", {"nome": "A,B"}), ("tarefas.pessoa_adicionar", {"nome": "  "}), ("tarefas.pessoa_adicionar", {"nome": "Ana", "email": "sem-arroba"}),
    ("tarefas.piscina_registar", {"item": "../x"}), ("tarefas.reatribuir", {"de": "A", "para": "B", "extra": 1}), ("tarefas.admin", {}),
    ("tarefas.admin", {"notificacoes": {"outra": []}}), ("tarefas.gerar", {"x": 1}),
])
def test_parametros_invalidos_sao_recusados_sem_tocar_no_modulo(conn, dados_falso, nome, params):        # noqa: F811
    with pytest.raises(actions.ContaErro) as e:
        correr(conn, dados_falso, nome, params, confirmado=True)
    assert e.value.codigo == "parametros_invalidos" and FalsoDados.escritas == []


def test_adicionar_pessoa_usa_o_proximo_numero_e_recusa_duplicados(conn, dados_falso):                # noqa: F811
    com_pessoas((1, "Bruno", "b@x.pt"), (3, "Camila", ""))
    assert correr(conn, dados_falso, "tarefas.pessoa_adicionar", {"nome": "Diana", "email": "D@X.pt"}) == {"num": 4}
    assert FalsoDados.escritas == [("PUT", "/tarefas/config", {"valores": {"Pessoa4_Nome": "Diana", "Pessoa4_Email": "d@x.pt"}}, EMAIL)]
    with pytest.raises(actions.ContaErro) as e:
        correr(conn, dados_falso, "tarefas.pessoa_adicionar", {"nome": "Bruno"})
    assert (e.value.status, e.value.codigo) == (409, "pessoa_existe")


def test_editar_pessoa_so_toca_no_que_mudou(conn, dados_falso):                                       # noqa: F811
    com_pessoas((1, "Bruno", "b@x.pt"), (2, "Camila", ""))
    correr(conn, dados_falso, "tarefas.pessoa_editar", {"nome": "Camila", "novoNome": "Camila", "email": "c@x.pt"})
    assert [e[:3] for e in FalsoDados.escritas] == [("PUT", "/tarefas/config", {"valores": {"Pessoa2_Email": "c@x.pt"}})]
    FalsoDados.escritas.clear()
    correr(conn, dados_falso, "tarefas.pessoa_editar", {"nome": "Bruno", "novoNome": "Bruno P.", "email": "b@x.pt"})
    assert [e[:3] for e in FalsoDados.escritas] == [("POST", "/tarefas/pessoas/reatribuir", {"de": "Bruno", "para": "Bruno P.", "apenasPendentes": False, "configChave": "Pessoa1_Nome"})]
    with pytest.raises(actions.ContaErro) as e:
        correr(conn, dados_falso, "tarefas.pessoa_editar", {"nome": "Bruno", "novoNome": "Camila"})
    assert e.value.codigo == "pessoa_existe"


def test_remover_pessoa_regras(conn, dados_falso):                                                    # noqa: F811
    com_pessoas((1, "Bruno", "b@x.pt"))
    with pytest.raises(actions.ContaErro) as e:
        correr(conn, dados_falso, "tarefas.pessoa_remover", {"nome": "Bruno"}, confirmado=True)
    assert e.value.codigo == "ultima_pessoa"
    inst = {"id": "I1", "tarefaId": "T1", "data": "2026-09-30", "pessoa": "Camila", "estado": "Pendente", "dataConclusao": ""}
    com_pessoas((1, "Bruno", ""), (2, "Camila", "c@x.pt"), instancias=[inst, {**inst, "id": "I2", "estado": "Feita"}])
    for ruim in (None, "Camila", "Fantasma"):
        with pytest.raises(actions.ContaErro) as e:
            correr(conn, dados_falso, "tarefas.pessoa_remover", {"nome": "Camila", "substituto": ruim}, confirmado=True)
        assert e.value.codigo == "substituto_necessario"
    assert FalsoDados.escritas == []
    assert correr(conn, dados_falso, "tarefas.pessoa_remover", {"nome": "Camila", "substituto": "Bruno"}, confirmado=True) == {"reatribuidas": 1}   # a Feita fica no histórico
    assert [e[:3] for e in FalsoDados.escritas] == [("POST", "/tarefas/pessoas/reatribuir", {"de": "Camila", "para": "Bruno", "apenasPendentes": True}),
                                                    ("PUT", "/tarefas/config", {"apagar": ["Pessoa2_Nome", "Pessoa2_Email"]})]
    FalsoDados.escritas.clear()
    com_pessoas((1, "Bruno", ""), (2, "Camila", ""))                                                    # sem tarefas: remove sem substituto
    correr(conn, dados_falso, "tarefas.pessoa_remover", {"nome": "Camila"}, confirmado=True)
    assert [e[:3] for e in FalsoDados.escritas] == [("PUT", "/tarefas/config", {"apagar": ["Pessoa2_Nome"]})]


def test_reatribuir_valida_as_pessoas(conn, dados_falso):                                             # noqa: F811
    com_pessoas((1, "Bruno", ""), (2, "Camila", ""))
    with pytest.raises(actions.ContaErro):
        correr(conn, dados_falso, "tarefas.reatribuir", {"de": "Bruno", "para": "Bruno"}, confirmado=True)
    with pytest.raises(Exception):
        correr(conn, dados_falso, "tarefas.reatribuir", {"de": "Bruno", "para": "Fantasma"}, confirmado=True)
    correr(conn, dados_falso, "tarefas.reatribuir", {"de": "Bruno", "para": "Camila"}, confirmado=True)
    assert [e[:3] for e in FalsoDados.escritas] == [("POST", "/tarefas/pessoas/reatribuir", {"de": "Bruno", "para": "Camila", "apenasPendentes": True})]


def test_registar_piscina_calcula_no_servidor_e_a_auditoria_nunca_bloqueia(conn, dados_falso):        # noqa: F811
    FalsoDados.respostas["/tarefas/dados"] = (200, {"tarefas": [], "instancias": [], "config": [{"chave": "Pessoa1_Nome", "valor": "Bruno"}, {"chave": "Pessoa1_Email", "valor": EMAIL}],
                                                    "piscina": [{"id": "P02", "nome": "Testar pH e cloro", "usarIntervaloLongo": False, "ultimaData": "2026-09-20", "proximaData": "2026-09-23",
                                                                 "notificacaoEnviada": True}]})
    FalsoDados.respostas["POST /tarefas/auditoria"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    r = correr(conn, dados_falso, "tarefas.piscina_registar", {"item": "P02"})
    assert r["atual"] == {"ultimaData": "2026-09-30", "proximaData": "2026-10-04", "notificacaoEnviada": False, "usarIntervaloLongo": True}
    assert r["anterior"] == {"ultimaData": "2026-09-20", "proximaData": "2026-09-23", "usarIntervaloLongo": False, "notificacaoEnviada": True}
    put = next(e for e in FalsoDados.escritas if e[0] == "PUT")
    assert put[1] == "/tarefas/piscina/P02" and put[2] == r["atual"]
    aud = next(e for e in FalsoDados.escritas if e[1] == "/tarefas/auditoria")
    assert aud[2] == {"acao": "piscina_feita", "tarefa": "Testar pH e cloro", "pessoa": "Bruno", "instanciaId": ""}
    assert atividade(conn) == [("tarefas", "tarefas.piscina_registar", "ui", "ok", "P02")]
