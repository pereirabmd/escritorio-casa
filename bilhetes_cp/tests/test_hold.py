"""Reter o lugar ANTES de T e disputar só o desconto (24/09/2026), ligação viva e guardas de segurança.

Medido no Pi: o POST /sale aceita-se dias antes de T; o desconto do passe (PUT items 302) só a T (antes: 500
«SIV:DIS:I:302»). O que aqui importa provar: nunca há duas vendas, o lugar retido é libertado quando sabemos que não vai
ser confirmado, nunca se confirma com o total diferente de 0 € (a guarda estava desligada: «€ 0,00» não se lia) e o
aquecimento já não usa o `HEAD /` que fechava a ligação.
"""

import unittest
from unittest import mock

import _env  # noqa: F401
import hot_buy
from cp_ticket import CPClient, CPError
from test_purchase_flow import FakeCP, FlowBase, resp

RECUSA = lambda: resp(500, {"error": "SIV:DIS:I:302", "description": "Sale item not available"})  # noqa: E731
ESGOTADO = lambda: resp(500, {"error": "WS:RES:114", "description": "Não há lugares disponíveis para a classe selecionada"})  # noqa: E731


class ToAmountTests(unittest.TestCase):
    def test_formatos_da_cp(self):
        for v, esperado in (("€ 0,00", 0.0), ("€ 23,45", 23.45), ("0.00", 0.0), ("0,00", 0.0), (0, 0.0), (12.5, 12.5),
                            ("€ 1.234,56", 1234.56), ({"value": "€ 0,00"}, 0.0), ("23,45 €", 23.45)):
            self.assertEqual(hot_buy.to_amount(v), esperado, v)
        for v in (None, "", "abc", {}, True):
            self.assertIsNone(hot_buy.to_amount(v), v)

    def test_a_guarda_do_total_apanha_23_45(self):
        # antes de 24/09 isto dava None e a compra seguia para a confirmação com 23,45 € por pagar
        self.assertNotEqual(hot_buy.to_amount("€ 23,45"), 0.0)


class WarmTests(unittest.TestCase):
    def test_aquece_com_um_pedido_que_deixa_a_ligacao_viva_e_nao_com_HEAD_barra(self):
        c = CPClient("tok")
        c.request = mock.Mock(return_value="r")
        c.warm(731, "2026-09-25")
        args, kw = c.request.call_args
        self.assertEqual(args, ("GET", "/travel-api/trains/731/timetable/2026-09-25"))
        self.assertFalse(kw["with_token"])

    def test_cancelar_venda_nunca_levanta(self):
        c = CPClient("tok")
        c.request = mock.Mock(side_effect=CPError("not_sent", "sem rede"))
        self.assertIsNone(c.cancel_sale(1))


class HoldBase(FlowBase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(hot_buy.Buyer, "precise_wait", lambda self, ts: None)   # não dormir a sério nos testes
        p.start(); self.addCleanup(p.stop)

    def run_early(self, cp, **kw):
        return self.run_buyer(cp, clock_offset=-200, advancing=True, **kw)     # 200 s antes de T


class HoldTests(HoldBase):
    def test_retem_o_lugar_antes_de_T_e_so_disputa_o_desconto(self):
        cp = FakeCP(steps={"items": [RECUSA(), RECUSA(), RECUSA()]})
        code, st = self.run_early(cp)
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertEqual([c for c in cp.calls if c != "warm"],
                         ["search", "sale", "passengers", "client", "fiscal", "items", "items", "items", "items", "confirm"])
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertIn("RETIDA antes de T", st["timing"])
        self.assertIn("warm", cp.calls)                         # manteve a ligação viva enquanto esperava
        self.assertNotIn("cancel", cp.calls)

    def test_o_desconto_tenta_com_intervalos_curtos_no_inicio(self):
        cp = FakeCP(steps={"items": [RECUSA()] * 5})
        self.run_early(cp)
        curtas = [s for s in self.sleeps if s == hot_buy.cfg("discount_fast_interval_s", 0.10)]
        self.assertGreaterEqual(len(curtas), 3)

    def test_esgotado_antes_de_T_cai_no_fluxo_normal_a_T(self):
        cp = FakeCP(sale_script=[ESGOTADO()] * 20 + [resp(200, {"saleID": 777})])
        code, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertGreaterEqual(cp.calls.count("sale"), 2)
        self.assertNotIn("RETIDA", st["timing"])                # a venda veio da rajada normal, não da retenção

    def test_retencao_que_recupera_a_meio_da_espera_usa_essa_venda(self):
        cp = FakeCP(sale_script=[ESGOTADO(), ESGOTADO(), resp(200, {"saleID": 777})])
        _, st = self.run_early(cp)
        self.assertEqual((st["state"], cp.calls.count("sale")), ("CONFIRMED", 3))
        self.assertIn("RETIDA antes de T", st["timing"])

    def test_desconto_nunca_aceite_cancela_a_venda_e_nao_confirma(self):
        cp = FakeCP(steps={"items": [RECUSA()] * 10_000})
        real = hot_buy.cfg
        with mock.patch.object(hot_buy, "cfg", lambda n, d: 5 if n == "discount_window_s" else real(n, d)):
            code, st = self.run_early(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertIn("cancel", cp.calls)
        self.assertNotIn("confirm", cp.calls)
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertTrue(any("Desconto do passe não aceite" in t for t in self.titles()))

    def test_429_no_desconto_espera_e_continua(self):
        cp = FakeCP(steps={"items": [resp(429), RECUSA()]})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertTrue(any(s >= 1.0 for s in self.sleeps))

    def test_429_sem_fim_desiste_com_a_venda_cancelada(self):
        cp = FakeCP(steps={"items": [resp(429)] * 100})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertIn("cancel", cp.calls)

    def test_erro_tecnico_no_desconto_repete_o_put_idempotente(self):
        cp = FakeCP(steps={"items": [resp(502), resp(503)]})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 1)

    def test_token_expirado_no_desconto_renova_e_continua(self):
        cp = FakeCP(steps={"items": [resp(401)]})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")

    def test_recusa_4xx_desconhecida_desiste_depressa_e_liberta_o_lugar(self):
        cp = FakeCP(steps={"items": [resp(422, {"error": "SIV:XXX"})] * 10_000})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertIn("cancel", cp.calls)


class SafetyTests(HoldBase):
    def test_total_23_45_depois_do_desconto_nao_confirma_e_liberta_o_lugar(self):
        cp = FakeCP(steps={"items": resp(200, {"totalAmount": "€ 23,45"})})
        code, st = self.run_early(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertNotIn("confirm", cp.calls)
        self.assertIn("cancel", cp.calls)

    def test_total_zero_em_euros_e_aceite(self):
        cp = FakeCP(steps={"items": resp(200, {"totalAmount": "€ 0,00"})})
        self.assertEqual(self.run_early(cp)[1]["state"], "CONFIRMED")

    def test_falha_a_confirmar_nunca_cancela_a_venda(self):
        cp = FakeCP(steps={"confirm": resp(200, {"status": {"code": "PENDING"}})})
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertNotIn("cancel", cp.calls)                   # incerto: pode estar confirmada

    def test_retoma_no_meio_com_T_no_futuro_espera_e_insiste_no_desconto(self):
        cp = FakeCP(steps={"items": [RECUSA(), RECUSA()]})
        _, st = self.run_early(cp, state={"state": "FISCAL_OK", "sale_id": 555})
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("sale", cp.calls)
        self.assertEqual([c for c in cp.calls if c not in ("warm",)], ["items", "items", "items", "confirm"])

    def test_atrasado_apos_T_nao_retem_e_segue_o_fluxo_normal(self):
        cp = FakeCP()
        _, st = self.run_buyer(cp, clock_offset=100)            # já depois de T
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("RETIDA", st["timing"])

    def test_com_a_retencao_desligada_e_o_fluxo_de_sempre(self):
        real = hot_buy.cfg
        cp = FakeCP()
        with mock.patch.object(hot_buy, "cfg", lambda n, d: False if n == "hold_before_open" else real(n, d)):
            _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("RETIDA", st["timing"])


if __name__ == "__main__":
    unittest.main()
