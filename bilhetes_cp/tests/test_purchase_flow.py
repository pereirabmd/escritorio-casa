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

    sale_detail = None

    def get_sale(self, sid):
        self.calls.append("get_sale")
        if isinstance(self.sale_detail, Exception):
            raise self.sale_detail
        return resp(200, self.sale_detail or {})

    def confirm(self, sid):
        return self._step("confirm", resp(200, {"status": {"code": "CONFIRMED"}, "reference": "REF123",
                                              "seatData": {"carriageNumber": 3, "seatNumber": 42}}))


class FakeSheets:
    def __init__(self, tickets=None):
        self.tickets, self.logs, self.bilhetes = tickets or [], [], []
        self.requests, self.request_updates = [], []

    def read_tickets(self): return self.tickets
    def append_log(self, *row): self.logs.append(row)
    def append_ticket(self, *row): self.bilhetes.append(row)
    def append_request(self, *row, **kw): self.requests.append((row, kw))
    def update_request(self, row, **fields): self.request_updates.append((row, fields))


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

    def run_buyer(self, cp, login_fn=None, sheets=None, state=None, clock_offset=100, advancing=False):
        if state:
            lock = common.PurchaseLock(self.leg.lock_key)
            lock.acquire(); lock.update(**state); lock.release()
        lock = common.PurchaseLock(self.leg.lock_key)
        fire = self.leg.fire.timestamp()
        now = [fire + clock_offset]                       # `advancing`: o tempo avança com cada espera
        def sleep(s):
            self.sleeps.append(s)
            if advancing:
                now[0] += s
        buyer = hot_buy.Buyer(
            self.leg, lock, sheets=sheets or self.sheets,
            login_fn=login_fn or (lambda: {"access_token": "a", "refresh_token": "r"}),
            refresh_fn=lambda rt: {"access_token": "a2", "refresh_token": "r2"},
            cp_factory=lambda tok: cp, clock=lambda: now[0], sleep=sleep,
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
        self.assertIn("Carruagem 3, lugar 42", lembrete[1])
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


class BoardingTimeTests(FlowBase):
    def test_hora_da_config_e_a_da_1a_estacao_o_lembrete_e_o_bilhete_usam_o_embarque(self):
        # Config 06:45 (o comboio parte do Porto); Bruno embarca em Aveiro às 07:27
        self.leg = common.Leg(DAY, "ida", "aveiro", "lisboa_oriente", 524, "06:45", 12,
                              anchor="06:45", anchor_date=DAY, board="07:27", board_date=DAY)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        cp = FakeCP()
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        lembrete = [n for n in self.notes if n[0].startswith("Partida às")][0]
        self.assertEqual(lembrete[0], "Partida às 07:27 · carruagem 3, lugar 42")                # não 06:45; lugar no título
        self.assertEqual(lembrete[2]["at"].strftime("%H:%M"), "06:57")                            # 07:27 - 30 min
        self.assertEqual(self.sheets.bilhetes[0][4], "07:27")                                      # hora do bilhete = embarque
        self.assertEqual(self.leg.fire.strftime("%H:%M"), "06:45")                                # o disparo, à 1.ª estação

    def test_nao_avisa_hora_diferente_quando_a_config_e_a_da_1a_estacao(self):
        self.leg = common.Leg(DAY, "ida", "aveiro", "lisboa_oriente", 524, "06:10", 12,
                              anchor="06:10", anchor_date=DAY, board="06:45", board_date=DAY)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        with mock.patch.object(hot_buy, "notify_once", return_value=True) as n:
            self.run_buyer(FakeCP())
        self.assertFalse(any("Hora não bate certo" in str(c) for c in n.call_args_list))


SEM_LUGAR = resp(200, {"status": {"code": "CONFIRMED"}, "reference": "REF9"})


class MultiTrainSeatTests(FlowBase):
    """Viagem com transbordo (ex.: 511 + 4609): um lugar por comboio (Bruno, 22/09)."""

    def test_dois_lugares_de_comboios_diferentes_aparecem_os_dois(self):
        cp = FakeCP(sale_script=[resp(200, {"saleID": 9, "outwardTrip": [
            {"trainNumber": 511, "seatData": {"carriageNumber": 2, "seatNumber": 14}},
            {"trainNumber": 4609, "seatData": {"carriageNumber": 7, "seatNumber": 3}}]})],
                    steps={"confirm": resp(200, {"status": {"code": "CONFIRMED"}, "reference": "REF123"})})
        _, st = self.run_buyer(cp)
        self.assertEqual(len(st["seats"]), 2)
        titulo = [n for n in self.notes if n[0].startswith("Partida às")][0][0]
        self.assertIn("carruagem 2, lugar 14 (comboio 511)", titulo)
        self.assertIn("carruagem 7, lugar 3 (comboio 4609)", titulo)
        self.assertEqual(self.sheets.bilhetes[0][5], "2 / 7")
        self.assertEqual(self.sheets.bilhetes[0][6], "14 / 3")

    def test_um_so_lugar_nao_leva_o_numero_do_comboio(self):
        _, st = self.run_buyer(FakeCP())
        titulo = [n for n in self.notes if n[0].startswith("Partida às")][0][0]
        self.assertIn("carruagem 3, lugar 42", titulo)
        self.assertNotIn("comboio", titulo)


class SeatInReminderTests(FlowBase):
    """O lembrete de partida tem de levar carruagem e lugar (Bruno, 22/09)."""

    def lembrete(self):
        return [n for n in self.notes if n[0].startswith("Partida às")][0]

    def test_o_lembrete_leva_carruagem_e_lugar_no_titulo_e_na_mensagem(self):
        _, st = self.run_buyer(FakeCP())
        titulo, msg, kw = self.lembrete()
        self.assertEqual(titulo, "Partida às 06:45 · carruagem 3, lugar 42")
        self.assertIn("Carruagem 3, lugar 42", msg)
        self.assertIn("Comboio 524", msg)
        self.assertIn("at", kw)
        self.assertTrue(st["seat_known"])

    def test_se_o_confirm_nao_traz_o_lugar_usa_o_do_post_sale(self):
        cp = FakeCP(sale_script=[resp(200, {"saleID": 9, "seatData": {"carriageNumber": 5, "seatNumber": 17}})],
                    steps={"confirm": SEM_LUGAR})
        _, st = self.run_buyer(cp)
        self.assertEqual((st["carriage"], st["seat"]), (5, 17))            # não foi sobrescrito por None
        self.assertEqual(self.lembrete()[0], "Partida às 06:45 · carruagem 5, lugar 17")
        self.assertNotIn("get_sale", cp.calls)                             # nem foi preciso ir à venda
        self.assertEqual(self.sheets.bilhetes[0][5:7], (5, 17))

    def test_como_ultimo_recurso_le_a_venda(self):
        cp = FakeCP(steps={"confirm": SEM_LUGAR})
        cp.sale_detail = {"seatData": {"carriageNumber": 8, "seatNumber": 61}}
        _, st = self.run_buyer(cp)
        self.assertIn("get_sale", cp.calls)
        self.assertEqual(self.lembrete()[0], "Partida às 06:45 · carruagem 8, lugar 61")

    def test_sem_lugar_em_lado_nenhum_o_lembrete_segue_e_diz_onde_ver(self):
        cp = FakeCP(steps={"confirm": SEM_LUGAR})
        cp.sale_detail = RuntimeError("HTTP 500")
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")                          # a compra não falha por isto
        titulo, msg, _ = self.lembrete()
        self.assertEqual(titulo, "Partida às 06:45 (daqui a 30 min)")
        self.assertIn("vê na App CP", msg)
        self.assertFalse(st["seat_known"])
        self.assertTrue(any("Bilhete comprado" in t for t in self.titles()))


class SaleOutcomeTests(FlowBase):
    def test_esgotado_confirma_se_com_uma_rajada_longa_antes_de_desistir(self):
        # Bruno, 22/09: o mesmo "esgotado" pode aparecer com a rede condicionada, não só a sério —
        # o servidor respondeu SEM criar venda, por isso repetir é seguro (como um erro transitório).
        # Esquema tão persistente quanto o que Bruno já fazia à mão: ~12 min, 25 retentativas (26 no total).
        delays = hot_buy.cfg("sold_out_retry_delays_s", [])
        self.assertEqual(len(delays), 25)
        self.assertAlmostEqual(sum(delays), 727.5)
        esgotado = resp(409, {}, messages=[{"message": "Comboio esgotado"}])
        cp = FakeCP(sale_script=[esgotado] * (len(delays) + 1))
        code, st = self.run_buyer(cp, advancing=True)
        self.assertEqual((code, st["state"]), (0, "SOLD_OUT"))
        self.assertEqual(cp.calls.count("sale"), len(delays) + 1)
        self.assertNotIn("passengers", cp.calls)
        self.assertEqual(self.sleeps, delays)
        self.assertTrue(any("Esgotado" in t for t in self.titles()))
        self.assertIn(f"confirmado depois de {len(delays) + 1} tentativas em ~12 min", self.notes[-1][1])

    def test_a_rajada_do_esgotado_renova_o_token_se_demorar_mais_de_4_min(self):
        # o access_token dura 5 min (3.1); uma rajada de ~12 min tem de o renovar a meio.
        delays = hot_buy.cfg("sold_out_retry_delays_s", [])
        esgotado = resp(409, {}, messages=[{"message": "Comboio esgotado"}])
        cp = FakeCP(sale_script=[esgotado] * (len(delays) + 1))
        reauths = []
        with mock.patch.object(hot_buy.Buyer, "reauth",
                               side_effect=lambda self, quiet=False: reauths.append(quiet), autospec=True):
            self.run_buyer(cp, advancing=True)
        self.assertTrue(any(reauths))            # renovou pelo menos uma vez

    def test_a_rajada_do_esgotado_para_se_o_comboio_ja_partiu(self):
        delays = hot_buy.cfg("sold_out_retry_delays_s", [])
        esgotado = resp(409, {}, messages=[{"message": "Comboio esgotado"}])
        cp = FakeCP(sale_script=[esgotado] * (len(delays) + 1))
        depart_offset = self.leg.departure.timestamp() - self.leg.fire.timestamp()
        code, st = self.run_buyer(cp, clock_offset=depart_offset + 1, advancing=True)
        self.assertEqual((code, st["state"]), (0, "SOLD_OUT"))
        self.assertEqual(cp.calls.count("sale"), 1)     # nem chegou a tentar: o comboio já partiu

    def test_esgotado_que_era_so_rede_condicionada_recupera_dentro_da_rajada(self):
        esgotado = resp(409, {}, messages=[{"message": "Comboio esgotado"}])
        cp = FakeCP(sale_script=[esgotado, esgotado, esgotado, resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")           # não desistiu: era transitório
        self.assertEqual(cp.calls.count("sale"), 4)
        self.assertEqual(self.sleeps[:3], [0, 0.5, 0.5])
        self.assertFalse(any("Esgotado" in t for t in self.titles()))

    def test_esgotado_sem_rajada_configurada_para_logo_como_antes(self):
        esgotado = resp(409, {}, messages=[{"message": "Comboio esgotado"}])
        cp = FakeCP(sale_script=[esgotado])
        with mock.patch.dict(hot_buy.app_config()["purchase"], {"sold_out_retry_delays_s": []}):
            code, st = self.run_buyer(cp)
        self.assertEqual((code, st["state"]), (0, "SOLD_OUT"))
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertEqual(self.sleeps, [])
        self.assertNotIn("confirmado depois de", self.notes[-1][1])

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


NAO_ABERTO = [{"message": "A venda para este comboio ainda não está aberta"}]


class NotOpenYetTests(FlowBase):
    """Uma venda que abre mais tarde do que o previsto é tratada na iteração seguinte (Bruno, 22/09)."""

    def test_ainda_nao_aberto_repete_e_compra_quando_abre(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO), resp(409, {}, messages=NAO_ABERTO),
                                 resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp)
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(cp.calls.count("sale"), 3)                       # duas recusas e uma venda
        self.assertEqual(cp.calls.count("passengers"), 1)                 # e só UMA sequência de passos
        self.assertEqual(len(self.sleeps), 2)
        self.assertEqual([t for t in self.titles() if t.startswith("Ainda não abriu")].__len__(), 1)   # avisa uma vez
        self.assertIn("abriu", st["timing"])                              # fica registado o atraso
        self.assertTrue(any(r[5] == "AINDA_NAO_ABERTO" for r in self.sheets.logs))

    def test_comeca_depressa_e_abranda(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO)] * 3 + [resp(200, {"saleID": 9})])
        self.run_buyer(cp, clock_offset=1, advancing=True)                # 1 s depois do alvo: fase rápida
        self.assertEqual(self.sleeps, [0.25, 0.25, 0.25])
        self.sleeps.clear()
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO)] * 2 + [resp(200, {"saleID": 9})])
        self.setUp()
        self.run_buyer(cp, clock_offset=60, advancing=True)               # 60 s depois: fase lenta
        self.assertEqual(self.sleeps, [2.0, 2.0])

    def test_nao_repete_para_sempre_e_diz_que_nao_abriu(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO)] * 2000)
        code, st = self.run_buyer(cp, clock_offset=0, advancing=True)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        n = cp.calls.count("sale")
        self.assertTrue(300 < n < 450, n)                                # 20 s a 0,25 s + ~10 min a 2 s
        self.assertNotIn("passengers", cp.calls)
        self.assertTrue(any("não abriu" in t for t in self.titles()))
        self.assertEqual(len([t for t in self.titles() if t.startswith("Ainda não abriu")]), 1)

    def test_recusa_nao_reconhecida_repete_uns_segundos_e_depois_falha(self):
        recusa = resp(400, {}, messages=["Pedido inválido"])
        cp = FakeCP(sale_script=[recusa, resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp, clock_offset=1, advancing=True)
        self.assertEqual((st["state"], cp.calls.count("sale")), ("CONFIRMED", 2))
        self.setUp()
        cp = FakeCP(sale_script=[recusa] * 1000)
        code, st = self.run_buyer(cp, clock_offset=0, advancing=True)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertTrue(40 < cp.calls.count("sale") < 100, cp.calls.count("sale"))     # ~15 s a 0,25 s
        self.assertTrue(any("Compra falhou" in t for t in self.titles()))

    def test_recusa_nao_reconhecida_depois_da_janela_curta_nao_repete(self):
        cp = FakeCP(sale_script=[resp(400, {}, messages=["Pedido inválido"]), resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp, clock_offset=100)
        self.assertEqual((st["state"], cp.calls.count("sale")), ("FAILED", 1))

    def test_esgotado_persistente_usa_o_seu_proprio_esquema_nao_o_ciclo_do_ainda_nao_aberto(self):
        delays = hot_buy.cfg("sold_out_retry_delays_s", [])
        esgotado = resp(409, {}, messages=["Comboio esgotado"])
        cp = FakeCP(sale_script=[esgotado] * (len(delays) + 1))
        _, st = self.run_buyer(cp, clock_offset=1, advancing=True)
        self.assertEqual((st["state"], cp.calls.count("sale")), ("SOLD_OUT", len(delays) + 1))
        self.assertEqual(self.sleeps, delays)          # o esquema do esgotado, não o do "ainda não aberto"

    def test_estado_ambiguo_nunca_e_repetido_mesmo_com_a_venda_por_abrir(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO), CPError("ambiguous", "ReadTimeout"),
                                 resp(200, {"saleID": 9})])
        _, st = self.run_buyer(cp, clock_offset=1, advancing=True)
        self.assertEqual((st["state"], cp.calls.count("sale")), ("AMBIGUOUS", 2))     # parou no ambíguo

    def test_para_de_tentar_quando_o_comboio_ja_partiu(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=NAO_ABERTO)] * 50)
        depart = self.leg.departure.timestamp() - self.leg.fire.timestamp()
        _, st = self.run_buyer(cp, clock_offset=depart + 5)              # já depois da partida
        self.assertEqual((st["state"], cp.calls.count("sale")), ("FAILED", 1))


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


class RequestMirrorTests(FlowBase):
    """Uma viagem da Config que esgota a validação/retry é espelhada para a fila de Pedidos
    (3.2.1), desde que o comboio ainda não tenha partido; uma confirmada nunca é."""

    def test_esgotado_e_espelhado_para_pedidos(self):
        cp = FakeCP(sale_script=[resp(409, {}, messages=[{"message": "Comboio esgotado"}])]
                    * (len(hot_buy.cfg("sold_out_retry_delays_s", [])) + 1))
        _, st = self.run_buyer(cp, advancing=True)
        self.assertEqual(st["state"], "SOLD_OUT")
        self.assertEqual(len(self.sheets.requests), 1)
        row = self.sheets.requests[0]
        self.assertEqual(row[0][0], self.leg.date.isoformat())
        self.assertEqual(row[0][3], self.leg.train)
        self.assertEqual(row[1]["estado"], "ESGOTADO")

    def test_falhou_e_espelhado_para_pedidos(self):
        cp = FakeCP(sale_script=[resp(400, {}, messages=["Pedido inválido"])])
        _, st = self.run_buyer(cp, clock_offset=100)
        self.assertEqual(st["state"], "FAILED")
        self.assertEqual(len(self.sheets.requests), 1)

    def test_confirmada_nunca_e_espelhada(self):
        _, st = self.run_buyer(FakeCP())
        self.assertEqual(st["state"], "CONFIRMED")
        self.assertEqual(self.sheets.requests, [])

    def test_viagem_ja_passada_nao_e_espelhada(self):
        self.leg = common.Leg(DAY, "v12", "aveiro", "lisboa_oriente", self.train, "06:45", 12,
                              board="06:45", board_date=DAY - timedelta(days=400))
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        cp = FakeCP(sale_script=[resp(400, {}, messages=["Pedido inválido"])])
        self.run_buyer(cp, clock_offset=100)
        self.assertEqual(self.sheets.requests, [])


class PedidoFlowBase(unittest.TestCase):
    """Como o FlowBase, mas para o `PedidoAttempt` — leve, sem hotstart nem rajada (3.2.1)."""
    train = 524

    def setUp(self):
        self.leg = common.Leg(DAY, "pedido5", "aveiro", "lisboa_oriente", self.train, "06:45", 5)
        common.lock_path(self.leg.lock_key).unlink(missing_ok=True)
        common._state_file("trains.json").unlink(missing_ok=True)
        self.notes = []
        self.sheets = FakeSheets()
        self.sleeps = []

    def notify_fn(self, title, message, **kw):
        self.notes.append((title, message, kw))
        return True

    def run_pedido(self, cp, login_fn=None, sheets=None):
        lock = common.PurchaseLock(self.leg.lock_key)
        attempt = hot_buy.PedidoAttempt(
            self.leg, lock, sheets=sheets or self.sheets,
            login_fn=login_fn or (lambda: {"access_token": "a", "refresh_token": "r"}),
            cp_factory=lambda tok: cp, clock=lambda: 1_800_000_000.0, sleep=self.sleeps.append,
            notify_fn=self.notify_fn)
        code = attempt.run()
        return code, common.peek_state(self.leg.lock_key)

    def titles(self):
        return [n[0] for n in self.notes]


class PedidoAttemptTests(PedidoFlowBase):
    def test_compra_completa_sem_esperas(self):
        code, st = self.run_pedido(FakeCP())
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertEqual(self.sheets.bilhetes[0][:2], (DAY.isoformat(), 524))
        self.assertTrue(any("Bilhete comprado" in t for t in self.titles()))
        # sem hotstart: nenhuma espera longa (só pausas curtas de retry, que aqui nem chegam a existir)
        self.assertEqual(self.sleeps, [])
        # escreve A_TENTAR logo no arranque e o resultado final, sempre com Ultima_Tentativa
        estados = [f["estado"] for _, f in self.sheets.request_updates]
        self.assertEqual(estados, ["A_TENTAR", "CONFIRMADO"])
        self.assertTrue(all("ultima_tentativa" in f for _, f in self.sheets.request_updates))
        self.assertEqual(self.sheets.request_updates[-1][1]["forcar"], "NAO")

    def test_esgotado_nao_faz_rajada_uma_so_tentativa(self):
        # a diferença central para a Config (3.10): aqui nunca há rajada de ~12 min — um "esgotado"
        # termina já a tentativa, mesmo que seja rede condicionada; a próxima oportunidade é o
        # intervalo agendado ou "Tentar agora" outra vez.
        cp = FakeCP(sale_script=[resp(409, {}, messages=[{"message": "Comboio esgotado"}])])
        code, st = self.run_pedido(cp)
        self.assertEqual((code, st["state"]), (0, "SOLD_OUT"))
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertEqual(self.sheets.request_updates[-1][1]["estado"], "ESGOTADO")

    def test_erro_tecnico_tem_no_maximo_uma_repeticao(self):
        cp = FakeCP(sale_script=[resp(503, {}), resp(200, {"saleID": 9})])
        code, st = self.run_pedido(cp)
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertEqual(cp.calls.count("sale"), 2)

    def test_erro_tecnico_duas_vezes_seguidas_falha_sem_terceira_tentativa(self):
        cp = FakeCP(sale_script=[resp(503, {}), resp(503, {})])
        code, st = self.run_pedido(cp)
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertEqual(cp.calls.count("sale"), 2)   # nunca uma 3.ª

    def test_ambiguo_nunca_repete(self):
        cp = FakeCP(sale_script=[CPError("ambiguous", "ReadTimeout")])
        code, st = self.run_pedido(cp)
        self.assertEqual((code, st["state"]), (2, "AMBIGUOUS"))
        self.assertEqual(cp.calls.count("sale"), 1)
        self.assertEqual(self.sheets.request_updates[-1][1]["estado"], "AMBIGUO")

    def test_falha_num_passo_pos_venda_tem_no_maximo_uma_repeticao(self):
        cp = FakeCP(steps={"passengers": [CPError("http", "HTTP 500", resp(500, {}))]})
        code, st = self.run_pedido(cp)
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))   # a repetição do passo salvou
        self.assertEqual(cp.calls.count("passengers"), 2)

    def test_login_impossivel_falha_ja_sem_esperar_pelo_disparo(self):
        code, st = self.run_pedido(FakeCP(), login_fn=lambda: (_ for _ in ()).throw(RuntimeError("CAPTCHA")))
        self.assertEqual((code, st["state"]), (2, "FAILED"))
        self.assertEqual(self.sleeps, [])   # sem hotstart: falha logo, não fica à espera de nada

    def test_ja_comprado_nao_repete(self):
        sheets = FakeSheets(tickets=[[self.leg.date.isoformat(), self.leg.train, "Aveiro", "Lisboa Oriente"]])
        cp = FakeCP()
        code, st = self.run_pedido(cp, sheets=sheets)
        self.assertEqual((code, st["state"]), (0, "CONFIRMED"))
        self.assertEqual(cp.calls, [])


class ClassifyTests(unittest.TestCase):
    def test_erro_real_de_22_09_500_com_ws_res_116_e_esgotado_nao_transitorio(self):
        # Resposta real da CP (comboio 521, 22/09/2026): HTTP 500, sem "messages", mas com error/
        # description/message ao nível de topo. Antes desta correção era lido como "transient" e
        # gerava 3 tentativas reais desnecessárias antes de desistir.
        body = {"status": 500, "error": "WS:RES:116",
                "description": "Atenção\nNão há lugares disponíveis para a totalidade do pedido\nWS:RES:9XX|116",
                "message": "Não foi possível reservar os lugares"}
        r = resp(500, body)
        self.assertEqual(extract_messages(body), ["WS:RES:116 | Não foi possível reservar os lugares | "
                                                   "Atenção\nNão há lugares disponíveis para a totalidade do pedido\nWS:RES:9XX|116"])
        self.assertEqual(classify_sale_response(r)[0], "sold_out")

    def test_classificacao_das_respostas_do_sale(self):
        self.assertEqual(classify_sale_response(resp(200, {"saleID": 1}))[0], "ok")
        self.assertEqual(classify_sale_response(resp(500))[0], "transient")
        self.assertEqual(classify_sale_response(resp(429))[0], "transient")
        self.assertEqual(classify_sale_response(resp(422, {}, messages=["Sem lugares disponíveis"]))[0], "sold_out")
        self.assertEqual(classify_sale_response(resp(409, {}, messages=["A venda ainda não está aberta"]))[0], "not_open")
        self.assertEqual(classify_sale_response(resp(409, {}, messages=["Comboio indisponível"]))[0], "not_open")   # nunca esgotado por engano
        self.assertEqual(classify_sale_response(resp(422, {}, messages=["Sale is not open yet"]))[0], "not_open")
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
