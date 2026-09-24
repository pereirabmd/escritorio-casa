"""SqliteStore: mesma interface e mesmos formatos que a SheetsClient, sobre o esquema real
(dados/migrations_bilhetes/). Verifica também que o resto do sistema (parsers, pedidos, live_delay,
already_bought) funciona alimentado por ele, sem alterações."""

import _env  # noqa: F401 — ambiente hermético (tem de vir antes dos scripts)

import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import common
import hot_buy
import live_delay
import pedidos
import store

SCHEMA = Path(__file__).resolve().parents[2] / "dados" / "migrations_bilhetes" / "001_bilhetes.sql"
TODAY = date(2026, 9, 24)


class StoreBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bilhetes.db"
        c = sqlite3.connect(self.path)
        c.executescript(SCHEMA.read_text())
        c.close()
        self.st = store.SqliteStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def sql(self, q, *a):
        c = sqlite3.connect(self.path)
        try:
            r = c.execute(q, a).fetchall()
            c.commit()
            return r
        finally:
            c.close()

    def viagem(self, id_=None, data="2026-09-25", org="Lisboa Oriente", dst="Aveiro", comboio=731, hora="17:30", ativo="SIM"):
        self.sql("INSERT INTO bilhetes_viagens (id, data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?,?)",
                 id_, data, org, dst, comboio, hora, ativo)


class ConfigTest(StoreBase):
    def test_passe_calculado_e_em_branco(self):
        snap = self.st.read_config()
        self.assertEqual(snap["passe"], ["", 29, "", ""])
        self.assertEqual(snap["weekly"], [])
        self.sql("UPDATE bilhetes_passe SET data_ultima_compra='2026-09-21' WHERE id=1")
        with mock.patch.object(common, "now_local", return_value=datetime(2026, 9, 24, 12, tzinfo=common.TZ)):
            passe = self.st.read_config()["passe"]
        self.assertEqual(passe, ["2026-09-21", 29, "2026-10-20", 26])      # 30 dias contando o dia do carregamento
        import pass_expiry_check
        self.assertEqual(pass_expiry_check.expiry_date(passe), date(2026, 10, 20))

    def test_viagens_alimentam_o_validador_com_o_id_como_numero_da_viagem(self):
        self.viagem(12, data="2026-09-25")
        self.viagem(None, data="2026-09-26", comboio=520, hora="06:45")   # id novo: >= 100
        self.viagem(30, data="2026-09-27", ativo="NAO")
        snap = self.st.read_config()
        legs, issues = common.parse_snapshot(snap, TODAY)
        self.assertEqual(issues, [])
        self.assertEqual([(l.leg, l.row, l.train) for l in legs], [("v12", 12, 731), ("v100", 100, 520)])
        self.assertEqual(snap["weekly"][0], ["2026-09-25", "Lisboa Oriente", "Aveiro", 731, "17:30", "SIM", 12])

    def test_ids_nunca_se_reutilizam_e_novos_comecam_em_100(self):
        self.viagem(12)
        self.viagem(None)
        self.assertEqual([r[0] for r in self.sql("SELECT id FROM bilhetes_viagens ORDER BY id")], [12, 100])
        self.sql("DELETE FROM bilhetes_viagens WHERE id=100")
        self.viagem(None)
        self.assertEqual([r[0] for r in self.sql("SELECT id FROM bilhetes_viagens ORDER BY id")], [12, 101])

    def test_apagar_uma_viagem_nao_muda_o_id_das_outras(self):
        for i in (12, 13, 14):
            self.viagem(i, data=f"2026-09-{12 + i}", comboio=700 + i)
        self.sql("DELETE FROM bilhetes_viagens WHERE id=12")
        legs, _ = common.parse_snapshot(self.st.read_config(), TODAY)
        self.assertEqual([l.leg for l in legs], ["v13", "v14"])      # na Sheet, apagar uma linha renumerava as seguintes


class TicketsTest(StoreBase):
    def test_append_read_e_sem_duplicados(self):
        args = ("2026-09-24", 731, "Lisboa Oriente", "Aveiro", "17:39", 22, 105, "CP-QHYZ7B4OKS1J")
        self.st.append_ticket(*args)
        self.st.append_ticket(*args)                                   # repetição da escrita: ignorada
        rows = self.st.read_tickets()
        self.assertEqual(rows, [["2026-09-24", 731, "Lisboa Oriente", "Aveiro", "17:39", "22", "105", "CP-QHYZ7B4OKS1J"]])

    def test_already_bought_e_live_delay_leem_do_store(self):
        self.st.append_ticket("2026-09-24", 731, "Lisboa Oriente", "Aveiro", "17:39", 22, 105, "CP-X")
        leg = common.Leg(date(2026, 9, 24), "v12", "lisboa_oriente", "aveiro", 731, "17:30", 12)
        self.assertTrue(hot_buy.already_bought(self.st, leg))
        outro = common.Leg(date(2026, 9, 24), "v13", "lisboa_oriente", "aveiro", 999, "17:30", 13)
        self.assertFalse(hot_buy.already_bought(self.st, outro))
        agora = datetime(2026, 9, 24, 17, 20, tzinfo=common.TZ)
        watches = live_delay.upcoming_watches(self.st.read_tickets(), agora)
        self.assertEqual([(w.train, w.carriage, w.seat) for w in watches], [(731, "22", "105")])


class LogsTest(StoreBase):
    def test_append_log_e_sanitizacao(self):
        self.st.append_log("COMPRA", "2026-09-24", "v12", 731, 200, "CONFIRMED", "CP-X", "")
        self.st.append_log("ERRO", "2026-09-24", "v12", 731, "", "FAILED", "", "senha-de-teste-123 falhou")
        rows = self.sql("SELECT tipo, perna, comboio, status_http, resultado, mensagem_erro FROM bilhetes_logs ORDER BY id")
        self.assertEqual(rows[0], ("COMPRA", "v12", "731", "200", "CONFIRMED", ""))
        self.assertNotIn("senha-de-teste-123", rows[1][5])               # nunca gravar segredos
        ts = self.sql("SELECT ts FROM bilhetes_logs")[0][0]
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$")


class PedidosTest(StoreBase):
    def test_ciclo_completo(self):
        self.st.append_request("2026-09-30", "Lisboa Oriente", "Aveiro", 731, "17:30", estado="ESGOTADO")
        (raw,) = self.st.read_requests()
        self.assertEqual(raw[:13], ["2026-09-30", "Lisboa Oriente", "Aveiro", 731, "17:30", "SIM", "NAO", "", "NAO", "ESGOTADO", "", "", ""])
        pid = raw[13]
        self.assertEqual(pid, 100)
        legs, issues = common.parse_request_rows([raw], TODAY)
        self.assertEqual((issues, [(l.leg, l.row) for l in legs]), ([], [("pedido100", 100)]))
        # a PWA liga a repetição e força; o Pi lê
        self.sql("UPDATE bilhetes_pedidos SET retry='SIM', intervalo_minutos=20, forcar='SIM' WHERE id=?", pid)
        (raw,) = self.st.read_requests()
        legs, _ = common.parse_request_rows([raw], TODAY)
        self.assertEqual((legs[0].retry, legs[0].retry_minutes), (True, 20.0))
        self.assertEqual(pedidos.is_due(legs[0], raw, 15, 1e12), (True, True))     # forçado
        # o Pi escreve o resultado: só os campos indicados mudam
        self.st.update_request(pid, ultima_tentativa="2026-09-24T09:00:00+01:00", estado="CONFIRMADO", referencia="CP-Z",
                               mensagem="ok", forcar="NAO")
        (raw,) = self.st.read_requests()
        self.assertEqual((raw[6], raw[7], raw[8], raw[9], raw[11]), ("SIM", 20, "NAO", "CONFIRMADO", "CP-Z"))
        self.assertEqual(pedidos.is_due(legs[0], raw, 15, 1e12), (False, False))   # terminal

    def test_request_row_procura_por_id_e_nao_por_posicao(self):
        for d in ("2026-09-30", "2026-10-01", "2026-10-02"):
            self.st.append_request(d, "A", "B", 1, "06:45")
        rows = self.st.read_requests()
        self.sql("DELETE FROM bilhetes_pedidos WHERE id=100")            # o pedido 101 passa a ser o 1.º da lista
        rows = self.st.read_requests()
        self.assertEqual(common.request_row(rows, 101)[13], 101)
        self.assertEqual(common.request_row(rows, 102)[13], 102)
        self.assertIsNone(common.request_row(rows, 100))

    def test_update_de_pedido_inexistente_e_campo_desconhecido_falham_alto(self):
        with self.assertRaises(LookupError):
            self.st.update_request(999, estado="X")
        with self.assertRaises(ValueError):
            self.st.update_request(1, coluna_inventada="x")


class BackendTest(unittest.TestCase):
    def test_get_store_escolhe_pelo_ambiente(self):
        with mock.patch.dict(os.environ, {"BILHETES_BACKEND": "sqlite"}):
            self.assertIsInstance(common.get_store(), store.SqliteStore)
        with mock.patch.dict(os.environ, {"BILHETES_BACKEND": "sheets"}), mock.patch.object(common, "SheetsClient") as sc:
            self.assertIs(common.get_store(), sc.return_value)
        with mock.patch.dict(os.environ, {"BILHETES_BACKEND": ""}), mock.patch.object(common, "SheetsClient") as sc:
            self.assertIs(common.get_store(), sc.return_value)          # por omissão: Sheet

    def test_nunca_cria_uma_bd_vazia_por_engano(self):
        with tempfile.TemporaryDirectory() as d:
            st = store.SqliteStore(Path(d) / "nao_existe.db")
            with self.assertRaises(FileNotFoundError):
                st.read_config()
            self.assertFalse((Path(d) / "nao_existe.db").exists())


if __name__ == "__main__":
    unittest.main()
