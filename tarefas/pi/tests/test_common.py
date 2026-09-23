import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
from tests.base import TarefasTestCase


class NormalizarHoraTests(unittest.TestCase):
    def test_vazio(self) -> None:
        self.assertEqual(common.normalizar_hora(""), "")
        self.assertEqual(common.normalizar_hora(None), "")

    def test_texto(self) -> None:
        self.assertEqual(common.normalizar_hora("20:10"), "20:10")
        self.assertEqual(common.normalizar_hora("8:05"), "08:05")

    def test_texto_invalido(self) -> None:
        self.assertEqual(common.normalizar_hora("não é hora"), "")
        self.assertEqual(common.normalizar_hora("25:10"), "")

    def test_fracao_de_dia(self) -> None:
        # a Sheet devolve uma hora "12:00" escrita via USER_ENTERED como 0.5
        # (ver PROJECT-CONTEXT.md — bug real de comparar isto como texto)
        self.assertEqual(common.normalizar_hora(0.5), "12:00")
        self.assertEqual(common.normalizar_hora(0.0), "00:00")

    def test_fora_do_intervalo(self) -> None:
        self.assertEqual(common.normalizar_hora(1.0), "")
        self.assertEqual(common.normalizar_hora(-0.1), "")


class ParseSheetDateTests(unittest.TestCase):
    def test_iso(self) -> None:
        self.assertEqual(common.parse_sheet_date("2026-09-24").isoformat(), "2026-09-24")

    def test_serial(self) -> None:
        # 1899-12-30 + 1 dia = 1899-12-31
        self.assertEqual(common.parse_sheet_date(1).isoformat(), "1899-12-31")

    def test_vazio_ou_invalido(self) -> None:
        self.assertIsNone(common.parse_sheet_date(""))
        self.assertIsNone(common.parse_sheet_date("não é data"))


class FernetTests(TarefasTestCase):
    def test_roundtrip(self) -> None:
        cifrado = common.encrypt("senha-super-secreta")
        self.assertNotIn("senha-super-secreta", cifrado)
        self.assertEqual(common.decrypt(cifrado), "senha-super-secreta")


class FileLockTests(TarefasTestCase):
    def test_segunda_tentativa_falha_sem_esperar(self) -> None:
        l1 = common.FileLock("teste")
        self.assertTrue(l1.acquire(timeout_s=0))
        l2 = common.FileLock("teste")
        self.assertFalse(l2.acquire(timeout_s=0))
        l1.release()
        self.assertTrue(l2.acquire(timeout_s=0))
        l2.release()


if __name__ == "__main__":
    unittest.main()
