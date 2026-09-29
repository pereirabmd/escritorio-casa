from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from tests.conftest import FalsoDados

EMAIL = "pereirabmd@gmail.com"
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
DADOS = {"tarefas": [{"id": "T1", "nome": "Limpar WC", "categoria": "Limpeza", "recorrencia": "Diaria", "diasSemana": "", "diaMes": None, "horaNotificacao": "",
                      "pessoaPadrao": "Bruno", "ativa": True, "prioridade": "Media", "icone": "", "rotacaoPessoas": "", "dependeDe": ""}],
         "instancias": [{"id": "I1", "tarefaId": "T1", "data": "2026-09-30", "pessoa": "Bruno", "estado": "Pendente", "dataConclusao": "", "notificacaoEnviada": False}],
         "config": [{"chave": "Pessoa1_Nome", "valor": "Bruno"}, {"chave": "Pessoa1_Email", "valor": EMAIL}, {"chave": "Categoria1", "valor": "Limpeza"}], "piscina": []}


@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso,
                     "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


def test_exige_sessao(cliente):
    cliente.cookies.clear()
    assert cliente.get("/api/v1/tasks").status_code == 401


def test_devolve_a_visao(cliente):
    FalsoDados.respostas["/tarefas/dados"] = (200, DADOS)
    r = cliente.get("/api/v1/tasks")
    assert r.status_code == 200
    j = r.json()
    assert j["pessoa"] == "Bruno" and j["categorias"] == ["Limpeza"] and [i["id"] for i in j["hoje"]] == ["I1"] and j["hoje"][0]["hora"] == "08:00"
    assert j["tarefas"][0]["resumo"] == "Todos os dias" and {p[1] for p in FalsoDados.pedidos} == {EMAIL}


def test_modulo_em_baixo_e_sem_acesso(cliente):
    FalsoDados.respostas["/tarefas/dados"] = (500, {"erro": {"codigo": "erro_interno", "mensagem": "x"}})
    assert cliente.get("/api/v1/tasks").status_code == 503
    FalsoDados.respostas["/tarefas/dados"] = (403, {"erro": {"codigo": "sem_acesso", "mensagem": "sem acesso a esta aplicação"}})
    assert cliente.get("/api/v1/tasks").status_code == 403
