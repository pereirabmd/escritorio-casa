import unittest

import importar_peso as ip


class ImportarPesoTest(unittest.TestCase):
    def test_serial_para_quando(self):
        self.assertEqual(ip.para_quando(46000.3125), "2025-12-09 07:30:00")
        self.assertEqual(ip.para_quando("2026-04-15 16:49"), "2026-04-15 16:49:00")
        self.assertIsNone(ip.para_quando("lixo"))
        self.assertIsNone(ip.para_quando(""))

    def test_preparar_separa_validos_vazias_e_problemas(self):
        linhas = [[46000.3125, 90.5, "a"], ["", "", ""], ["x", 80, ""], [46001.5, 0, ""], [46002.5, 99999, ""], [46003.5, 88.0]]
        validos, problemas, vazias = ip.preparar(linhas)
        self.assertEqual([v["cid"] for v in validos], ["imp-000002", "imp-000007"])
        self.assertEqual(vazias, 1)
        self.assertEqual([n for n, _ in problemas], [4, 5, 6])

    def test_qualidade_deteta_duplicados_saltos_lacunas(self):
        def r(l, q, p): return {"linha": l, "quando": q, "peso": p, "nota": "", "cid": f"imp-{l:06d}"}
        vs = [r(2, "2026-01-01 08:00:00", 100), r(3, "2026-01-01 08:00:00", 100),
              r(4, "2026-01-02 08:00:00", 108), r(5, "2026-02-01 08:00:00", 107), r(6, "2026-01-15 08:00:00", 20)]
        texto = " | ".join(ip.qualidade(vs))
        for esperado in ("duplicado exato", "salto de", "lacuna de", "fora de ordem", "peso improvável"):
            self.assertIn(esperado, texto)

    def test_normaliza_atividade_como_a_pwa(self):
        self.assertEqual(ip.normaliza_atividade(46024), 1.2)   # data convertida pelo Sheets
        self.assertEqual(ip.normaliza_atividade(2), 1.45)
        self.assertEqual(ip.normaliza_atividade(1.46), 1.45)
        self.assertEqual(ip.normaliza_atividade(""), 1.2)

    def test_config(self):
        cfg, probs = ip.config_do_sheets([[190], [30000], ["M"], [95], [46024], [1], [92], [97]])
        self.assertEqual(cfg["atividade"], "1.2")
        self.assertEqual(cfg["sexo"], "M")
        self.assertEqual(len(probs), 1)


if __name__ == "__main__":
    unittest.main()
