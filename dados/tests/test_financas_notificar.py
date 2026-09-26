import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import db
import financas_notificar as fn

AGORA = datetime(2031, 5, 10, 9, 5, 0)


class NotificarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.db")
        db.migrate(self.conn)

    def tearDown(self):
        self.conn.close(); self.tmp.cleanup()

    def novo(self, desc, venc, tipo="despesa", pago=None, valor=1234.5):
        self.conn.execute("INSERT INTO financas_lancamentos (tipo, descricao, valor, categoria_id, data_vencimento, data_pagamento, mes_referencia) "
                          "VALUES (?,?,?,1,?,?,?)", (tipo, desc, valor, venc, pago, venc[:7]))

    def test_so_avisa_no_dia_do_vencimento_o_que_esta_por_pagar(self):
        self.novo("Luz", "2031-05-10")
        self.novo("Salário", "2031-05-10", tipo="rendimento", valor=1500)
        self.novo("Água", "2031-05-10", pago="2031-05-09")   # já paga
        self.novo("Net", "2031-05-11")                        # amanhã
        self.novo("Gás", "2031-05-09")                        # ontem: sem segundo aviso
        enviadas = []
        r = fn.correr(self.conn, AGORA, enviar=lambda m: enviadas.append(m) or True)
        self.assertEqual(r, (2, 0))
        self.assertEqual([m["title"] for m in enviadas], ["Vence hoje: Luz", "Rendimento previsto hoje: Salário"])
        self.assertEqual(enviadas[0]["message"], "1 234,50 € · Habitação")
        # segunda passagem no mesmo dia: nada
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: True), (0, 0))

    def test_falha_do_ntfy_nao_marca_e_tenta_de_novo(self):
        self.novo("Luz", "2031-05-10")
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: False), (0, 1))
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: True), (1, 0))

    def test_publicar_sem_config_falha_sem_rebentar(self):
        self.assertFalse(fn.publicar({"title": "x", "message": "y"}, env={}))


if __name__ == "__main__":
    unittest.main()
