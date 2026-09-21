"""Scheduler daemon (PLANO_FINAL 3.2, 3.3.1, 3.10.2, 3.10.3): o que lançar e quando."""

import os
import socket
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import _env  # noqa: F401
import common
import scheduler

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=common.TZ)   # domingo 20/09/2026 12:00
NOW_TS = NOW.timestamp()


def row(data="2026-09-22", t_ida=524, h_ida="06:45", t_volta=525, h_volta="18:30", ativo="SIM"):
    return [data, "aveiro", "lisboa_oriente", t_ida, h_ida, t_volta, h_volta, ativo]


def serial(d):
    return (d - date(1899, 12, 30)).days


class Base(unittest.TestCase):
    def setUp(self):
        for f in common.BASE_DIR.glob("locks/*.json"):
            f.unlink()
        for n in ("seen.json", "launched.json"):
            common._state_file(n).unlink(missing_ok=True)
        self.notes = []
        self.snap = {"weekly": [row()], "passe": []}
        patches = [
            mock.patch.object(scheduler, "notify_once",
                              side_effect=lambda key, title, msg, **kw: self.notes.append((key, title)) or True),
            # hermético: nunca consultar o horário oficial pela rede
            mock.patch.object(scheduler.timetable, "check_leg_cached", return_value=(None, False)),
            mock.patch.object(scheduler.timetable, "apply_anchor", side_effect=lambda leg: leg),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ev(self, now=NOW_TS, **kw):
        return scheduler.evaluate(self.snap, kw.pop("from_cache", False), now, **kw)

    def keys(self):
        return [k for k, _ in self.notes]

    def mark_seen(self, before_fire=True):
        """Simula que a perna já era conhecida (ciclos anteriores) antes da hora do disparo."""
        legs = common.parse_snapshot(self.snap, NOW.date())[0]
        common._write_json_atomic(common._state_file("seen.json"),
                                  {l.key: l.fire.timestamp() - (3600 if before_fire else -3600) for l in legs})
        return legs

    def set_state(self, leg, state, **kw):
        lock = common.PurchaseLock(leg.lock_key)
        lock.acquire(); lock.update(state=state, **kw); lock.release()


class PlanTests(Base):
    def test_uma_entrada_por_perna_com_arranque_antes_do_disparo(self):
        items = self.ev()
        self.assertEqual([i.leg.key for i in items], ["2026-09-22-ida", "2026-09-22-volta"])
        self.assertEqual(items[0].fire_ts, datetime(2026, 9, 21, 6, 45, tzinfo=common.TZ).timestamp())
        self.assertEqual(items[0].fire_ts - items[0].launch_ts, 6 * 60)          # launch_lead_minutes

    def test_linha_desativada_ou_alterada_nao_exige_remover_nada(self):
        self.snap = {"weekly": [row(ativo="NAO")], "passe": []}
        self.assertEqual(self.ev(), [])
        self.snap = {"weekly": [row(t_ida=530)], "passe": []}
        self.assertEqual([i.leg.train for i in self.ev()], [530, 525])

    def test_com_a_sheet_em_baixo_o_plano_da_cache_continua_a_valer(self):
        self.assertEqual(len(self.ev(from_cache=True)), 2)

    def test_perna_ja_terminada_ou_viagem_passada_nao_entram(self):
        legs = common.parse_snapshot(self.snap, NOW.date())[0]
        self.set_state(legs[0], "CONFIRMED")
        self.assertEqual([i.leg.leg for i in self.ev()], ["volta"])
        self.assertEqual(self.ev(now=datetime(2026, 9, 23, 12, 0, tzinfo=common.TZ).timestamp()), [])

    def test_linha_invalida_avisa_mas_nao_trava_as_outras(self):
        self.snap = {"weekly": [row(h_ida="25:90"), row(data="2026-09-23")], "passe": []}
        items = self.ev()
        self.assertEqual({i.leg.date.isoformat() for i in items}, {"2026-09-23"})
        self.assertTrue(any(k.startswith("config-issue-") for k in self.keys()))

    def test_plan_only_nao_notifica_nem_grava_estado(self):
        self.snap = {"weekly": [row(h_ida="25:90"), row(data="2026-09-23")], "passe": []}
        self.assertEqual(len(self.ev(plan_only=True)), 2)
        self.assertEqual(self.notes, [])
        self.assertFalse(common._state_file("seen.json").exists())


class AnchorTests(Base):
    def test_o_arranque_e_o_disparo_seguem_a_partida_na_primeira_estacao(self):
        import dataclasses
        anchor = lambda leg: dataclasses.replace(leg, anchor="06:10", anchor_date=leg.date) if leg.leg == "ida" else leg  # noqa: E731
        with mock.patch.object(scheduler.timetable, "apply_anchor", side_effect=anchor):
            items = self.ev()
        ida = [i for i in items if i.leg.leg == "ida"][0]
        self.assertEqual(ida.fire_ts, datetime(2026, 9, 21, 6, 10, tzinfo=common.TZ).timestamp())     # não 06:45
        self.assertEqual(ida.fire_ts - ida.launch_ts, 6 * 60)
        self.assertNotIn("anchor-2026-09-22-ida", self.keys())          # a ida foi ancorada: sem aviso
        self.assertIn("anchor-2026-09-22-volta", self.keys())           # a volta não foi: avisa

    def test_sem_a_primeira_estacao_usa_a_hora_da_config_e_avisa(self):
        items = self.ev()                                   # apply_anchor devolve a perna sem âncora
        ida = [i for i in items if i.leg.leg == "ida"][0]
        self.assertEqual(ida.fire_ts, datetime(2026, 9, 21, 6, 45, tzinfo=common.TZ).timestamp())
        self.assertIn("anchor-2026-09-22-ida", self.keys())

    def test_o_plano_sai_ordenado_pelo_arranque(self):
        import dataclasses
        # a ida ancorada a 06:10 e a volta às 18:30: continua ordenado
        anchor = lambda leg: dataclasses.replace(leg, anchor="06:10", anchor_date=leg.date)  # noqa: E731
        with mock.patch.object(scheduler.timetable, "apply_anchor", side_effect=anchor):
            items = self.ev()
        self.assertEqual([i.launch_ts for i in items], sorted(i.launch_ts for i in items))


class LateAndRecoveryTests(Base):
    """Disparo já passado com a partida ainda futura (3.10.3, 3.2 ponto 5)."""
    LATE = datetime(2026, 9, 21, 6, 50, tzinfo=common.TZ).timestamp()      # 5 min depois do disparo da ida

    def test_configuracao_tardia_avisa_e_nao_compra(self):
        items = self.ev(now=self.LATE)                     # a perna nunca tinha sido vista antes do disparo
        self.assertEqual([i.leg.leg for i in items], ["volta"])          # a volta ainda é futura
        self.assertIn("late-config-2026-09-22-ida-524", self.keys())

    def test_perna_conhecida_antes_do_disparo_e_recuperada_depois_de_um_reboot(self):
        self.mark_seen()
        items = self.ev(now=self.LATE)
        ida = [i for i in items if i.leg.leg == "ida"]
        self.assertEqual(len(ida), 1)
        self.assertEqual(ida[0].launch_ts, self.LATE)                   # arranca já
        self.assertFalse(any(k.startswith("late-config") for k in self.keys()))

    def test_fora_da_tolerancia_avisa_janela_perdida(self):
        self.mark_seen()
        items = self.ev(now=datetime(2026, 9, 21, 7, 30, tzinfo=common.TZ).timestamp())   # 45 min depois
        self.assertEqual([i.leg.leg for i in items], ["volta"])
        self.assertIn("missed-2026-09-22-ida-524", self.keys())

    def test_venda_a_meio_pode_ser_retomada_ate_aos_15_min(self):
        legs = self.mark_seen()
        self.set_state(legs[0], "FISCAL_OK", sale_id=7)
        t12 = datetime(2026, 9, 21, 6, 57, tzinfo=common.TZ).timestamp()     # 12 min depois: fora da tolerância de 10, dentro dos 15
        self.assertTrue(any(i.leg.leg == "ida" for i in self.ev(now=t12)))
        t20 = datetime(2026, 9, 21, 7, 5, tzinfo=common.TZ).timestamp()      # 20 min depois: a venda expirou
        self.assertFalse(any(i.leg.leg == "ida" for i in self.ev(now=t20)))
        self.assertTrue(any(k.startswith("missed-") for k in self.keys()))


class ValidationTests(Base):
    def test_viagem_depois_de_o_passe_expirar_nao_e_agendada(self):
        self.snap = {"weekly": [row()], "passe": [serial(date(2026, 8, 1)), 29, "", ""]}        # até 30/08
        self.assertEqual(self.ev(), [])
        self.assertTrue(any(k.startswith("after-pass-") for k in self.keys()))

    def test_viagem_no_ultimo_dia_do_passe_e_agendada(self):
        self.snap = {"weekly": [row()], "passe": [serial(date(2026, 8, 24)), 29, "", ""]}       # 24/08 + 29 = 22/09
        self.assertEqual(len(self.ev()), 2)

    def test_horario_oficial_que_nao_bate_bloqueia_e_avisa(self):
        # PLANO_FINAL 3.10.3: a Config tem de bater com o horário oficial; senão a linha é inválida
        with mock.patch.object(scheduler.timetable, "check_leg_cached",
                               side_effect=lambda leg: ("o comboio 524 parte às 13:27 segundo a CP", True)
                               if leg.leg == "ida" else (None, False)):
            items = self.ev()
        self.assertEqual([i.leg.leg for i in items], ["volta"])
        self.assertTrue(any(k.startswith("timetable-") for k in self.keys()))

    def test_viagens_distantes_nao_consultam_o_horario(self):
        self.snap = {"weekly": [row(data="2026-11-20")], "passe": []}
        with mock.patch.object(scheduler.timetable, "check_leg_cached") as chk:
            self.ev()
        chk.assert_not_called()


class LaunchTests(Base):
    def test_cycle_so_lanca_o_que_ja_e_devido_e_devolve_o_proximo_marco(self):
        launched = []
        items, nxt = scheduler.cycle(self.snap, False, NOW_TS, launcher=lambda it, now: launched.append(it.leg.key))
        self.assertEqual((launched, len(items)), ([], 2))
        self.assertEqual(nxt, items[0].launch_ts)
        due = items[0].launch_ts + 1
        launched.clear()
        scheduler.cycle(self.snap, False, due, launcher=lambda it, now: launched.append(it.leg.key))
        self.assertEqual(launched, ["2026-09-22-ida"])

    def test_plan_only_nunca_lanca(self):
        launched = []
        scheduler.cycle(self.snap, False, datetime(2026, 9, 21, 7, 0, tzinfo=common.TZ).timestamp(),
                        plan_only=True, launcher=lambda it, now: launched.append(1))
        self.assertEqual(launched, [])

    def test_launch_arranca_subprocesso_separado_e_nao_relanca_de_imediato(self):
        leg = common.parse_snapshot(self.snap, NOW.date())[0][0]
        item = scheduler.Item(leg, NOW_TS, NOW_TS)
        with mock.patch.object(scheduler.subprocess, "Popen") as popen:
            self.assertTrue(scheduler.launch(item, NOW_TS))
            self.assertFalse(scheduler.launch(item, NOW_TS + 10))          # acabou de ser lançado
            self.assertTrue(scheduler.launch(item, NOW_TS + 60))
        args, kw = popen.call_args
        self.assertEqual(args[0][1:], ["scripts/hot_buy.py", "--date", "2026-09-22", "--leg", "ida"])
        self.assertTrue(kw["start_new_session"])                            # sobrevive a um restart do daemon

    def test_nao_lanca_se_o_processo_quente_ja_esta_a_correr(self):
        leg = common.parse_snapshot(self.snap, NOW.date())[0][0]
        lock = common.PurchaseLock(leg.lock_key)
        self.assertTrue(lock.acquire())
        try:
            self.assertTrue(scheduler.is_running(leg))
            with mock.patch.object(scheduler.subprocess, "Popen") as popen:
                self.assertFalse(scheduler.launch(scheduler.Item(leg, NOW_TS, NOW_TS), NOW_TS))
            popen.assert_not_called()
        finally:
            lock.release()
        self.assertFalse(scheduler.is_running(leg))

    def test_processo_que_morre_sempre_antes_de_gravar_estado_nao_e_relancado_para_sempre(self):
        leg = common.parse_snapshot(self.snap, NOW.date())[0][0]
        item = scheduler.Item(leg, NOW_TS, NOW_TS)
        with mock.patch.object(scheduler.subprocess, "Popen") as popen:
            for i in range(6):
                scheduler.launch(item, NOW_TS + 100 * i)
        self.assertEqual(popen.call_count, scheduler.MAX_LAUNCHES)

    def test_falha_a_lancar_nao_e_silenciosa(self):
        leg = common.parse_snapshot(self.snap, NOW.date())[0][0]
        with mock.patch.object(scheduler.subprocess, "Popen", side_effect=OSError("sem memória")):
            self.assertFalse(scheduler.launch(scheduler.Item(leg, NOW_TS, NOW_TS), NOW_TS))
        self.assertTrue(any(k.startswith("launch-fail-") for k in self.keys()))


class SystemdTests(unittest.TestCase):
    def test_sd_notify_fala_com_o_socket_do_systemd(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "notify.sock")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            srv.bind(path)
            srv.settimeout(2)
            try:
                with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": path}):
                    sd = scheduler.SdNotify()
                    sd.ready(); sd.watchdog(); sd.status("2 perna(s) no plano")
                got = [srv.recv(100).decode() for _ in range(3)]
            finally:
                srv.close()
        self.assertEqual(got, ["READY=1", "WATCHDOG=1", "STATUS=2 perna(s) no plano"])

    def test_sem_systemd_nao_faz_nada(self):
        with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": ""}):
            scheduler.SdNotify().watchdog()        # não levanta

    def test_o_sono_avisa_o_watchdog_em_fatias(self):
        sd = mock.Mock()
        with mock.patch.object(scheduler.time, "sleep") as sl, \
             mock.patch.object(scheduler.time, "time", side_effect=[0, 0, 15, 15, 30, 30, 45, 45, 50]):
            scheduler.sleep_until(45, sd, step=15)
        self.assertGreaterEqual(sd.watchdog.call_count, 3)
        self.assertTrue(all(c.args[0] <= 15 for c in sl.call_args_list))


class ReadConfigTests(Base):
    def test_leitura_falhada_usa_a_cache_e_avisa(self):
        common.save_config_cache({"weekly": [row()], "passe": [], "first_row": 12})
        with mock.patch.object(common, "SheetsClient", side_effect=RuntimeError("403")):
            snap, from_cache = scheduler.read_config()
        self.assertTrue(from_cache)
        self.assertEqual(snap["weekly"][0][3], 524)
        self.assertTrue(any(k.startswith("sheet-read-") for k in self.keys()))

    def test_sem_sheet_e_sem_cache_devolve_none(self):
        common.CACHE_FILE.unlink(missing_ok=True)
        with mock.patch.object(common, "SheetsClient", side_effect=RuntimeError("403")):
            self.assertEqual(scheduler.read_config(), (None, True))


if __name__ == "__main__":
    unittest.main()
