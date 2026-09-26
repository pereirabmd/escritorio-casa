import sqlite3
import tempfile
import unittest
from pathlib import Path

import db
import bilhetes_utilizadores as bu

CHAVE = bu.gerar_chave()


class BilhetesUtilizadoresTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conn = db.connect(self.dir / "b.db")
        db.migrate(self.conn, db.BASE_DIR / "migrations_bilhetes")
        import os
        self._antes = os.environ.get("BILHETES_FERNET_KEY")
        os.environ["BILHETES_FERNET_KEY"] = CHAVE

    def tearDown(self):
        import os
        if self._antes is None:
            os.environ.pop("BILHETES_FERNET_KEY", None)
        else:
            os.environ["BILHETES_FERNET_KEY"] = self._antes
        self.conn.close(); self.tmp.cleanup()

    def erro(self, fn, *a):
        with self.assertRaises(bu.UtilizadorErro) as c:
            fn(*a)
        return c.exception

    # -- modelo -----------------------------------------------------------
    def test_migracao_cria_o_bruno_como_admin_com_o_passe_atual(self):
        self.conn.execute("UPDATE bilhetes_passe SET data_ultima_compra='2026-09-21' WHERE id=1")   # o gatilho espelha
        b = bu.obter(self.conn, 1)
        self.assertEqual((b["nome"], b["admin"], b["ativo"], b["passe_data_ultima_compra"], b["passe_validade_dias"]),
                         ("Bruno", True, True, "2026-09-21", 29))

    def test_dados_existentes_e_novos_sem_dono_ficam_do_utilizador_1_e_o_dono_tem_de_existir(self):
        self.conn.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora) VALUES ('2031-01-01','A','B',1,'08:00')")
        self.assertEqual(self.conn.execute("SELECT utilizador_id FROM bilhetes_viagens").fetchone()[0], 1)
        for tabela, cols, vals in [("bilhetes_viagens", "data, origem, destino, comboio, hora, utilizador_id", "'2031-01-01','A','B',1,'08:00',99"),
                                   ("bilhetes_pedidos", "data, utilizador_id", "'2031-01-01',99"),
                                   ("bilhetes_compras", "data, utilizador_id", "'2031-01-01',99")]:
            with self.assertRaises(sqlite3.IntegrityError, msg=tabela):
                self.conn.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({vals})")
        # um registo nunca falha por causa do dono
        self.conn.execute("INSERT INTO bilhetes_logs (ts, utilizador_id) VALUES ('2031-01-01 10:00:00', 99)")

    def test_utilizador_com_dados_ou_o_bruno_nao_se_apagam(self):
        ana = bu.criar(self.conn, {"nome": "Camila"})
        self.conn.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, utilizador_id) VALUES ('2031-01-01','A','B',1,'08:00',?)", (ana["id"],))
        self.assertEqual(self.erro(bu.apagar, self.conn, ana["id"]).status, 409)
        self.assertEqual(self.erro(bu.apagar, self.conn, 1).status, 409)
        outro = bu.criar(self.conn, {"nome": "Davi"})
        self.assertEqual(bu.apagar(self.conn, outro["id"])["nome"], "Davi")
        self.assertEqual(self.erro(bu.apagar, self.conn, outro["id"]).status, 404)

    # -- CRUD e segredos --------------------------------------------------
    def test_criar_e_atualizar_sem_expor_a_password(self):
        u = bu.criar(self.conn, {"nome": "Camila", "email": "Camila@Exemplo.PT", "cp_email": "c@cp.pt", "password": "segredo-123",
                                 "nif": "123456789", "passe_verde_numero": "PV 12345", "passageiro_cc": "12345678 9 zz0", "passageiro_telemovel": "912 345 678"})
        self.assertEqual((u["email"], u["nif"], u["passe_verde_numero"], u["passageiro_cc"], u["passageiro_telemovel"], u["cp_password_definida"]),
                         ("camila@exemplo.pt", "123456789", "PV12345", "123456789ZZ0", "912345678", True))
        self.assertEqual({k for k in u if "password" in k}, {"cp_password_definida"})    # nem a cifrada sai, só se está definida
        self.assertNotIn("segredo-123", str(bu.listar(self.conn)))
        guardado = self.conn.execute("SELECT cp_password_enc FROM bilhetes_utilizadores WHERE id=?", (u["id"],)).fetchone()[0]
        self.assertNotIn("segredo-123", guardado)
        self.assertEqual(bu.decifrar(guardado), "segredo-123")
        # sem password no pedido = não muda; com password = muda; limpar = apaga
        nov, campos = bu.atualizar(self.conn, u["id"], {"nif": "", "password": ""})
        self.assertEqual((nov["nif"], campos, nov["cp_password_definida"]), ("", ["nif"], True))
        self.assertEqual(bu.atualizar(self.conn, u["id"], {"password": "outra"})[1], ["cp_password"])
        self.assertEqual(bu.decifrar(self.conn.execute("SELECT cp_password_enc FROM bilhetes_utilizadores WHERE id=?", (u["id"],)).fetchone()[0]), "outra")
        self.assertFalse(bu.atualizar(self.conn, u["id"], {"limpar_password": True})[0]["cp_password_definida"])

    def test_sem_chave_recusa_guardar_password(self):
        import os
        os.environ.pop("BILHETES_FERNET_KEY")
        self.assertEqual(self.erro(bu.criar, self.conn, {"nome": "X", "password": "abc"}).status, 500)
        self.assertEqual(len(bu.listar(self.conn)), 1)      # nada ficou criado
        self.assertEqual(bu.criar(self.conn, {"nome": "X"})["nome"], "X")   # sem password não precisa da chave

    def test_validacao(self):
        for dados in [{"nome": ""}, {"nome": "x" * 41}, {"nome": "A", "email": "sem-arroba"}, {"nome": "A", "nif": "123456788"},
                      {"nome": "A", "nif": "12345"}, {"nome": "A", "passageiro_cc": "12"}, {"nome": "A", "passageiro_telemovel": "12"},
                      {"nome": "A", "passe_verde_numero": "ab"}, {"nome": "A", "passe_data_ultima_compra": "2026-02-30"},
                      {"nome": "A", "passe_validade_dias": 0}, {"nome": "A", "admin": "sim"}, {"nome": "A", "cp_email": "x"},
                      {"nome": "A", "password": "x" * 201}, {"nome": "A", "extra": 1}, {}]:
            self.assertEqual(self.erro(bu.criar, self.conn, dados).status, 400, dados)

    def test_nome_e_email_unicos_sem_distinguir_maiusculas(self):
        bu.criar(self.conn, {"nome": "Camila", "email": "c@x.pt"})
        self.assertEqual(self.erro(bu.criar, self.conn, {"nome": "camila"}).status, 409)
        self.assertEqual(self.erro(bu.criar, self.conn, {"nome": "Outra", "email": "C@X.pt"}).status, 409)
        bu.criar(self.conn, {"nome": "A"}); bu.criar(self.conn, {"nome": "B"})      # vários sem e-mail (NULL) são permitidos

    def test_o_bruno_continua_administrador_e_ativo(self):
        self.assertEqual(self.erro(bu.atualizar, self.conn, 1, {"admin": False}).status, 400)
        self.assertEqual(self.erro(bu.atualizar, self.conn, 1, {"ativo": False}).status, 400)
        self.assertEqual(self.erro(bu.atualizar, self.conn, 99, {"nome": "X"}).status, 404)
        self.assertEqual(self.erro(bu.atualizar, self.conn, 1, {}).status, 400)

    def test_nif(self):
        self.assertTrue(bu.nif_valido("123456789"))
        self.assertFalse(bu.nif_valido("123456788"))
        self.assertFalse(bu.nif_valido("abcdefghi"))

    def test_importar_env_campo_a_campo_e_sem_mostrar_valores(self):
        env = self.dir / ".env"
        env.write_text("# comentário\nCP_EMAIL='b@cp.pt'\nCP_PASSWORD=palavra-passe\nCP_PASSENGER_NAME=Bruno P\nCP_PASSENGER_NIF=111111111\n"
                       "CP_GREEN_PASS_NUMBER=\"9876543\"\nOUTRA=1\n", encoding="utf-8")
        r = bu.importar_env(self.conn, env, 1)
        self.assertEqual(sorted(r["definidos"]), ["cp_email", "cp_password", "passageiro_nome", "passe_verde_numero"])
        self.assertEqual(list(r["ignorados"]), ["nif"])            # NIF inválido: só esse campo é recusado
        self.assertNotIn("palavra-passe", str(r))
        u = bu.obter(self.conn, 1)
        self.assertEqual((u["cp_email"], u["passe_verde_numero"], u["cp_password_definida"]), ("b@cp.pt", "9876543", True))


if __name__ == "__main__":
    unittest.main()
