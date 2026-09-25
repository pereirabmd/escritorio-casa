"""Os fluxos reais de compra (Buyer e PedidoAttempt, com a CP falsa) a escrever numa base SQLite de
verdade — não numa Sheet falsa. Prova que o que a compra grava (bilhete, registos, espelho para Pedidos,
resultado do pedido) chega certo à BD e que as protecções (já comprado) leem dela."""

import _env  # noqa: F401

import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import common
import hot_buy
import store
from test_purchase_flow import DAY, FakeCP, FlowBase, PedidoFlowBase, resp
from test_store import SCHEMA


class SqliteFlowMixin:
    def make_db(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = Path(self.tmp.name) / "bilhetes.db"
        c = sqlite3.connect(self.dbpath)
        c.executescript(SCHEMA.read_text())
        c.close()
        self.sheets = store.SqliteStore(self.dbpath)

    def q(self, sql, *a):
        c = sqlite3.connect(self.dbpath)
        try:
            return c.execute(sql, a).fetchall()
        finally:
            c.close()


class BuyerSqliteTests(SqliteFlowMixin, FlowBase):
    def setUp(self):
        super().setUp()
        self.make_db()

    def test_compra_completa_grava_bilhete_e_registos(self):
        code, st = self.run_buyer(FakeCP())
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertEqual(self.q("SELECT data, comboio, hora_partida, carruagem, lugar, referencia FROM bilhetes_compras"),
                         [(DAY.isoformat(), 524, "06:45", "3", "42", "REF123")])
        tipos = [(r[0], r[1]) for r in self.q("SELECT tipo, resultado FROM bilhetes_logs ORDER BY id")]
        self.assertIn(("COMPRA", "CONFIRMED"), tipos)
        self.assertEqual(self.q("SELECT count(*) FROM bilhetes_pedidos"), [(0,)])          # confirmada: nunca espelhada

    def test_grava_os_pedidos_a_cp_na_tabela_de_tentativas(self):
        self.run_buyer(FakeCP())
        rows = self.q("SELECT fase, resultado, http, perna, comboio, rel_t_ms, ligacao_nova FROM bilhetes_tentativas ORDER BY id")
        self.assertEqual([r[:2] for r in rows], [("venda", "ok"), ("desconto", "ok")])         # T já passou: sem retenção
        self.assertEqual(rows[0][2:5], (200, "ida", 524))
        self.assertIsNotNone(rows[0][5])                 # relativo a T

    def test_esgotado_grava_todas_as_tentativas_da_rajada(self):
        n = len(hot_buy.sold_out_delays()) + 1
        cp = FakeCP(sale_script=[resp(409, {}, messages=[{"message": "Comboio esgotado"}])] * n)
        self.run_buyer(cp, advancing=True)
        self.assertEqual(self.q("SELECT count(*), min(resultado), max(resultado) FROM bilhetes_tentativas"), [(n, "sold_out", "sold_out")])

    def test_base_antiga_sem_a_tabela_nunca_estraga_a_compra(self):
        c = sqlite3.connect(self.dbpath); c.execute("DROP TABLE bilhetes_tentativas"); c.commit(); c.close()
        code, st = self.run_buyer(FakeCP())
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))

    def test_esgotado_e_espelhado_para_pedidos_com_id_novo(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=[{"message": "Comboio esgotado"}])]
                    * (len(hot_buy.sold_out_delays()) + 1))
        _, st = self.run_buyer(cp, advancing=True)
        self.assertEqual(st["state"], "SOLD_OUT")
        rows = self.q("SELECT id, data, comboio, estado, retry, forcar FROM bilhetes_pedidos")
        self.assertEqual(rows, [(100, DAY.isoformat(), 524, "ESGOTADO", "NAO", "NAO")])
        self.assertEqual(self.q("SELECT count(*) FROM bilhetes_compras"), [(0,)])

    def test_ja_comprado_nao_compra_outra_vez(self):
        self.sheets.append_ticket(DAY.isoformat(), 524, "Aveiro", "Lisboa Oriente", "06:45", 3, 42, "R-ANTIGA")
        cp = FakeCP()
        code, st = self.run_buyer(cp)
        self.assertEqual(cp.calls.count("sale"), 0)
        self.assertEqual(self.q("SELECT count(*) FROM bilhetes_compras"), [(1,)])

    def test_bd_indisponivel_nunca_interrompe_a_compra(self):
        self.dbpath.unlink()                                  # a BD "desaparece" a meio: a compra tem de continuar
        with mock.patch.object(hot_buy, "notify_once", return_value=True) as n:
            code, st = self.run_buyer(FakeCP())
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertTrue(n.called)                             # e avisa que não conseguiu escrever (nada falha em silêncio)


class PedidoSqliteTests(SqliteFlowMixin, PedidoFlowBase):
    def setUp(self):
        super().setUp()
        self.make_db()

        # o Pi espelhou o pedido (id 100) depois de uma viagem esgotar; o Pedido usa esse id como 'pedido100'
        self.sheets.append_request(DAY.isoformat(), "Aveiro", "Lisboa Oriente", 524, "06:45", estado="ESGOTADO")
        self.q_write("UPDATE bilhetes_pedidos SET forcar='SIM', retry='SIM', intervalo_minutos=10 WHERE id=100")
        self.leg = common.Leg(DAY, "pedido100", "aveiro", "lisboa_oriente", 524, "06:45", 100)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)

    def q_write(self, sql):
        c = sqlite3.connect(self.dbpath)
        c.execute(sql)
        c.commit()
        c.close()

    def test_pedido_grava_a_tentativa(self):
        self.run_pedido(FakeCP())
        self.assertEqual(self.q("SELECT fase, resultado, perna, rel_t_ms FROM bilhetes_tentativas"), [("venda", "ok", "pedido100", None)])

    def test_pedido_confirmado_atualiza_a_linha_certa(self):
        code, st = self.run_pedido(FakeCP())
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        (estado, forcar, ref, ult, retry), = self.q("SELECT estado, forcar, referencia, ultima_tentativa, retry FROM bilhetes_pedidos WHERE id=100")
        self.assertEqual((estado, forcar, ref, retry), ("CONFIRMADO", "NAO", "REF123", "SIM"))   # `Retry` da PWA intacto
        self.assertRegex(ult, r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(self.q("SELECT count(*) FROM bilhetes_compras"), [(1,)])


if __name__ == "__main__":
    unittest.main()
