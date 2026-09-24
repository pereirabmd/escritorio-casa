"""Os importadores do bilhetes_cp e das tarefas usam, cada um, o `common.py` do respetivo projeto do Pi — dois módulos com o
mesmo nome que não podem coexistir no mesmo processo. Por isso cada conjunto de verificações corre num processo à parte."""

import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class ImportadoresTest(unittest.TestCase):
    def _correr(self, modulo: str):
        r = subprocess.run([sys.executable, "-m", "unittest", f"tests.isolados.{modulo}"], cwd=RAIZ,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_importar_bilhetes(self):
        self._correr("verificacoes_importar_bilhetes")

    def test_importar_tarefas(self):
        self._correr("verificacoes_importar_tarefas")


if __name__ == "__main__":
    unittest.main()
