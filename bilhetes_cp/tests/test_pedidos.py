"""Fila de pedidos avulsos (PLANO_FINAL.md 3.2): elegibilidade, retentativa e forçar."""

import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import _env  # noqa: F401
import common
import pedidos

D = date.today() + timedelta(days=3)


def prow(comboio=520, hora="06:45", ativo="SIM", retry="NAO", forcar="NAO", estado="",
        ultima="", data=None):
    return [(data or D).isoformat(), "Aveiro", "Lisboa Oriente", comboio, hora, ativo, retry,
           forcar, estado, ultima, "", ""]


class IsDueTests(unittest.TestCase):
    NOW = 1_000_000.0

    def test_nunca_tentado_e_sempre_devido_mesmo_sem_retry(self):
        self.assertEqual(pedidos.is_due(prow(), retry=False, interval_s=900, now_ts=self.NOW), (True, False))

    def test_forcar_e_devido_mesmo_dentro_do_intervalo(self):
        row = prow(forcar="SIM", estado="FALHOU", ultima=datetime.fromtimestamp(self.NOW, common.TZ).isoformat())
        self.assertEqual(pedidos.is_due(row, retry=False, interval_s=900, now_ts=self.NOW), (True, True))

    def test_sem_retry_e_sem_forcar_nao_repete_apos_falhar(self):
        row = prow(estado="FALHOU", ultima=datetime.fromtimestamp(self.NOW - 3600, common.TZ).isoformat())
        self.assertEqual(pedidos.is_due(row, retry=False, interval_s=900, now_ts=self.NOW)[0], False)

    def test_com_retry_espera_o_intervalo(self):
        recente = datetime.fromtimestamp(self.NOW - 60, common.TZ).isoformat()
        row = prow(estado="FALHOU", ultima=recente)
        self.assertEqual(pedidos.is_due(row, retry=True, interval_s=900, now_ts=self.NOW)[0], False)
        antigo = datetime.fromtimestamp(self.NOW - 1000, common.TZ).isoformat()
        row = prow(estado="ESGOTADO", ultima=antigo)
        self.assertEqual(pedidos.is_due(row, retry=True, interval_s=900, now_ts=self.NOW)[0], True)

    def test_confirmado_ou_ambiguo_nunca_sao_devidos_mesmo_com_retry_ou_forcar(self):
        for estado in ("CONFIRMADO", "AMBIGUO"):
            row = prow(estado=estado, forcar="SIM", retry="SIM")
            self.assertEqual(pedidos.is_due(row, retry=True, interval_s=1, now_ts=self.NOW)[0], False, estado)

    def test_ultima_tentativa_ilegivel_nao_rebenta_trata_como_nunca(self):
        row = prow(estado="FALHOU", ultima="not-a-date")
        self.assertEqual(pedidos.is_due(row, retry=True, interval_s=900, now_ts=self.NOW)[0], True)


class RunTests(unittest.TestCase):
    def setUp(self):
        for f in common.BASE_DIR.glob("locks/*.json"):
            f.unlink()
        self.notes = []
        self.launched = []
        p1 = mock.patch.object(pedidos, "launch", side_effect=lambda leg, out=print: self.launched.append(leg.key) or True)
        p2 = mock.patch.object(common, "notify_once",
                               side_effect=lambda key, title, msg, **kw: self.notes.append(key) or True)
        p1.start(); p2.start(); self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def rows(self, *rs):
        return mock.patch.object(common.SheetsClient, "read_requests", return_value=list(rs))

    def test_pedido_novo_e_lancado(self):
        with self.rows(prow()):
            self.assertEqual(pedidos.run(), 0)
        self.assertEqual(len(self.launched), 1)

    def test_plan_only_nunca_lanca_nem_notifica(self):
        with self.rows(prow(comboio="abc")):
            pedidos.run(plan_only=True)
        self.assertEqual((self.launched, self.notes), ([], []))

    def test_comboio_ja_partido_nao_e_lancado(self):
        with self.rows(prow(data=date.today() - timedelta(days=1), hora="06:45")):
            pedidos.run()
        self.assertEqual(self.launched, [])

    def test_confirmado_nunca_e_relancado(self):
        with self.rows(prow(estado="CONFIRMADO")):
            pedidos.run()
        self.assertEqual(self.launched, [])

    def test_nao_lanca_se_ja_estiver_a_correr(self):
        legs, _ = common.parse_request_rows([prow()], common.now_local().date())
        lock = common.PurchaseLock(legs[0].lock_key)
        self.assertTrue(lock.acquire())
        try:
            with self.rows(prow()):
                pedidos.run()
        finally:
            lock.release()
        self.assertEqual(self.launched, [])

    def test_linha_invalida_avisa_mas_nao_trava_as_outras(self):
        with self.rows(prow(comboio="???"), prow(comboio=521)):
            pedidos.run()
        self.assertEqual(len(self.launched), 1)
        self.assertTrue(any(k.startswith("pedido-issue-") for k in self.notes))

    def test_falha_a_ler_a_sheet_nao_e_silenciosa(self):
        with mock.patch.object(common.SheetsClient, "read_requests", side_effect=RuntimeError("403")):
            self.assertEqual(pedidos.run(), 1)
        self.assertTrue(any(k == "pedidos-sheet-read" for k in self.notes))


class LaunchTests(unittest.TestCase):
    def setUp(self):
        for f in common.BASE_DIR.glob("locks/*.json"):
            f.unlink()
        common._state_file("launched_pedidos.json").unlink(missing_ok=True)

    def test_launch_reinicia_o_lock_antes_de_lancar(self):
        legs, _ = common.parse_request_rows([prow()], common.now_local().date())
        leg = legs[0]
        lock = common.PurchaseLock(leg.lock_key)
        lock.acquire(); lock.update(state="FALHOU_QUALQUER_COISA"); lock.release()
        self.assertTrue(common.lock_path(leg.lock_key).exists())
        with mock.patch("pedidos.subprocess.Popen") as popen:
            self.assertTrue(pedidos.launch(leg, out=lambda *a: None))
        self.assertFalse(common.lock_path(leg.lock_key).exists())
        args, kw = popen.call_args
        self.assertEqual(args[0][1:], ["scripts/hot_buy.py", "--date", leg.date.isoformat(), "--leg", leg.leg])
        self.assertTrue(kw["start_new_session"])

    def test_falha_a_lancar_nao_e_silenciosa(self):
        legs, _ = common.parse_request_rows([prow()], common.now_local().date())
        with mock.patch("pedidos.subprocess.Popen", side_effect=OSError("sem memória")), \
             mock.patch.object(common, "notify_once", return_value=True) as n:
            self.assertFalse(pedidos.launch(legs[0], out=lambda *a: None))
        n.assert_called_once()

    def test_para_apos_falhas_repetidas_sem_progresso_e_avisa(self):
        # Regressão (22/09): um processo que morre sempre antes de gravar estado (ex.: "--leg"
        # com um valor que o argparse do hot_buy.py rejeita) era relançado a cada minuto, para
        # sempre, sem nunca tentar comprar nem notificar — 30 lançamentos seguidos em produção.
        legs, _ = common.parse_request_rows([prow()], common.now_local().date())
        leg = legs[0]
        clock = iter(2_000_000.0 + 40 * i for i in range(20))
        with mock.patch("pedidos.subprocess.Popen"), \
             mock.patch("pedidos.time.time", side_effect=lambda: next(clock)), \
             mock.patch.object(common, "notify_once", return_value=True) as n:
            oks = [pedidos.launch(leg, out=lambda *a: None) for _ in range(pedidos.MAX_LAUNCHES + 2)]
        self.assertEqual(oks, [True] * pedidos.MAX_LAUNCHES + [False, False])
        self.assertEqual(n.call_count, 2)

    def test_uma_tentativa_real_mesmo_falhada_nunca_conta_para_o_limite(self):
        legs, _ = common.parse_request_rows([prow()], common.now_local().date())
        leg = legs[0]
        clock = iter(2_000_000.0 + 40 * i for i in range(40))
        with mock.patch("pedidos.subprocess.Popen"), \
             mock.patch("pedidos.time.time", side_effect=lambda: next(clock)), \
             mock.patch.object(common, "notify_once", return_value=True) as n:
            oks = []
            for _ in range(pedidos.MAX_LAUNCHES + 3):
                oks.append(pedidos.launch(leg, out=lambda *a: None))
                lock = common.PurchaseLock(leg.lock_key)
                lock.acquire(); lock.update(state="FAILED"); lock.release()   # simula uma tentativa real
        self.assertTrue(all(oks), oks)
        n.assert_not_called()


if __name__ == "__main__":
    unittest.main()
