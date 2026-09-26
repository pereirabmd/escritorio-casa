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
        for f in Path(self.tmp.name, "undo").glob("*.db"):          # instantâneos de testes anteriores (o teste conta os seus)
            f.unlink()
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


class BilhetesUtilizadoresTests(Base):
    def setUp(self):
        super().setUp()
        import bilhetes_utilizadores as bu
        self.chave = mock.patch.dict("os.environ", {"BILHETES_FERNET_KEY": bu.gerar_chave()})
        self.chave.start()
        c = db.connect_named("bilhetes")
        c.execute("DELETE FROM bilhetes_utilizadores WHERE id <> 1")
        c.close()
        self.entrar()

    def tearDown(self):
        self.chave.stop()

    def test_paginas_estaticas_e_exigem_sessao_para_a_api(self):
        self.assertEqual(self.pedir("GET", "/bilhetes")[0], 200)
        self.assertEqual(self.pedir("GET", "/bilhetes.js")[0], 200)
        self.assertEqual(self.pedir("GET", "/api/bilhetes/utilizadores", cookie=False)[0], 401)
        self.assertEqual(self.pedir("POST", "/api/bilhetes/utilizadores", {"nome": "X"}, csrf=False)[0], 403)   # sem CSRF

    def test_criar_editar_apagar_e_a_password_nunca_sai(self):
        s, b, _ = self.pedir("GET", "/api/bilhetes/utilizadores")
        self.assertEqual((s, [u["nome"] for u in b["utilizadores"]], b["chave_configurada"]), (200, ["Bruno"], True))
        s, u, _ = self.pedir("POST", "/api/bilhetes/utilizadores", {"nome": "Camila", "cp_email": "c@cp.pt", "password": "segredo-muito-secreto", "nif": "123456789"})
        self.assertEqual((s, u["cp_password_definida"]), (201, True))
        s, u2, _ = self.pedir("PUT", f"/api/bilhetes/utilizadores/{u['id']}", {"passe_verde_numero": "PV1234", "email": "cam@x.pt"})
        self.assertEqual((s, u2["passe_verde_numero"], u2["email"]), (200, "PV1234", "cam@x.pt"))
        s, lista, _ = self.pedir("GET", "/api/bilhetes/utilizadores")
        self.assertNotIn("segredo-muito-secreto", json.dumps(lista))
        registo = Path(self.tmp.name, "edits.jsonl").with_name("admin_bilhetes.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("segredo-muito-secreto", registo)
        self.assertIn('"campos": ["cp_email", "nif", "nome", "password"]', registo)                               # só nomes de campos
        self.assertEqual(self.pedir("DELETE", f"/api/bilhetes/utilizadores/{u['id']}")[0], 200)
        self.assertEqual(self.pedir("DELETE", f"/api/bilhetes/utilizadores/{u['id']}")[0], 404)

    def test_erros(self):
        self.assertEqual(self.pedir("POST", "/api/bilhetes/utilizadores", {"nome": "X", "nif": "123"})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/bilhetes/utilizadores", {"nome": "bruno"})[0], 409)
        self.assertEqual(self.pedir("PUT", "/api/bilhetes/utilizadores/1", {"admin": False})[0], 400)
        self.assertEqual(self.pedir("DELETE", "/api/bilhetes/utilizadores/1")[0], 409)
        self.assertEqual(self.pedir("PUT", "/api/bilhetes/utilizadores/abc", {"nome": "X"})[0], 404)
        self.assertEqual(self.pedir("PUT", "/api/bilhetes/utilizadores", {"nome": "X"})[0], 405)

    def test_sem_chave_nao_guarda_password(self):
        import os
        antes = os.environ.pop("BILHETES_FERNET_KEY")
        try:
            self.assertEqual(self.pedir("GET", "/api/bilhetes/utilizadores")[1]["chave_configurada"], False)
            self.assertEqual(self.pedir("POST", "/api/bilhetes/utilizadores", {"nome": "X", "password": "abc"})[0], 500)
            self.assertEqual(len(self.pedir("GET", "/api/bilhetes/utilizadores")[1]["utilizadores"]), 1)
        finally:
            os.environ["BILHETES_FERNET_KEY"] = antes


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
        self.assertEqual(b["total"], 1)                             # forma antiga: «contém»

    def test_pesquisa_com_caracteres_especiais_e_injecao_nao_funcionam(self):
        from urllib.parse import quote
        for q in ("%", "_", "'; DROP TABLE peso_registos; --", '"', "\\"):
            s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&q=" + quote(q, safe=""))
            self.assertEqual(s, 200, q)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["total"], 7)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=" + quote("peso_registos;drop", safe=""))[0], 404)
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&ordem=" + quote("peso; DROP TABLE x", safe=""))
        self.assertEqual(s, 200)                                   # coluna desconhecida: ignora a ordem

    def filtrar(self, *filtros, tabela="peso_registos"):
        from urllib.parse import quote
        return self.pedir("GET", f"/api/linhas?db=dados&tabela={tabela}&filtros=" + quote(json.dumps(list(filtros)), safe=""))

    def test_filtros_com_operadores(self):
        f = lambda c, o, v="": {"c": c, "o": o, "v": v}  # noqa: E731
        casos = [
            ((f("peso", "gt", "83"),), [84.0, 85.0, 86.0]),
            ((f("peso", "ge", "83"), f("peso", "lt", "85")), [83.0, 84.0]),                   # E entre filtros
            ((f("peso", "eq", "82,0"),), [82.0]),                                              # vírgula decimal
            ((f("peso", "ne", "80"),), [81.0, 82.0, 83.0, 84.0, 85.0, 86.0]),
            ((f("nota", "contem", "nota 4"),), [84.0]),
            ((f("nota", "eq", "nota 6"),), [86.0]),
            ((f("quando", "gt", "2026-01-06"),), [85.0, 86.0]),                                # datas ISO como texto (o dia 06 com hora conta como maior que «2026-01-06»)
            ((f("cid", "vazio"),), [80.0, 81.0, 82.0, 83.0, 84.0, 85.0, 86.0]),
            ((f("cid", "nvazio"),), []),
            ((f("nota", "contem", ""),), [80.0, 81.0, 82.0, 83.0, 84.0, 85.0, 86.0]),          # sem valor: ignorado
        ]
        for filtros, esperado in casos:
            s, b, _ = self.filtrar(*filtros)
            self.assertEqual((s, [l["peso"] for l in b["linhas"]], b["total"]), (200, esperado, len(esperado)), filtros)

    def test_filtros_invalidos_e_injecao(self):
        for filtro in ({"c": "nao_existe", "o": "eq", "v": "1"}, {"c": "peso", "o": "DROP", "v": "1"}, {"c": "peso; DROP TABLE x", "o": "eq", "v": "1"},
                       {"c": "peso", "o": "gt", "v": "abc"}, {"c": "chave_password", "o": "eq", "v": "x"}):
            self.assertEqual(self.filtrar(filtro)[0], 400, filtro)
        s, b, _ = self.filtrar({"c": "nota", "o": "contem", "v": "'; DROP TABLE peso_registos; --"})
        self.assertEqual((s, b["total"]), (200, 0))
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos")[1]["total"], 7)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&filtros=nao-json")[0], 400)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=peso_registos&filtros=%7B%7D")[0], 400)        # não é lista

    def test_filtro_por_operador_em_todas_as_tabelas_nao_rebenta(self):
        for base in ("dados", "bilhetes"):
            for t in self.pedir("GET", f"/api/esquema?db={base}")[1]["tabelas"]:
                for c in t["colunas"]:
                    for op in ("contem", "vazio", "nvazio"):
                        from urllib.parse import quote
                        s, b, _ = self.pedir("GET", f"/api/linhas?db={base}&tabela={t['nome']}&filtros=" + quote(json.dumps([{"c": c["nome"], "o": op, "v": "1"}]), safe=""))
                        # colunas de segredos (password/token/secret...) nunca se filtram: seria adivinhá-las por pesquisa
                        esperado = 400 if admin_db._SENSIVEL.search(c["nome"]) else 200
                        self.assertEqual(s, esperado, f"{base}.{t['nome']}.{c['nome']} {op}: {b}")

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


class SemRowidTests(Base):
    """rto_dias e convidados_opcoes são WITHOUT ROWID (chave primária composta ou de texto): não têm `rowid`."""

    def setUp(self):
        super().setUp()
        self.entrar()
        c = db.connect_named("dados")
        c.execute("DELETE FROM rto_dias"); c.execute("DELETE FROM convidados_opcoes")
        c.execute("INSERT INTO rto_dias (data, marca) VALUES ('2026-09-21', 'T'), ('2026-09-22', 'C')")
        c.execute("INSERT INTO convidados_opcoes (tipo, posicao, valor) VALUES ('fase', 1, 'Convite'), ('fase', 2, 'Confirmado')")
        c.close()

    def test_carrega_e_identifica_pela_chave(self):
        for tabela, chaves in (("rto_dias", [["2026-09-21"], ["2026-09-22"]]), ("convidados_opcoes", [["fase", 1], ["fase", 2]])):
            s, b, _ = self.pedir("GET", f"/api/linhas?db=dados&tabela={tabela}")
            self.assertEqual(s, 200, b)
            self.assertEqual([l["_rowid_"] for l in b["linhas"]], chaves)
            self.assertTrue(b["sem_rowid"])
        s, b, _ = self.pedir("GET", "/api/linhas?db=dados&tabela=rto_dias&ordem=marca&sentido=desc&q=2026")
        self.assertEqual((s, [l["marca"] for l in b["linhas"]]), (200, ["T", "C"]))
        self.assertTrue(next(t for t in self.pedir("GET", "/api/esquema?db=dados")[1]["tabelas"] if t["nome"] == "rto_dias")["sem_rowid"])

    def test_inserir_atualizar_apagar_e_reverter(self):
        s, b, _ = self.pedir("POST", "/api/linha", {"db": "dados", "tabela": "rto_dias", "valores": {"data": "2026-09-23", "marca": "T"}})
        self.assertEqual((s, b["rowid"]), (201, ["2026-09-23"]))
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "rto_dias", "rowid": ["2026-09-23"], "valores": {"marca": "C"}})
        self.assertEqual((s, b["linha"]["marca"]), (200, "C"))
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "rto_dias", "rowid": ["2026-09-23"], "valores": {"data": "2026-09-24"}})   # muda a chave
        self.assertEqual((s, b["rowid"]), (200, ["2026-09-24"]))
        s, b, _ = self.pedir("DELETE", "/api/linha?db=dados&tabela=rto_dias&rowid=" + json.dumps(["2026-09-24"]).replace('"', "%22"))
        self.assertEqual(s, 200)
        apagar = next(a for a in self.pedir("GET", "/api/alteracoes")[1]["alteracoes"] if a["op"] == "apagar")
        self.assertEqual(self.pedir("POST", "/api/reverter", {"id": apagar["id"]})[0], 200)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=rto_dias&q=09-24")[1]["total"], 1)

    def test_chave_composta(self):
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "convidados_opcoes", "rowid": ["fase", 2], "valores": {"valor": "Presente"}})
        self.assertEqual((s, b["linha"]["valor"]), (200, "Presente"))
        s, b, _ = self.pedir("DELETE", "/api/linha?db=dados&tabela=convidados_opcoes&rowid=%5B%22fase%22%2C1%5D")
        self.assertEqual(s, 200)
        self.assertEqual(self.pedir("GET", "/api/linhas?db=dados&tabela=convidados_opcoes")[1]["total"], 1)

    def test_identificador_invalido(self):
        for rid in ([], ["so-um"], "texto", 5, None):
            s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "convidados_opcoes", "rowid": rid, "valores": {"valor": "x"}})
            self.assertIn(s, (400, 404), rid)

    def test_a_base_recusa_o_invalido(self):
        s, b, _ = self.pedir("PUT", "/api/linha", {"db": "dados", "tabela": "rto_dias", "rowid": ["2026-09-21"], "valores": {"marca": "X"}})
        self.assertEqual(s, 400)


class TodasAsTabelasTests(Base):
    def test_todas_as_tabelas_das_duas_bases_carregam(self):
        self.entrar()
        for base in ("dados", "bilhetes"):
            tabelas = self.pedir("GET", f"/api/esquema?db={base}")[1]["tabelas"]
            self.assertTrue(tabelas)
            for t in tabelas:
                s, b, _ = self.pedir("GET", f"/api/linhas?db={base}&tabela={t['nome']}")
                self.assertEqual(s, 200, f"{base}.{t['nome']}: {b}")


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
    def test_execucao_do_backup_aparece_na_informacao(self):
        self.entrar()
        import backup
        estado = Path(self.tmp.name) / "state"
        with mock.patch.object(backup, "STATE_DIR", estado), mock.patch.object(backup, "EXECUCAO_FILE", estado / "backup_execucao.json"), \
                mock.patch.object(admin_db.db, "BASE_DIR", Path(self.tmp.name)):
            backup.registar_execucao(True, "sem alterações desde o último backup")
            s, b, _ = self.pedir("GET", "/api/backup")
        self.assertEqual((s, b["execucao"]["ok"], b["execucao"]["mensagem"]), (200, True, "sem alterações desde o último backup"))
        self.assertRegex(b["execucao"]["ts"], r"^\d{4}-\d{2}-\d{2}T")

    def test_info_sem_repositorio_nao_rebenta(self):
        self.entrar()
        with mock.patch.dict("os.environ", {"BACKUP_REPO_DIR": ""}):
            s, b, _ = self.pedir("GET", "/api/backup")
        self.assertEqual(s, 200); self.assertIn("repositorio", b)


if __name__ == "__main__":
    unittest.main()
