import json
import sqlite3
import unittest
from datetime import datetime, timedelta

import db
from tests.test_api import ApiBase

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

    def test_acesso(self):
        self.assertEqual(self.pedir("GET", "/bilhetes/dados", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/bilhetes/dados", token=None)[0], 401)

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
