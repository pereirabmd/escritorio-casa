import unittest

import importar_rto as ir


class ImportarRtoTest(unittest.TestCase):
    def test_para_data(self):
        self.assertEqual(ir.para_data(46023), "2026-01-01")
        self.assertEqual(ir.para_data("2026-01-02"), "2026-01-02")
        self.assertEqual(ir.para_data("26/06/2026"), "2026-06-26")
        self.assertIsNone(ir.para_data("31/02/2026"))
        self.assertIsNone(ir.para_data("lixo"))
        self.assertIsNone(ir.para_data(""))

    def test_dias(self):
        dias, sem, prob = ir.preparar_dias([[46023, ""], [46024, "C"], [46025, "t"], [46026, "X"], [46024, "T"], ["lixo", "T"]])
        self.assertEqual(dias, {"2026-01-02": "T", "2026-01-03": "T"})   # 46024 repetido: fica o último
        self.assertEqual(sem, 1)
        textos = " | ".join(m for _, m in prob)
        for esperado in ("minúscula", "desconhecida", "repetida", "ilegível"):
            self.assertIn(esperado, textos)

    def test_notas(self):
        linhas = [[46031, 46031, "Ferias", "x"], [], ["26/06/2026", "14/07/2026", "Férias", ""], ["14/07/2026", "26/06/2026", "Ferias"],
                  ["lixo", "", "Cat", ""], ["", "", "", ""]]
        notas, vazias, prob = ir.preparar_notas(linhas)
        self.assertEqual([n["linha"] for n in notas], [2, 4, 6])
        self.assertEqual(notas[1]["dataInicio"], "2026-06-26")
        self.assertEqual(vazias, 2)
        self.assertEqual(len(prob), 2)   # intervalo invertido (nota ignorada) + data ilegível (a nota fica, só com categoria)

    def test_qualidade(self):
        dias = {"2026-01-03": "T", "2026-01-05": "C"}     # sábado + segunda
        notas = [{"dataInicio": "2026-01-05", "dataFim": "2026-01-06", "categoria": "Férias", "descricao": ""},
                 {"dataInicio": "2026-02-02", "dataFim": "2026-02-02", "categoria": "Astreinte", "descricao": ""},
                 {"dataInicio": "2026-02-02", "dataFim": "2026-02-02", "categoria": "astreinte", "descricao": ""}]
        texto = " | ".join(ir.qualidade(dias, notas))
        for esperado in ("fim de semana", "dentro de Férias", "duplicada"):
            self.assertIn(esperado, texto)


if __name__ == "__main__":
    unittest.main()
