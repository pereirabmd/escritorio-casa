import os
import shutil
import tempfile
import unittest
from pathlib import Path

# o importador usa o `common` do bilhetes_cp: apontá-lo para o repositório e para uma pasta temporária
_REPO = Path(__file__).resolve().parents[2] / "bilhetes_cp"
_TMP = tempfile.mkdtemp(prefix="imp_bilhetes_")
shutil.copytree(_REPO / "config", Path(_TMP) / "config", ignore=shutil.ignore_patterns("service-account.json"))
os.environ["BILHETES_CP_SCRIPTS"] = str(_REPO / "scripts")
os.environ["BILHETES_CP_HOME"] = _TMP
os.environ.setdefault("TZ", "Europe/Lisbon")

import importar_bilhetes as ib  # noqa: E402


class ImportarBilhetesTest(unittest.TestCase):
    def test_viagens_mantem_o_numero_da_linha_como_id_e_ignora_notas(self):
        snap = {"first_row": 12, "weekly": [
            ["2026-09-24", "Lisboa Oriente", "Aveiro", 731, "17:30", "SIM"],
            ["^ linha de exemplo (comboios/horas fictícios) — apagar/substituir", "", "", "", "", ""],
            ["", "", "", "", "", ""],
            [46289, "Aveiro", "Lisboa Oriente", 520.0, 0.28125, "NAO"],          # serial de data e fração de dia (07:30 -> 06:45?)
            ["2026-09-30", "Aveiro", "", 520, "06:45", "SIM"],                     # incompleta e ATIVA: nunca calada
        ]}
        v, ign = ib.preparar_viagens(snap)
        self.assertEqual([x["id"] for x in v], [12, 15])
        self.assertEqual((v[0]["data"], v[0]["comboio"], v[0]["hora"], v[0]["ativo"]), ("2026-09-24", 731, "17:30", "SIM"))
        self.assertEqual((v[1]["comboio"], v[1]["hora"], v[1]["ativo"]), (520, "06:45", "NAO"))
        self.assertEqual([r for r, _ in ign], [13, 16])
        self.assertIn("ATIVA", ign[1][1])

    def test_compras_pedidos_e_logs(self):
        c, ign = ib.preparar_compras([["2026-09-24", 731, "Lisboa Oriente", "Aveiro", "17:39", 22, 105, "CP-X"], [], ["lixo", 1]])
        self.assertEqual(c, [{"data": "2026-09-24", "comboio": 731, "origem": "Lisboa Oriente", "destino": "Aveiro",
                              "hora": "17:39", "carruagem": "22", "lugar": "105", "referencia": "CP-X"}])
        self.assertEqual(len(ign), 1)
        p, _ = ib.preparar_pedidos([[], ["2026-09-30", "A", "B", 731, "17:30", "SIM", "SIM", 20, "NAO", "ESGOTADO", "", "", "msg"]])
        self.assertEqual((p[0]["id"], p[0]["retry"], p[0]["intervalo"], p[0]["estado"]), (6, "SIM", 20, "ESGOTADO"))   # id = linha (5 + 1)
        self.assertEqual(len(ib.preparar_logs([["2026-09-22T01:39:01.723+01:00", "PREFLIGHT", "2026-09-22", "ida", "521", "", "OK"], []])), 1)

    def test_passe(self):
        ultima, validade, expira = ib.preparar_passe({"passe": ["2026-09-21", 29, 46315, 26]})
        self.assertEqual((ultima.isoformat(), validade, expira.isoformat()), ("2026-09-21", 29, "2026-10-20"))


if __name__ == "__main__":
    unittest.main()
