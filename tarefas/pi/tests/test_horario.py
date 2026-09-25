import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import horario
import recalcular
from tests.fakes import FakeSheetsClient

TZ = common.TZ


def aula(dia, ini, fim, disc, sala="B7", aluno="Bruno", ano="2026/2027"):
    return {"Aluno": aluno, "AnoLetivo": ano, "DiaSemana": dia, "HoraInicio": ini, "HoraFim": fim, "Disciplina": disc, "Sala": sala}


HORARIO = [aula(1, "11:35", "12:25", "C.D."), aula(1, "11:35", "12:25", "TIC", "INF"), aula(1, "12:35", "13:25", "E.MUS", "CEM"),
           aula(2, "16:35", "17:25", "DT")]


class UltimaAulaTests(unittest.TestCase):
    def test_ultima_e_a_que_acaba_mais_tarde(self):
        fim, u = horario.ultima_aula(HORARIO, "Bruno", date(2026, 9, 28))     # 2.ª feira
        self.assertEqual((fim, [a["Disciplina"] for a in u]), ("13:25", ["E.MUS"]))

    def test_turma_dividida_conta_as_duas(self):
        h = [aula(3, "11:35", "12:25", "ED-TEC"), aula(3, "11:35", "12:25", "OUTRA")]
        fim, u = horario.ultima_aula(h, "Bruno", date(2026, 9, 30))
        self.assertEqual((fim, len(u)), ("12:25", 2))

    def test_sem_aulas_fim_de_semana_e_fora_do_ano(self):
        self.assertIsNone(horario.ultima_aula(HORARIO, "Bruno", date(2026, 9, 26)))       # sábado
        self.assertIsNone(horario.ultima_aula(HORARIO, "Bruno", date(2026, 8, 31)))       # antes do ano letivo
        self.assertIsNone(horario.ultima_aula(HORARIO, "Bruno", date(2027, 8, 2)))        # depois
        self.assertIsNotNone(horario.ultima_aula(HORARIO, "Bruno", date(2027, 6, 28)))

    def test_emr_nao_conta_e_avisa_pela_aula_anterior(self):
        h = [aula(5, "15:35", "16:25", "C-NAT"), aula(5, "16:35", "17:25", "E.M.R.", "B1")]
        fim, u = horario.ultima_aula(h, "Bruno", date(2026, 9, 25))           # 6.ª feira
        self.assertEqual((fim, [a["Disciplina"] for a in u]), ("16:25", ["C-NAT"]))
        self.assertIsNone(horario.ultima_aula([aula(5, "16:35", "17:25", "E.M.R.")], "Bruno", date(2026, 9, 25)))

    def test_alvo_30_min_antes(self):
        self.assertEqual(horario.alvo_aviso("13:25", date(2026, 9, 28), 30), datetime(2026, 9, 28, 12, 55, tzinfo=TZ))


class ReconciliarTests(unittest.TestCase):
    def correr(self, agora, estado=None, config=None, aulas=HORARIO):
        store = FakeSheetsClient({"Horario": [dict(a, _rowIndex=i + 2) for i, a in enumerate(aulas)]})
        estado = {} if estado is None else estado
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m1"}) as pub, \
                mock.patch.object(common, "ntfy_cancel") as canc:
            res = horario.reconciliar(store, config or {}, estado, agora, False, recalcular.reconciliar_chave, "http://x", dias=1)
        return res, estado, pub, canc

    def test_agenda_para_amanha_e_hoje_se_ainda_vai_a_tempo(self):
        agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)                    # 2.ª feira 08:00
        res, estado, pub, _ = self.correr(agora)
        self.assertEqual(res, ["agendado", "agendado"])                   # hoje (12:55) e amanhã (16:55)
        alvos = sorted(v["alvo"] for v in estado.values())
        self.assertTrue(alvos[0].startswith("2026-09-28T12:55"), alvos)
        self.assertTrue(alvos[1].startswith("2026-09-29T16:55"), alvos)
        self.assertIn("13:25", pub.call_args_list[0].kwargs["title"])

    def test_nao_avisa_tarde(self):
        res, estado, pub, _ = self.correr(datetime(2026, 9, 28, 13, 0, tzinfo=TZ))
        self.assertEqual(res, ["agendado"])                               # só amanhã
        pub.assert_called_once()

    def test_click_abre_o_dia_do_aviso(self):
        _, estado, pub, _ = self.correr(datetime(2026, 9, 28, 8, 0, tzinfo=TZ))
        self.assertEqual([c.kwargs["click"] for c in pub.call_args_list], ["http://x/1", "http://x/2"])   # 2.ª e 3.ª feira

    def test_segunda_passagem_nao_repete(self):
        agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)
        _, estado, _, _ = self.correr(agora)
        res, _, pub, _ = self.correr(agora, estado=estado)
        self.assertEqual(res, ["sem_alteracao", "sem_alteracao"])
        pub.assert_not_called()

    def test_pausar_cancela(self):
        agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)
        _, estado, _, _ = self.correr(agora)
        res, estado, _, canc = self.correr(agora, estado=estado, config={"HorarioAvisos": "FALSE"})
        self.assertEqual(sorted(res), ["cancelado", "cancelado"])
        self.assertEqual(estado, {})

    def test_horario_apagado_cancela_o_que_estava_agendado(self):
        agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)
        _, estado, _, _ = self.correr(agora)
        res, estado, _, canc = self.correr(agora, estado=estado, aulas=[])
        self.assertEqual(canc.call_count, 2)
        self.assertEqual(estado, {})


CFG = {"Pessoa1_Nome": "Bruno", "Pessoa1_NtfyUser": "tarefas_bruno", "Pessoa2_Nome": "Camila", "Pessoa2_NtfyUser": "tarefas_camila"}


class DestinatariosTests(unittest.TestCase):
    def test_padrao_ninguem_e_lista(self):
        self.assertEqual(common.destinatarios_geral(CFG, "piscina", ["Bruno", "Camila"]), ["Bruno", "Camila"])
        self.assertEqual(common.destinatarios_geral({**CFG, "Notif_piscina": "-"}, "piscina", ["Bruno"]), [])
        self.assertEqual(common.destinatarios_geral({**CFG, "Notif_piscina": "Camila,Fantasma"}, "piscina", ["Bruno"]), ["Camila"])

    def test_topicos(self):
        self.assertEqual(common.topicos_de(CFG, ["Camila", "Bruno"]), ["tarefas_bruno", "tarefas_camila"])
        semuser = {"Pessoa1_Nome": "Bruno", "Pessoa2_Nome": "Camila", "Pessoa2_NtfyUser": "camila"}
        self.assertEqual(common.topicos_de(semuser, ["Bruno", "Camila"]), ["tarefas_camila"])   # quem não tem utilizador fica de fora
        self.assertEqual(common.topicos_de(semuser, ["Bruno"]), [None])                          # ninguém tem: tópico legado
        self.assertEqual(common.topicos_de(CFG, []), [])


class HorarioDestinatariosTests(unittest.TestCase):
    agora = datetime(2026, 9, 28, 8, 0, tzinfo=TZ)

    def correr(self, config, estado):
        store = FakeSheetsClient({"Horario": [dict(a, _rowIndex=i + 2) for i, a in enumerate(HORARIO)]})
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m"}) as pub, mock.patch.object(common, "ntfy_cancel") as canc:
            horario.reconciliar(store, config, estado, self.agora, False, recalcular.reconciliar_chave, "http://x", dias=0)
        return pub, canc

    def test_por_omissao_so_a_pessoa_do_aluno(self):
        estado = {}
        pub, _ = self.correr(CFG, estado)
        self.assertEqual([c.kwargs["topic"] for c in pub.call_args_list], ["tarefas_bruno"])

    def test_admin_escolhe_varios_e_depois_retira(self):
        estado = {}
        pub, _ = self.correr({**CFG, "Notif_horario": "Bruno,Camila"}, estado)
        self.assertEqual(sorted(c.kwargs["topic"] for c in pub.call_args_list), ["tarefas_bruno", "tarefas_camila"])
        pub, canc = self.correr({**CFG, "Notif_horario": "Bruno"}, estado)          # tira a Camila
        pub.assert_not_called()
        canc.assert_called_once()
        self.assertEqual(list(estado), ["horario:Bruno:2026-09-28:tarefas_bruno"])

    def test_ninguem_cancela_tudo(self):
        estado = {}
        self.correr(CFG, estado)
        _, canc = self.correr({**CFG, "Notif_horario": "-"}, estado)
        canc.assert_called_once()
        self.assertEqual(estado, {})


if __name__ == "__main__":
    unittest.main()
