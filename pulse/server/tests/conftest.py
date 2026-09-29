import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pulse import config


class FalsoDados(BaseHTTPRequestHandler):
    """Imita o dados-api: /saude público, o resto exige X-Pulse-Key certa."""
    CHAVE = "k" * 40
    pedidos: list = []
    escritas: list = []           # (metodo, caminho, corpo, utilizador) dos POST/PUT/DELETE
    respostas: dict = {}          # caminho (sem query) -> (status, corpo): respostas fixas para um teste

    def log_message(self, *a):
        pass

    def _resp(self, status, corpo):
        raw = json.dumps(corpo).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _escrita(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n).decode()) if n else None
        if self.headers.get("X-Pulse-Key") != self.CHAVE:
            return self._resp(401, {"erro": {"codigo": "nao_autenticado", "mensagem": "sem chave"}})
        FalsoDados.escritas.append((self.command, self.path, corpo, self.headers.get("X-Pulse-User")))
        fixa = FalsoDados.respostas.get(f"{self.command} {self.path}")
        self._resp(*(fixa if fixa is not None else (200, {"ok": True})))

    do_POST = do_PUT = do_DELETE = _escrita

    def do_GET(self):
        if self.path == "/saude":
            return self._resp(200, {"ok": True})
        if self.headers.get("X-Pulse-Key") != self.CHAVE:
            return self._resp(401, {"erro": {"codigo": "nao_autenticado", "mensagem": "sem chave"}})
        FalsoDados.pedidos.append((self.path, self.headers.get("X-Pulse-User")))
        fixa = FalsoDados.respostas.get(self.path) or FalsoDados.respostas.get(self.path.split("?")[0])
        if fixa is not None:
            return self._resp(*fixa)
        if self.path.startswith("/conflito"):
            return self._resp(409, {"erro": {"codigo": "conflito", "mensagem": "já existe"}})
        if self.path.startswith("/avaria"):
            return self._resp(500, {"erro": {"codigo": "erro_interno", "mensagem": "erro interno"}})
        self._resp(200, {"ok": True})


@pytest.fixture
def dados_falso():
    FalsoDados.pedidos = []
    FalsoDados.escritas = []
    FalsoDados.respostas = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FalsoDados)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown(); srv.server_close()


@pytest.fixture
def settings(tmp_path, dados_falso):
    return config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"),
                        "PULSE_DADOS_URL": dados_falso, "PULSE_TAREFAS_URL": "", "PULSE_SERVICE_KEY": FalsoDados.CHAVE})
