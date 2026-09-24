"""admin_db: autenticação, só rede local, edição segura (esquema, segredos, restrições), instantâneos, reversão e consola só de leitura."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import admin_db
import db

PW = "uma-password-comprida"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict("os.environ", {"DADOS_DB": str(Path(cls.tmp.name) / "d.db"), "BILHETES_DB": str(Path(cls.tmp.name) / "b.db")})
        cls.env.start()
        db.migrate_all()
        cls.editor = admin_db.Editor(Path(cls.tmp.name) / "undo", Path(cls.tmp.name) / "edits.jsonl")
        cls.estado = admin_db.Estado(admin_db.hash_password(PW, 1000), cls.editor)
        cls.srv = admin_db.criar_servidor(cls.estado, "127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.env.stop(); cls.tmp.cleanup()

    def setUp(self):
        self.estado.falhas.clear()
        self.editor._ultimo_snap.clear()
        c = db.connect_named("dados")
        for t in ("peso_registos", "tarefas_config"):
            c.execute(f"DELETE FROM {t}")
        c.close()
        Path(self.tmp.name, "edits.jsonl").unlink(missing_ok=True)
        self.cookie, self.csrf = None, None

    def pedir(self, metodo, caminho, corpo=None, cookie=True, csrf=True):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=5)
        h = {}
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        if csrf and self.csrf and metodo != "GET":
            h["X-CSRF"] = self.csrf
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo); h["Content-Type"] = "application/json"
        c.request(metodo, caminho, body=dados, headers=h)
        r = c.getresponse(); texto = r.read().decode()
        try:
            corpo_r = json.loads(texto)
        except ValueError:
            corpo_r = texto
        hdr = dict(r.getheaders()); c.close()
        return r.status, corpo_r, hdr

    def entrar(self):
        s, b, h = self.pedir("POST", "/api/login", {"password": PW}, cookie=False)
        self.assertEqual(s, 200, b)
        self.cookie = h["Set-Cookie"].split(";")[0]
        self.csrf = b["csrf"]


class PasswordTests(unittest.TestCase):
    def test_hash_e_verificacao(self):
        h = admin_db.hash_password("segredo-forte", 1000)
        self.assertTrue(admin_db.verificar_password("segredo-forte", h))
        self.assertFalse(admin_db.verificar_password("outra", h))
        for lixo in ("", "x", "a$b$c$d", "pbkdf2_sha256$x$y$z"):
            self.assertFalse(admin_db.verificar_password("x", lixo))

    def test_so_enderecos_privados(self):
        e = admin_db.Estado("x", None)
        for ip in ("192.168.68.10", "10.0.0.5", "172.16.3.4", "127.0.0.1"):
            self.assertTrue(e.ip_permitido(ip), ip)
        for ip in ("8.8.8.8", "82.155.166.140", "lixo", "2001:4860:4860::8888"):
            self.assertFalse(e.ip_permitido(ip), ip)
        so_lan = admin_db.Estado("x", None, ["192.168.68.0/24"])
        self.assertTrue(so_lan.ip_permitido("192.168.68.7")); self.assertFalse(so_lan.ip_permitido("192.168.1.7"))


class AuthTests(Base):
    def test_sem_sessao_tudo_401_e_a_pagina_serve_com_csp(self):
        self.assertEqual(self.pedir("GET", "/api/esquema?db=dados")[0], 401)
        s, corpo, h = self.pedir("GET", "/")
        self.assertEqual(s, 200); self.assertIn("Bases de dados", corpo)
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(self.pedir("GET", "/../admin_db.py")[0], 404)

    def test_login_errado_e_bloqueio(self):
        for _ in range(5):
            self.assertEqual(self.pedir("POST", "/api/login", {"password": "errada"}, cookie=False)[0], 401)
        self.assertEqual(self.pedir("POST", "/api/login", {"password": PW}, cookie=False)[0], 429)   # mesmo a certa: bloqueado

    def test_csrf_obrigatorio_nas_escritas(self):
        self.entrar()
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"quando": "2026-01-01 08:00:00", "peso": "80"}}, csrf=False)
        self.assertEqual(s, 403)

    def test_cookie_httponly_samesite(self):
        _, _, h = self.pedir("POST", "/api/login", {"password": PW}, cookie=False)
        self.assertIn("HttpOnly", h["Set-Cookie"]); self.assertIn("SameSite=Strict", h["Set-Cookie"])


class LeituraTests(Base):
    def setUp(self):
        super().setUp()
        self.entrar()
        c = db.connect_named("dados")
        for i in range(7):
            c.execute("INSERT INTO peso_registos (quando, peso, nota) VALUES (?, ?, ?)", (f"2026-01-0{i+1} 08:00:00", 80 + i, "nota %d" % i))
        c.execute("INSERT INTO tarefas_config (chave, valor) VALUES ('Pessoa1_Nome', 'Bruno'), ('Pessoa1_NtfyPasswordEnc', 'gAAAAsegredocifrado')")
        c.close()

    def test_esquema_lista_tabelas_com_contagens(self):
        s, b, _ = self.pedir("GET", "/api/esquema?db=dados")
        nomes = {t["nome"]: t for t in b["tabelas"]}
        self.assertEqual(s, 200); self.assertEqual(nomes["peso_registos"]["linhas"], 7)
        self.assertNotIn("sqlite_sequence", nomes)
        self.assertIn("peso", [c["nome"] for c in nomes["peso_registos"]["colunas"]])
        self.assertEqual(self.pedir("GET", "/api/esquema?db=bilhetes")[0], 200)
        self.assertEqual(self.pedir("GET", "/api/esquema?db=nao_existe")[0], 400)

    def test_paginacao_ordem_e_pesquisa(self):
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&tamanho=3&pagina=2&ordem=peso&sentido=desc")
        self.assertEqual((b["total"], [l["peso"] for l in b["linhas"]]), (7, [83.0, 82.0, 81.0]))
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&q=nota%204")
        self.assertEqual(b["total"], 1)
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&f.nota=nota%206")
        self.assertEqual(b["total"], 1)

    def test_pesquisa_com_caracteres_especiais_e_injecao_nao_funcionam(self):
        from urllib.parse import quote
        for q in ("%", "_", "'; DROP TABLE peso_registos; --", '"', "\\"):
            s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&q=" + quote(q, safe=""))
            self.assertEqual(s, 200, q)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["total"], 7)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=" + quote("peso_registos;drop", safe=""))[0], 404)
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&ordem=" + quote("peso; DROP TABLE x", safe=""))
        self.assertEqual(s, 200)                                   # coluna desconhecida: ignora a ordem

    def test_segredos_saem_mascarados(self):
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=tarefas_config")
        por_chave = {l["chave"]: l["valor"] for l in b["linhas"]}
        self.assertEqual(por_chave["Pessoa1_Nome"], "Bruno")
        self.assertEqual(por_chave["Pessoa1_NtfyPasswordEnc"], admin_db.MASCARA)
        self.assertNotIn("gAAAA", json.dumps(b))


class EscritaTests(Base):
    def setUp(self):
        super().setUp()
        self.entrar()

    def novo(self, peso="81.5", nota="x"):
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"quando": "2026-02-01 07:30:00", "peso": peso, "nota": nota}})
        self.assertEqual(s, 201, b)
        return b["rowid"]

    def test_inserir_atualizar_apagar(self):
        rid = self.novo()
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "peso_registos", "rowid": rid, "valores": {"peso": "82,25"}})
        self.assertEqual((s, b["linha"]["peso"], b["alterada"]), (200, 82.25, True))       # vírgula decimal
        self.assertEqual(self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "peso_registos", "rowid": rid, "valores": {"peso": "82.25"}})[1]["alterada"], False)
        self.assertEqual(self.pedir("DELETE", f"/api/linha?db=dados&tabela=peso_registos&rowid={rid}")[0], 200)
        self.assertEqual(self.pedir("DELETE", f"/api/linha?db=dados&tabela=peso_registos&rowid={rid}")[0], 404)

    def test_a_base_recusa_o_invalido_e_nada_muda(self):
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"quando": "2026-02-01 07:30:00", "peso": "-5"}})
        self.assertEqual(s, 400); self.assertIn("recusou", b["erro"])
        for quando in ("hoje", "2026-13-40 08:00:00", "2026-02-01 7:30:00", "2026-02-01"):
            s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"quando": quando, "peso": "80"}})
            self.assertEqual((s, "formato" in b["erro"]), (400, True), quando)
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"quando": "2026-02-01 07:30:00", "peso": "abc"}})
        self.assertEqual((s, "número" in b["erro"]), (400, True))
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["total"], 0)

    def test_tabelas_e_colunas_vem_do_esquema(self):
        for corpo in ({"db": "dados", "tabela": "nao_existe", "valores": {"a": "1"}},
                      {"db": "dados", "tabela": "peso_registos; DROP TABLE x", "valores": {"peso": "80"}},
                      {"db": "dados", "tabela": "sqlite_master", "valores": {"name": "x"}}):
            self.assertIn(self.pedir("POST", "/api/linha", corpo)[0], (400, 404), corpo)
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "peso_registos", "valores": {"peso; DROP": "80"}})
        self.assertEqual(s, 400)

    def test_segredos_nao_se_editam_nem_se_criam(self):
        c = db.connect_named("dados")
        c.execute("INSERT INTO tarefas_config (chave, valor) VALUES ('Pessoa1_NtfyPasswordEnc', 'gAAAAx')"); rid = c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.close()
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "tarefas_config", "rowid": rid, "valores": {"valor": "outro"}})
        self.assertEqual(s, 403)
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "tarefas_config", "valores": {"chave": "X_NtfyPasswordEnc", "valor": "y"}})
        self.assertEqual(s, 403)
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "tarefas_config", "valores": {"chave": "Categoria1", "valor": "Limpeza"}})
        self.assertEqual(s, 201)

    def test_instantaneo_e_auditoria(self):
        rid = self.novo()
        snaps = list(Path(self.tmp.name, "undo").glob("dados-*.db"))
        self.assertEqual(len(snaps), 1)
        s, b, _ = self.pedir("GET", "/api/alteracoes")
        self.assertEqual((b["alteracoes"][0]["op"], b["alteracoes"][0]["rowid"]), ("inserir", rid))
        self.assertEqual(len(b["snapshots"]), 1)

    def test_reverter_atualizacao_insercao_e_remocao(self):
        rid = self.novo(peso="80")
        self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "peso_registos", "rowid": rid, "valores": {"peso": "85"}})
        alts = self.pedir("GET", "/api/alteracoes")[1]["alteracoes"]                   # mais recente primeiro
        upd = next(a for a in alts if a["op"] == "atualizar")
        self.assertEqual(self.pedir("POST", "/api/reverter", {"id": upd["id"]})[0], 200)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["linhas"][0]["peso"], 80.0)
        self.assertEqual(self.pedir("POST", "/api/reverter", {"id": upd["id"]})[0], 409)          # já revertida
        self.pedir("DELETE", f"/api/linha?db=dados&tabela=peso_registos&rowid={rid}")
        apagar = next(a for a in self.pedir("GET", "/api/alteracoes")[1]["alteracoes"] if a["op"] == "apagar")
        self.assertEqual(self.pedir("POST", "/api/reverter", {"id": apagar["id"]})[0], 200)
        l = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["linhas"]
        self.assertEqual((len(l), l[0]["_rowid_"], l[0]["peso"]), (1, rid, 80.0))                # mesmo rowid, mesmos valores

    def test_nao_reverte_por_cima_de_alteracoes_posteriores(self):
        rid = self.novo(peso="80")
        self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "peso_registos", "rowid": rid, "valores": {"peso": "85"}})
        primeira = next(a for a in self.pedir("GET", "/api/alteracoes")[1]["alteracoes"] if a["op"] == "atualizar")
        self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "peso_registos", "rowid": rid, "valores": {"peso": "90"}})
        self.assertEqual(self.pedir("POST", "/api/reverter", {"id": primeira["id"]})[0], 409)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["linhas"][0]["peso"], 90.0)


class SqlTests(Base):
    def setUp(self):
        super().setUp()
        self.entrar()
        c = db.connect_named("dados")
        c.execute("INSERT INTO peso_registos (quando, peso) VALUES ('2026-03-01 08:00:00', 80)")
        c.execute("INSERT INTO tarefas_config (chave, valor) VALUES ('Pessoa1_NtfyPasswordEnc', 'gAAAAx')")
        c.close()

    def sql(self, texto):
        return self.pedir("POST", "/api/sql", {"db": "dados", "sql": texto})

    def test_select_funciona(self):
        s, b, _ = self.sql("SELECT quando, peso FROM peso_registos")
        self.assertEqual((s, b["linhas"], b["colunas"]), (200, [["2026-03-01 08:00:00", 80.0]], ["quando", "peso"]))
        self.assertEqual(self.sql("WITH x AS (SELECT 1 AS a) SELECT a FROM x")[0], 200)

    def test_so_leitura(self):
        for texto in ("DELETE FROM peso_registos", "UPDATE peso_registos SET peso=1", "DROP TABLE peso_registos", "INSERT INTO peso_registos (quando, peso) VALUES ('x', 1)",
                      "PRAGMA user_version=9", "ATTACH DATABASE '/tmp/x.db' AS x", "SELECT 1; DELETE FROM peso_registos", "VACUUM"):
            self.assertEqual(self.sql(texto)[0], 400, texto)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["total"], 1)

    def test_colunas_de_segredos_saem_a_null(self):
        s, b, _ = self.sql("SELECT chave, valor FROM tarefas_config")
        self.assertEqual(s, 200)                                  # `valor` não é «sensível» por nome; o valor cifrado sai como está
        s, b, _ = self.pedir("POST", "/api/sql", {"db": "bilhetes", "sql": "SELECT 1 AS token"})
        self.assertEqual(s, 200)

    def test_limite_de_linhas(self):
        s, b, _ = self.sql("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i < 2000) SELECT i FROM n")
        self.assertEqual((len(b["linhas"]), b["truncado"]), (admin_db.SQL_LINHAS_MAX, True))


class BackupTests(Base):
    def test_info_sem_repositorio_nao_rebenta(self):
        self.entrar()
        with mock.patch.dict("os.environ", {"BACKUP_REPO_DIR": ""}):
            s, b, _ = self.pedir("GET", "/api/backup")
        self.assertEqual(s, 200); self.assertIn("repositorio", b)


if __name__ == "__main__":
    unittest.main()
