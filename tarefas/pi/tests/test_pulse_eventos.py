from datetime import datetime, timedelta

import common
import pulse_eventos as pe
from tests.base import TarefasTestCase

AGORA = datetime(2031, 5, 10, 9, 0, tzinfo=common.TZ)
CONFIG = {"Pessoa1_Nome": "Bruno", "Pessoa1_Email": "Bruno@x.pt", "Pessoa1_NtfyUser": "bruno",
          "Pessoa2_Nome": "Camila", "Pessoa2_Email": "camila@x.pt", "Pessoa2_NtfyUser": "tarefas_camila"}


class Falso:
    def __init__(self, codigo=201):
        self.pedidos, self.codigo = [], codigo

    def __call__(self, metodo, url, corpo):
        self.pedidos.append((metodo, url, corpo))
        return self.codigo


class PulseEventosTest(TarefasTestCase):
    def rec(self, http, alvo, estado, emails=("bruno@x.pt",), plan=False, chave="inst:I1", agora=AGORA):
        return pe.reconciliar(chave, alvo, "Lixo", "Bruno: é a vez", list(emails), estado, agora, plan, http=http)

    def test_quem_recebe(self):
        self.assertEqual(pe.emails_da_pessoa(CONFIG, "Bruno"), ["bruno@x.pt"])
        self.assertEqual(pe.emails_da_pessoa(CONFIG, ""), ["bruno@x.pt", "camila@x.pt"])          # sem responsável: todas
        self.assertEqual(pe.emails_do_topico(CONFIG, "tarefas_bruno"), ["bruno@x.pt"])
        self.assertEqual(pe.emails_do_topico(CONFIG, "tarefas_camila"), ["camila@x.pt"])
        self.assertEqual(pe.emails_do_topico(CONFIG, None), ["bruno@x.pt", "camila@x.pt"])         # tópico legado: toda a gente

    def test_agenda_uma_vez_e_repetir_nao_duplica(self):
        http, estado = Falso(), {}
        alvo = AGORA + timedelta(hours=2)
        self.assertEqual(self.rec(http, alvo, estado), "agendado")
        m, url, corpo = http.pedidos[0]
        self.assertEqual((m, corpo["modulo"], corpo["entregarEm"]), ("POST", "tarefas", int(alvo.timestamp())))
        self.assertEqual(self.rec(http, alvo, estado), "sem_alteracao")
        self.assertEqual(len(http.pedidos), 1)

    def test_mudar_a_hora_cancela_o_antigo_e_agenda_o_novo(self):
        http, estado = Falso(), {}
        self.rec(http, AGORA + timedelta(hours=2), estado)
        antigo = next(iter(estado["inst:I1"]["chaves"].values()))
        self.assertEqual(self.rec(http, AGORA + timedelta(hours=5), estado), "agendado")
        self.assertEqual([p[0] for p in http.pedidos], ["POST", "DELETE", "POST"])
        self.assertIn(antigo, http.pedidos[1][1])
        self.assertNotEqual(next(iter(estado["inst:I1"]["chaves"].values())), antigo)

    def test_tarefa_feita_cancela(self):
        http, estado = Falso(), {}
        self.rec(http, AGORA + timedelta(hours=2), estado)
        self.assertEqual(self.rec(http, None, estado), "cancelado")
        self.assertEqual(http.pedidos[-1][0], "DELETE")
        self.assertEqual(estado, {})
        self.assertEqual(self.rec(http, None, estado), "sem_alteracao")

    def test_hora_ja_passada_sai_logo_sem_entregar_em(self):
        http, estado = Falso(), {}
        self.rec(http, AGORA - timedelta(minutes=1), estado)
        self.assertNotIn("entregarEm", http.pedidos[0][2])

    def test_falha_nao_guarda_estado_e_repete_no_ciclo_seguinte(self):
        http, estado = Falso(503), {}
        alvo = AGORA + timedelta(hours=1)
        self.assertEqual(self.rec(http, alvo, estado), "falhou")
        self.assertEqual(estado, {})
        http.codigo = 201
        self.assertEqual(self.rec(http, alvo, estado), "agendado")

    def test_fora_do_horizonte_e_plan_only_nao_fazem_pedidos(self):
        http, estado = Falso(), {}
        self.assertEqual(self.rec(http, AGORA + timedelta(days=9), estado), "fora_do_horizonte")
        self.assertEqual(self.rec(http, AGORA + timedelta(hours=1), estado, plan=True), "agendado")
        self.assertEqual((http.pedidos, estado), ([], {}))

    def test_varios_destinatarios_um_evento_cada(self):
        http, estado = Falso(), {}
        self.rec(http, AGORA + timedelta(hours=1), estado, emails=("bruno@x.pt", "camila@x.pt"), chave="piscina:P1")
        self.assertEqual(len(http.pedidos), 2)
        self.assertEqual(len(set(estado["piscina:P1"]["chaves"].values())), 2)

    def test_desligado_sem_configuracao(self):
        self.assertEqual(pe.reconciliar("inst:I1", AGORA + timedelta(hours=1), "t", "c", ["a@b.pt"], {}, AGORA, False), "desligado")


class SemInjecao(TarefasTestCase):
    """O caminho real (sem `http` falso): tem de montar o pedido certo e nunca rebentar."""

    def test_pedido_real_com_cabecalhos_certos(self):
        from unittest import mock
        visto = []

        class R:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def urlopen(req, timeout=0):
            visto.append((req.get_method(), req.full_url, req.get_header("X-pulse-user"), req.get_header("X-pulse-key")))
            return R()
        with mock.patch.dict("os.environ", {"PULSE_EVENTS_URL": "http://127.0.0.1:8897/api/v1/internal/events", "PULSE_SERVICE_KEY": "k" * 40}), \
                mock.patch("urllib.request.urlopen", urlopen):
            estado = {}
            r = pe.reconciliar("inst:I1", AGORA + timedelta(hours=1), "Lixo", "c", ["bruno@x.pt"], estado, AGORA, False)
            self.assertEqual(r, "agendado")
            pe.reconciliar("inst:I1", None, "", "", [], estado, AGORA, False)
        self.assertEqual([v[0] for v in visto], ["POST", "DELETE"])
        self.assertTrue(visto[1][1].startswith("http://127.0.0.1:8897/api/v1/internal/events/tar-"))
        self.assertEqual({v[2] for v in visto}, {"bruno@x.pt"})
        self.assertEqual({v[3] for v in visto}, {"k" * 40})


class DadosDoAviso(TarefasTestCase):
    def test_destino_e_instancia_para_a_app(self):
        self.assertEqual(pe.dados_do_aviso("inst:I42"), {"link": "pulse://tarefas/hoje", "instancia": "I42"})
        self.assertEqual(pe.dados_do_aviso("piscina:P11:tarefas_bruno"), {"link": "pulse://tarefas/piscina"})
        self.assertEqual(pe.dados_do_aviso("horario:Bruno:2031-05-10"), {"link": "pulse://tarefas/horario"})

    def test_o_evento_leva_os_dados(self):
        http, estado = Falso(), {}
        pe.reconciliar("inst:I42", AGORA + timedelta(hours=1), "Lixo", "c", ["bruno@x.pt"], estado, AGORA, False, http=http)
        self.assertEqual(http.pedidos[0][2]["dados"], {"link": "pulse://tarefas/hoje", "instancia": "I42"})


class NtfyPausado(TarefasTestCase):
    def test_pausado_so_para_os_topicos_indicados(self):
        from unittest import mock
        from datetime import timedelta
        import recalcular
        publicados = []
        with mock.patch.dict("os.environ", {"NTFY_PAUSADO_TOPICOS": "tarefas_bruno"}), \
                mock.patch.object(common, "ntfy_publish", lambda **kw: publicados.append(kw["topic"]) or {"id": "m1"}):
            for topico in ("tarefas_bruno", "tarefas_camila"):
                # o mesmo que o wrapper de `_recalcular_sem_lock` faz: tópico pausado → alvo None (não agenda)
                pausado = topico in {t.strip() for t in common.env("NTFY_PAUSADO_TOPICOS").split(",")}
                recalcular.reconciliar_chave("inst:I1:" + topico, None if pausado else AGORA + timedelta(hours=1), "t", "c", None, {}, AGORA, False, topico=topico)
        self.assertEqual(publicados, ["tarefas_camila"])


class DispositivosAtivos(TarefasTestCase):
    def test_sem_resposta_nao_se_sabe(self):
        self.assertIsNone(pe.dispositivos_ativos("a@b.pt"))                                  # desligado
        self.assertEqual(pe.dispositivos_ativos("a@b.pt", http=lambda m, e: 2), 2)

    def test_pedido_real(self):
        from unittest import mock
        visto = []

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ativos": 1}'

        def urlopen(req, timeout=0):
            visto.append((req.full_url, req.get_header("X-pulse-user")))
            return R()
        with mock.patch.dict("os.environ", {"PULSE_EVENTS_URL": "http://127.0.0.1:8897/api/v1/internal/events", "PULSE_SERVICE_KEY": "k" * 40}), \
                mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(pe.dispositivos_ativos("camila@x.pt"), 1)
        self.assertEqual(visto, [("http://127.0.0.1:8897/api/v1/internal/devices/count", "camila@x.pt")])
