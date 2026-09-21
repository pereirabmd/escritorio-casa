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
        self.assertIn("parte às 08:00", timetable.check_leg(leg(), boom, lambda l: trip("08:00")))


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


if __name__ == "__main__":
    unittest.main()
