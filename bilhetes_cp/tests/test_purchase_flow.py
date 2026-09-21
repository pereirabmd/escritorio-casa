"""Máquina de estados da compra (3.3.1, 3.10.5, 3.10.6) com uma CP falsa.

O que mais importa provar: nunca há um segundo POST /sale às cegas — só um
retry quando é seguro (erro antes de enviar, ou 5xx) — e um estado AMBÍGUO
nunca é repetido nem confirmado sem verificação.
"""

import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import _env  # noqa: F401
import common
import hot_buy
import pre_flight
from cp_ticket import CPError, CPResponse, classify_sale_response, extract_messages

DAY = date.today() + timedelta(days=30)   # no futuro: o lembrete T-30min consegue agendar-se


def resp(status=200, body=None, messages=None):
    body = {} if body is None else body
    if messages is not None:
        body = {**body, "messages": messages}
    text = str(body)
    return CPResponse(status=status, body=body, text=text, date_header="Mon, 21 Sep 2026 12:50:10 GMT",
                      sent_at=1.0, received_at=1.2, elapsed_ms=200.0, messages=extract_messages(body))


class FakeCP:
    """Regista chamadas; `sale_script` é a lista de respostas/exceções do POST /sale."""

    def __init__(self, sale_script=None, steps=None):
        self.calls = []
        self.sale_script = list(sale_script if sale_script is not None
                                else [resp(200, {"saleID": 777})])
        self.steps = steps or {}
        self.access_token = "tok"

    def warm(self):
        self.calls.append("warm")

    trip = None

    def search_journeys(self, *a):
        self.calls.append("search")
        return {"outwardTrip": [self.trip or {"saleableOnline": False, "departureTime": "06:45", "arrivalTime": "09:10", "travelSections": [
            {"trainNumber": 524, "serviceCode": {"code": "IC", "designation": "Intercidades"},
             "departureStation": {"code": "94-38000"}, "arrivalStation": {"code": "94-31039"}}]}]}

    def create_sale_request(self, *a):
        self.sale_args = a
        self.calls.append("sale")
        item = self.sale_script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _step(self, name, default):
        """Comporta-se como o CPClient real: erro de rede ou resposta não-2xx levantam CPError."""
        self.calls.append(name)
        item = self.steps.get(name, default)
        if isinstance(item, list):           # sequência: consome uma por chamada, depois o normal
            item = item.pop(0) if item else default
        if isinstance(item, Exception):
            raise item
        if not item.ok:
            raise CPError("http", f"HTTP {item.status}", item)
        return item

    def set_passengers(self, sid): return self._step("passengers", resp())
    def set_client(self, sid): return self._step("client", resp())
    def set_fiscal(self, sid): return self._step("fiscal", resp())
    def apply_green_pass(self, sid): return self._step("items", resp(200, {"totalAmount": 0}))

    def confirm(self, sid):
        return self._step("confirm", resp(200, {"status": {"code": "CONFIRMED"}, "reference": "REF123",
                                              "seatData": {"carriageNumber": 3, "seatNumber": 42}}))


class FakeSheets:
    def __init__(self, tickets=None):
        self.tickets, self.logs, self.bilhetes = tickets or [], [], []

    def read_tickets(self): return self.tickets
    def append_log(self, *row): self.logs.append(row)
    def append_ticket(self, *row): self.bilhetes.append(row)


class FlowBase(unittest.TestCase):
    train = 524

    def setUp(self):
        self.leg = common.Leg(DAY, "ida", "aveiro", "lisboa_oriente", self.train, "06:45", 12)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        common._state_file("trains.json").unlink(missing_ok=True)
        self.notes = []
        self.sheets = FakeSheets()
        self.sleeps = []
        p1 = mock.patch.object(pre_flight, "run_preflight", return_value=[])
        p2 = mock.patch.object(pre_flight, "check_ntfy",
                               return_value=pre_flight.Check("ntfy", True, "ok"))
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def notify_fn(self, title, message, **kw):
        self.notes.append((title, message, kw))
        return True

    def run_buyer(self, cp, login_fn=None, sheets=None, state=None):
        if state:
            lock = common.PurchaseLock(self.leg.lock_key)
            lock.acquire(); lock.update(**state); lock.release()
        lock = common.PurchaseLock(self.leg.lock_key)
        fire = self.leg.fire.timestamp()
        buyer = hot_buy.Buyer(
            self.leg, lock, sheets=sheets or self.sheets,
            login_fn=login_fn or (lambda: {"access_token": "a", "refresh_token": "r"}),
            refresh_fn=lambda rt: {"access_token": "a2", "refresh_token": "r2"},
            cp_factory=lambda tok: cp, clock=lambda: fire + 100, sleep=self.sleeps.append,
            notify_fn=self.notify_fn)
        code = buyer.run()
        return code, common.peek_state(self.leg.lock_key)

    def titles(self):
        return [n[0] for n in self.notes]


class HappyPathTests(FlowBase):
    def test_compra_completa(self):
        cp = FakeCP()
        code, st = self.run_buyer(cp)
        self.assertEqual(code, 0)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertEqual([c for c in cp.calls if c not in ("warm",)],
                         ["search", "sale", "passengers", "client", "fiscal", "items", "confirm"])
        self.assertEqual((st["reference"], st["carriage"], st["seat"]), ("REF123", 3, 42))
        self.assertEqual(self.sheets.bilhetes[0][:2], (DAY.isoformat(), 524))
        self.assertEqual(self.sheets.bilhetes[0][5:], (3, 42, "REF123"))
        self.assertTrue(any("Bilhete comprado" in t for t in self.titles()))
        # lembrete T-30min agendado no servidor (kwarg `at`), 30 min antes da partida
        lembrete = [n for n in self.notes if n[0].startswith("Partida às")][0]
        self.assertEqual(lembrete[2]["at"], self.leg.departure - timedelta(minutes=30))
        self.assertIn("carruagem 3, lugar 42", lembrete[1])
        self.assertTrue(st["reminder_scheduled"])
        self.assertEqual(self.sheets.logs[-1][0], "COMPRA")

    def test_guarda_o_servico_pesquisado_para_uso_futuro(self):
        self.run_buyer(FakeCP())
        cache = common._read_json(common._state_file("trains.json"), {})
        self.assertEqual(cache["524|aveiro|lisboa_oriente"][0]["code"], "IC")


class SectionsAndTokensTests(FlowBase):
    def test_comboio_com_transbordo_envia_uma_entrada_por_seccao(self):
        # PLANO_FINAL 7.3: pedir o IC 510, que vem em [4656, 510], não pode comprar só o 4656
        self.leg = common.Leg(DAY, "ida", "aveiro", "lisboa_oriente", 510, "07:44", 12)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        cp = FakeCP()
        cp.trip = {"saleableOnline": True, "departureTime": "07:44", "travelSections": [
            {"trainNumber": 4656, "serviceCode": {"code": "R", "designation": "Regional"},
             "departureStation": {"code": "94-38000"}, "arrivalStation": {"code": "94-37002"}},
            {"trainNumber": 510, "serviceCode": {"code": "IC", "designation": "Intercidades"},
             "departureStation": {"code": "94-37002"}, "arrivalStation": {"code": "94-31039"}}]}
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        _date, sections = cp.sale_args
        self.assertEqual([(s["train"], s["dep"], s["arr"], s["code"]) for s in sections],
                         [(4656, "94-38000", "94-37002", "R"), (510, "94-37002", "94-31039", "IC")])

    def test_transbordo_sem_estacoes_e_erro_claro_e_nao_uma_compra_a_adivinhar(self):
        cp = FakeCP()
        cp.trip = {"departureTime": "06:45", "travelSections": [
            {"trainNumber": 4656, "serviceCode": {"code": "R", "designation": "R"}},
            {"trainNumber": 524, "serviceCode": {"code": "IC", "designation": "IC"}}]}
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertNotIn("sale", cp.calls)

    def test_guarda_os_tokens_no_login_e_na_renovacao(self):
        common.TOKEN_FILE.unlink(missing_ok=True)
        cp = FakeCP()
        _, st = self.run_buyer(cp, login_fn=lambda: {"access_token": "a1", "refresh_token": "r1", "expires_in": 300})
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(common.load_tokens()["refresh_token"], "r1")


class SearchOnlyTests(FlowBase):
    def test_pesquisa_e_mostra_sem_criar_venda_nem_estado_nem_login(self):
        cp = FakeCP()
        linhas = []
        code = hot_buy.search_only(self.leg, cp_factory=lambda tok: cp, out=linhas.append)
        self.assertEqual(code, 0)
        self.assertEqual(cp.calls, ["search"])                       # só pesquisou
        self.assertFalse(common.lock_path(self.leg.lock_key).exists() and common.peek_state(self.leg.lock_key))
        texto = "\n".join(linhas)
        self.assertIn("Nenhuma venda foi criada", texto)
        self.assertIn("bate certo", texto)
        self.assertEqual(self.notes, [])

    def test_avisa_quando_a_hora_da_config_difere_da_cp(self):
        cp = FakeCP(); cp.trip = {"departureTime": "13:27", "travelSections": [
            {"trainNumber": 524, "serviceCode": {"code": "IC", "designation": "IC"},
             "departureStation": {"code": "94-38000"}, "arrivalStation": {"code": "94-31039"}}]}
        linhas = []
        hot_buy.search_only(self.leg, cp_factory=lambda tok: cp, out=linhas.append)
        self.assertIn("NÃO bate certo", "\n".join(linhas))

    def test_falha_de_pesquisa_devolve_erro_sem_excecao(self):
        cp = FakeCP(); cp.search_journeys = mock.Mock(side_effect=RuntimeError("Comboio nº 524 não encontrado"))
        linhas = []
        self.assertEqual(hot_buy.search_only(self.leg, cp_factory=lambda tok: cp, out=linhas.append), 2)
        self.assertIn("FALHA", "\n".join(linhas))


class SaleOutcomeTests(FlowBase):
    def test_esgotado_notifica_e_para_sem_repetir(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=[{"message": "Comboio esgotado"}])])
        code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (0, "SOLD_OUT"))
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertNotIn("passengers", cp.calls)
        self.assertTrue(any("Esgotado" in t for t in self.titles()))

    def test_erro_tecnico_5xx_faz_retry_seguro(self):
        cp = FakeCP(sale_script=[resp(503, {}), resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 2)

    def test_5xx_persistente_falha_ao_fim_das_tentativas(self):
        cp = FakeCP(sale_script=[resp(500), resp(502), resp(503)])
        code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertEqual(cp.calls.count("sale"), 3)

    def test_falha_antes_de_enviar_faz_retry(self):
        cp = FakeCP(sale_script=[CPError("not_sent", "ligação recusada"), resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 2)

    def test_timeout_ambiguo_nunca_repete_e_pede_verificacao_manual(self):
        cp = FakeCP(sale_script=[CPError("ambiguous", "ReadTimeout"), resp(200, {"saleID": 9})])
        code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (2, "AMBIGUOUS"))
        self.assertEqual(cp.calls.count("sale"), 1)        # o ponto crítico
        self.assertNotIn("passengers", cp.calls)
        self.assertTrue(any("AMBÍGUO" in t for t in self.titles()))
        self.assertTrue(any("App CP" in n[1] for n in self.notes))

    def test_erro_4xx_desconhecido_nao_e_repetido(self):
        cp = FakeCP(sale_script=[resp(400, {}, messages=["Pedido inválido"]), resp(200, {"saleID": 9})])
        code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertEqual(cp.calls.count("sale"), 1)

    def test_200_sem_saleid_nao_conta_como_sucesso(self):
        cp = FakeCP(sale_script=[resp(200, {"algo": "estranho"})])
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertNotIn("passengers", cp.calls)


class CompletionTests(FlowBase):
    def test_desconto_que_nao_zera_o_total_nao_confirma(self):
        cp = FakeCP(steps={"items": resp(200, {"totalAmount": 12.5})})
        code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertNotIn("confirm", cp.calls)
        self.assertTrue(any("Desconto do passe" in t for t in self.titles()))

    def test_total_zero_em_dict_ou_texto_e_aceite(self):
        for total in ({"value": 0}, "0.00", "0,00"):
            self.setUp()
            cp = FakeCP(steps={"items": resp(200, {"totalAmount": total})})
            self.assertEqual(self.run_buyer(cp)[1]["state"], "CONFIRMED", total)

    def test_confirmacao_com_estado_inesperado_nao_e_sucesso(self):
        cp = FakeCP(steps={"confirm": resp(200, {"status": {"code": "PENDING"}})})
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "FAILED")

    def test_passo_com_500_ocasional_e_repetido_e_conclui(self):
        cp = FakeCP(steps={"client": [resp(500), resp(502)]})
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("client"), 3)
        self.assertEqual(cp.calls.count("sale"), 1)

    def test_passo_com_500_persistente_esgota_tentativas_sem_nova_venda(self):
        cp = FakeCP(steps={"client": resp(500)})
        code, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertEqual(cp.calls.count("client"), len(hot_buy.cfg("step_retry_delays_s", [0.5, 1, 2, 4, 8])) + 1)
        self.assertEqual(cp.calls.count("sale"), 1)  # nunca cria outra venda
        self.assertTrue(any("Venda por concluir" in t for t in self.titles()))

    def test_token_expirado_no_meio_renova_e_continua(self):
        cp = FakeCP(steps={"fiscal": [resp(401)]})
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("fiscal"), 2)

    def test_erro_4xx_num_passo_nao_e_repetido(self):
        cp = FakeCP(steps={"passengers": resp(422, {}, messages=["CC inválido"])})
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "FAILED")
        self.assertEqual(cp.calls.count("passengers"), 1)

    def test_repete_o_passo_durante_o_prazo_da_venda_de_15_min(self):
        delays = hot_buy.cfg("step_retry_delays_s", [])
        self.assertGreaterEqual(sum(delays), 10 * 60)         # PLANO_FINAL 3.3.1: dentro dos 15 min
        self.assertLess(sum(delays), 15 * 60)
        cp = FakeCP(steps={"client": [resp(500)] * 10})       # falha 10 vezes e depois passa
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("client"), 11)
        self.assertEqual(cp.calls.count("sale"), 1)

    def test_regista_o_timestamp_do_servidor_para_a_calibracao(self):
        cp = FakeCP(sale_script=[resp(200, {"saleID": 9, "timestamp": "2026-09-21T13:50:44.610+01:00"})])
        _, st = self.run_buyer(cp)
        self.assertIn("timestamp CP 2026-09-21T13:50:44.610+01:00", st["timing"])

    def test_confirmacao_ambigua_nao_e_repetida_como_compra(self):
        cp = FakeCP(steps={"confirm": CPError("ambiguous", "ReadTimeout")})
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "AMBIGUOUS")
        self.assertEqual(cp.calls.count("sale"), 1)


class ResumeAndProtectionTests(FlowBase):
    def test_retoma_uma_venda_a_meio_sem_criar_outra(self):
        cp = FakeCP()
        _, st = self.run_buyer(cp, state={"state": "FISCAL_OK", "sale_id": 555})
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertNotIn("sale", cp.calls)
        self.assertNotIn("search", cp.calls)
        self.assertEqual([c for c in cp.calls if c != "warm"], ["items", "confirm"])

    def test_retoma_desde_sale_created(self):
        cp = FakeCP()
        self.run_buyer(cp, state={"state": "SALE_CREATED", "sale_id": 555})
        self.assertEqual([c for c in cp.calls if c != "warm"],
                         ["passengers", "client", "fiscal", "items", "confirm"])

    def test_estado_terminal_nao_faz_nada(self):
        for terminal in ("CONFIRMED", "SOLD_OUT", "FAILED", "AMBIGUOUS"):
            self.setUp()
            cp = FakeCP()
            code, st = self.run_buyer(cp, state={"state": terminal})
            self.assertEqual((code, cp.calls, st["state"]), (0, [], terminal))
            self.assertEqual(self.notes, [])

    def test_bilhete_ja_na_sheet_nao_e_comprado_outra_vez(self):
        sheets = FakeSheets(tickets=[[DAY.isoformat(), 524, "Aveiro", "Lisboa Oriente", "06:45", 3, 42, "R"]])
        cp = FakeCP()
        code, st = self.run_buyer(cp, sheets=sheets)
        self.assertEqual((code, st["state"], cp.calls), (0, "CONFIRMED", []))
        self.assertTrue(any("Já comprado" in t for t in self.titles()))

    def test_lock_ocupado_sai_sem_comprar(self):
        other = common.PurchaseLock(self.leg.lock_key)
        self.assertTrue(other.acquire())
        try:
            cp = FakeCP()
            code, _ = self.run_buyer(cp)
            self.assertEqual((code, cp.calls), (0, []))
        finally:
            other.release()

    def test_processo_relancado_demasiadas_vezes_e_abandonado_com_aviso(self):
        cp = FakeCP()
        code, st = self.run_buyer(cp, state={"state": "WARMING", "starts": hot_buy.MAX_STARTS})
        self.assertEqual(st["state"], "FAILED")
        self.assertEqual(cp.calls, [])
        self.assertTrue(any("abandonada" in t for t in self.titles()))

    def test_excecao_inesperada_nao_e_silenciosa(self):
        cp = FakeCP()
        cp.search_journeys = mock.Mock(side_effect=ValueError("bug"))
        with mock.patch.object(hot_buy, "notify_once", return_value=True) as n:
            code, st = self.run_buyer(cp)
        # ValueError na pesquisa não é apanhada como falha de pesquisa: vai para a rede de segurança
        self.assertEqual(code, 1)
        n.assert_called()
        self.assertIn("Erro inesperado", n.call_args[0][1])
        self.assertNotIn("sale", cp.calls)


class LoginTests(FlowBase):
    def test_login_impossivel_falha_com_aviso_e_sem_comprar(self):
        cp = FakeCP()

        def bad_login():
            raise RuntimeError("CAPTCHA")

        code, st = self.run_buyer(cp, login_fn=bad_login)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertEqual(cp.calls, [])
        self.assertTrue(any("Login na CP falhou" in t for t in self.titles()))

    def test_falha_da_sheet_nao_impede_a_compra_mas_fica_visivel(self):
        class BrokenSheets(FakeSheets):
            def read_tickets(self): raise RuntimeError("quota")
            def append_log(self, *r): raise RuntimeError("quota")
            def append_ticket(self, *r): raise RuntimeError("quota")

        with mock.patch.object(hot_buy, "notify_once", return_value=True) as n:
            code, st = self.run_buyer(FakeCP(), sheets=BrokenSheets())
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertTrue(n.called)   # avisou que não conseguiu escrever na Sheet


class ClassifyTests(unittest.TestCase):
    def test_classificacao_das_respostas_do_sale(self):
        self.assertEqual(classify_sale_response(resp(200, {"saleID": 1}))[0], "ok")
        self.assertEqual(classify_sale_response(resp(500))[0], "transient")
        self.assertEqual(classify_sale_response(resp(429))[0], "transient")
        self.assertEqual(classify_sale_response(resp(422, {}, messages=["Sem lugares disponíveis"]))[0], "sold_out")
        self.assertEqual(classify_sale_response(resp(200, {}, messages=["Comboio esgotado"]))[0], "sold_out")
        self.assertEqual(classify_sale_response(resp(400, {}, messages=["Estação inválida"]))[0], "known")
        self.assertEqual(classify_sale_response(resp(200, {"x": 1}))[0], "known")

    def test_extract_messages_aceita_varios_formatos(self):
        self.assertEqual(extract_messages({"messages": ["a", "b"]}), ["a", "b"])
        self.assertEqual(extract_messages({"messages": [{"type": "ERROR", "message": "falhou"}]}),
                         ["ERROR | falhou"])
        self.assertEqual(extract_messages({"messages": "só texto"}), ["só texto"])
        self.assertEqual(extract_messages({}), [])
        self.assertEqual(extract_messages(None), [])


if __name__ == "__main__":
    unittest.main()
