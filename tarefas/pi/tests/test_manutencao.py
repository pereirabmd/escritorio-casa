import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import manutencao
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient


class LimparHistoricoAntigoTests(TarefasTestCase):
    def test_apaga_so_as_concluidas_ha_mais_de_90_dias(self) -> None:
        hoje = common.now_local().date()
        antiga = (hoje - timedelta(days=manutencao.DIAS_RETER_HISTORICO + 5)).isoformat()
        recente = (hoje - timedelta(days=1)).isoformat()
        sheets = FakeSheetsClient({"Instancias": [
            {"ID": "I1", "Data": antiga, "Estado": "Feita"},
            {"ID": "I2", "Data": antiga, "Estado": "Pendente"},  # antiga mas ainda não concluída: fica
            {"ID": "I3", "Data": recente, "Estado": "Saltada"},  # concluída mas recente: fica
        ]})
        n = manutencao.limpar_historico_antigo(sheets)
        self.assertEqual(n, 1)
        ids_restantes = {r["ID"] for r in sheets.read_objects("Instancias")}
        self.assertEqual(ids_restantes, {"I2", "I3"})

    def test_plan_only_nao_apaga_nada(self) -> None:
        hoje = common.now_local().date()
        antiga = (hoje - timedelta(days=manutencao.DIAS_RETER_HISTORICO + 5)).isoformat()
        sheets = FakeSheetsClient({"Instancias": [{"ID": "I1", "Data": antiga, "Estado": "Feita"}]})
        n = manutencao.limpar_historico_antigo(sheets, plan_only=True)
        self.assertEqual(n, 1)
        self.assertEqual(len(sheets.read_objects("Instancias")), 1)


class LimparSubscricoesInativasTests(TarefasTestCase):
    def test_sem_efeito_se_a_aba_ja_nao_existir(self) -> None:
        sheets = FakeSheetsClient({})  # já renomeada/removida
        self.assertEqual(manutencao.limpar_subscricoes_inativas(sheets), 0)

    def test_apaga_inativas_antigas(self) -> None:
        hoje = common.now_local().date()
        antiga = (hoje - timedelta(days=manutencao.DIAS_RETER_SUBSCRICOES_INATIVAS + 5)).isoformat()
        sheets = FakeSheetsClient({"Subscriptions": [
            {"Pessoa": "Bruno", "Criada": antiga, "Ativa": "FALSE"},
            {"Pessoa": "Ana", "Criada": antiga, "Ativa": "TRUE"},  # ainda ativa: fica
        ]})
        n = manutencao.limpar_subscricoes_inativas(sheets)
        self.assertEqual(n, 1)
        self.assertEqual(len(sheets.read_objects("Subscriptions")), 1)


class ManutencaoOrquestracaoTests(TarefasTestCase):
    def test_devolve_as_duas_contagens(self) -> None:
        sheets = FakeSheetsClient({"Instancias": [], "Subscriptions": []})
        resultado = manutencao.manutencao(sheets)
        self.assertEqual(resultado, {"instancias_apagadas": 0, "subscricoes_apagadas": 0})


if __name__ == "__main__":
    unittest.main()
