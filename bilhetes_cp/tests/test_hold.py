"""Reter o lugar ANTES de T e disputar só o desconto (24/09/2026), ligação viva e guardas de segurança.

Medido no Pi: o POST /sale aceita-se dias antes de T; o desconto do passe (PUT items 302) só a T (antes: 500
«SIV:DIS:I:302»). O que aqui importa provar: nunca há duas vendas, o lugar retido é libertado quando sabemos que não vai
ser confirmado, nunca se confirma com o total diferente de 0 € (a guarda estava desligada: «€ 0,00» não se lia) e o
aquecimento já não usa o `HEAD /` que fechava a ligação.
"""

import unittest
from unittest import mock

import _env  # noqa: F401
import cp_ticket
import hot_buy
from cp_ticket import CPClient, CPError
from test_purchase_flow import DAY, FakeCP, FlowBase, resp

RECUSA = lambda: resp(500, {"error": "SIV:DIS:I:302", "description": "Sale item not available"})  # noqa: E731
ESGOTADO = lambda: resp(500, {"error": "WS:RES:114", "description": "Não há lugares disponíveis para a classe selecionada"})  # noqa: E731


def place(seat, status=0, ptype=1):
    return {"placeType": ptype, "seatNumber": seat, "rowCode": 1, "plugType": 0, "withTable": False, "statusCode": status, "changeable": True}


def carriage(number, lines):
    """`lines`: 5 listas de lugares (janela, corredor, [corredor vazio], corredor, janela) como no mapa real da CP."""
    rows = [{"number": i, "places": pl} for i, pl in enumerate(lines)]
    return {"number": number, "attributes": ["WC"], "rows": rows}


AISLE_ROW = [{"placeType": 0, "withTable": False}] * 3     # a linha do corredor: sem `seatNumber`


def mapa(status_corredor=(0, 0), atual=(21, 112)):
    """Carruagem 21, 2+2: janela (112,111), corredor (118,113), corredor (114,117), janela (116,115)."""
    def seat(n, st=0):
        return place(n, 2) if (21, n) == atual else place(n, st)
    linhas = [[seat(112), seat(111)], [seat(118, status_corredor[0]), seat(113, status_corredor[1])], AISLE_ROW,
              [seat(114), seat(117)], [seat(116), seat(115)]]
    return {"trainNumber": 731, "carriages": [carriage(21, linhas)]}


class SeatMapTests(unittest.TestCase):
    def test_deteta_janela_e_corredor_pela_linha_vazia(self):
        seats = {s["seat"]: s["position"] for s in cp_ticket.seats_by_position(mapa())}
        self.assertEqual((seats[112], seats[118], seats[114], seats[116]), ("janela", "corredor", "corredor", "janela"))

    def test_escolhe_livres_ao_corredor_perto_do_atual(self):
        cand = cp_ticket.pick_aisle_seats(mapa(), 21, 112)
        self.assertTrue(all(c[1] in (118, 113, 114, 117) for c in cand))
        self.assertEqual(cand[0], (21, 113))            # |113−112| = 1: o mais perto

    def test_ignora_ocupados_e_lugares_especiais(self):
        cand = cp_ticket.pick_aisle_seats(mapa(status_corredor=(1, 3)), 21, 112)
        self.assertNotIn((21, 118), cand); self.assertNotIn((21, 113), cand)
        m = mapa(); m["carriages"][0]["rows"][1]["places"][1]["placeType"] = 7
        self.assertNotIn((21, 113), cp_ticket.pick_aisle_seats(m, 21, 112))

    def test_ja_no_corredor_nao_muda(self):
        self.assertEqual(cp_ticket.pick_aisle_seats(mapa(atual=(21, 118)), 21, 118), [])

    def test_mapa_estranho_nao_rebenta(self):
        for m in (None, {}, {"carriages": []}, {"carriages": [{"number": 1, "rows": []}]}, "x"):
            self.assertEqual(cp_ticket.pick_aisle_seats(m, 21, 112), [])
        sem_corredor = {"carriages": [carriage(21, [[place(1)], [place(2)]])]}
        self.assertEqual(cp_ticket.pick_aisle_seats(sem_corredor, 21, 1), [])


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


SALE_COM_LUGAR = {"saleID": 777, "seatData": {"carriageNumber": 21, "seatNumber": 112}}


class SeatTests(HoldBase):
    def cp(self, **kw):
        cp = FakeCP(sale_script=[resp(200, SALE_COM_LUGAR)], **kw)
        cp.seat_map = mapa()
        return cp

    def test_muda_para_o_corredor_com_a_venda_retida_e_antes_do_desconto(self):
        cp = self.cp()
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertIn(("change_seat", 21, 113), cp.calls)
        calls = [c for c in cp.calls if c != "warm"]
        self.assertLess(calls.index(("change_seat", 21, 113)), calls.index("passengers"))   # logo depois de reter
        self.assertEqual((st["carriage"], st["seat"]), (3, 42))    # no fim vale o lugar que o confirm devolve
        self.assertEqual(st["seat_changed"], "21/112 → 21/113 (corredor)")

    def test_lugar_ocupado_tenta_o_seguinte(self):
        cp = self.cp()
        cp.seat_changes = [resp(500, {"error": "WS:RES:120", "message": "lugar ocupado"})]
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        tentativas = [c for c in cp.calls if isinstance(c, tuple)]
        self.assertEqual(len(tentativas), 2)
        self.assertIn("→", st["seat_changed"])

    def test_todos_ocupados_segue_com_o_lugar_atribuido(self):
        cp = self.cp()
        cp.seat_changes = [resp(500, {"error": "WS:RES:120"})] * 10
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("seat_changed", st)

    def test_erro_no_mapa_nunca_estraga_a_compra(self):
        cp = self.cp()
        cp.seat_map = CPError("http", "mapa indisponível")
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 1)

    def test_excecao_inesperada_nunca_estraga_a_compra(self):
        cp = self.cp()
        cp.seat_map = {"carriages": "lixo"}
        self.assertEqual(self.run_early(cp)[1]["state"], "CONFIRMED")

    def test_ja_ao_corredor_nao_muda(self):
        cp = FakeCP(sale_script=[resp(200, {"saleID": 777, "seatData": {"carriageNumber": 21, "seatNumber": 118}})])
        cp.seat_map = mapa(atual=(21, 118))
        _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertFalse([c for c in cp.calls if isinstance(c, tuple)])

    def test_desligada_por_configuracao(self):
        real = hot_buy.cfg
        cp = self.cp()
        with mock.patch.object(hot_buy, "cfg", lambda n, d: "none" if n == "seat_preference" else real(n, d)):
            _, st = self.run_early(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("seat_map", cp.calls)

    def test_sem_retencao_a_compra_a_T_nao_perde_tempo_com_lugares(self):
        cp = self.cp()
        _, st = self.run_buyer(cp, clock_offset=100)       # T já passou: fluxo normal
        self.assertNotIn("seat_map", cp.calls)


class AttemptLogTests(HoldBase):
    def test_regista_cada_pedido_e_grava_no_fim(self):
        cp = FakeCP(sale_script=[resp(200, SALE_COM_LUGAR)], steps={"items": [RECUSA(), RECUSA()]})
        cp.seat_map = mapa()
        _, st = self.run_early(cp)
        rows = self.sheets.attempts
        self.assertEqual(st["state"], "CONFIRMED")
        fases = [r["fase"] for r in rows]
        self.assertEqual(fases, ["retencao", "lugar", "desconto", "desconto", "desconto"])
        self.assertEqual([r["resultado"] for r in rows], ["ok", "ok", "recusado", "recusado", "ok"])
        self.assertTrue(all(r["perna"] == "ida" and r["data_viagem"] == DAY.isoformat() for r in rows))
        self.assertLess(rows[0]["rel_t_ms"], 0)                        # a retenção sai antes de T
        self.assertEqual(rows[2]["codigo"], "SIV:DIS:I:302")

    def test_falha_a_gravar_nunca_estraga_a_compra(self):
        class Estraga(type(self.sheets)):
            def append_attempts(self, rows):
                raise RuntimeError("base cheia")
        self.sheets = Estraga()
        self.assertEqual(self.run_early(FakeCP())[1]["state"], "CONFIRMED")

    def test_uma_base_sem_suporte_e_ignorada(self):
        class SemSuporte:
            def __getattr__(self, nome):
                if nome == "append_attempts":
                    raise AttributeError(nome)
                return lambda *a, **k: None
            def read_tickets(self): return []
        self.assertEqual(self.run_early(FakeCP(), sheets=SemSuporte())[1]["state"], "CONFIRMED")


class ConfirmSeatTests(HoldBase):
    def test_a_mensagem_diz_corredor_quando_o_bilhete_reflete_a_mudanca(self):
        cp = FakeCP(sale_script=[resp(200, SALE_COM_LUGAR)])
        cp.seat_map = mapa()
        cp.steps = {"confirm": resp(200, {"status": {"code": "CONFIRMED"}, "reference": "R", "seatData": {"carriageNumber": 21, "seatNumber": 113}})}
        self.run_early(cp)
        msg = [n for n in self.notes if n[0].startswith("Bilhete comprado")][0][1]
        self.assertIn("(corredor)", msg); self.assertNotIn("⚠️", msg)

    def test_avisa_se_a_cp_devolver_outro_lugar(self):
        cp = FakeCP(sale_script=[resp(200, SALE_COM_LUGAR)])
        cp.seat_map = mapa()
        cp.steps = {"confirm": resp(200, {"status": {"code": "CONFIRMED"}, "reference": "R", "seatData": {"carriageNumber": 21, "seatNumber": 112}})}
        self.run_early(cp)
        msg = [n for n in self.notes if n[0].startswith("Bilhete comprado")][0][1]
        self.assertIn("⚠️ pedi o lugar 21/113", msg); self.assertNotIn("lugar 112 (corredor)", msg)

    def test_sem_mudanca_de_lugar_a_mensagem_e_a_de_sempre(self):
        self.run_early(FakeCP())
        msg = [n for n in self.notes if n[0].startswith("Bilhete comprado")][0][1]
        self.assertNotIn("corredor", msg); self.assertNotIn("⚠️", msg)


class PedidoNovoTests(unittest.TestCase):
    """Os pedidos avulsos também levam o lugar ao corredor e explicam o desconto que ainda não abriu."""

    def setUp(self):
        from test_purchase_flow import PedidoFlowBase
        self.b = PedidoFlowBase(); self.b.setUp()

    def test_pedido_muda_o_lugar_para_o_corredor(self):
        cp = FakeCP(sale_script=[resp(200, SALE_COM_LUGAR)])
        cp.seat_map = mapa()
        code, st = self.b.run_pedido(cp)
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertIn(("change_seat", 21, 113), cp.calls)
        self.assertEqual(st["seat_changed"], "21/112 → 21/113 (corredor)")

    def test_desconto_antes_de_T_liberta_o_lugar_e_explica(self):
        cp = FakeCP(steps={"items": [RECUSA(), RECUSA()]})
        code, st = self.b.run_pedido(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertIn("cancel", cp.calls)
        self.assertTrue(any("desconto do passe ainda não abriu" in t for t in self.b.titles()))
        self.assertNotIn("confirm", cp.calls)

    def test_pedido_regista_a_tentativa(self):
        self.b.run_pedido(FakeCP())
        self.assertEqual([r["fase"] for r in self.b.sheets.attempts], ["venda"])


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
