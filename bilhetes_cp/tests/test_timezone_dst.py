"""T-24h com mudanças de hora (PLANO_FINAL.md 3.4 e 3.10.7).

É o ponto onde é mais fácil introduzir bugs: a janela de venda acompanha a hora
do relógio, por isso o disparo é "dia anterior, mesma hora local" e NÃO
`partida - 86400s`. Em Portugal a hora muda no último domingo de março
(29/03/2026) e de outubro (25/10/2026).
"""

import unittest
from datetime import date, datetime, timedelta

import _env  # noqa: F401
import common
from common import TZ, departure_dt, fire_time, local_dt


def real_gap(a: datetime, b: datetime) -> float:
    """Horas reais entre dois instantes. (`a - b` com o mesmo ZoneInfo faria
    aritmética de relógio de parede e esconderia a mudança de hora.)"""
    return (a.timestamp() - b.timestamp()) / 3600


def minus_24h_real(d: datetime) -> datetime:
    """O cálculo ingénuo `partida - 86400 s`, em segundos reais."""
    return datetime.fromtimestamp(d.timestamp() - 86400, TZ)


class FireTimeTests(unittest.TestCase):
    def test_dia_normal_e_24h_reais(self):
        d, f = departure_dt(date(2026, 9, 22), "06:45"), fire_time(date(2026, 9, 22), "06:45")
        self.assertEqual(f.strftime("%Y-%m-%d %H:%M"), "2026-09-21 06:45")
        self.assertEqual(real_gap(d, f), 24)
        self.assertEqual(f.utcoffset(), timedelta(hours=1))  # WEST (verão)

    def test_partida_no_dia_da_mudanca_de_marco_sao_23h_reais(self):
        # Domingo 29/03/2026 06:45 (WEST). Disparo: sábado 28/03 06:45 (WET, UTC+0).
        d, f = departure_dt(date(2026, 3, 29), "06:45"), fire_time(date(2026, 3, 29), "06:45")
        self.assertEqual(f.strftime("%Y-%m-%d %H:%M"), "2026-03-28 06:45")
        self.assertEqual(f.utcoffset(), timedelta(0))
        self.assertEqual(d.utcoffset(), timedelta(hours=1))
        self.assertEqual(real_gap(d, f), 23)
        # o cálculo ingénuo (menos 86400 s reais) daria uma hora errada:
        self.assertNotEqual(minus_24h_real(d).strftime("%H:%M"), "06:45")

    def test_partida_no_dia_da_mudanca_de_outubro_sao_25h_reais(self):
        # Domingo 25/10/2026 06:45 (WET). Disparo: sábado 24/10 06:45 (WEST).
        d, f = departure_dt(date(2026, 10, 25), "06:45"), fire_time(date(2026, 10, 25), "06:45")
        self.assertEqual(f.strftime("%Y-%m-%d %H:%M"), "2026-10-24 06:45")
        self.assertEqual(f.utcoffset(), timedelta(hours=1))
        self.assertEqual(d.utcoffset(), timedelta(0))
        self.assertEqual(real_gap(d, f), 25)
        self.assertNotEqual(minus_24h_real(d).strftime("%H:%M"), "06:45")

    def test_segunda_seguinte_a_mudanca_volta_a_ser_24h(self):
        # Segunda 30/03/2026: o disparo (domingo 29/03, já em WEST) tem o mesmo offset.
        d, f = departure_dt(date(2026, 3, 30), "06:45"), fire_time(date(2026, 3, 30), "06:45")
        self.assertEqual(real_gap(d, f), 24)
        self.assertEqual(f.strftime("%H:%M"), "06:45")

    def test_meia_noite_e_viragem_de_ano(self):
        f = fire_time(date(2027, 1, 1), "00:05")
        self.assertEqual(f.strftime("%Y-%m-%d %H:%M"), "2026-12-31 00:05")

    def test_horas_que_nao_existem_ou_repetem_nao_rebentam(self):
        # 29/03/2026 01:30 não existe em Lisboa; 25/10/2026 01:30 acontece duas vezes.
        for d in (date(2026, 3, 29), date(2026, 10, 25)):
            dt = local_dt(d, "01:30")
            self.assertIsNotNone(dt.tzinfo)
            self.assertIn(dt.astimezone(TZ).hour, (0, 1, 2))

    def test_o_disparo_e_instante_absoluto_correto(self):
        f = fire_time(date(2026, 3, 29), "06:45")
        self.assertEqual(f.timestamp(), datetime(2026, 3, 28, 6, 45, tzinfo=common.UTC).timestamp())


class AnchorFireTests(unittest.TestCase):
    def test_disparo_ancorado_a_primeira_estacao_respeita_o_dst(self):
        # comboio de domingo 29/03/2026 (dia da mudança de hora) que parte da 1.ª estação às 05:50:
        # a véspera é sábado 28/03 (WET), por isso o disparo é sábado 05:50 local
        leg = common.Leg(date(2026, 3, 29), "ida", "aveiro", "lisboa_oriente", 520, "06:45", 12,
                         anchor="05:50", anchor_date=date(2026, 3, 29))
        self.assertEqual(leg.fire.strftime("%Y-%m-%d %H:%M"), "2026-03-28 05:50")
        self.assertEqual(leg.fire.utcoffset(), timedelta(0))
        self.assertEqual(leg.departure.strftime("%H:%M"), "06:45")

    def test_sem_ancora_e_igual_ao_calculo_original(self):
        leg = common.Leg(date(2026, 9, 22), "ida", "aveiro", "lisboa_oriente", 520, "06:45", 12)
        self.assertEqual(leg.fire, fire_time(date(2026, 9, 22), "06:45"))


class SheetParsingTests(unittest.TestCase):
    def test_datas(self):
        serial = (date(2026, 9, 22) - date(1899, 12, 30)).days
        for v in (serial, float(serial), "2026-09-22", "22/09/2026", " 22-09-2026 "):
            self.assertEqual(common.parse_sheet_date(v), date(2026, 9, 22), v)
        for v in ("", None, "abc", "32/13/2026", True):
            self.assertIsNone(common.parse_sheet_date(v), v)

    def test_horas(self):
        self.assertEqual(common.parse_sheet_time((6 * 60 + 45) / 1440), "06:45")
        self.assertEqual(common.parse_sheet_time("6:45"), "06:45")
        self.assertEqual(common.parse_sheet_time("06:45:00"), "06:45")
        self.assertEqual(common.parse_sheet_time(0), "00:00")
        for v in ("25:90", "24:00", "6.45", "", None, 1.5, -0.1, "abc"):
            self.assertIsNone(common.parse_sheet_time(v), v)


if __name__ == "__main__":
    unittest.main()
