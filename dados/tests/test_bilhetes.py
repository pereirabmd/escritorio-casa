import json
import sqlite3
import unittest
from datetime import datetime, timedelta

import db
from tests.test_api import ApiBase, EU, OUTRO

INI = "2035-03-05"     # uma segunda-feira, no futuro


def dia(n):
    return (datetime.fromisoformat(INI) + timedelta(days=n)).strftime("%Y-%m-%d")


def viagem(n=0, comboio=731, hora="17:30", org="Lisboa Oriente", dst="Aveiro", ativo="SIM"):
    return {"data": dia(n), "origem": org, "destino": dst, "comboio": comboio, "hora": hora, "ativo": ativo}


class BilhetesApiTest(ApiBase):
    def bd(self):
        return db.connect_named("bilhetes")

    def semana(self, viagens, inicio=INI):
        return self.pedir("PUT", "/bilhetes/semana", {"inicio": inicio, "viagens": viagens})

    def limpar(self):
        c = self.bd(); c.execute("DELETE FROM bilhetes_viagens"); c.execute("DELETE FROM bilhetes_pedidos"); c.close()

    def setUp(self):
        self.limpar()
        c = self.bd()                                       # a conta que pede tem de estar registada nos Bilhetes (ADR-063): aqui é o utilizador 1 (Bruno)
        c.execute("UPDATE bilhetes_utilizadores SET email = ?, admin = 1, ativo = 1 WHERE id = 1", (EU,))
        c.execute("DELETE FROM bilhetes_utilizadores WHERE id > 1"); c.execute("DELETE FROM bilhetes_compras"); c.execute("DELETE FROM bilhetes_logs")
        c.close()

    def test_historico_so_do_administrador_com_o_nome_de_quem_viaja(self):
        hoje = datetime.now().date()
        c = self.bd()
        c.execute("INSERT INTO bilhetes_utilizadores (id, nome, email, ativo) VALUES (2, 'Camila', 'camila@example.com', 1)")
        c.execute("INSERT INTO bilhetes_viagens (id, data, origem, destino, comboio, hora, ativo, utilizador_id) VALUES (102, ?, 'A', 'B', 731, '17:30', 'SIM', 2)", (hoje.isoformat(),))
        c.execute("DELETE FROM bilhetes_tentativas")
        for ts, perna, res in ((f"{hoje}T17:20:00.100+01:00", "v102", "sold_out"), (f"{hoje - timedelta(days=100)}T10:00:00.000+01:00", "v102", "ok")):
            c.execute("INSERT INTO bilhetes_tentativas (ts, data_viagem, perna, comboio, fase, http, resultado, rtt_ms) VALUES (?,?,?,?,?,?,?,?)",
                      (ts, hoje.isoformat(), perna, 731, "retencao", 200, res, 90))
        c.close()
        s, b, _ = self.pedir("GET", "/bilhetes/historico")
        self.assertEqual(s, 200)
        self.assertIsInstance(b["pedidos"][0]["id"], int)
        self.assertEqual([(p["perna"], p["pessoa"], p["resultado"], p["fase"], p["rttMs"]) for p in b["pedidos"]], [("v102", "Camila", "sold_out", "retencao", 90)])
        self.assertEqual(self.pedir("GET", "/bilhetes/historico?dias=91")[0], 400)
        c = self.bd(); c.execute("UPDATE bilhetes_utilizadores SET admin = 0 WHERE id = 1"); c.close()
        self.assertEqual(self.pedir("GET", "/bilhetes/historico")[0], 403)

    def test_acesso(self):
        self.assertEqual(self.pedir("GET", "/bilhetes/dados", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/bilhetes/dados", token=None)[0], 401)

    def test_proximo_escolhe_a_primeira_viagem_ativa_futura_com_a_compra(self):
        hoje = datetime.now().date()
        d = lambda n: (hoje + timedelta(days=n)).isoformat()
        c = self.bd()
        for data, hora, comboio, ativo in ((d(-1), "10:00", 1, "SIM"), (d(2), "09:00", 2, "NAO"),
                                           (d(3), "18:00", 3, "SIM"), (d(3), "08:00", 4, "SIM")):
            c.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?)",
                      (data, "Lisboa Oriente", "Aveiro", comboio, hora, ativo))
        c.execute("INSERT INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia) "
                  "VALUES (?,?,?,?,?,?,?,?)", (d(3), 4, "Lisboa Oriente", "Aveiro", "08:00", "5", "23", "REF-XYZ"))
        c.close()
        s, b, _ = self.pedir("GET", "/bilhetes/proximo")
        self.assertEqual(s, 200)
        p = b["proximo"]
        self.assertEqual((p["data"], p["hora"], p["comboio"]), (d(3), "08:00", 4))   # ignora passadas e inativas
        self.assertEqual(p["compra"], {"carruagem": "5", "lugar": "23", "referencia": "REF-XYZ"})
        self.assertIn("passe", b)

    def test_proximo_encontra_a_compra_mesmo_com_a_hora_da_venda_diferente_da_de_embarque(self):
        # a viagem tem a hora a que abre a venda (06:45) e a compra guarda a de embarque (07:27)
        d = (datetime.now().date() + timedelta(days=3)).isoformat()
        c = self.bd()
        c.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?)", (d, "Aveiro", "Lisboa Oriente", 520, "06:45", "SIM"))
        c.execute("INSERT INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia) VALUES (?,?,?,?,?,?,?,?)",
                  (d, 520, "Aveiro", "Lisboa Oriente", "07:27", "21", "77", "REF-HORA"))
        c.execute("INSERT INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia) VALUES (?,?,?,?,?,?,?,?)",
                  (d, 520, "Lisboa Oriente", "Aveiro", "09:00", "1", "1", "REF-OUTRO-SENTIDO"))
        c.close()
        _, b, _ = self.pedir("GET", "/bilhetes/proximo")
        self.assertEqual(b["proximo"]["compra"]["referencia"], "REF-HORA")

    def test_proximo_mantem_a_viagem_em_curso_ate_ao_fim_estimado(self):
        agora = datetime.now()
        c = self.bd()
        for comboio, quando in ((1, agora - timedelta(hours=1)), (2, agora - timedelta(hours=4)), (3, agora + timedelta(hours=5))):
            if quando.date() != agora.date():
                self.skipTest("perto da meia-noite")
            c.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?)",
                      (quando.date().isoformat(), "Lisboa Oriente", "Aveiro", comboio, quando.strftime("%H:%M"), "SIM"))
        c.close()
        p = self.pedir("GET", "/bilhetes/proximo")[1]["proximo"]
        self.assertEqual((p["comboio"], p["emCurso"]), (1, True))       # partiu há 1 h, ainda dentro das 3 h estimadas

    def test_proximo_sem_compra_sem_viagens_e_acesso(self):
        s, b, _ = self.pedir("GET", "/bilhetes/proximo")
        self.assertEqual((s, b["proximo"]), (200, None))
        amanha = (datetime.now().date() + timedelta(days=1)).isoformat()
        c = self.bd()
        c.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?)",
                  (amanha, "Aveiro", "Lisboa Oriente", 9, "07:00", "SIM")); c.close()
        self.assertIsNone(self.pedir("GET", "/bilhetes/proximo")[1]["proximo"]["compra"])
        self.assertEqual(self.pedir("GET", "/bilhetes/proximo", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/bilhetes/proximo", token=None)[0], 401)

    def test_usa_a_base_de_dados_propria(self):
        self.assertEqual(self.semana([viagem()])[0], 200)
        c = sqlite3.connect(db.db_path("dados"))
        tabelas = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        c.close()
        self.assertFalse(any(t.startswith("bilhetes_") for t in tabelas))       # nada de bilhetes na BD partilhada
        self.assertEqual(self.bd().execute("select count(*) from bilhetes_viagens").fetchone()[0], 1)

    def test_dados_iniciais(self):
        s, d, _ = self.pedir("GET", "/bilhetes/dados")
        self.assertEqual(s, 200)
        self.assertEqual(d["passe"], {"dataUltimaCompra": None, "validadeDias": 29, "dataExpira": None, "diasRestantes": None})
        self.assertEqual((d["viagens"], d["pedidos"]), ([], []))

    def test_semana_guarda_e_atribui_ids_novos_a_partir_de_100(self):
        s, r, _ = self.semana([viagem(0), viagem(0, comboio=520, hora="06:45"), viagem(2, ativo="NAO")])
        self.assertEqual(s, 200)
        self.assertTrue(all(v["id"] >= 100 for v in r["viagens"]))
        self.assertEqual([(v["comboio"], v["hora"]) for v in r["viagens"]], [(520, "06:45"), (731, "17:30"), (731, "17:30")])

    def test_guardar_de_novo_preserva_os_ids_das_viagens_que_continuam(self):
        _, r1, _ = self.semana([viagem(0), viagem(1, comboio=520, hora="06:45")])
        ids = {(v["data"], v["comboio"]): v["id"] for v in r1["viagens"]}
        # muda só o destino de uma, acrescenta outra: as duas originais mantêm o id (chave do lock de compra!)
        _, r2, _ = self.semana([viagem(0, dst="Porto Campanhã"), viagem(1, comboio=520, hora="06:45"), viagem(3, comboio=800, hora="08:00")])
        ids2 = {(v["data"], v["comboio"]): v["id"] for v in r2["viagens"]}
        self.assertEqual(ids2[(dia(0), 731)], ids[(dia(0), 731)])
        self.assertEqual(ids2[(dia(1), 520)], ids[(dia(1), 520)])
        self.assertNotIn(ids2[(dia(3), 800)], ids.values())
        self.assertEqual([v["destino"] for v in r2["viagens"] if v["comboio"] == 731], ["Porto Campanhã"])

    def test_remover_uma_viagem_apaga_so_essa_e_nao_reutiliza_ids(self):
        _, r1, _ = self.semana([viagem(0), viagem(1, comboio=520, hora="06:45")])
        removida = next(v["id"] for v in r1["viagens"] if v["comboio"] == 520)
        _, r2, _ = self.semana([viagem(0)])
        self.assertEqual([v["comboio"] for v in r2["viagens"]], [731])
        _, r3, _ = self.semana([viagem(0), viagem(1, comboio=520, hora="06:45")])
        self.assertNotEqual(next(v["id"] for v in r3["viagens"] if v["comboio"] == 520), removida)

    def test_semana_so_mexe_nessa_semana(self):
        outra = "2035-03-12"
        self.semana([viagem(0)], inicio=INI)
        self.pedir("PUT", "/bilhetes/semana", {"inicio": outra, "viagens": [{**viagem(0), "data": outra}]})
        self.semana([], inicio=INI)                                   # limpar a 1.ª semana
        _, d, _ = self.pedir("GET", "/bilhetes/dados")
        self.assertEqual([v["data"] for v in d["viagens"]], [outra])

    def test_semana_validacao_e_atomicidade(self):
        self.semana([viagem(0)])
        casos = [
            [{**viagem(0), "data": "2035-04-01"}],                     # fora da semana
            [viagem(0), viagem(0)],                                    # repetida
            [viagem(0, comboio=0)], [viagem(0, comboio="731")], [viagem(0, comboio=True)],
            [viagem(0, hora="25:00")], [viagem(0, hora="6:45")], [viagem(0, org="Aveiro", dst="aveiro")],
            [viagem(0, org="")], [viagem(0, org="x" * 61)], [viagem(0, ativo="TALVEZ")],
            [{**viagem(0), "extra": 1}], ["não é objeto"],
        ]
        for c in casos:
            self.assertEqual(self.semana(c)[0], 400, c)
        self.assertEqual(self.pedir("PUT", "/bilhetes/semana", {"inicio": "2035-13-01", "viagens": []})[0], 400)
        self.assertEqual(self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "viagens": "x"})[0], 400)
        # uma viagem má no meio não deixa gravar as boas nem apagar as que lá estavam
        self.assertEqual(self.semana([viagem(1, comboio=520, hora="06:45"), viagem(2, hora="99:99")])[0], 400)
        _, d, _ = self.pedir("GET", "/bilhetes/dados")
        self.assertEqual([(v["data"], v["comboio"]) for v in d["viagens"]], [(dia(0), 731)])

    def test_passe(self):
        s, p, _ = self.pedir("PUT", "/bilhetes/passe", {"dataUltimaCompra": "2026-09-21"})
        self.assertEqual((s, p["dataUltimaCompra"], p["validadeDias"], p["dataExpira"]), (200, "2026-09-21", 29, "2026-10-20"))
        self.assertIsInstance(p["diasRestantes"], int)
        s, p, _ = self.pedir("PUT", "/bilhetes/passe", {"dataUltimaCompra": "2026-09-21", "validadeDias": 30})
        self.assertEqual(p["dataExpira"], "2026-10-21")
        for c in ({}, {"dataUltimaCompra": "ontem"}, {"dataUltimaCompra": "2099-01-01"}, {"dataUltimaCompra": "2026-09-21", "validadeDias": 0},
                  {"dataUltimaCompra": "2026-09-21", "validadeDias": "29"}, {"dataUltimaCompra": "2026-09-21", "x": 1}):
            self.assertEqual(self.pedir("PUT", "/bilhetes/passe", c)[0], 400, c)

    def pedido(self, estado="ESGOTADO"):
        c = self.bd()
        cur = c.execute("INSERT INTO bilhetes_pedidos (data, origem, destino, comboio, hora, estado) VALUES (?, 'A', 'B', 731, '17:30', ?)",
                        (dia(1), estado))
        c.close()
        return cur.lastrowid

    def test_pedidos_retry_e_forcar(self):
        pid = self.pedido()
        s, p, _ = self.pedir("PUT", f"/bilhetes/pedidos/{pid}", {"retry": True, "intervaloMinutos": 20})
        self.assertEqual((s, p["retry"], p["intervaloMinutos"]), (200, "SIM", 20))
        s, p, _ = self.pedir("PUT", f"/bilhetes/pedidos/{pid}", {"retry": False, "intervaloMinutos": None})
        self.assertEqual((p["retry"], p["intervaloMinutos"]), ("NAO", None))
        s, p, _ = self.pedir("POST", f"/bilhetes/pedidos/{pid}/forcar", {})
        self.assertEqual((s, p["forcar"], p["estado"]), (200, "SIM", "ESGOTADO"))
        for c in ({"retry": "SIM"}, {}, {"retry": True, "intervaloMinutos": 0}, {"retry": True, "intervaloMinutos": 1441},
                  {"retry": True, "intervaloMinutos": "10"}, {"retry": True, "estado": "CONFIRMADO"}):    # a PWA nunca escreve o estado
            self.assertEqual(self.pedir("PUT", f"/bilhetes/pedidos/{pid}", c)[0], 400, c)
        self.assertEqual(self.pedir("PUT", "/bilhetes/pedidos/999999", {"retry": True})[0], 404)
        self.assertEqual(self.pedir("POST", "/bilhetes/pedidos/999999/forcar", {})[0], 404)

    def test_pedido_terminal_nao_se_forca(self):
        for estado in ("CONFIRMADO", "AMBIGUO"):
            pid = self.pedido(estado)
            s, _, _ = self.pedir("POST", f"/bilhetes/pedidos/{pid}/forcar", {})
            self.assertEqual(s, 409, estado)
            self.assertEqual(self.bd().execute("select forcar from bilhetes_pedidos where id=?", (pid,)).fetchone()[0], "NAO")

    def test_dados_devolve_compras_logs_e_pedidos_do_pi(self):
        c = self.bd()
        c.execute("INSERT INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia) "
                  "VALUES ('2026-09-24', 731, 'Lisboa Oriente', 'Aveiro', '17:39', '22', '105', 'CP-X')")
        for i in range(3):
            c.execute("INSERT INTO bilhetes_logs (ts, tipo, resultado) VALUES (?, 'COMPRA', ?)", (f"2026-09-24T17:3{i}:00.000+01:00", f"R{i}"))
        c.close()
        self.pedido()
        _, d, _ = self.pedir("GET", "/bilhetes/dados")
        self.assertEqual(d["compras"], [{"id": 1, "data": "2026-09-24", "comboio": 731, "origem": "Lisboa Oriente", "destino": "Aveiro",
                                         "hora": "17:39", "carruagem": "22", "lugar": "105", "referencia": "CP-X"}])
        self.assertEqual([l["resultado"] for l in d["logs"]], ["R0", "R1", "R2"])      # do mais antigo para o mais recente
        self.assertEqual(d["pedidos"][0]["estado"], "ESGOTADO")


if __name__ == "__main__":
    unittest.main()


class BilhetesUtilizadoresApiTest(ApiBase):
    """A PWA só sabe quem é o utilizador e (se administrador) um resumo SEM dados pessoais nem segredos."""

    def setUp(self):
        c = db.connect_named("bilhetes")
        c.execute("UPDATE bilhetes_utilizadores SET email = 'eu@example.com', admin = 1, ativo = 1, nif = '123456789', cp_password_enc = 'cifrada', "
                  "passageiro_cc = '12345678' WHERE id = 1")
        c.close()

    def test_eu_e_admin(self):
        s, b, _ = self.pedir("GET", "/bilhetes/eu")
        self.assertEqual((s, b["admin"], b["utilizador"]["nome"]), (200, True, "Bruno"))

    def test_nao_admin_nao_ve_o_resumo(self):
        c = db.connect_named("bilhetes"); c.execute("UPDATE bilhetes_utilizadores SET admin = 0 WHERE id = 1"); c.close()
        s, b, _ = self.pedir("GET", "/bilhetes/eu")
        self.assertEqual((s, b["admin"]), (200, False))
        self.assertEqual(self.pedir("GET", "/bilhetes/admin/utilizadores")[0], 403)

    def test_sem_utilizador_para_o_email(self):
        c = db.connect_named("bilhetes"); c.execute("UPDATE bilhetes_utilizadores SET email = NULL WHERE id = 1"); c.close()
        s, b, _ = self.pedir("GET", "/bilhetes/eu")
        self.assertEqual((s, b), (200, {"utilizador": None, "admin": False}))
        self.assertEqual(self.pedir("GET", "/bilhetes/admin/utilizadores")[0], 403)

    def test_resumo_sem_segredos_nem_dados_pessoais(self):
        s, b, _ = self.pedir("GET", "/bilhetes/admin/utilizadores")
        self.assertEqual(s, 200)
        bruno = b["utilizadores"][0]
        self.assertEqual((bruno["nome"], bruno["nif"], bruno["cp_password"], bruno["cc"]), ("Bruno", True, True, True))   # só booleanos
        texto = json.dumps(b)
        for segredo in ("123456789", "cifrada", "12345678"):
            self.assertNotIn(segredo, texto)
        self.assertTrue(b["urlAdmin"].startswith("http://"))
        self.assertTrue(b["naLan"])                       # o teste liga-se por loopback

    def test_na_lan(self):
        from apps import bilhetes as ab
        from unittest import mock
        with mock.patch.object(ab, "_ip_publico_de_casa", return_value="82.1.2.3"):
            self.assertTrue(ab.na_lan("192.168.68.20"))
            self.assertTrue(ab.na_lan("82.1.2.3"))          # de casa, via NAT loopback do router
            self.assertFalse(ab.na_lan("85.9.9.9"))         # dados móveis / outra rede
            self.assertFalse(ab.na_lan("2a01:4f8::1"))
            self.assertFalse(ab.na_lan("lixo"))



class BilhetesPorPessoaTest(ApiBase):
    """O Bruno (administrador) marca para outras pessoas; cada pessoa só vê o que é seu (ADR-063)."""

    bd = BilhetesApiTest.bd
    limpar = BilhetesApiTest.limpar

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import threading
        import api
        from tests.test_api import CLIENT
        cls.srv.shutdown(); cls.srv.server_close()
        cls.settings = api.Settings({"GOOGLE_CLIENT_IDS": CLIENT, "ACL_BILHETES": f"{EU},{OUTRO}", "RATE_IP_POR_MIN": "1000", "RATE_FALHAS_POR_MIN": "1000"})
        cls.srv = api.criar_servidor(cls.settings, cls.verifier, porta=0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    def setUp(self):
        self.limpar()
        c = self.bd()
        c.execute("UPDATE bilhetes_utilizadores SET email = ?, admin = 1, ativo = 1 WHERE id = 1", (EU,))
        c.execute("DELETE FROM bilhetes_utilizadores WHERE id > 1"); c.execute("DELETE FROM bilhetes_compras"); c.execute("DELETE FROM bilhetes_logs")
        c.execute("INSERT INTO bilhetes_utilizadores (id, nome, email, ativo) VALUES (2, 'Camila', ?, 1)", (OUTRO,))
        c.execute("INSERT INTO bilhetes_utilizadores (id, nome, ativo) VALUES (3, 'Davi', 1)")          # sem login próprio
        c.close()

    def dela(self, metodo, caminho, corpo=None):
        return self.pedir(metodo, caminho, corpo, token="t" * 30 + "outro")

    def test_o_bruno_marca_para_a_camila_e_cada_um_ve_so_o_seu(self):
        s, b, _ = self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "utilizadorId": 2, "viagens": [viagem(0, comboio=520, hora="07:27")]})
        self.assertEqual(s, 200, b)
        self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "viagens": [viagem(1, comboio=731)]})             # a dele
        dela = self.dela("GET", "/bilhetes/dados")[1]
        dele = self.pedir("GET", "/bilhetes/dados")[1]
        self.assertEqual([v["comboio"] for v in dela["viagens"]], [520])
        self.assertEqual([v["comboio"] for v in dele["viagens"]], [731])
        self.assertEqual((dela["utilizador"]["nome"], dela["pessoas"]), ("Camila", []))                             # ela não escolhe por quem marca
        vista = self.pedir("GET", "/bilhetes/dados?utilizador=2")[1]                                               # o Bruno vê a dela
        self.assertEqual(([v["comboio"] for v in vista["viagens"]], vista["utilizador"]), ([520], {"id": 2, "nome": "Camila", "eu": False}))
        self.assertEqual([p["nome"] for p in dele["pessoas"]], ["Bruno", "Camila", "Davi"])
        c = self.bd()
        self.assertEqual({r[0] for r in c.execute("SELECT utilizador_id FROM bilhetes_viagens WHERE comboio = 520")}, {2})     # o dono fica gravado: é com as credenciais dela que se compra
        c.close()

    def test_gravar_uma_semana_so_mexe_nas_viagens_da_pessoa_indicada(self):
        self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "viagens": [viagem(0, comboio=731)]})
        self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "utilizadorId": 2, "viagens": [viagem(0, comboio=520, hora="07:27")]})
        self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "utilizadorId": 2, "viagens": []})                    # esvazia a da Camila…
        self.assertEqual([v["comboio"] for v in self.pedir("GET", "/bilhetes/dados")[1]["viagens"]], [731])          # …e a do Bruno fica como estava

    def test_so_o_administrador_marca_por_outros_e_so_por_pessoas_ativas(self):
        corpo = {"inicio": INI, "utilizadorId": 1, "viagens": [viagem(0)]}
        self.assertEqual(self.dela("PUT", "/bilhetes/semana", corpo)[0], 403)                                       # a Camila não marca pelo Bruno
        self.assertEqual(self.dela("GET", "/bilhetes/dados?utilizador=1")[0], 403)
        c = self.bd(); c.execute("UPDATE bilhetes_utilizadores SET ativo = 0 WHERE id = 3"); c.close()
        self.assertEqual(self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "utilizadorId": 3, "viagens": []})[0], 404)
        self.assertEqual(self.pedir("PUT", "/bilhetes/semana", {"inicio": INI, "utilizadorId": 99, "viagens": []})[0], 404)
        self.assertEqual(self.pedir("GET", "/bilhetes/dados?utilizador=abc")[0], 400)

    def test_conta_nao_registada_nos_bilhetes_nao_ve_nada_nem_assume_ser_o_bruno(self):
        c = self.bd(); c.execute("UPDATE bilhetes_utilizadores SET email = NULL WHERE id = 2"); c.close()            # a Camila ainda não tem login nos Bilhetes
        for caminho in ("/bilhetes/dados", "/bilhetes/proximo"):
            s, b, _ = self.dela("GET", caminho)
            self.assertEqual((s, b["erro"]["codigo"]), (403, "sem_utilizador"))

    def test_passe_por_pessoa(self):
        d = lambda n: (datetime.now().date() - timedelta(days=n)).isoformat()         # noqa: E731 (o passe não pode estar no futuro)
        self.pedir("PUT", "/bilhetes/passe", {"dataUltimaCompra": d(9)})
        s, b, _ = self.pedir("PUT", "/bilhetes/passe", {"dataUltimaCompra": d(3), "validadeDias": 20, "utilizadorId": 2})
        self.assertEqual((s, b["dataUltimaCompra"], b["validadeDias"]), (200, d(3), 20))
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["passe"]["dataUltimaCompra"], d(9))                   # o dele não mudou
        self.assertEqual(self.dela("GET", "/bilhetes/dados")[1]["passe"]["dataUltimaCompra"], d(3))

    def test_pedidos_so_do_dono_ou_do_administrador(self):
        c = self.bd()
        c.execute("INSERT INTO bilhetes_pedidos (id, data, origem, destino, comboio, hora, estado, utilizador_id) VALUES (50, ?, 'Aveiro', 'Lisboa Oriente', 520, '07:27', 'PENDENTE', 1)", (dia(0),))
        c.execute("INSERT INTO bilhetes_pedidos (id, data, origem, destino, comboio, hora, estado, utilizador_id) VALUES (51, ?, 'Aveiro', 'Lisboa Oriente', 522, '07:27', 'PENDENTE', 2)", (dia(0),))
        c.close()
        self.assertEqual(self.dela("PUT", "/bilhetes/pedidos/50", {"retry": True})[0], 404)                          # o do Bruno: «inexistente»
        self.assertEqual(self.dela("POST", "/bilhetes/pedidos/50/forcar", {})[0], 404)
        self.assertEqual(self.dela("PUT", "/bilhetes/pedidos/51", {"retry": True})[0], 200)
        self.assertEqual(self.pedir("PUT", "/bilhetes/pedidos/51", {"retry": False})[0], 200)                        # o administrador mexe em qualquer um
        self.assertEqual([p["id"] for p in self.dela("GET", "/bilhetes/dados")[1]["pedidos"]], [51])

    def test_proximo_e_da_propria_conta(self):
        hoje = datetime.now().date()
        c = self.bd()
        c.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo, utilizador_id) VALUES (?, 'Aveiro', 'Lisboa Oriente', 520, '23:50', 'SIM', 2)", ((hoje + timedelta(days=2)).isoformat(),))
        c.close()
        self.assertEqual(self.dela("GET", "/bilhetes/proximo")[1]["proximo"]["comboio"], 520)
        self.assertIsNone(self.pedir("GET", "/bilhetes/proximo")[1]["proximo"])

    # --- a conta da CP (ADR-075) ---------------------------------------------------------------------------------------

    def _cp_falsa(self, saida, guardar=None):
        from unittest import mock
        def run(args, **kw):
            if guardar is not None:
                guardar.append(args)
            return mock.Mock(stdout=json.dumps(saida) + "\n", returncode=0)
        return mock.patch("apps.bilhetes.subprocess.run", run)

    def test_cp_futuros_da_propria_conta_e_do_administrador_por_outra_pessoa(self):
        chamadas = []
        with self._cp_falsa({"ok": True, "bilhetes": [{"venda": 5}]}, chamadas):
            self.assertEqual(self.dela("GET", "/bilhetes/cp/futuros")[1]["bilhetes"], [{"venda": 5}])
            self.assertEqual(self.pedir("GET", "/bilhetes/cp/futuros?utilizador=2")[0], 200)
            self.assertEqual(self.dela("GET", "/bilhetes/cp/futuros?utilizador=1")[0], 403)      # só o administrador vê a conta de outra pessoa
        self.assertEqual([a[a.index("--utilizador") + 1] for a in chamadas], ["2", "2"])

    def test_cp_cancelar_valida_e_passa_so_a_venda(self):
        chamadas = []
        with self._cp_falsa({"ok": True, "venda": 77, "estado": "CONFIRMED", "reembolso": "€ 0,00"}, chamadas):
            s, b, _ = self.dela("POST", "/bilhetes/cp/cancelar", {"venda": 77})
            self.assertEqual((s, b["estado"]), (200, "CONFIRMED"))
            self.assertEqual(self.dela("POST", "/bilhetes/cp/cancelar", {"venda": "77"})[0], 400)
            self.assertEqual(self.dela("POST", "/bilhetes/cp/cancelar", {"venda": 77, "comando": "x"})[0], 400)
            self.assertEqual(self.dela("POST", "/bilhetes/cp/cancelar", {"venda": 77, "utilizadorId": 1})[0], 403)
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0][-3:], ["cancelar", "--venda", "77"])

    def _cp_por_comando(self, respostas, guardar=None):
        """Uma CP falsa que responde conforme o comando (`futuros`, `elegibilidade`, `cancelar`…)."""
        from unittest import mock
        def run(args, **kw):
            comando = next(c for c in ("futuros", "elegibilidade", "cancelar", "passe") if c in args)
            if guardar is not None:
                guardar.append(comando)
            return mock.Mock(stdout=json.dumps(respostas[comando]) + "\n", returncode=0)
        return mock.patch("apps.bilhetes.subprocess.run", run)

    ANTIGO = {"venda": 77, "referencia": "CP-ANTIGO", "estado": "CONFIRMED", "origem": "Lisboa Oriente", "destino": "Aveiro", "data": "2035-03-06",
              "hora": "19:39", "comboio": 723, "podeCancelar": True}

    def test_cp_cancelar_tira_a_compra_da_lista(self):
        c = self.bd()
        c.execute("INSERT INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia, utilizador_id) VALUES (?,?,?,?,?,?,?,?,1)",
                  ("2035-03-06", 723, "Lisboa Oriente", "Aveiro", "19:39", "22", "77", "CP-ANTIGO"))
        c.close()
        with self._cp_falsa({"ok": True, "venda": 77, "estado": "CONFIRMED", "reembolso": "€ 0,00", "referencia": "CP-ANTIGO"}):
            self.assertEqual(self.pedir("POST", "/bilhetes/cp/cancelar", {"venda": 77})[0], 200)
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["compras"], [])

    def test_troca_cria_um_pedido_de_15_em_15_min_depois_de_confirmar_na_cp_que_o_bilhete_se_pode_cancelar(self):
        chamadas = []
        with self._cp_por_comando({"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO"}}, chamadas):
            s, b, _ = self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"})
        self.assertEqual(s, 201)
        self.assertEqual((b["comboio"], b["hora"], b["data"], b["origem"], b["destino"]), (731, "17:30", "2035-03-06", "Lisboa Oriente", "Aveiro"))
        self.assertEqual((b["retry"], b["intervaloMinutos"], b["trocaVenda"], b["trocaReferencia"], b["trocaAntecedenciaMin"]), ("SIM", 15, 77, "CP-ANTIGO", 30))
        self.assertEqual(chamadas, ["futuros", "elegibilidade"])                  # só leitura: nada foi cancelado
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["pedidos"][0]["trocaVenda"], 77)

    def test_troca_recusada_se_a_cp_nao_deixa_cancelar_ou_ja_ha_troca_ou_pedido_invalido(self):
        base = {"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": False, "motivo": "A CP já não permite devolver este bilhete."}}
        with self._cp_por_comando(base):
            s, b, _ = self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"})
        self.assertEqual(s, 409)
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["pedidos"], [])           # nada ficou criado
        ok = {**base, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO"}}
        with self._cp_por_comando(ok):
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"})[0], 201)
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"})[0], 409)   # já ativa
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 723, "hora": "17:30"})[0], 409)   # o mesmo comboio já é permitido (mudar de lugar), mas já há troca ativa
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "7:30"})[0], 400)
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 99, "comboio": 731, "hora": "17:30"})[0], 404)   # não é um bilhete desta conta
            self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30", "x": 1})[0], 400)

    def test_troca_com_inicio_agendado_guarda_o_inicio_e_recusa_um_inicio_invalido_ou_tarde_demais(self):
        ok = {"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO"}}
        base = {"venda": 77, "comboio": 731, "hora": "17:30"}
        with self._cp_por_comando(ok):
            for mau in ("amanha", "2035-03-05 08:00", "2035-03-05T25:00", 5, "2035-03-06T17:00"):      # o último é depois do limite (17:30 − 30 min = 17:00)
                self.assertEqual(self.pedir("POST", "/bilhetes/trocas", {**base, "inicio": mau})[0], 400, mau)
            s, b, _ = self.pedir("POST", "/bilhetes/trocas", {**base, "inicio": "2035-03-05T08:00"})
        self.assertEqual((s, b["trocaInicio"]), (201, "2035-03-05T08:00"))
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["pedidos"][0]["trocaInicio"], "2035-03-05T08:00")

    def test_troca_pelo_mesmo_comboio_e_permitida_mudar_de_lugar(self):
        ok = {"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO"}}
        with self._cp_por_comando(ok):
            s, b, _ = self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 723, "hora": "19:39"})
        self.assertEqual((s, b["comboio"], b["trocaVenda"]), (201, 723, 77))

    def test_simular_a_devolucao_so_le_e_diz_se_a_cp_deixa_e_quanto(self):
        chamadas = []
        ok = {"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO", "valor": "€ 6,10"}}
        with self._cp_por_comando(ok, chamadas):
            s, b, _ = self.pedir("GET", "/bilhetes/trocas/simular?venda=77")
            self.assertEqual((s, b["cancelavel"], b["valor"], b["referencia"]), (200, True, "€ 6,10", "CP-ANTIGO"))
            self.assertEqual(self.pedir("GET", "/bilhetes/trocas/simular?venda=99")[0], 404)
            self.assertEqual(self.pedir("GET", "/bilhetes/trocas/simular")[0], 400)
        self.assertEqual(sorted(set(chamadas)), ["elegibilidade", "futuros"])                    # só leituras: nunca «cancelar»
        self.assertEqual(self.pedir("GET", "/bilhetes/dados")[1]["pedidos"], [])                  # não cria nenhuma troca
        rec = {**ok, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": False, "motivo": "A CP já não permite devolver este bilhete."}}
        with self._cp_por_comando(rec):
            self.assertEqual(self.pedir("GET", "/bilhetes/trocas/simular?venda=77")[1]["cancelavel"], False)

    def test_desarmar_a_troca_para_o_pedido_sem_cancelar_nada(self):
        ok = {"futuros": {"ok": True, "bilhetes": [self.ANTIGO]}, "elegibilidade": {"ok": True, "venda": 77, "cancelavel": True, "referencia": "CP-ANTIGO"}}
        with self._cp_por_comando(ok):
            pid = self.pedir("POST", "/bilhetes/trocas", {"venda": 77, "comboio": 731, "hora": "17:30"})[1]["id"]
        s, b, _ = self.pedir("DELETE", f"/bilhetes/trocas/{pid}")
        self.assertEqual((s, b["ativo"], b["estado"]), (200, "NAO", "DESARMADO"))
        normal = self.pedir("GET", "/bilhetes/dados")[1]["pedidos"]
        self.assertEqual(normal[0]["estado"], "DESARMADO")
        c = self.bd()
        c.execute("INSERT INTO bilhetes_pedidos (id, data, origem, destino, comboio, hora, estado, utilizador_id) VALUES (60, ?, 'Aveiro', 'Lisboa Oriente', 520, '07:27', 'PENDENTE', 1)", (dia(0),))
        c.close()
        self.assertEqual(self.pedir("DELETE", "/bilhetes/trocas/60")[0], 404)                # um pedido normal não é uma troca

    def test_cp_erros_da_consulta_chegam_como_erros_da_api(self):
        with self._cp_falsa({"ok": False, "erro": "nao_cancelavel", "mensagem": "A CP já não permite devolver este bilhete."}):
            s, b, _ = self.dela("POST", "/bilhetes/cp/cancelar", {"venda": 1})
        self.assertEqual((s, b["erro"]["codigo"] if "erro" in b and isinstance(b["erro"], dict) else b.get("codigo")), (409, "cp_nao_cancelavel"))
        with self._cp_falsa({"ok": False, "erro": "credenciais", "mensagem": "faltam dados de Davi: NIF"}):
            self.assertEqual(self.pedir("GET", "/bilhetes/cp/passe?utilizador=3")[0], 409)

    def test_cp_passe_calcula_os_dias_que_faltam(self):
        hoje = datetime.now().date()
        validade = (hoje + timedelta(days=12)).isoformat()
        from apps import bilhetes
        bilhetes._cp_cache.clear()
        with self._cp_falsa({"ok": True, "passes": [{"designacao": "Passe", "validade": validade, "inicio": "2026-09-21"}]}):
            p = self.dela("GET", "/bilhetes/cp/passe")[1]["passes"][0]
        self.assertEqual((p["validade"], p["diasRestantes"]), (validade, 12))


if __name__ == "__main__":
    unittest.main()
