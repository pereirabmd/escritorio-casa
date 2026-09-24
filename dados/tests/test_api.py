import http.client
import io
import json
import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import api
import auth
import db

CLIENT = "cliente-teste.apps.googleusercontent.com"
EU, OUTRO = "eu@example.com", "intruso@example.com"
ORIGEM = "https://pereirabmd.github.io"
TOKENS = {  # token -> resposta do tokeninfo
    "t" * 30 + "eu": (200, {"aud": CLIENT, "email": EU, "email_verified": "true", "expires_in": "3000"}),
    "t" * 30 + "outro": (200, {"aud": CLIENT, "email": OUTRO, "email_verified": "true", "expires_in": "3000"}),
    "t" * 30 + "alheio": (200, {"aud": "outra-app", "email": EU, "email_verified": "true", "expires_in": "3000"}),
    "t" * 30 + "semmail": (200, {"aud": CLIENT, "email_verified": "false", "expires_in": "3000"}),
    "t" * 30 + "expirado": (200, {"aud": CLIENT, "email": EU, "email_verified": "true", "expires_in": "0"}),
}
BOM = "t" * 30 + "eu"


def fetch_falso(token):
    if token == "t" * 30 + "fora":
        raise auth.Unavailable("sem rede")
    return TOKENS.get(token, (400, {}))


class ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict("os.environ", {"DADOS_DB": str(Path(cls.tmp.name) / "t.db"),
                                                 "BILHETES_DB": str(Path(cls.tmp.name) / "b.db")})
        cls.env.start()
        db.migrate_all()
        cls.settings = api.Settings({"GOOGLE_CLIENT_IDS": CLIENT, "ACL_PESO": EU, "ACL_RTO": EU, "ACL_CONVIDADOS": EU, "ACL_BILHETES": EU, "RATE_IP_POR_MIN": "1000",
                                     "RATE_FALHAS_POR_MIN": "1000"})
        cls.verifier = auth.TokenVerifier({CLIENT}, fetch=fetch_falso)
        cls.srv = api.criar_servidor(cls.settings, cls.verifier, porta=0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.env.stop(); cls.tmp.cleanup()

    def pedir(self, metodo, caminho, corpo=None, token=BOM, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=5)
        h = dict(headers or {})
        if token:
            h["Authorization"] = f"Bearer {token}"
        dados = raw
        if corpo is not None:
            dados = json.dumps(corpo)
            h.setdefault("Content-Type", "application/json")
        c.request(metodo, caminho, body=dados, headers=h)
        r = c.getresponse()
        texto = r.read().decode()
        c.close()
        try:
            return r.status, json.loads(texto) if texto else None, r
        except ValueError:
            return r.status, texto, r


class AuthTest(ApiBase):
    def test_sem_token_401(self):
        s, b, r = self.pedir("GET", "/peso/registos", token=None)
        self.assertEqual(s, 401)
        self.assertIn("Bearer", r.getheader("WWW-Authenticate"))

    def test_token_invalido_alheio_semmail_expirado(self):
        for t in ("x" * 30, "t" * 30 + "alheio", "t" * 30 + "semmail", "t" * 30 + "expirado", "curto"):
            self.assertEqual(self.pedir("GET", "/peso/registos", token=t)[0], 401, t)

    def test_rota_inexistente_sem_auth_nao_revela_nada(self):
        self.assertEqual(self.pedir("GET", "/nao/existe", token=None)[0], 401)

    def test_utilizador_fora_da_acl_403(self):
        self.assertEqual(self.pedir("GET", "/peso/registos", token="t" * 30 + "outro")[0], 403)

    def test_google_em_baixo_e_503_nao_401(self):
        s, _, r = self.pedir("GET", "/peso/registos", token="t" * 30 + "fora")
        self.assertEqual(s, 503)
        self.assertEqual(r.getheader("Retry-After"), "5")

    def test_saude_publica_e_minima(self):
        s, b, _ = self.pedir("GET", "/saude", token=None)
        self.assertEqual((s, b), (200, {"ok": True}))

    def test_token_nunca_aparece_nos_logs(self):
        buf = io.StringIO()
        h = logging.StreamHandler(buf); api.LOG.addHandler(h); api.LOG.setLevel(logging.INFO)
        try:
            self.pedir("GET", "/peso/registos")
            self.pedir("GET", "/peso/registos", token="t" * 30 + "alheio")
        finally:
            api.LOG.removeHandler(h)
        self.assertIn(EU, buf.getvalue())
        self.assertNotIn("t" * 30, buf.getvalue())


class AclTest(unittest.TestCase):
    def test_acl_por_app_a_partir_do_env(self):
        st = api.Settings({"GOOGLE_CLIENT_IDS": "x", "ACL_PESO": " A@x.com , b@x.com ",
                           "ACL_TAREFAS": "a@x.com,c@x.com"})
        self.assertEqual(st.acl["peso"], {"a@x.com", "b@x.com"})
        self.assertEqual(st.acl["tarefas"], {"a@x.com", "c@x.com"})

    def test_app_sem_linha_fica_vazia(self):
        self.assertEqual(api.Settings({"GOOGLE_CLIENT_IDS": "x"}).acl["peso"], set())


class CorsEHeadersTest(ApiBase):
    def test_preflight_origem_permitida(self):
        s, _, r = self.pedir("OPTIONS", "/peso/registos", token=None, headers={"Origin": ORIGEM})
        self.assertEqual(s, 204)
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), ORIGEM)
        self.assertIn("Authorization", r.getheader("Access-Control-Allow-Headers"))

    def test_preflight_origem_estranha_recusada(self):
        s, _, r = self.pedir("OPTIONS", "/peso/registos", token=None, headers={"Origin": "https://evil.example"})
        self.assertEqual(s, 403)
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))

    def test_resposta_so_ecoa_origem_permitida(self):
        _, _, r = self.pedir("GET", "/peso/registos", headers={"Origin": "https://evil.example"})
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))
        _, _, r = self.pedir("GET", "/peso/registos", headers={"Origin": ORIGEM})
        self.assertEqual(r.getheader("Access-Control-Allow-Origin"), ORIGEM)

    def test_headers_de_seguranca(self):
        _, _, r = self.pedir("GET", "/peso/registos")
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.getheader("Server"), "dados")


class PedidoTest(ApiBase):
    def test_tipo_tamanho_e_json(self):
        self.assertEqual(self.pedir("POST", "/peso/registos", raw="{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.pedir("POST", "/peso/registos", raw="{", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.pedir("POST", "/peso/registos", raw="[1]", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.pedir("POST", "/peso/registos", raw='{"peso": NaN}', headers={"Content-Type": "application/json"})[0], 400)
        grande = json.dumps({"peso": 80, "nota": "x" * 20000})
        self.assertEqual(self.pedir("POST", "/peso/registos", raw=grande, headers={"Content-Type": "application/json"})[0], 413)

    def test_metodo_e_rota(self):
        s, _, r = self.pedir("DELETE", "/peso/config")
        self.assertEqual(s, 405)
        self.assertEqual(r.getheader("Allow"), "GET, PUT")
        self.assertEqual(self.pedir("GET", "/peso/nada")[0], 404)
        self.assertEqual(self.pedir("PATCH", "/peso/registos")[0], 405)

    def test_rate_limit_por_ip(self):
        lim = api.RateLimiter(3)
        self.assertEqual([lim.allow("a") for _ in range(5)], [True, True, True, False, False])
        self.assertTrue(lim.allow("b"))


class PesoTest(ApiBase):
    def test_crud_completo(self):
        s, criado, _ = self.pedir("POST", "/peso/registos", {"quando": "2026-09-01 08:00:00", "peso": 80.5, "nota": " ok "})
        self.assertEqual(s, 201)
        self.assertEqual(criado["nota"], "ok")
        rid = criado["id"]
        s, b, _ = self.pedir("GET", "/peso/registos?desde=2026-09-01&ate=2026-09-01")
        self.assertEqual([r["id"] for r in b["registos"]], [rid])
        s, b, _ = self.pedir("PUT", f"/peso/registos/{rid}", {"quando": "2026-09-01 09:00:00", "peso": 79.9, "nota": ""})
        self.assertEqual((s, b["peso"]), (200, 79.9))
        s, apagado, _ = self.pedir("DELETE", f"/peso/registos/{rid}")
        self.assertEqual((s, apagado["id"]), (200, rid))
        self.assertEqual(self.pedir("DELETE", f"/peso/registos/{rid}")[0], 404)
        self.assertEqual(self.pedir("PUT", f"/peso/registos/{rid}", {"quando": "2026-09-01 09:00:00", "peso": 1, "nota": ""})[0], 404)

    def test_post_idempotente_com_cid(self):
        corpo = {"quando": "2026-09-02 08:00:00", "peso": 81, "cid": "abcd-1234-efgh"}
        s1, b1, _ = self.pedir("POST", "/peso/registos", corpo)
        s2, b2, _ = self.pedir("POST", "/peso/registos", corpo)
        self.assertEqual((s1, s2, b1["id"] == b2["id"]), (201, 200, True))
        _, lista, _ = self.pedir("GET", "/peso/registos?desde=2026-09-02&ate=2026-09-02")
        self.assertEqual(len(lista["registos"]), 1)

    def test_validacao(self):
        casos = [
            {"peso": 0}, {"peso": -5}, {"peso": "80"}, {"peso": True}, {"peso": 1e9}, {},
            {"peso": 80, "quando": "ontem"}, {"peso": 80, "quando": "2026-13-45 99:99:99"},
            {"peso": 80, "nota": 5}, {"peso": 80, "nota": "x" * 501}, {"peso": 80, "extra": 1},
            {"peso": 80, "cid": "curto"}, {"peso": 80, "cid": "a" * 8 + "'; DROP TABLE x;--"},
        ]
        for c in casos:
            self.assertEqual(self.pedir("POST", "/peso/registos", c)[0], 400, c)
        for q in ("desde=abc", "ate=2026-1-1", "desde=2026-01-01'%20OR%201=1"):
            self.assertEqual(self.pedir("GET", "/peso/registos?" + q)[0], 400, q)

    def test_sql_injection_fica_como_texto(self):
        s, b, _ = self.pedir("POST", "/peso/registos", {"quando": "2026-09-03 08:00:00", "peso": 70,
                                                       "nota": "x'); DROP TABLE peso_registos;--"})
        self.assertEqual(s, 201)
        _, lista, _ = self.pedir("GET", "/peso/registos?desde=2026-09-03&ate=2026-09-03")
        self.assertIn("DROP TABLE", lista["registos"][0]["nota"])

    def test_importar_em_lote_idempotente_e_isola_invalidos(self):
        itens = [{"quando": "2025-01-0%d 07:00:00" % d, "peso": 90 + d, "nota": "", "cid": f"imp-00000{d}"} for d in range(1, 4)]
        itens.append({"quando": "lixo", "peso": 90, "cid": "imp-000009"})
        itens.append({"quando": "2025-01-09 07:00:00", "peso": 0, "cid": "imp-000010"})
        itens.append({"quando": "2025-01-09 07:00:00", "peso": 90})  # sem cid
        s, b, _ = self.pedir("POST", "/peso/importar", {"registos": itens})
        self.assertEqual((s, b["criados"], b["existentes"], len(b["rejeitados"])), (200, 3, 0, 3))
        s, b, _ = self.pedir("POST", "/peso/importar", {"registos": itens})
        self.assertEqual((b["criados"], b["existentes"]), (0, 3))
        _, lista, _ = self.pedir("GET", "/peso/registos?desde=2025-01-01&ate=2025-01-31")
        self.assertEqual(len(lista["registos"]), 3)

    def test_importar_limites(self):
        self.assertEqual(self.pedir("POST", "/peso/importar", {"registos": []})[0], 400)
        self.assertEqual(self.pedir("POST", "/peso/importar", {"registos": "x"})[0], 400)
        muitos = [{"quando": "2025-02-01 07:00:00", "peso": 80, "cid": f"imp-{i:06d}"} for i in range(101)]
        self.assertEqual(self.pedir("POST", "/peso/importar", {"registos": muitos})[0], 400)
        cem = muitos[:100]
        self.assertEqual(len(json.dumps({"registos": cem})) < api.MAX_BODY, True)

    def test_config(self):
        s, b, _ = self.pedir("PUT", "/peso/config", {"altura": 180, "sexo": "M", "diaControlo": 2, "nascimento": "1990-05-01"})
        self.assertEqual((s, b["altura"], b["diaControlo"], b["sexo"]), (200, 180.0, 2, "M"))
        self.assertEqual(self.pedir("PUT", "/peso/config", {"altura": 10})[0], 400)
        self.assertEqual(self.pedir("PUT", "/peso/config", {"sexo": "X"})[0], 400)
        self.assertEqual(self.pedir("PUT", "/peso/config", {"diaControlo": 9})[0], 400)
        self.assertEqual(self.pedir("PUT", "/peso/config", {"nome": "x"})[0], 400)
        # tudo-ou-nada: um valor mau não deixa gravar os bons
        self.assertEqual(self.pedir("PUT", "/peso/config", {"pesoAlvo": 75, "sexo": "X"})[0], 400)
        _, atual, _ = self.pedir("GET", "/peso/config")
        self.assertNotIn("pesoAlvo", atual)
        s, b, _ = self.pedir("PUT", "/peso/config", {"altura": None})
        self.assertNotIn("altura", b)


class VerificadorTest(unittest.TestCase):
    def test_cache_e_expiracao(self):
        chamadas, t = [], [1000.0]

        def fetch(tok):
            chamadas.append(tok)
            return TOKENS.get(tok, (400, {}))
        v = auth.TokenVerifier({CLIENT}, fetch=fetch, now=lambda: t[0], ok_ttl=300)
        self.assertEqual(v.verify(BOM), EU)
        self.assertEqual(v.verify(BOM), EU)
        self.assertEqual(len(chamadas), 1)
        t[0] += 301
        v.verify(BOM)
        self.assertEqual(len(chamadas), 2)

    def test_token_invalido_tambem_e_cacheado(self):
        chamadas = []
        v = auth.TokenVerifier({CLIENT}, fetch=lambda tok: (chamadas.append(tok), (400, {}))[1], bad_ttl=60)
        for _ in range(3):
            with self.assertRaises(auth.Unauthorized):
                v.verify("z" * 40)
        self.assertEqual(len(chamadas), 1)

    def test_cache_com_limite(self):
        v = auth.TokenVerifier({CLIENT}, fetch=lambda tok: (400, {}), cache_max=5)
        for i in range(50):
            with self.assertRaises(auth.Unauthorized):
                v.verify(f"{i:040d}")
        self.assertLessEqual(len(v._cache), 5)

    def test_google_indisponivel_nao_e_cacheado(self):
        estado = {"n": 0}

        def fetch(tok):
            estado["n"] += 1
            if estado["n"] == 1:
                raise auth.Unavailable("x")
            return TOKENS[BOM]
        v = auth.TokenVerifier({CLIENT}, fetch=fetch)
        with self.assertRaises(auth.Unavailable):
            v.verify(BOM)
        self.assertEqual(v.verify(BOM), EU)

    def test_token_vai_no_corpo_e_nao_no_url(self):
        visto = {}

        class R:
            status = 200
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s, n): return json.dumps(TOKENS[BOM][1]).encode()

        def falso(req, timeout):
            visto["url"], visto["corpo"] = req.full_url, req.data
            return R()
        with mock.patch("urllib.request.urlopen", falso):
            auth._fetch_google(BOM)
        self.assertNotIn(BOM, visto["url"])
        self.assertIn(BOM.encode(), visto["corpo"])


if __name__ == "__main__":
    unittest.main()
