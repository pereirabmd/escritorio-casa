"""A camada HTTP do servidor.py: autenticação Google nos endpoints da PWA, CORS, e o caminho HMAC das ações do ntfy."""

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import recalcular
import servidor
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient

ORIGEM = "https://pereirabmd.github.io"


class _Verificador:
    def __init__(self, tokens):
        self.tokens = tokens

    def verify(self, token):
        if token in self.tokens:
            return self.tokens[token]
        e = Exception("token recusado")
        e.status = 401
        raise e


class ServidorHttpTest(TarefasTestCase):
    def setUp(self):
        super().setUp()
        self.sheets = FakeSheetsClient({
            "Config": [{"Chave": "DiasAntecedenciaGeracao", "Valor": 1}], "Tarefas": [], "Piscina": [],
            "Instancias": [{"ID": "I1", "TarefaID": "T1", "Data": "2026-09-23", "Pessoa": "Bruno", "Estado": "Pendente", "NotificacaoEnviada": "FALSE"}],
        })
        self.env = mock.patch.dict("os.environ", {"ACL_TAREFAS": "eu@x.com,ela@x.com", "GOOGLE_CLIENT_IDS": "cid"})
        self.env.start(); self.addCleanup(self.env.stop)
        v = mock.patch.object(servidor, "_VERIFICADOR", _Verificador({"T" * 30: "eu@x.com", "U" * 30: "intruso@x.com"}))
        v.start(); self.addCleanup(v.stop)
        self.srv = servidor.criar_servidor(0, sheets_factory=lambda: self.sheets)
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def pedir(self, metodo, caminho, corpo=None, token=None, origem=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=5)
        h = {}
        if token:
            h["Authorization"] = f"Bearer {token}"
        if origem:
            h["Origin"] = origem
        if corpo is not None:
            h["Content-Type"] = "application/json"
        c.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None, headers=h)
        r = c.getresponse()
        texto = r.read().decode()
        c.close()
        return r.status, (json.loads(texto) if texto else None), r

    def test_endpoints_da_pwa_exigem_token_google_da_acl(self):
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m"}), mock.patch.object(common, "ntfy_cancel", return_value=True):
            for caminho in ("/gerar", "/recalcularAgora", "/testar", "/configurarNtfy"):
                self.assertEqual(self.pedir("POST", caminho, {})[0], 401, caminho)                       # sem token
                self.assertEqual(self.pedir("POST", caminho, {}, token="X" * 30)[0], 401, caminho)      # token recusado
                self.assertEqual(self.pedir("POST", caminho, {}, token="U" * 30)[0], 403, caminho)      # token válido, e-mail fora da ACL
            s, b, _ = self.pedir("POST", "/gerar", {}, token="T" * 30)
            self.assertEqual((s, b["ok"]), (200, True))
            s, b, _ = self.pedir("POST", "/testar", {"pessoa": "Bruno"}, token="T" * 30)
            self.assertEqual((s, b["ok"]), (200, True))

    def test_falha_fechado_se_a_autenticacao_nao_estiver_configurada(self):
        with mock.patch.dict("os.environ", {"ACL_TAREFAS": ""}):
            self.assertEqual(self.pedir("POST", "/gerar", {}, token="T" * 30)[0], 503)

    def test_google_indisponivel_e_503_nao_401(self):
        class Em_baixo:
            def verify(self, t):
                e = Exception("sem rede"); e.status = 503; raise e
        with mock.patch.object(servidor, "_VERIFICADOR", Em_baixo()):
            self.assertEqual(self.pedir("POST", "/gerar", {}, token="T" * 30)[0], 503)     # o fail2ban não conta 503

    def test_saude_e_publica_e_o_endpoint_desconhecido_da_404(self):
        self.assertEqual(self.pedir("GET", "/saude")[0], 200)
        self.assertEqual(self.pedir("GET", "/nada")[0], 404)

    def test_acao_da_notificacao_continua_a_funcionar_por_hmac_sem_token(self):
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m"}), mock.patch.object(common, "ntfy_cancel", return_value=True):
            s, b, _ = self.pedir("POST", "/marcarFeita?id=I1&s=" + recalcular.assinar_instancia("I1"))
            self.assertEqual((s, b), (200, {"ok": True}))
            s, b, _ = self.pedir("POST", "/marcarFeita?id=I1&s=errada")
            self.assertEqual((s, b["erro"]), (401, "assinatura inválida"))

    def test_cors_so_para_origens_permitidas(self):
        _, _, r = self.pedir("GET", "/saude", origem=ORIGEM)
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), ORIGEM)
        _, _, r = self.pedir("GET", "/saude", origem="https://evil.example")
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))
        s, _, r = self.pedir("OPTIONS", "/gerar", origem=ORIGEM)
        self.assertEqual((s, r.getheader("Access-Control-Allow-Headers")), (204, "Authorization, Content-Type"))
        self.assertEqual(self.pedir("OPTIONS", "/gerar", origem="https://evil.example")[0], 403)
        # a resposta 401 também é legível pela PWA (para mostrar "sessão expirada")
        _, _, r = self.pedir("POST", "/gerar", {}, origem=ORIGEM)
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), ORIGEM)

    def test_corpo_enorme_e_recusado(self):
        s, b, _ = self.pedir("POST", "/testar", {"pessoa": "x" * 20000}, token="T" * 30)
        self.assertEqual((s, b["erro"]), (413, "corpo demasiado grande"))


if __name__ == "__main__":
    unittest.main()
