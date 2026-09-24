import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import recalcular

TZ = common.TZ
CONFIG = {"Pessoa1_Nome": "Bruno", "Pessoa1_NtfyUser": "tarefas_bruno", "Pessoa2_Nome": "Camila", "Pessoa2_NtfyUser": "Camila",
          "Pessoa3_Nome": "Visita"}


class TopicoDaPessoaTests(unittest.TestCase):
    def test_convencao_tarefas_utilizador(self):
        self.assertEqual(common.topico_da_pessoa(CONFIG, "Bruno"), "tarefas_bruno")     # já vem com o prefixo
        self.assertEqual(common.topico_da_pessoa(CONFIG, "Camila"), "tarefas_camila")   # só o utilizador: acrescenta o prefixo

    def test_sem_utilizador_ou_pessoa_desconhecida_usa_o_legado(self):
        self.assertIsNone(common.topico_da_pessoa(CONFIG, "Visita"))
        self.assertIsNone(common.topico_da_pessoa(CONFIG, "Outra"))
        self.assertIsNone(common.topico_da_pessoa(CONFIG, ""))

    def test_utilizador_com_caracteres_estranhos_nao_gera_topico(self):
        self.assertIsNone(common.topico_da_pessoa({"Pessoa1_Nome": "X", "Pessoa1_NtfyUser": "a/b c"}, "X"))


class ReconciliarComTopicoTests(unittest.TestCase):
    agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)
    alvo = agora + timedelta(hours=5)

    def correr(self, estado, topico):
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "novo"}) as pub, \
                mock.patch.object(common, "ntfy_cancel") as canc:
            r = recalcular.reconciliar_chave("k", self.alvo, "t", "c", None, estado, self.agora, False, topico=topico)
        return r, pub, canc

    def test_agenda_no_topico_da_pessoa_e_guarda_o_topico(self):
        estado = {}
        r, pub, _ = self.correr(estado, "tarefas_camila")
        self.assertEqual((r, pub.call_args.kwargs["topic"], estado["k"]["topico"]), ("agendado", "tarefas_camila", "tarefas_camila"))

    def test_mesmo_topico_nao_repete(self):
        estado = {"k": {"message_id": "m1", "alvo": self.alvo.isoformat(), "topico": "tarefas_camila"}}
        r, pub, canc = self.correr(estado, "tarefas_camila")
        self.assertEqual(r, "sem_alteracao")
        pub.assert_not_called(); canc.assert_not_called()

    def test_mudar_de_topico_cancela_no_antigo_e_reagenda_no_novo(self):
        estado = {"k": {"message_id": "m1", "alvo": self.alvo.isoformat()}}          # agendado no legado (sem "topico")
        r, pub, canc = self.correr(estado, "tarefas_camila")
        self.assertEqual(r, "reagendado")
        canc.assert_called_once_with("m1", "tarefas")
        self.assertEqual(pub.call_args.kwargs["topic"], "tarefas_camila")
        self.assertEqual(estado["k"]["message_id"], "novo")

    def test_cancelar_usa_o_topico_guardado(self):
        estado = {"k": {"message_id": "m1", "alvo": self.alvo.isoformat(), "topico": "tarefas_bruno"}}
        with mock.patch.object(common, "ntfy_cancel") as canc:
            recalcular.reconciliar_chave("k", None, "", "", None, estado, self.agora, False)
        canc.assert_called_once_with("m1", "tarefas_bruno")


class ClickTests(unittest.TestCase):
    agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)
    alvo = agora + timedelta(hours=5)

    def test_url_por_separador(self):
        self.assertTrue(recalcular.url_tab("horario").endswith("/tarefas/#horario"))
        self.assertTrue(recalcular.url_tab("hoje").endswith("#hoje"))

    def test_mudar_o_click_reagenda_e_o_estado_guarda_o_click(self):
        estado = {"k": {"message_id": "m1", "alvo": self.alvo.isoformat(), "topico": "tarefas"}}      # estado antigo, sem click
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "novo"}) as pub, mock.patch.object(common, "ntfy_cancel") as canc:
            r = recalcular.reconciliar_chave("k", self.alvo, "t", "c", None, estado, self.agora, False, click="http://x/#hoje")
            self.assertEqual(r, "reagendado")
            canc.assert_called_once()
            self.assertEqual((pub.call_args.kwargs["click"], estado["k"]["click"]), ("http://x/#hoje",) * 2)
            self.assertEqual(recalcular.reconciliar_chave("k", self.alvo, "t", "c", None, estado, self.agora, False, click="http://x/#hoje"), "sem_alteracao")


if __name__ == "__main__":
    unittest.main()
