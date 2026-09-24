import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import recalcular
import servidor
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient


class MarcarFeitaTests(TarefasTestCase):
    def _sheets(self) -> FakeSheetsClient:
        return FakeSheetsClient({
            "Instancias": [{"ID": "I1", "TarefaID": "T1", "Data": "2026-09-23", "Pessoa": "Bruno",
                            "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"}],
            "Config": [], "Tarefas": [], "Piscina": [],
        })

    def test_instanciaId_em_falta(self) -> None:
        self.assertEqual(servidor.handle_marcar_feita(self._sheets(), {}),
                         {"ok": False, "erro": "instanciaId é obrigatório"})

    def test_instancia_inexistente(self) -> None:
        resultado = servidor.handle_marcar_feita(self._sheets(), {"instanciaId": "I999"})
        self.assertEqual(resultado, {"ok": False, "erro": "instância não encontrada"})

    def test_marca_feita_sem_assinatura_chamada_pela_pwa(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_marcar_feita(sheets, {"instanciaId": "I1"})
        self.assertEqual(resultado, {"ok": True})
        inst = sheets.read_objects("Instancias")[0]
        self.assertEqual(inst["Estado"], "Feita")
        self.assertTrue(inst["DataConclusao"])

    def test_assinatura_invalida_da_acao_ntfy_e_rejeitada(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_marcar_feita(sheets, {"instanciaId": "I1", "s": "assinatura-errada"})
        self.assertEqual(resultado, {"ok": False, "erro": "assinatura inválida"})
        self.assertEqual(sheets.read_objects("Instancias")[0]["Estado"], "Pendente")

    def test_assinatura_correta_da_acao_ntfy_e_aceite(self) -> None:
        sheets = self._sheets()
        assinatura = recalcular.assinar_instancia("I1")
        resultado = servidor.handle_marcar_feita(sheets, {"instanciaId": "I1", "s": assinatura})
        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(sheets.read_objects("Instancias")[0]["Estado"], "Feita")


class SnoozeTests(TarefasTestCase):
    def _sheets(self) -> FakeSheetsClient:
        return FakeSheetsClient({
            "Instancias": [{"ID": "I1", "TarefaID": "T1", "Data": "2026-09-23", "Pessoa": "Bruno",
                            "Estado": "Pendente", "NotificacaoEnviada": "TRUE"}],
            "Config": [], "Tarefas": [], "Piscina": [],
        })

    def test_reabre_a_instancia_e_regista_o_snooze(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_snooze(sheets, {"instanciaId": "I1", "minutos": "30"})
        self.assertTrue(resultado["ok"])
        self.assertIn("ate", resultado)
        inst = sheets.read_objects("Instancias")[0]
        self.assertEqual(inst["NotificacaoEnviada"], "FALSE")
        snoozes = recalcular.carregar_snoozes(common.now_local())
        self.assertIn("I1", snoozes)

    def test_assinatura_invalida_e_rejeitada(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_snooze(sheets, {"instanciaId": "I1", "s": "errada"})
        self.assertEqual(resultado, {"ok": False, "erro": "assinatura inválida"})
        self.assertEqual(sheets.read_objects("Instancias")[0]["NotificacaoEnviada"], "TRUE")


class ConfigurarNtfyTests(TarefasTestCase):
    def _sheets(self) -> FakeSheetsClient:
        return FakeSheetsClient({
            "Config": [{"Chave": "Pessoa1_Nome", "Valor": "Bruno"},
                      {"Chave": "Pessoa2_Nome", "Valor": "Ana"}],
        })

    @mock.patch.object(common, "pedir_provisionamento_ntfy")
    def test_cria_as_linhas_quando_ainda_nao_existem(self, pedir) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_configurar_ntfy(
            sheets, {"pessoa": "Bruno", "ntfyUser": "bruno_leitor", "ntfyPassword": "abc123"})
        self.assertTrue(resultado["ok"])
        self.assertIn("tarefas_bruno_leitor", resultado["aviso"])
        pedir.assert_called_once_with("bruno_leitor", "abc123")          # a conta ntfy é criada com o que a app recebeu
        user = sheets.find_config("Pessoa1_NtfyUser")
        senha = sheets.find_config("Pessoa1_NtfyPasswordEnc")
        self.assertEqual(user["Valor"], "bruno_leitor")
        self.assertNotEqual(senha["Valor"], "abc123")  # tem de ir cifrada
        self.assertEqual(common.decrypt(senha["Valor"]), "abc123")

    def test_utilizador_ou_password_invalidos_nao_gravam_nem_pedem_conta(self) -> None:
        sheets = self._sheets()
        with mock.patch.object(common, "pedir_provisionamento_ntfy") as pedir:
            for u, p in (("tarefas-pi", "abc123"), ("Bruno Silva", "abc123"), ("bruno", "curta")):
                self.assertFalse(servidor.handle_configurar_ntfy(sheets, {"pessoa": "Bruno", "ntfyUser": u, "ntfyPassword": p})["ok"])
            pedir.assert_not_called()
        self.assertIsNone(sheets.find_config("Pessoa1_NtfyUser"))

    def test_pessoa_desconhecida_falha(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_configurar_ntfy(
            sheets, {"pessoa": "Alguém", "ntfyUser": "u", "ntfyPassword": "p"})
        self.assertFalse(resultado["ok"])

    def test_campos_em_falta(self) -> None:
        sheets = self._sheets()
        resultado = servidor.handle_configurar_ntfy(sheets, {"pessoa": "Bruno"})
        self.assertFalse(resultado["ok"])


class TestarTests(TarefasTestCase):
    @mock.patch.object(common, "ntfy_publish")
    def test_publica_mensagem_dirigida_a_pessoa(self, publicar) -> None:
        publicar.return_value = {"id": "m1"}
        resultado = servidor.handle_testar(FakeSheetsClient(), {"pessoa": "Bruno"})
        self.assertTrue(resultado["ok"])
        self.assertIn("Bruno", publicar.call_args.kwargs["message"])
        self.assertEqual(publicar.call_args.kwargs.get("click"), servidor.URL_APP)

    @mock.patch.object(common, "ntfy_publish")
    def test_falha_do_ntfy_e_reportada(self, publicar) -> None:
        publicar.return_value = None
        resultado = servidor.handle_testar(FakeSheetsClient(), {"pessoa": "Bruno"})
        self.assertFalse(resultado["ok"])

    def test_pessoa_em_falta(self) -> None:
        resultado = servidor.handle_testar(FakeSheetsClient(), {})
        self.assertFalse(resultado["ok"])


if __name__ == "__main__":
    unittest.main()
