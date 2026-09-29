import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pulse import actions
from pulse.clients.tarefas_api import TarefasApiClient
from tests.conftest import FalsoDados
from tests.test_actions import AGORA, EMAIL, conn, correr, dados_tarefas   # noqa: F401  (fixture `conn`)

CHAVE = "k" * 40


class FalsoTarefasApi(BaseHTTPRequestHandler):
    recebidos: list = []
    status = 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        FalsoTarefasApi.recebidos.append((self.path, self.headers.get("X-Pulse-Key"), self.headers.get("X-Pulse-User")))
        raw = json.dumps({"ok": True}).encode()
        self.send_response(FalsoTarefasApi.status); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)


@pytest.fixture
def tarefas_api():
    FalsoTarefasApi.recebidos, FalsoTarefasApi.status = [], 200
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FalsoTarefasApi)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown(); srv.server_close()


def test_recalcular_envia_a_chave_de_servico_e_o_utilizador(tarefas_api):
    assert TarefasApiClient(tarefas_api, CHAVE).recalcular(EMAIL) is True
    assert FalsoTarefasApi.recebidos == [("/recalcularAgora", CHAVE, EMAIL)]


def test_recalcular_nunca_levanta_erro(tarefas_api):
    FalsoTarefasApi.status = 503
    assert TarefasApiClient(tarefas_api, CHAVE).recalcular(EMAIL) is False
    assert TarefasApiClient("http://127.0.0.1:1", CHAVE, timeout=1).recalcular(EMAIL) is False       # ninguém à escuta
    assert TarefasApiClient("", CHAVE).recalcular(EMAIL) is False                                    # desligado
    assert TarefasApiClient(tarefas_api, "").recalcular(EMAIL) is False


def test_so_as_acoes_de_tarefas_com_sucesso_pedem_o_recalculo(conn, dados_falso):    # noqa: F811
    pedidos = []
    ctx = actions.Contexto(actions_client(dados_falso), EMAIL, AGORA, avisos_tarefas=lambda: pedidos.append(1))
    dados_tarefas(("I1", "T001", "2026-09-30", "Pendente"))
    actions.executar(conn, ctx, "tarefas.saltar", {"instancia": "I1"})
    assert pedidos == [1]
    actions.executar(conn, ctx, "peso.registar", {"peso": 80})
    assert pedidos == [1]                                           # peso não mexe nos avisos
    FalsoDados.respostas["PUT /tarefas/instancias/I2"] = (409, {"erro": {"codigo": "conflito", "mensagem": "x"}})
    with pytest.raises(Exception):
        actions.executar(conn, ctx, "tarefas.saltar", {"instancia": "I2"})
    assert pedidos == [1]                                           # falhou: nada mudou, nada a recalcular


def actions_client(url):
    from pulse.clients.dados import DadosClient
    return DadosClient(url, FalsoDados.CHAVE)
