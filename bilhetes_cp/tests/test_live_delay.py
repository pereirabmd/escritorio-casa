"""Vigilância do comboio nos últimos 30 minutos (Bruno, 22/09): só notifica quando algo muda."""

import unittest
from datetime import date, timedelta
from unittest import mock

import _env  # noqa: F401
import common
import live_delay

D = date(2026, 9, 22)


def row(data="2026-09-22", train=520, org="Aveiro", dst="Lisboa Oriente", hora="06:45",
        carriage=3, seat=42, ref="REF1"):
    return [data, train, org, dst, hora, carriage, seat, ref]


def stops(delay=None, platform="8", supression=None, eta=None, etd=None, status=None, disrupt=False,
          code="94-38000"):
    return {"status": status, "hasDisruptions": disrupt,
            "trainStops": [{"station": {"code": code}, "departure": "06:45", "delay": delay,
                            "platform": platform, "supression": supression, "ETA": eta, "ETD": etd}]}


class UpcomingWatchesTests(unittest.TestCase):
    def test_so_entram_bilhetes_nos_proximos_30_minutos(self):
        now = common.local_dt(D, "06:20")
        rows = [row(hora="06:45"),                     # 25 min à frente: entra
               row(hora="07:00", train=999),           # 40 min à frente: fora da janela
               row(hora="06:10", train=888),           # já partiu: fora
               row(hora="06:20", train=777)]           # agora mesmo: entra (limite 0)
        ws = live_delay.upcoming_watches(rows, now)
        self.assertEqual(sorted(w.train for w in ws), [520, 777])

    def test_linhas_incompletas_sao_ignoradas_sem_rebentar(self):
        self.assertEqual(live_delay.upcoming_watches([["", "", "", "", ""], [], row()[:2]],
                                                      common.local_dt(D, "06:20")), [])

    def test_estacoes_normalizadas_para_comparar_com_a_config(self):
        w = live_delay.upcoming_watches([row(org="Lisboa Oriente", dst="Aveiro")], common.local_dt(D, "06:20"))[0]
        self.assertEqual((w.origin, w.destination), ("lisboa_oriente", "aveiro"))


class SnapshotAndDiffTests(unittest.TestCase):
    def watch(self):
        return live_delay.Watch(D, 520, "aveiro", "lisboa_oriente", "06:45", "3", "42")

    def test_snapshot_le_a_paragem_da_estacao_de_embarque(self):
        snap = live_delay.snapshot(self.watch(), fetch=lambda t, d: stops(delay=5, platform="8"))
        self.assertEqual((snap["delay"], snap["platform"]), (5, "8"))

    def test_sem_paragem_correspondente_devolve_none(self):
        self.assertIsNone(live_delay.snapshot(self.watch(), fetch=lambda t, d: stops(code="outra")))
        self.assertIsNone(live_delay.snapshot(self.watch(), fetch=lambda t, d: None))

    def test_describe_changes_so_lista_o_que_mudou(self):
        a = {"delay": 0, "platform": "8", "supression": False, "eta": None, "etd": None,
             "train_status": None, "has_disruptions": False}
        b = dict(a, delay=13, platform="5")
        changes = live_delay.describe_changes(a, b)
        self.assertEqual(len(changes), 2)
        self.assertTrue(any("atraso: 0 → 13" in c for c in changes))
        self.assertTrue(any("cais: 8 → 5" in c for c in changes))
        self.assertEqual(live_delay.describe_changes(a, dict(a)), [])

    def test_supressao_mostra_sim_nao(self):
        a = {"delay": 0, "platform": "8", "supression": False, "eta": None, "etd": None,
             "train_status": None, "has_disruptions": False}
        b = dict(a, supression=True)
        self.assertIn("supressão: não → sim", live_delay.describe_changes(a, b))


class CheckOneTests(unittest.TestCase):
    def setUp(self):
        common._state_file("notified.json").unlink(missing_ok=True)
        self.watch = live_delay.Watch(D, 520, "aveiro", "lisboa_oriente", "06:45", "3", "42")
        self.notes = []
        self.p = mock.patch.object(live_delay, "notify", side_effect=lambda t, m, **kw: self.notes.append((t, m, kw)) or True)
        self.p.start(); self.addCleanup(self.p.stop)

    def test_primeira_leitura_nao_notifica_so_guarda(self):
        cache = {}
        with mock.patch.object(live_delay, "snapshot", return_value={"delay": 0, "platform": "8",
                "supression": False, "eta": None, "etd": None, "train_status": None, "has_disruptions": False}):
            live_delay.check_one(self.watch, cache, 0)
        self.assertEqual(self.notes, [])
        self.assertIn(self.watch.key, cache)

    def test_sem_alteracao_nao_notifica(self):
        snap = {"delay": 0, "platform": "8", "supression": False, "eta": None, "etd": None,
               "train_status": None, "has_disruptions": False}
        cache = {self.watch.key: dict(snap)}
        with mock.patch.object(live_delay, "snapshot", return_value=snap):
            live_delay.check_one(self.watch, cache, 0)
        self.assertEqual(self.notes, [])

    def test_atraso_novo_notifica_com_o_lugar(self):
        cache = {self.watch.key: {"delay": 0, "platform": "8", "supression": False, "eta": None,
                                  "etd": None, "train_status": None, "has_disruptions": False}}
        with mock.patch.object(live_delay, "snapshot", return_value=dict(cache[self.watch.key], delay=13)):
            live_delay.check_one(self.watch, cache, 0)
        self.assertEqual(len(self.notes), 1)
        title, msg, kw = self.notes[0]
        self.assertIn("Mudou algo no comboio", title)
        self.assertIn("atraso: 0 → 13", msg)
        self.assertIn("carruagem 3, lugar 42", msg)
        self.assertEqual(kw["tags"], ["warning"])

    def test_supressao_nova_e_urgente(self):
        cache = {self.watch.key: {"delay": 0, "platform": "8", "supression": False, "eta": None,
                                  "etd": None, "train_status": None, "has_disruptions": False}}
        with mock.patch.object(live_delay, "snapshot", return_value=dict(cache[self.watch.key], supression=True)):
            live_delay.check_one(self.watch, cache, 0)
        title, msg, kw = self.notes[0]
        self.assertIn("suprimido", title)
        self.assertEqual(kw["tags"], ["rotating_light"])

    def test_falha_a_consultar_nao_e_silenciosa_mas_nao_inunda(self):
        with mock.patch.object(live_delay, "snapshot", side_effect=RuntimeError("HTTP 500")), \
             mock.patch.object(live_delay, "notify_once", return_value=True) as n:
            live_delay.check_one(self.watch, {}, 0)
        n.assert_called_once()
        self.assertEqual(n.call_args.kwargs["cooldown_s"], 600)  # não inunda: 10 min de intervalo

    def test_sem_paragem_correspondente_nao_notifica(self):
        with mock.patch.object(live_delay, "snapshot", return_value=None):
            live_delay.check_one(self.watch, {}, 0)
        self.assertEqual(self.notes, [])


class MainTests(unittest.TestCase):
    def setUp(self):
        common._state_file("live_delay.json").unlink(missing_ok=True)

    def test_fora_da_janela_nao_le_o_horario(self):
        with mock.patch.object(common, "now_local", return_value=common.local_dt(D, "01:00")), \
             mock.patch.object(common, "SheetsClient") as sc, \
             mock.patch.object(live_delay, "snapshot") as snap:
            sc.return_value.read_tickets.return_value = [row(hora="06:45")]
            self.assertEqual(live_delay.main(), 0)
        snap.assert_not_called()

    def test_limpa_do_cache_os_comboios_que_ja_partiram(self):
        common._write_json_atomic(common._state_file("live_delay.json"),
                                  {"2026-09-01-999": {"delay": 0}, "sobrevive": "nao-deveria"})
        with mock.patch.object(common, "now_local", return_value=common.local_dt(D, "06:20")), \
             mock.patch.object(common, "SheetsClient") as sc, \
             mock.patch.object(live_delay, "snapshot", return_value={"delay": 0, "platform": "8",
                     "supression": False, "eta": None, "etd": None, "train_status": None, "has_disruptions": False}):
            sc.return_value.read_tickets.return_value = [row(hora="06:45")]
            live_delay.main()
        cache = common._read_json(common._state_file("live_delay.json"), {})
        self.assertEqual(list(cache), ["2026-09-22-520"])

    def test_falha_a_ler_a_sheet_nao_e_silenciosa(self):
        with mock.patch.object(common, "SheetsClient", side_effect=RuntimeError("403")), \
             mock.patch.object(live_delay, "notify_once", return_value=True) as n:
            self.assertEqual(live_delay.main(), 1)
        n.assert_called_once()


if __name__ == "__main__":
    unittest.main()
