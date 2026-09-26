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

    def lembrete(self, titulo, data, hora="09:00", rep="unica", ativo=1, ultimo=None):
        self.conn.execute("INSERT INTO financas_lembretes (titulo, data, hora, repeticao, ativo, ultimo_aviso) VALUES (?,?,?,?,?,?)",
                          (titulo, data, hora, rep, ativo, ultimo))

    def titulos(self, agora):
        return [l["titulo"] for l in fn.lembretes_devidos(self.conn, agora)]

    def test_lembrete_unico_so_no_dia_e_depois_da_hora(self):
        self.lembrete("Hoje 09h", "2031-05-10")
        self.lembrete("Hoje 15h", "2031-05-10", hora="15:00")
        self.lembrete("Amanhã", "2031-05-11")
        self.lembrete("Ontem", "2031-05-09")
        self.lembrete("Desligado", "2031-05-10", ativo=0)
        self.assertEqual(self.titulos(AGORA), ["Hoje 09h"])                      # 09:05: o das 15h ainda não
        self.assertEqual(self.titulos(datetime(2031, 5, 10, 16, 5)), ["Hoje 09h", "Hoje 15h"])

    def test_lembrete_mensal_no_dia_do_mes_e_no_ultimo_dia_de_meses_curtos(self):
        self.lembrete("Dia 10", "2031-01-10", rep="mensal")
        self.lembrete("Dia 31", "2031-01-31", rep="mensal")
        self.lembrete("Ainda nao comecou", "2031-06-10", rep="mensal")
        self.assertEqual(self.titulos(AGORA), ["Dia 10"])                        # 10 de maio
        self.assertEqual(self.titulos(datetime(2031, 4, 30, 9, 5)), ["Dia 31"])  # abril tem 30 dias
        self.assertEqual(self.titulos(datetime(2031, 6, 10, 9, 5)), ["Dia 10", "Ainda nao comecou"])

    def test_envia_uma_vez_por_dia_e_so_marca_se_o_ntfy_aceitar(self):
        self.lembrete("Mensal", "2031-01-10", rep="mensal")
        self.lembrete("Unico", "2031-05-10")
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: False), (0, 2))
        enviadas = []
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: enviadas.append(m) or True), (2, 0))
        self.assertEqual(sorted(m["title"] for m in enviadas), ["Mensal", "Unico"])
        self.assertEqual(enviadas[0]["message"], "Lembrete")
        self.assertEqual(fn.correr(self.conn, AGORA, enviar=lambda m: True), (0, 0))                # no mesmo dia: nada
        self.assertEqual(self.titulos(datetime(2031, 6, 10, 9, 5)), ["Mensal"])                    # o mensal volta no mês seguinte
        self.assertEqual(self.titulos(datetime(2031, 5, 10, 21, 0)), [])                            # o único nunca mais

    def test_publicar_sem_config_falha_sem_rebentar(self):
        self.assertFalse(fn.publicar({"title": "x", "message": "y"}, env={}))


if __name__ == "__main__":
    unittest.main()
