"""Validação da Config contra o horário oficial da CP (sem login)."""

import unittest
from datetime import date
from unittest import mock

import _env  # noqa: F401
import common
import timetable

D = date(2026, 9, 23)


def leg(train=520, hhmm="07:27"):
    return common.Leg(D, "ida", "aveiro", "lisboa_oriente", train, hhmm, 12)


def tt(*stops):
    return {"trainStops": [{"station": {"code": c}, "departure": dep, "arrival": None} for c, dep in stops]}


AVEIRO, LISBOA = "94-38000", "94-31039"


class CheckLegTests(unittest.TestCase):
    def test_tudo_certo(self):
        f = lambda t, d: tt(("94-2006", "06:45"), (AVEIRO, "07:27"), (LISBOA, None))  # noqa: E731
        self.assertIsNone(timetable.check_leg(leg(), f))

    def test_comboio_que_nao_circula(self):
        for resposta in (None, {}, {"trainStops": []}):
            msg = timetable.check_leg(leg(), lambda t, d, r=resposta: r)
            self.assertIn("não consta do horário oficial", msg)

    def test_nao_para_na_origem(self):
        msg = timetable.check_leg(leg(), lambda t, d: tt(("94-2006", "06:45"), (LISBOA, None)))
        self.assertIn("não para em aveiro", msg)

    def test_sentido_errado(self):  # destino antes da origem
        msg = timetable.check_leg(leg(), lambda t, d: tt((LISBOA, "06:00"), (AVEIRO, "07:27")))
        self.assertIn("não segue de aveiro para lisboa oriente", msg)

    def test_hora_diferente(self):
        msg = timetable.check_leg(leg(hhmm="07:30"), lambda t, d: tt((AVEIRO, "07:27"), (LISBOA, None)))
        self.assertIn("às 07:27 segundo a CP", msg)
        self.assertIn("Config tem 07:30", msg)

    def test_aceita_a_hora_da_primeira_estacao_ou_a_de_embarque(self):
        # o caso real: o 520 parte do Porto às 06:45 e passa em Aveiro às 07:27; Bruno configura 06:45
        f = lambda t, d: tt(("94-2006", "06:45"), (AVEIRO, "07:27"), (LISBOA, None))  # noqa: E731
        self.assertIsNone(timetable.check_leg(leg(hhmm="06:45"), f))      # 1.ª estação
        self.assertIsNone(timetable.check_leg(leg(hhmm="07:27"), f))      # embarque
        msg = timetable.check_leg(leg(hhmm="07:00"), f)                    # nenhuma das duas
        self.assertIn("às 06:45", msg)
        self.assertIn("às 07:27", msg)
        self.assertIn("Config tem 07:00", msg)

    def test_erro_de_rede_nas_duas_fontes_propaga_para_o_chamador_decidir(self):
        def boom(*a):
            raise RuntimeError("HTTP 500")
        with self.assertRaises(RuntimeError):
            timetable.check_leg(leg(), boom, boom)

    def test_se_o_timetable_falha_confirma_pelo_journeys(self):
        def boom(t, d):
            raise RuntimeError("HTTP 500")
        trip = lambda dep, train=520: {"outwardTrip": [{"departureTime": dep, "travelSections": [  # noqa: E731
            {"trainNumber": train, "serviceCode": {"code": "IC", "designation": "IC"}}]}]}
        self.assertIsNone(timetable.check_leg(leg(), boom, lambda l: trip("07:27")))
        self.assertIn("não consta dos horários", timetable.check_leg(leg(), boom, lambda l: trip("07:27", train=999)))
        # o journeys só dá a hora de embarque: a da Config pode ser a da 1.ª estação, por isso não a compara
        self.assertIsNone(timetable.check_leg(leg(hhmm="06:45"), boom, lambda l: trip("07:27")))


class CacheTests(unittest.TestCase):
    def setUp(self):
        common._state_file("timetable_checks.json").unlink(missing_ok=True)

    def test_nao_repete_a_consulta_dentro_do_ttl(self):
        f = mock.Mock(return_value=tt((AVEIRO, "07:30"), (LISBOA, None)))
        p1, novo1 = timetable.check_leg_cached(leg(), f)
        p2, novo2 = timetable.check_leg_cached(leg(), f)
        self.assertEqual((novo1, novo2), (True, False))
        self.assertEqual(p1, p2)
        self.assertIn("às 07:30", p1)
        f.assert_called_once()

    def test_config_alterada_volta_a_consultar(self):
        f = mock.Mock(return_value=tt((AVEIRO, "07:27"), (LISBOA, None)))
        timetable.check_leg_cached(leg(hhmm="07:27"), f)
        timetable.check_leg_cached(leg(hhmm="07:30"), f)
        self.assertEqual(f.call_count, 2)

    def test_falha_de_rede_nao_notifica_e_nao_guarda_cache(self):
        f = mock.Mock(side_effect=RuntimeError("HTTP 500"))
        self.assertEqual(timetable.check_leg_cached(leg(), f), (None, False))
        self.assertFalse(common._state_file("timetable_checks.json").exists())


class AnchorTests(unittest.TestCase):
    """A venda abre 24 h antes da partida do comboio na sua 1.ª estação (PLANO_FINAL 3.11)."""
    PORTO = "94-2006"

    def setUp(self):
        common._state_file("anchors.json").unlink(missing_ok=True)

    def stops(self, first="06:10", board="06:45"):
        return {"trainStops": [
            {"station": {"code": self.PORTO, "designation": "Porto Campanha"}, "departure": first},
            {"station": {"code": AVEIRO, "designation": "Aveiro"}, "departure": board},
            {"station": {"code": LISBOA, "designation": "Lisboa Oriente"}, "arrival": "09:52", "departure": None}]}

    def test_comboio_de_dia_ancora_a_partida_na_primeira_estacao(self):
        a = timetable.anchor_for(leg(hhmm="06:45"), lambda t, d: self.stops())
        self.assertEqual(a, ("06:10", D, "Porto Campanha", "06:45", D))

    def test_o_disparo_passa_a_ser_24h_antes_da_primeira_estacao(self):
        l = timetable.apply_anchor(leg(hhmm="06:45"), lambda t, d: self.stops())
        self.assertEqual((l.anchor, l.anchor_date), ("06:10", D))
        self.assertEqual(l.fire.strftime("%Y-%m-%d %H:%M"), "2026-09-22 06:10")     # véspera 06:10, não 06:45
        self.assertEqual(l.departure.strftime("%H:%M"), "06:45")                      # o embarque não muda

    def test_o_caso_do_har_aveiro_0727_de_um_comboio_que_parte_do_porto_as_0645(self):
        l = timetable.apply_anchor(leg(hhmm="07:27"), lambda t, d: self.stops(first="06:45", board="07:27"))
        self.assertEqual(l.fire.strftime("%H:%M"), "06:45")
        self.assertEqual(l.fire.timestamp() - common.fire_time(D, "07:27").timestamp(), -42 * 60)

    def test_comboio_que_passa_a_meia_noite_parte_na_vespera(self):
        # 1.ª estação às 23:30 e embarque às 01:10 (já do dia seguinte): o comboio partiu na véspera
        l = timetable.apply_anchor(leg(hhmm="01:10"), lambda t, d: self.stops(first="23:30", board="01:10"))
        self.assertEqual((l.anchor, l.anchor_date.isoformat()), ("23:30", "2026-09-22"))
        self.assertEqual(l.fire.strftime("%Y-%m-%d %H:%M"), "2026-09-21 23:30")

    def test_hora_da_config_e_a_da_primeira_estacao_como_no_caso_do_520(self):
        # Bruno configura 06:45 (Porto); embarca em Aveiro às 07:27: o disparo é 24 h antes das 06:45
        f = lambda t, d: self.stops(first="06:45", board="07:27")  # noqa: E731
        l = timetable.apply_anchor(leg(hhmm="06:45"), f)
        self.assertEqual(l.fire.strftime("%Y-%m-%d %H:%M"), "2026-09-22 06:45")
        self.assertEqual((l.board, l.board_date), ("07:27", D))
        self.assertEqual(l.departure.strftime("%H:%M"), "07:27")          # o embarque é às 07:27
        self.assertEqual(l.hhmm, "06:45")

    def test_meia_noite_com_a_hora_da_primeira_estacao_a_data_e_a_do_inicio(self):
        # Config 23:30 no dia 23 (início da viagem); embarca às 01:10, já no dia 24
        l = timetable.apply_anchor(leg(hhmm="23:30"), lambda t, d: self.stops(first="23:30", board="01:10"))
        self.assertEqual((l.anchor_date, l.board_date.isoformat()), (D, "2026-09-24"))
        self.assertEqual(l.fire.strftime("%Y-%m-%d %H:%M"), "2026-09-22 23:30")
        self.assertEqual(l.departure.strftime("%Y-%m-%d %H:%M"), "2026-09-24 01:10")

    def test_quando_embarca_na_primeira_estacao_nada_muda(self):
        l = timetable.apply_anchor(leg(hhmm="07:27"), lambda t, d: self.stops(first="07:27", board="07:27"))
        self.assertEqual(l.fire, leg(hhmm="07:27").fire)

    def test_cache_de_24h_e_valor_antigo_se_a_cp_falhar(self):
        f = mock.Mock(return_value=self.stops())
        timetable.anchor_for(leg(hhmm="06:45"), f)
        timetable.anchor_for(leg(hhmm="06:45"), f)
        f.assert_called_once()
        cache = common._read_json(common._state_file("anchors.json"), {})
        for v in cache.values():
            v["ts"] -= 2 * 86400                                    # expirou
        common._write_json_atomic(common._state_file("anchors.json"), cache)
        boom = mock.Mock(side_effect=RuntimeError("HTTP 500"))
        self.assertEqual(timetable.anchor_for(leg(hhmm="06:45"), boom)[0], "06:10")   # mantém o último conhecido

    def test_sem_informacao_devolve_a_mesma_perna(self):
        boom = mock.Mock(side_effect=RuntimeError("HTTP 500"))
        l = leg(hhmm="06:45")
        self.assertIs(timetable.apply_anchor(l, boom), l)
        self.assertIsNone(timetable.anchor_for(l, lambda t, d: {"trainStops": []}))
        self.assertIsNone(timetable.anchor_for(l, lambda t, d: None))
        self.assertIsNone(timetable.anchor_for(l, lambda t, d: {"trainStops": [{"station": {"code": "outra"}, "departure": "06:10"}]}))


if __name__ == "__main__":
    unittest.main()
