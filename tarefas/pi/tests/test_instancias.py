import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import instancias
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient


class OcorreNestaDataTests(unittest.TestCase):
    def test_diaria(self) -> None:
        self.assertTrue(instancias.ocorre_nesta_data({"Recorrencia": "Diaria"}, date(2026, 1, 1), "Qui", 1))

    def test_semanal(self) -> None:
        tarefa = {"Recorrencia": "Semanal", "DiasSemana": "Seg, Qua, Sex"}
        self.assertTrue(instancias.ocorre_nesta_data(tarefa, date.today(), "Seg", 1))
        self.assertFalse(instancias.ocorre_nesta_data(tarefa, date.today(), "Ter", 1))

    def test_mensal(self) -> None:
        tarefa = {"Recorrencia": "Mensal", "DiaMes": 15}
        self.assertTrue(instancias.ocorre_nesta_data(tarefa, date(2026, 3, 15), "Dom", 15))
        self.assertFalse(instancias.ocorre_nesta_data(tarefa, date(2026, 3, 16), "Seg", 16))

    def test_trimestral(self) -> None:
        tarefa = {"Recorrencia": "Trimestral", "DiasSemana": "2026-01-10"}
        self.assertTrue(instancias.ocorre_nesta_data(tarefa, date(2026, 4, 10), "Sex", 10))
        self.assertFalse(instancias.ocorre_nesta_data(tarefa, date(2026, 2, 10), "Ter", 10))

    def test_pontual_nunca_gera_sozinha(self) -> None:
        self.assertFalse(instancias.ocorre_nesta_data({"Recorrencia": "Pontual"}, date.today(), "Seg", 1))


class CalcularResponsavelTests(unittest.TestCase):
    def test_sem_rotacao_usa_pessoa_padrao(self) -> None:
        tarefa = {"ID": "T1", "PessoaPadrao": "Bruno", "RotacaoPessoas": ""}
        self.assertEqual(instancias.calcular_responsavel(tarefa, {}), "Bruno")

    def test_alterna_entre_duas_pessoas(self) -> None:
        tarefa = {"ID": "T1", "PessoaPadrao": "Bruno", "RotacaoPessoas": "Bruno, Ana"}
        contagem: dict[str, int] = {}
        resultado = [instancias.calcular_responsavel(tarefa, contagem) for _ in range(4)]
        self.assertEqual(resultado, ["Bruno", "Ana", "Bruno", "Ana"])


class GerarInstanciasTests(TarefasTestCase):
    def test_gera_para_o_horizonte_configurado_sem_duplicar(self) -> None:
        sheets = FakeSheetsClient({
            "Config": [{"Chave": "DiasAntecedenciaGeracao", "Valor": 2}],
            "Tarefas": [{"ID": "T1", "Nome": "Lavar loiça", "Ativa": "TRUE",
                        "Recorrencia": "Diaria", "RotacaoPessoas": "", "PessoaPadrao": "Bruno"}],
            "Instancias": [],
        })
        n = instancias.gerar_instancias(sheets)
        self.assertEqual(n, 3)  # hoje, +1, +2
        datas = {r["Data"] for r in sheets.read_objects("Instancias")}
        hoje = common.now_local().date()
        self.assertEqual(datas, {(hoje + timedelta(days=d)).isoformat() for d in range(3)})

        # correr outra vez não deve duplicar nenhuma
        n2 = instancias.gerar_instancias(sheets)
        self.assertEqual(n2, 0)
        self.assertEqual(len(sheets.read_objects("Instancias")), 3)

    def test_ignora_tarefas_inativas(self) -> None:
        sheets = FakeSheetsClient({
            "Config": [{"Chave": "DiasAntecedenciaGeracao", "Valor": 0}],
            "Tarefas": [{"ID": "T1", "Nome": "X", "Ativa": "FALSE", "Recorrencia": "Diaria"}],
            "Instancias": [],
        })
        self.assertEqual(instancias.gerar_instancias(sheets), 0)


if __name__ == "__main__":
    unittest.main()
