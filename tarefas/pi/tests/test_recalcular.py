import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import recalcular
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient

TZ = common.TZ


class AlvoInstanciaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config: dict = {}
        self.hoje = date(2026, 9, 23)

    def test_none_se_tarefa_inativa(self) -> None:
        tarefa = {"Ativa": "FALSE"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23"}
        self.assertIsNone(recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje, {}))

    def test_none_se_ja_feita(self) -> None:
        tarefa = {"Ativa": "TRUE"}
        inst = {"Estado": "Feita", "Data": "2026-09-23"}
        self.assertIsNone(recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje, {}))

    def test_none_se_ja_notificada(self) -> None:
        tarefa = {"Ativa": "TRUE"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23", "NotificacaoEnviada": "TRUE"}
        self.assertIsNone(recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje, {}))

    def test_usa_hora_da_tarefa(self) -> None:
        tarefa = {"Ativa": "TRUE", "HoraNotificacao": "09:30"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23"}
        alvo = recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje, {})
        self.assertEqual(alvo, datetime(2026, 9, 23, 9, 30, tzinfo=TZ))

    def test_dependencia_por_cumprir_bloqueia(self) -> None:
        tarefa = {"Ativa": "TRUE", "HoraNotificacao": "09:30", "DependeDe": "T0"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23"}
        self.assertIsNone(recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje,
                                                    {"T0": {"Estado": "Pendente"}}))

    def test_dependencia_cumprida_liberta(self) -> None:
        tarefa = {"Ativa": "TRUE", "HoraNotificacao": "09:30", "DependeDe": "T0"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23"}
        alvo = recalcular.alvo_instancia(inst, tarefa, self.config, self.hoje, {"T0": {"Estado": "Feita"}})
        self.assertIsNotNone(alvo)

    def test_nao_incomodar_desloca_para_o_fim_da_janela(self) -> None:
        config = {"NaoIncomodarInicio": "22:00", "NaoIncomodarFim": "08:00"}
        tarefa = {"Ativa": "TRUE", "HoraNotificacao": "23:00"}
        inst = {"Estado": "Pendente", "Data": "2026-09-23"}
        alvo = recalcular.alvo_instancia(inst, tarefa, config, self.hoje, {})
        self.assertEqual(alvo, datetime(2026, 9, 24, 8, 0, tzinfo=TZ))


class ReconciliarChaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agora = datetime(2026, 9, 23, 10, 0, tzinfo=TZ)

    @mock.patch.object(common, "ntfy_publish")
    def test_agenda_quando_nada_agendado(self, publicar) -> None:
        publicar.return_value = {"id": "m1"}
        estado: dict = {}
        alvo = self.agora + timedelta(hours=1)
        resultado = recalcular.reconciliar_chave("inst:I1", alvo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "agendado")
        self.assertEqual(estado["inst:I1"]["message_id"], "m1")
        self.assertEqual(publicar.call_args.kwargs["delay_at"], alvo)

    @mock.patch.object(common, "ntfy_cancel")
    @mock.patch.object(common, "ntfy_publish")
    def test_sem_alteracao_nao_toca_no_ntfy(self, publicar, cancelar) -> None:
        alvo = self.agora + timedelta(hours=1)
        estado = {"inst:I1": {"message_id": "m1", "alvo": alvo.isoformat()}}
        resultado = recalcular.reconciliar_chave("inst:I1", alvo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "sem_alteracao")
        publicar.assert_not_called()
        cancelar.assert_not_called()

    @mock.patch.object(common, "ntfy_cancel")
    @mock.patch.object(common, "ntfy_publish")
    def test_reagenda_quando_a_hora_muda(self, publicar, cancelar) -> None:
        cancelar.return_value = True
        publicar.return_value = {"id": "m2"}
        alvo_antigo = self.agora + timedelta(hours=1)
        alvo_novo = self.agora + timedelta(hours=2)
        estado = {"inst:I1": {"message_id": "m1", "alvo": alvo_antigo.isoformat()}}
        resultado = recalcular.reconciliar_chave("inst:I1", alvo_novo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "reagendado")
        cancelar.assert_called_once_with("m1")
        self.assertEqual(estado["inst:I1"]["message_id"], "m2")

    @mock.patch.object(common, "ntfy_cancel")
    @mock.patch.object(common, "ntfy_publish")
    def test_cancela_quando_deixa_de_ser_aplicavel(self, publicar, cancelar) -> None:
        cancelar.return_value = True
        estado = {"inst:I1": {"message_id": "m1", "alvo": (self.agora + timedelta(hours=1)).isoformat()}}
        resultado = recalcular.reconciliar_chave("inst:I1", None, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "cancelado")
        cancelar.assert_called_once_with("m1")
        self.assertNotIn("inst:I1", estado)

    def test_fora_do_horizonte_nao_agenda(self) -> None:
        estado: dict = {}
        alvo = self.agora + timedelta(days=10)
        resultado = recalcular.reconciliar_chave("inst:I1", alvo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "fora_do_horizonte")
        self.assertEqual(estado, {})

    @mock.patch.object(common, "ntfy_publish")
    def test_entrega_imediata_se_atrasada_e_nunca_agendada(self, publicar) -> None:
        publicar.return_value = {"id": "m9"}
        estado: dict = {}
        alvo = self.agora - timedelta(minutes=5)
        resultado = recalcular.reconciliar_chave("inst:I1", alvo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "entregue")
        self.assertNotIn("inst:I1", estado)
        self.assertIsNone(publicar.call_args.kwargs.get("delay_at"))

    @mock.patch.object(common, "ntfy_cancel")
    @mock.patch.object(common, "ntfy_publish")
    def test_presumivelmente_entregue_nao_republica(self, publicar, cancelar) -> None:
        alvo = self.agora - timedelta(minutes=1)
        estado = {"inst:I1": {"message_id": "m1", "alvo": alvo.isoformat()}}
        resultado = recalcular.reconciliar_chave("inst:I1", alvo, "T", "c", None, estado, self.agora, False)
        self.assertEqual(resultado, "presumivelmente_entregue")
        publicar.assert_not_called()
        cancelar.assert_not_called()
        self.assertNotIn("inst:I1", estado)


class RecalcularIntegrationTests(TarefasTestCase):
    def _sheets(self, **overrides) -> FakeSheetsClient:
        base = {
            "Config": [{"Chave": "HoraPadrao", "Valor": "08:00"}],
            "Tarefas": [{"ID": "T1", "Nome": "Lavar loiça", "Ativa": "TRUE", "HoraNotificacao": "09:00"}],
            "Instancias": [],
            "Piscina": [],
        }
        base.update(overrides)
        return FakeSheetsClient(base)

    @mock.patch.object(common, "ntfy_publish")
    def test_agenda_instancia_pendente_dentro_do_horizonte(self, publicar) -> None:
        publicar.return_value = {"id": "m1"}
        agora = datetime(2026, 9, 23, 7, 0, tzinfo=TZ)
        sheets = self._sheets(Instancias=[
            {"ID": "I1", "TarefaID": "T1", "Data": "2026-09-23", "Pessoa": "Bruno",
             "Estado": "Pendente", "NotificacaoEnviada": "FALSE"},
        ])
        with mock.patch.object(recalcular, "now_local", return_value=agora):
            contagens = recalcular.recalcular(sheets)
        self.assertEqual(contagens.get("agendado"), 1)
        publicar.assert_called_once()
        inst = sheets.read_objects("Instancias")[0]
        self.assertEqual(inst["NotificacaoEnviada"], "FALSE")  # só agendado, ainda por entregar

    @mock.patch.object(common, "ntfy_publish")
    def test_nunca_agenda_alem_do_horizonte_do_ntfy(self, publicar) -> None:
        agora = datetime(2026, 9, 23, 7, 0, tzinfo=TZ)
        sheets = self._sheets(
            Tarefas=[{"ID": "T1", "Nome": "X", "Ativa": "TRUE", "HoraNotificacao": "23:00"}],
            Instancias=[{"ID": "I1", "TarefaID": "T1", "Data": "2026-09-27", "Pessoa": "Bruno",
                        "Estado": "Pendente", "NotificacaoEnviada": "FALSE"}],
        )
        with mock.patch.object(recalcular, "now_local", return_value=agora):
            contagens = recalcular.recalcular(sheets)
        self.assertEqual(contagens.get("fora_do_horizonte"), 1)
        publicar.assert_not_called()

    @mock.patch.object(common, "ntfy_cancel")
    @mock.patch.object(common, "ntfy_publish")
    def test_cancela_quando_tarefa_e_desativada(self, publicar, cancelar) -> None:
        publicar.return_value = {"id": "m1"}
        cancelar.return_value = True
        agora = datetime(2026, 9, 23, 7, 0, tzinfo=TZ)
        sheets = self._sheets(Instancias=[
            {"ID": "I1", "TarefaID": "T1", "Data": "2026-09-23", "Pessoa": "Bruno",
             "Estado": "Pendente", "NotificacaoEnviada": "FALSE"},
        ])
        with mock.patch.object(recalcular, "now_local", return_value=agora):
            recalcular.recalcular(sheets)  # 1ª passagem: agenda
            sheets.tabs["Tarefas"][0]["Ativa"] = "FALSE"
            contagens = recalcular.recalcular(sheets)  # 2ª passagem: deve cancelar
        self.assertEqual(contagens.get("cancelado"), 1)
        cancelar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
