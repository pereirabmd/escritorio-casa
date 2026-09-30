"""Compra com as credenciais de cada pessoa (PLANO_FINAL 9.11, fase 2): o Bruno marca, a compra faz-se como quem viaja."""

import _env  # noqa: F401 — ambiente hermético (tem de vir antes dos scripts)

import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import common
import credenciais
import cp_ticket
import hot_buy
import store
from cp_ticket import CPClient

MIGRACOES = Path(__file__).resolve().parents[2] / "dados" / "migrations_bilhetes"
CHAVE = "JmV0o_4a3M2bqV6bBqzN9p7Q0l8c1d2e3f4g5h6i7j8="      # Fernet válida só para os testes


def cifrar(texto: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(CHAVE.encode()).encrypt(texto.encode()).decode()


def base_com_camila(completa=True, ativa=True, email="camila@exemplo.pt"):
    tmp = tempfile.TemporaryDirectory()
    caminho = Path(tmp.name) / "bilhetes.db"
    c = sqlite3.connect(caminho)
    for f in ("001_bilhetes.sql", "002_tentativas.sql", "003_utilizadores.sql"):
        c.executescript((MIGRACOES / f).read_text())
    c.execute("INSERT INTO bilhetes_utilizadores (id, nome, email, ativo, cp_email, cp_password_enc, passageiro_nome, passageiro_cc, passageiro_telemovel, nif, passe_verde_numero) "
              "VALUES (2, 'Camila', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (email, int(ativa), "camila.cp@exemplo.pt" if completa else "", cifrar("senha-da-camila"), "Camila Silva", "87654321", "PT933333333", "987654321", "7777777777"))
    c.commit(); c.close()
    return tmp, caminho


class CredenciaisTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.base = base_com_camila()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict("os.environ", {"BILHETES_FERNET_KEY": CHAVE}); p.start(); self.addCleanup(p.stop)

    def test_o_bruno_usa_o_ambiente_sem_ler_a_base(self):
        c = credenciais.carregar(1, base="/nao/existe.db")
        self.assertEqual((c.cp_email, c.passageiro_nome, c.passageiro_cc), (_env.FAKE["CP_EMAIL"], _env.FAKE["CP_PASSENGER_NAME"], _env.FAKE["CP_PASSENGER_CC"]))

    def test_a_camila_vem_da_base_com_a_password_decifrada(self):
        c = credenciais.carregar(2, base=self.base)
        self.assertEqual((c.cp_email, c.cp_password, c.passageiro_nome, c.passageiro_cc, c.passageiro_telemovel, c.nif, c.passe_numero),
                         ("camila.cp@exemplo.pt", "senha-da-camila", "Camila Silva", "87654321", "PT933333333", "987654321", "7777777777"))
        self.assertNotIn("senha-da-camila", repr(c))                     # nunca vai parar a um log
        self.assertNotIn("87654321", repr(c))

    def test_dados_em_falta_recusam_sem_mostrar_valores(self):
        tmp, base = base_com_camila(completa=False); self.addCleanup(tmp.cleanup)
        with self.assertRaises(credenciais.CredenciaisIncompletas) as e:
            credenciais.carregar(2, base=base)
        self.assertIn("e-mail da CP", str(e.exception)); self.assertNotIn("senha", str(e.exception)); self.assertNotIn("87654321", str(e.exception))

    def test_desativada_inexistente_ou_sem_chave_ou_chave_errada_nunca_compram(self):
        tmp, base = base_com_camila(ativa=False); self.addCleanup(tmp.cleanup)
        for uid, b in ((2, base), (9, self.base)):
            with self.assertRaises(credenciais.CredenciaisIncompletas):
                credenciais.carregar(uid, base=b)
        with mock.patch.dict("os.environ", {"BILHETES_FERNET_KEY": ""}), self.assertRaisesRegex(credenciais.CredenciaisIncompletas, "BILHETES_FERNET_KEY"):
            credenciais.carregar(2, base=self.base)
        from cryptography.fernet import Fernet
        with mock.patch.dict("os.environ", {"BILHETES_FERNET_KEY": Fernet.generate_key().decode()}), self.assertRaisesRegex(credenciais.CredenciaisIncompletas, "decifra"):
            credenciais.carregar(2, base=self.base)

    def test_email_pulse_e_nome(self):
        self.assertIsNone(credenciais.email_pulse(1, base=self.base))
        self.assertEqual(credenciais.email_pulse(2, base=self.base), "camila@exemplo.pt")
        self.assertEqual((credenciais.nome_de(2, base=self.base), credenciais.nome_de(1, base=self.base)), ("Camila", ""))


class ClienteDaCpTests(unittest.TestCase):
    CAMILA = credenciais.Credenciais(2, "Camila", "camila.cp@exemplo.pt", "senha", "Camila Silva", "87654321", "PT933333333", "987654321", "7777777777")

    def corpos(self, cliente):
        cliente._checked = mock.Mock()
        cliente.set_passengers(1); cliente.set_client(1); cliente.set_fiscal(1); cliente.apply_green_pass(1)
        return [c.kwargs["body"] for c in cliente._checked.call_args_list]

    def test_com_credenciais_da_camila_usa_so_os_dados_dela(self):
        pass_, cli, fisc, verde = self.corpos(CPClient("tok", cred=self.CAMILA))
        self.assertEqual(pass_["salePassengers"][0]["passengerID"], "87654321")
        self.assertEqual((cli["clientEmail"], cli["clientMobile"], cli["clientName"]), ("camila.cp@exemplo.pt", "PT933333333", "Camila Silva"))
        self.assertEqual((fisc["fiscalID"], fisc["fiscalName"]), ("987654321", "Camila Silva"))
        self.assertEqual(verde["requestedItems"][0]["inputData"], "7777777777")
        blob = str([pass_, cli, fisc, verde])
        for bruno in (_env.FAKE["CP_EMAIL"], _env.FAKE["CP_PASSENGER_CC"], _env.FAKE["CP_PASSENGER_NIF"], _env.FAKE["CP_GREEN_PASS_NUMBER"]):
            self.assertNotIn(bruno, blob)                                # nenhum dado do Bruno vai na compra dela

    def test_sem_credenciais_continua_a_usar_o_ambiente(self):
        pass_, cli, fisc, verde = self.corpos(CPClient("tok"))
        self.assertEqual((pass_["salePassengers"][0]["passengerID"], cli["clientEmail"], fisc["fiscalID"], verde["requestedItems"][0]["inputData"]),
                         (_env.FAKE["CP_PASSENGER_CC"], _env.FAKE["CP_EMAIL"], _env.FAKE["CP_PASSENGER_NIF"], _env.FAKE["CP_GREEN_PASS_NUMBER"]))

    def test_a_morada_fiscal_do_bruno_nunca_vai_na_compra_de_outra_pessoa(self):
        with mock.patch.dict("os.environ", {"CP_FISCAL_ADDRESS": '{"street": "Rua do Bruno"}'}):
            self.assertIn("fiscalAddress", self.corpos(CPClient("tok"))[2])
            self.assertNotIn("fiscalAddress", self.corpos(CPClient("tok", cred=self.CAMILA))[2])

    def test_cabecalho_do_cliente_e_o_email_de_quem_compra(self):
        self.assertEqual(CPClient("t", cred=self.CAMILA)._headers("k", with_client_id=True)["x-cp-client-id"], "camila.cp@exemplo.pt")
        self.assertEqual(CPClient("t")._headers("k", with_client_id=True)["x-cp-client-id"], _env.FAKE["CP_EMAIL"])

    def test_o_login_usa_as_credenciais_dela(self):
        enviados = []

        class Sessao:
            def get(self, *a, **k):
                return mock.Mock(text='<form action="http://login/x">', raise_for_status=lambda: None)

            def post(self, url, data=None, **k):
                enviados.append(data)
                return mock.Mock(status_code=200, headers={})                # recusa: só interessa o que se enviou

        with mock.patch.object(cp_ticket, "make_session", lambda: Sessao()), self.assertRaises(RuntimeError):
            cp_ticket.login(self.CAMILA)
        self.assertEqual((enviados[0]["username"], enviados[0]["password"]), ("camila.cp@exemplo.pt", "senha"))


class TokensPorPessoaTests(unittest.TestCase):
    def test_cada_pessoa_tem_o_seu_ficheiro_de_sessao(self):
        self.assertEqual(common.token_file(1), common.TOKEN_FILE)
        self.assertEqual(common.token_file(2), common.TOKEN_FILE.parent / "tokens" / "2.json")
        common.save_tokens({"access_token": "a-bruno", "refresh_token": "r-bruno"}, 1)
        common.save_tokens({"access_token": "a-camila", "refresh_token": "r-camila"}, 2)
        self.assertEqual(common.load_tokens(1)["access_token"], "a-bruno")          # o dela não sobrepõe o dele
        self.assertEqual(common.load_tokens(2)["access_token"], "a-camila")
        self.assertIsNone(common.load_tokens(3))


class DonoDasViagensTests(unittest.TestCase):
    def test_o_dono_vem_da_coluna_extra_e_por_omissao_e_o_bruno(self):
        hoje = date(2026, 9, 30)
        legs, _ = common.parse_config_rows([["2026-10-01", "Aveiro", "Lisboa Oriente", 520, "07:27", "SIM", 12, 2],
                                            ["2026-10-02", "Aveiro", "Lisboa Oriente", 522, "07:27", "SIM", 13],
                                            ["2026-10-03", "Aveiro", "Lisboa Oriente", 524, "07:27", "SIM", 14, ""]], hoje)
        self.assertEqual([l.utilizador_id for l in legs], [2, 1, 1])
        legs, _ = common.parse_request_rows([["2026-10-05", "Aveiro", "Lisboa Oriente", 520, "07:27", "SIM", "NAO", "", "NAO", "PENDENTE", "", "", "", 4, 2]], hoje)
        self.assertEqual(legs[0].utilizador_id, 2)

    def test_o_bilhete_de_uma_pessoa_nao_conta_como_comprado_para_outra(self):
        leg = lambda uid: common.Leg(date(2026, 10, 1), "v12", "aveiro", "lisboa_oriente", 520, "07:27", 12, utilizador_id=uid)     # noqa: E731
        class Folha:
            def read_tickets(self): return [["2026-10-01", 520, "Aveiro", "Lisboa Oriente", "07:27", "5", "12", "REF", 2]]
        self.assertTrue(hot_buy.already_bought(Folha(), leg(2)))
        self.assertFalse(hot_buy.already_bought(Folha(), leg(1)))          # o Bruno no mesmo comboio ainda tem de comprar o seu
        class FolhaAntiga:                                                   # linhas sem a coluna do dono (a Sheet) são do Bruno
            def read_tickets(self): return [["2026-10-01", 520, "Aveiro", "Lisboa Oriente", "07:27", "5", "12", "REF"]]
        self.assertTrue(hot_buy.already_bought(FolhaAntiga(), leg(1)))
        self.assertFalse(hot_buy.already_bought(FolhaAntiga(), leg(2)))


class ConfigurarDonoTests(unittest.TestCase):
    def setUp(self):
        self.camila = ClienteDaCpTests.CAMILA
        self.leg = lambda uid: common.Leg(date(2026, 10, 1), "v12", "aveiro", "lisboa_oriente", 520, "07:27", 12, utilizador_id=uid)   # noqa: E731

    def buyer(self, uid, **kw):
        with mock.patch.object(credenciais, "carregar", return_value=self.camila):
            return hot_buy.Buyer(self.leg(uid), mock.Mock(), sheets=mock.Mock(), **kw)

    def test_bruno_nada_muda(self):
        b = self.buyer(1)
        self.assertIsNone(b.cred)
        self.assertIs(b.login_fn, hot_buy.login); self.assertIs(b.cp_factory, CPClient); self.assertIs(b.notify, hot_buy.notify)
        self.assertNotIn("—", b.label.split(")")[-1])

    def test_a_compra_da_camila_usa_as_credenciais_dela_e_avisa_os_dois(self):
        b = self.buyer(2)
        self.assertEqual(b.cred, self.camila)
        self.assertTrue(b.label.endswith("— Camila"))
        self.assertEqual(b.cp_factory("tok").cp_email, "camila.cp@exemplo.pt")
        with mock.patch.object(cp_ticket, "make_session", side_effect=RuntimeError("parou aqui")), self.assertRaises(RuntimeError):
            b.login_fn()                                                   # o login é o dela (a sessão falsa só o interrompe)
        self.assertEqual(b.notify.keywords["utilizador_id"], 2)                # o aviso leva o dono: o Pulse avisa o Bruno e a própria pessoa

    def test_injecoes_dos_testes_sao_respeitadas(self):
        falso_login = lambda: {"access_token": "x", "refresh_token": "y"}     # noqa: E731
        b = self.buyer(2, login_fn=falso_login)
        self.assertIs(b.login_fn, falso_login)

    def test_credenciais_incompletas_nao_compram_e_avisam_uma_vez(self):
        leg = self.leg(2)
        with mock.patch.object(hot_buy, "load_leg", return_value=leg), \
                mock.patch.object(credenciais, "carregar", side_effect=credenciais.CredenciaisIncompletas("faltam dados de Camila: NIF")), \
                mock.patch.object(credenciais, "nome_de", return_value="Camila"), \
                mock.patch.object(hot_buy, "notify_once") as aviso, mock.patch("sys.argv", ["hot_buy", "--date", "2026-10-01", "--leg", "v12"]):
            self.assertEqual(hot_buy.main(), 1)
        titulo, msg = aviso.call_args.args[1], aviso.call_args.args[2]
        self.assertIn("Não consigo comprar — Camila", titulo); self.assertIn("faltam dados de Camila: NIF", msg)
        self.assertEqual(aviso.call_args.kwargs["utilizador_id"], 2)


class AvisosParaOsDoisTests(unittest.TestCase):
    ENV = {"PULSE_EVENTS_URL": "http://127.0.0.1:8897/api/v1/internal/events", "PULSE_SERVICE_KEY": "s" * 40, "PULSE_EVENTS_USER": "bruno@exemplo.pt"}

    def enviados(self, uid):
        posts = []

        def fake(url, json=None, headers=None, auth=None, timeout=None):
            posts.append((headers.get("X-Pulse-User") if headers else None, json))
            return mock.Mock(status_code=201)
        with mock.patch.dict("os.environ", self.ENV), mock.patch("requests.post", fake), \
                mock.patch("credenciais.email_pulse", lambda u: {2: "camila@exemplo.pt", 3: None}.get(u)):
            ok = common.pulse_event("Comprado — comboio 520 — Camila", "Carruagem 5", utilizador_id=uid)
        return ok, posts

    def test_viagem_do_bruno_avisa_so_o_bruno(self):
        ok, posts = self.enviados(1)
        self.assertTrue(ok); self.assertEqual([u for u, _ in posts], ["bruno@exemplo.pt"])

    def test_viagem_da_camila_avisa_o_bruno_e_a_camila_com_chaves_diferentes(self):
        ok, posts = self.enviados(2)
        self.assertTrue(ok)
        self.assertEqual([u for u, _ in posts], ["bruno@exemplo.pt", "camila@exemplo.pt"])
        self.assertEqual(len({c["chave"] for _, c in posts}), 2)            # o Pulse deduplica por chave: cada um tem a sua

    def test_pessoa_sem_conta_no_pulse_so_avisa_o_bruno(self):
        ok, posts = self.enviados(3)
        self.assertEqual([u for u, _ in posts], ["bruno@exemplo.pt"])

    def test_varias_pessoas_no_mesmo_aviso(self):
        ok, posts = self.enviados({1, 2})
        self.assertEqual([u for u, _ in posts], ["bruno@exemplo.pt", "camila@exemplo.pt"])


if __name__ == "__main__":
    unittest.main()


class VigilanciaEPreFlightTests(unittest.TestCase):
    def test_duas_pessoas_no_mesmo_comboio_uma_vigilancia_e_avisos_para_as_duas(self):
        import live_delay
        agora = common.local_dt(date(2026, 10, 1), "07:10")
        linhas = [["2026-10-01", 520, "Aveiro", "Lisboa Oriente", "07:27", "5", "12", "R1", 1],
                  ["2026-10-01", 520, "Aveiro", "Lisboa Oriente", "07:27", "5", "13", "R2", 2]]
        w = live_delay.upcoming_watches(linhas, agora)
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0].donos, frozenset({1, 2}))

    def test_preflight_da_pessoa_sem_dados_falha_sem_mostrar_valores(self):
        import pre_flight
        leg = common.Leg(date(2026, 10, 1), "v12", "aveiro", "lisboa_oriente", 520, "07:27", 12, utilizador_id=2)
        with mock.patch.object(credenciais, "carregar", side_effect=credenciais.CredenciaisIncompletas("faltam dados de Camila: NIF")):
            c = pre_flight.check_credenciais_da_pessoa(leg)
        self.assertFalse(c.ok); self.assertIn("NIF", c.detail)
        with mock.patch.object(credenciais, "carregar", return_value=ClienteDaCpTests.CAMILA):
            self.assertTrue(pre_flight.check_credenciais_da_pessoa(leg).ok)


class EnsaioComOutraPessoaTests(unittest.TestCase):
    def test_o_cliente_do_ensaio_tambem_leva_as_credenciais_dela(self):
        import ensaio_compra
        leg = common.Leg(date(2026, 10, 1), "ens", "aveiro", "lisboa_oriente", 520, "07:27", 0, utilizador_id=2)
        with mock.patch.object(credenciais, "carregar", return_value=ClienteDaCpTests.CAMILA):
            b = hot_buy.Buyer(leg, mock.Mock(), sheets=mock.Mock(), cp_factory=ensaio_compra.CPEnsaio)
        cliente = b.cp_factory("tok")
        self.assertIsInstance(cliente, ensaio_compra.CPEnsaio)                   # continua a ser o cliente que cancela em vez de confirmar
        self.assertEqual((cliente.cp_email, cliente.nif), ("camila.cp@exemplo.pt", "987654321"))      # e nunca os dados do Bruno

    def test_ensaio_recusa_pessoa_sem_dados(self):
        import ensaio_compra
        with mock.patch.object(credenciais, "carregar", side_effect=credenciais.CredenciaisIncompletas("faltam dados de Camila: NIF")), \
                mock.patch.object(ensaio_compra.timetable, "apply_anchor", side_effect=lambda l: l), \
                mock.patch("sys.argv", ["ensaio", "--date", "2031-01-01", "--train", "520", "--hhmm", "07:27", "--sem-ancora", "--utilizador", "2"]):
            self.assertEqual(ensaio_compra.main(), 3)
