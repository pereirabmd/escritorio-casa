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


if __name__ == "__main__":
    unittest.main()
