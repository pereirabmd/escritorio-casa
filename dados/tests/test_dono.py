"""Peso e RTO por pessoa (ADR-063): cada conta vê e escreve só o que é seu; o acesso por módulo pode ser delegado ao Pulse."""
import threading
import unittest

import api
import db
from tests.test_api import ApiBase, CHAVE, CLIENT, EU, OUTRO

TOKEN_OUTRO = "t" * 30 + "outro"


class DonoTest(ApiBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv.shutdown(); cls.srv.server_close()
        cls.settings = api.Settings({"GOOGLE_CLIENT_IDS": CLIENT, "ACL_PESO": f"{EU},{OUTRO}", "ACL_RTO": f"{EU},{OUTRO}",
                                     "PULSE_SERVICE_KEY": CHAVE, "PULSE_ACL_DELEGADA": "1", "RATE_IP_POR_MIN": "1000", "RATE_FALHAS_POR_MIN": "1000"})
        cls.srv = api.criar_servidor(cls.settings, cls.verifier, porta=0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    def meu(self, *a, **k):
        return self.pedir(*a, **k)

    def dela(self, metodo, caminho, corpo=None):
        return self.pedir(metodo, caminho, corpo, token=TOKEN_OUTRO)

    # --- peso -------------------------------------------------------------------------------------------------------------------
    def test_peso_so_ve_os_seus_registos(self):
        s, r, _ = self.meu("POST", "/peso/registos", {"quando": "2031-01-01 08:00:00", "peso": 80})
        self.assertEqual(s, 201)
        self.dela("POST", "/peso/registos", {"quando": "2031-01-01 08:00:00", "peso": 60})
        self.assertEqual([x["peso"] for x in self.meu("GET", "/peso/registos?desde=2031-01-01&ate=2031-01-01")[1]["registos"]], [80])
        self.assertEqual([x["peso"] for x in self.dela("GET", "/peso/registos?desde=2031-01-01&ate=2031-01-01")[1]["registos"]], [60])

    def test_peso_nao_edita_nem_apaga_o_de_outra_pessoa(self):
        _, r, _ = self.meu("POST", "/peso/registos", {"quando": "2031-02-01 08:00:00", "peso": 81})
        self.assertEqual(self.dela("PUT", f"/peso/registos/{r['id']}", {"quando": "2031-02-01 08:00:00", "peso": 1, "nota": ""})[0], 404)
        self.assertEqual(self.dela("DELETE", f"/peso/registos/{r['id']}")[0], 404)
        self.assertEqual([x["peso"] for x in self.meu("GET", "/peso/registos?desde=2031-02-01&ate=2031-02-01")[1]["registos"]], [81])

    def test_peso_cid_repetido_so_devolve_o_proprio(self):
        cid = "cid-de-teste-dono-01"
        self.assertEqual(self.meu("POST", "/peso/registos", {"quando": "2031-03-01 08:00:00", "peso": 82, "cid": cid})[0], 201)
        self.assertEqual(self.meu("POST", "/peso/registos", {"quando": "2031-03-01 08:00:00", "peso": 82, "cid": cid})[0], 200)       # repetição: o mesmo
        s, b, _ = self.dela("POST", "/peso/registos", {"quando": "2031-03-01 09:00:00", "peso": 55, "cid": cid})
        self.assertNotEqual((s, b.get("peso")), (200, 82))                                                                              # nunca devolve o registo de outra pessoa

    def test_peso_config_por_pessoa(self):
        self.meu("PUT", "/peso/config", {"altura": 180})
        self.dela("PUT", "/peso/config", {"altura": 165})
        self.assertEqual(self.meu("GET", "/peso/config")[1]["altura"], 180)
        self.assertEqual(self.dela("GET", "/peso/config")[1]["altura"], 165)

    # --- rto --------------------------------------------------------------------------------------------------------------------
    def test_rto_dias_por_pessoa(self):
        self.meu("PUT", "/rto/dias/2031-05-05", {"marca": "T"})
        self.dela("PUT", "/rto/dias/2031-05-05", {"marca": "C"})
        self.assertEqual(self.meu("GET", "/rto/dias?desde=2031-05-01&ate=2031-05-31")[1]["dias"], {"2031-05-05": "T"})
        self.assertEqual(self.dela("GET", "/rto/dias?desde=2031-05-01&ate=2031-05-31")[1]["dias"], {"2031-05-05": "C"})
        self.dela("PUT", "/rto/dias/2031-05-05", {"marca": ""})                                                                         # limpar o dela não toca no meu
        self.assertEqual(self.meu("GET", "/rto/dias?desde=2031-05-01&ate=2031-05-31")[1]["dias"], {"2031-05-05": "T"})

    def test_rto_notas_por_pessoa_e_id_alheio_e_404(self):
        _, n, _ = self.meu("POST", "/rto/notas", {"dataInicio": "2031-06-01", "categoria": "Férias", "descricao": "minhas"})
        self.assertEqual([x["descricao"] for x in self.dela("GET", "/rto/notas")[1]["notas"] if x["descricao"] == "minhas"], [])
        corpo = {"dataInicio": "2031-06-01", "categoria": "Férias", "descricao": "roubada"}
        self.assertEqual(self.dela("PUT", f"/rto/notas/{n['id']}", corpo)[0], 404)                # o upsert por id não sobrepõe nem recria a de outra pessoa
        self.assertEqual(self.dela("DELETE", f"/rto/notas/{n['id']}")[0], 404)
        self.assertEqual([x["descricao"] for x in self.meu("GET", "/rto/notas")[1]["notas"] if x["id"] == n["id"]], ["minhas"])

    # --- acesso delegado ao Pulse --------------------------------------------------------------------------------------------------
    def test_pedidos_do_pulse_nao_passam_pela_lista_mas_os_do_token_google_sim(self):
        h = {"X-Pulse-Key": CHAVE, "X-Pulse-User": "nova@exemplo.pt"}
        self.assertEqual(self.pedir("GET", "/peso/registos", token=None, headers=h)[0], 200)        # quem decide é o Pulse
        self.assertEqual(self.pedir("GET", "/peso/registos", token=None, headers=h)[1], {"registos": []})   # e uma pessoa nova não vê nada de ninguém
        self.assertEqual(self.pedir("GET", "/rto/dias", token=None, headers=h)[0], 200)                # qualquer módulo
        self.assertEqual(self.pedir("GET", "/peso/registos", token="t" * 30 + "alheio")[0], 401)   # token de outra app continua recusado


class AdocaoTest(unittest.TestCase):
    def test_orfaos_passam_para_o_dono_inicial_sem_pisar_os_de_ninguem(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            conn = db.connect(Path(d) / "t.db"); db.migrate(conn)
            conn.execute("INSERT INTO peso_registos (quando, peso, cid) VALUES ('2031-01-01 08:00:00', 80, 'cid-orfao-0001')")
            conn.execute("INSERT INTO peso_registos (quando, peso, cid, dono) VALUES ('2031-01-02 08:00:00', 60, 'cid-dela-00001', 'outra@x.pt')")
            conn.execute("INSERT INTO peso_config (chave, valor) VALUES ('altura', '180')")
            conn.execute("INSERT INTO rto_dias (data, marca) VALUES ('2031-01-01', 'T')")
            conn.execute("INSERT INTO rto_notas (categoria, descricao) VALUES ('Férias', 'x')")
            self.assertEqual(db.contar_orfaos(conn), 4)
            self.assertEqual(db.adotar_orfaos(conn, "Eu@X.pt"), 4)
            self.assertEqual(db.contar_orfaos(conn), 0)
            self.assertEqual(db.adotar_orfaos(conn, "eu@x.pt"), 0)                                   # idempotente
            self.assertEqual({r[0] for r in conn.execute("SELECT dono FROM peso_registos")}, {"eu@x.pt", "outra@x.pt"})
            self.assertEqual(db.adotar_orfaos(conn, ""), 0)
            conn.close()


if __name__ == "__main__":
    unittest.main()
