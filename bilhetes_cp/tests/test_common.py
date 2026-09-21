"""Validação da Config (3.10.3), sanitização de logs (3.10.8), avisos sem
repetição, lock/estado da compra e helpers de pre-flight/scheduler."""

import json
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import _env  # noqa: F401
import common
import pre_flight
import config_reminder
import pass_expiry_check

TODAY = date(2026, 9, 21)


def row(data="2026-09-22", org="aveiro", dst="lisboa_oriente", t_ida=524, h_ida="06:45",
        t_volta=525, h_volta="18:30", ativo="SIM"):
    return [data, org, dst, t_ida, h_ida, t_volta, h_volta, ativo]


class ConfigValidationTests(unittest.TestCase):
    def parse(self, *rows):
        return common.parse_config_rows(list(rows), TODAY)

    def test_linha_valida_gera_ida_e_volta(self):
        legs, issues = self.parse(row())
        self.assertEqual(issues, [])
        self.assertEqual([(l.leg, l.origin, l.destination, l.train, l.hhmm) for l in legs],
                         [("ida", "aveiro", "lisboa_oriente", 524, "06:45"),
                          ("volta", "lisboa_oriente", "aveiro", 525, "18:30")])
        self.assertEqual(legs[0].key, "2026-09-22-ida")
        self.assertEqual(legs[0].lock_key, "2026-09-22-ida-524")

    def test_inativa_e_ignorada_mesmo_se_invalida(self):
        self.assertEqual(self.parse(row(ativo="NAO", h_ida="25:90")), ([], []))
        self.assertEqual(self.parse(row(ativo="")), ([], []))

    def test_problemas_sao_reportados_sem_bloquear_as_outras_linhas(self):
        legs, issues = self.parse(row(h_ida="25:90"), row(data="2026-09-23"))
        self.assertEqual(len(issues), 1)
        self.assertIn("Linha 12", issues[0])
        self.assertIn("hora de ida inválida", issues[0])
        self.assertEqual({l.date for l in legs}, {date(2026, 9, 23)})

    def test_varios_problemas_tipicos(self):
        cases = {
            "já passou": row(data="2026-09-01"),
            "data inválida": row(data="lixo"),
            "origem igual ao destino": row(dst="aveiro"),
            "origem desconhecida": row(org="marte"),
            "comboio de ida inválido": row(t_ida="abc"),
            "hora de ida inválida": row(h_ida="6.45"),
            "comboio de volta inválido": row(t_volta=""),  # hora preenchida, comboio não
            "hora de volta inválida": row(h_volta="99:99"),
            "não é depois da ida": row(h_volta="06:00"),
        }
        for expected, r in cases.items():
            legs, issues = self.parse(r)
            self.assertEqual(legs, [], expected)
            self.assertTrue(any(expected in i for i in issues), f"{expected!r} não em {issues}")

    def test_datas_duplicadas(self):
        legs, issues = self.parse(row(), row(t_ida=999))
        self.assertEqual(len(legs), 2)  # só a primeira
        self.assertIn("repetida", issues[0])
        self.assertIn("Linha 13", issues[0])

    def test_volta_vazia_significa_so_ida(self):
        legs, issues = self.parse(row(t_volta="", h_volta=""))
        self.assertEqual(issues, [])
        self.assertEqual([l.leg for l in legs], ["ida"])

    def test_valores_como_a_sheet_os_devolve(self):
        serial = (date(2026, 9, 22) - date(1899, 12, 30)).days
        legs, issues = self.parse(row(data=serial, t_ida=524.0, h_ida=(6 * 60 + 45) / 1440,
                                      h_volta=(18 * 60 + 30) / 1440, org="Lisboa Oriente", dst="Aveiro"))
        self.assertEqual(issues, [])
        self.assertEqual(legs[0].origin, "lisboa_oriente")
        self.assertEqual(legs[0].hhmm, "06:45")

    def test_linhas_curtas_nao_rebentam(self):
        self.assertEqual(self.parse(["2026-09-22"]), ([], []))


class SanitizeTests(unittest.TestCase):
    def test_remove_valores_sensiveis_e_tokens(self):
        cru = ("login com teste.pessoa@exemplo.pt senha-de-teste-123 CC 12345678 NIF 123456789 "
               "tel PT912345678 (912345678) passe 9999999999 password-ntfy-falsa "
               "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456 "
               "x-access-token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig")
        limpo = common.sanitize(cru)
        for segredo in ("teste.pessoa@exemplo.pt", "senha-de-teste-123", "12345678", "123456789",
                        "912345678", "9999999999", "password-ntfy-falsa", "abcdefghijklmnopqrstuvwxyz0123456",
                        "eyJhbGciOiJIUzI1NiJ9"):
            self.assertNotIn(segredo, limpo)

    def test_nao_estraga_texto_normal(self):
        self.assertEqual(common.sanitize("Comboio 524 esgotado às 06:45"), "Comboio 524 esgotado às 06:45")

    def test_payload_json_com_campos_sensiveis(self):
        limpo = common.sanitize('{"passengerID": "87654321", "fiscalID":"555666777", "clientMobile":"+351999"}')
        for v in ("87654321", "555666777", "+351999"):
            self.assertNotIn(v, limpo)

    def test_o_ficheiro_de_log_nunca_contem_dados_sensiveis(self):
        logger = common.get_logger("teste_sanitize")
        logger.info("login de %s com senha-de-teste-123 e NIF %s", "teste.pessoa@exemplo.pt", "123456789")
        logger.error("resposta: passengerID=12345678 token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig")
        for h in logger.handlers:
            h.flush()
        conteudo = (common.BASE_DIR / "logs" / "teste_sanitize.log").read_text(encoding="utf-8")
        self.assertIn("login de", conteudo)  # escreveu mesmo
        for segredo in ("senha-de-teste-123", "teste.pessoa@exemplo.pt", "123456789", "12345678",
                        "eyJhbGciOiJIUzI1NiJ9"):
            self.assertNotIn(segredo, conteudo)


class NotifyOnceTests(unittest.TestCase):
    def setUp(self):
        (common._state_file("notified.json")).unlink(missing_ok=True)

    def test_nao_repete_dentro_do_cooldown_e_repete_depois(self):
        with mock.patch.object(common, "notify", return_value=True) as n:
            self.assertTrue(common.notify_once("k1", "t", "m", cooldown_s=3600))
            self.assertFalse(common.notify_once("k1", "t", "m", cooldown_s=3600))
            self.assertTrue(common.notify_once("k2", "t", "m", cooldown_s=3600))
            self.assertEqual(n.call_count, 2)
            seen = json.loads(common._state_file("notified.json").read_text())
            seen["k1"] -= 7200
            common._state_file("notified.json").write_text(json.dumps(seen))
            self.assertTrue(common.notify_once("k1", "t", "m", cooldown_s=3600))

    def test_se_a_entrega_falha_tenta_de_novo_na_proxima(self):
        with mock.patch.object(common, "notify", return_value=False):
            self.assertFalse(common.notify_once("k3", "t", "m"))
        with mock.patch.object(common, "notify", return_value=True) as n:
            self.assertTrue(common.notify_once("k3", "t", "m"))
            n.assert_called_once()


class NotifyTests(unittest.TestCase):
    def test_todas_as_notificacoes_saem_com_priority_high_e_delay_opcional(self):
        sent = []

        def fake_post(url, json=None, auth=None, timeout=None):
            sent.append((url, json, auth))
            return mock.Mock(status_code=200)

        with mock.patch("requests.post", fake_post):
            self.assertTrue(common.notify("Título", "Mensagem com acentuação", tags=["train"]))
            at = datetime.now(common.TZ) + timedelta(hours=1)
            self.assertTrue(common.notify("Depois", "x", at=at))
        self.assertEqual(sent[0][1]["priority"], 4)
        self.assertNotIn("delay", sent[0][1])
        self.assertEqual(sent[1][1]["priority"], 4)
        self.assertEqual(sent[1][1]["delay"], str(int(at.timestamp())))
        self.assertEqual(sent[0][1]["topic"], "topico_teste")

    def test_faz_fallback_para_o_ntfy_local_e_nunca_falha_calada(self):
        import requests
        urls = []

        def fake_post(url, **kw):
            urls.append(url)
            if "invalido" in url:
                raise requests.ConnectionError("sem rede")
            return mock.Mock(status_code=200)

        with mock.patch("requests.post", fake_post):
            self.assertTrue(common.notify("t", "m"))
        self.assertEqual(urls, ["https://ntfy.invalido.test/", "http://127.0.0.1:8080/"])

        with mock.patch("requests.post", side_effect=requests.ConnectionError("x")):
            with self.assertLogs("cp.notify", level="ERROR") as cm:
                self.assertFalse(common.notify("Importante", "corpo"))
        self.assertIn("NÃO ENTREGUE", cm.output[0])


class PurchaseLockTests(unittest.TestCase):
    def test_lock_exclusivo_e_estado_persistente(self):
        a, b = common.PurchaseLock("teste-lock-1"), common.PurchaseLock("teste-lock-1")
        self.assertTrue(a.acquire())
        self.assertFalse(b.acquire())          # segunda instância recusada
        a.update(state="SALE_CREATED", sale_id=123)
        a.release()
        c = common.PurchaseLock("teste-lock-1")
        self.assertTrue(c.acquire())
        self.assertEqual((c.state["state"], c.state["sale_id"]), ("SALE_CREATED", 123))
        c.release()
        self.assertEqual(common.peek_state("teste-lock-1")["sale_id"], 123)

    def test_estado_corrompido_nao_rebenta(self):
        common.lock_path("teste-lock-2").write_text("{isto nao e json")
        lock = common.PurchaseLock("teste-lock-2")
        self.assertTrue(lock.acquire())
        self.assertIn("corrupted_state_backup", lock.state)
        lock.release()


class PreFlightTests(unittest.TestCase):
    CHRONY_OK = ("Reference ID    : A29FC801 (time.cloudflare.com)\nStratum         : 4\n"
                 "System time     : 0.000001000 seconds fast of NTP time\nLeap status     : Normal\n")

    def test_parse_chrony(self):
        self.assertEqual(pre_flight.parse_chrony_tracking(self.CHRONY_OK),
                         (0.000001, "Normal", "A29FC801"))
        off, leap, ref = pre_flight.parse_chrony_tracking(
            "Reference ID    : 00000000 ()\nSystem time     : 0.500000000 seconds slow of NTP time\n"
            "Leap status     : Not synchronised\n")
        self.assertEqual((off, leap, ref), (-0.5, "Not synchronised", "00000000"))

    def _clock_with(self, text):
        with mock.patch("shutil.which", return_value="/usr/bin/chronyc"), \
             mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout=text)):
            return pre_flight.check_clock()

    def test_relogio_ok_e_desvio_acima_do_limite(self):
        self.assertTrue(self._clock_with(self.CHRONY_OK).ok)
        c = self._clock_with(self.CHRONY_OK.replace("0.000001000 seconds fast", "0.300000000 seconds fast"))
        self.assertFalse(c.ok)
        self.assertIn("acima do limite", c.detail)

    def test_relogio_nao_sincronizado_falha(self):
        c = self._clock_with(self.CHRONY_OK.replace("Normal", "Not synchronised"))
        self.assertFalse(c.ok)

    def test_check_config_exige_a_perna_na_cache(self):
        legs, _ = common.parse_config_rows([row()], TODAY)
        with mock.patch.object(common, "load_config_cache", return_value=None):
            self.assertFalse(pre_flight.check_config(legs[0], TODAY).ok)
        cache = {"weekly": [row()], "passe": []}
        with mock.patch.object(common, "load_config_cache", return_value=cache):
            self.assertTrue(pre_flight.check_config(legs[0], TODAY).ok)
            outra = common.Leg(legs[0].date, "ida", "aveiro", "lisboa_oriente", 111, "06:45", 12)
            self.assertFalse(pre_flight.check_config(outra, TODAY).ok)


class TokenTests(unittest.TestCase):
    def test_tokens_ficam_em_token_json_com_permissoes_600(self):
        import stat
        common.save_tokens({"access_token": "acc-123", "refresh_token": "ref-456", "expires_in": 300, "refresh_expires_in": 1799})
        self.assertEqual(stat.S_IMODE(common.TOKEN_FILE.stat().st_mode), 0o600)
        t = common.load_tokens()
        self.assertEqual((t["access_token"], t["refresh_token"]), ("acc-123", "ref-456"))
        self.assertGreater(t["refresh_expires_at"], t["access_expires_at"])
        common.TOKEN_FILE.unlink()
        self.assertIsNone(common.load_tokens())

    def test_o_token_do_ntfy_e_preferido_e_a_password_fica_de_reserva(self):
        seen = []

        def fake_post(url, json=None, auth=None, headers=None, timeout=None):
            seen.append(("token" if headers else "basic"))
            return mock.Mock(status_code=401 if (headers and len(seen) == 1) else 200)

        with mock.patch.dict("os.environ", {"NTFY_TOKEN": "tk_abcdefghijklmnopqrstuvwxyz012"}), \
             mock.patch("requests.post", fake_post):
            self.assertTrue(common.notify("t", "m"))
        self.assertEqual(seen, ["token", "basic"])            # token recusado -> tenta a password
        seen.clear()
        with mock.patch.dict("os.environ", {"NTFY_TOKEN": "tk_abcdefghijklmnopqrstuvwxyz012"}), \
             mock.patch("requests.post", lambda *a, **k: (seen.append("token" if k.get("headers") else "basic"), mock.Mock(status_code=200))[1]):
            self.assertTrue(common.notify("t", "m"))
        self.assertEqual(seen, ["token"])                     # aceite à primeira: não usa a password

    def test_o_token_do_ntfy_nunca_aparece_nos_logs(self):
        with mock.patch.dict("os.environ", {"NTFY_TOKEN": "tk_abcdefghijklmnopqrstuvwxyz012"}):
            self.assertNotIn("tk_abcdefghij", common.sanitize("cabeçalho Bearer tk_abcdefghijklmnopqrstuvwxyz012 usado"))


class HeartbeatTests(unittest.TestCase):
    def test_sem_url_nao_faz_nada_e_com_url_faz_ping(self):
        import heartbeat
        with mock.patch.dict("os.environ", {"HEALTHCHECKS_PING_URL": ""}), mock.patch("requests.get") as g:
            self.assertEqual(heartbeat.main(), 0)
            g.assert_not_called()
        with mock.patch.dict("os.environ", {"HEALTHCHECKS_PING_URL": "https://hc.invalido.test/abc"}), \
             mock.patch("requests.get", return_value=mock.Mock(raise_for_status=lambda: None)) as g:
            self.assertEqual(heartbeat.main(), 0)
            g.assert_called_once()

    def test_falha_do_ping_nao_e_silenciosa(self):
        import heartbeat, requests
        common._state_file("notified.json").unlink(missing_ok=True)
        with mock.patch.dict("os.environ", {"HEALTHCHECKS_PING_URL": "https://hc.invalido.test/abc"}), \
             mock.patch("requests.get", side_effect=requests.ConnectionError("x")), \
             mock.patch.object(common, "notify", return_value=True) as n:
            self.assertEqual(heartbeat.main(), 1)
        n.assert_called_once()


class LocateConfigTests(unittest.TestCase):
    P = ["Data_Ultima_Compra", "Validade_Dias", "Data_Expira", "Dias_Restantes"]
    W = ["Data", "Origem", "Destino", "Comboio_Ida", "Hora_Ida", "Comboio_Volta", "Hora_Volta", "Ativo"]

    def sheet(self, prefix=0):
        top = [["Passe"]] * prefix
        return top + [["Título"], [], self.P, [45000, 30, 45029, 5], [], [], self.W,
                      ["2026-09-22", "Aveiro", "Lisboa Oriente", 524, "06:45", 525, "18:30", "SIM"], []]

    def test_encontra_os_blocos_pelo_nome(self):
        passe, weekly, first = common.locate_config(self.sheet())
        self.assertEqual(passe, [45000, 30, 45029, 5])
        self.assertEqual(first, 8)                       # cabeçalho na linha 7 -> dados na 8
        self.assertEqual(weekly[0][:3], ["2026-09-22", "Aveiro", "Lisboa Oriente"])

    def test_inserir_linhas_no_topo_nao_desalinha(self):
        passe, weekly, first = common.locate_config(self.sheet(prefix=3))
        self.assertEqual((passe[1], first), (30, 11))
        legs, issues = common.parse_snapshot({"weekly": weekly, "first_row": first}, TODAY)
        self.assertEqual((len(legs), issues), (2, []))

    def test_colunas_trocadas_ou_com_extras_sao_lidas_pelo_nome(self):
        w = ["Extra"] + [self.W[i] for i in (7, 0, 1, 2, 3, 4, 5, 6)]      # Ativo primeiro, coluna extra antes
        vals = [["Extra"] + self.P, ["x", 45000, 30, 45029, 5], w,
                ["x", "SIM", "2026-09-22", "Aveiro", "Lisboa Oriente", 524, "06:45", 525, "18:30"]]
        passe, weekly, _ = common.locate_config(vals)
        self.assertEqual(passe, [45000, 30, 45029, 5])
        self.assertEqual(weekly[0], ["2026-09-22", "Aveiro", "Lisboa Oriente", 524, "06:45", 525, "18:30", "SIM"])

    def test_cabecalho_em_falta_nunca_le_as_cegas(self):
        for vals, falta in (([self.W], "bloco do passe"), ([self.P], "tabela semanal"), ([], "bloco do passe")):
            with self.assertRaises(ValueError) as cm:
                common.locate_config(vals)
            self.assertIn(falta, str(cm.exception))

    def test_cabecalhos_tolerantes_a_maiusculas_e_espacos(self):
        vals = [[" data_ultima_compra", "VALIDADE DIAS", "data-expira", "Dias Restantes"], [45000, 30, 1, 1],
                [h.lower().replace("_", " ") for h in self.W]]
        self.assertEqual(common.locate_config(vals)[0][1], 30)


class RemindersTests(unittest.TestCase):
    def test_semana_seguinte(self):
        self.assertEqual(config_reminder.next_week(date(2026, 9, 19)), (date(2026, 9, 21), date(2026, 9, 27)))  # sábado
        self.assertEqual(config_reminder.next_week(date(2026, 9, 21)), (date(2026, 9, 28), date(2026, 10, 4)))  # segunda

    def test_semana_configurada_ou_nao(self):
        mon, sun = date(2026, 9, 21), date(2026, 9, 27)
        sat = date(2026, 9, 19)
        self.assertTrue(config_reminder.week_is_configured([row(data="2026-09-22")], mon, sun, sat))
        self.assertFalse(config_reminder.week_is_configured([row(data="2026-09-29")], mon, sun, sat))
        self.assertFalse(config_reminder.week_is_configured([row(data="2026-09-22", ativo="NAO")], mon, sun, sat))
        self.assertFalse(config_reminder.week_is_configured([], mon, sun, sat))

    def test_validade_do_passe(self):
        serial = lambda d: (d - date(1899, 12, 30)).days  # noqa: E731
        # 30 dias contando o dia do carregamento: 21/09 + 29 = 20/10 (Validade_Dias = 29)
        expira = date(2026, 10, 20)
        self.assertEqual(pass_expiry_check.expiry_date([serial(date(2026, 9, 21)), 29, serial(expira), 29]), expira)
        # a coluna Data_Expira da Sheet é a fonte da regra
        self.assertEqual(pass_expiry_check.expiry_date([serial(date(2026, 9, 21)), 29, serial(date(2026, 10, 25))]), date(2026, 10, 25))
        # sem Data_Expira, calcula A + B como a fórmula da Sheet
        self.assertEqual(pass_expiry_check.expiry_date([serial(date(2026, 9, 21)), 29, ""]), expira)
        self.assertIsNone(pass_expiry_check.expiry_date([]))
        self.assertIsNone(pass_expiry_check.expiry_date(["", "", ""]))
        self.assertIsNotNone(pass_expiry_check.message_for(3, expira))
        self.assertIsNotNone(pass_expiry_check.message_for(1, expira))
        self.assertIsNotNone(pass_expiry_check.message_for(0, expira))
        self.assertIsNone(pass_expiry_check.message_for(2, expira))
        self.assertIsNone(pass_expiry_check.message_for(10, expira))


if __name__ == "__main__":
    unittest.main()
