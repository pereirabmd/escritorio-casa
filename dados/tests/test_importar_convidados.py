import unittest

import importar_convidados as ic


class ImportarConvidadosTest(unittest.TestCase):
    def test_opcoes(self):
        fases, estados = ic.opcoes_do_sheets([["1ª fase", "Por convidar"], ["2ª fase", "Convidado"], ["", "Confirmado"], ["1ª FASE", ""]])
        self.assertEqual((fases, estados), (["1ª fase", "2ª fase"], ["Por convidar", "Convidado", "Confirmado"]))

    def test_data_convite(self):
        self.assertEqual(ic.para_data_convite(46281.95880787037), "2026-09-16 23:00:41")
        self.assertEqual(ic.para_data_convite("15/09/2026, 23:00:56"), "2026-09-15 23:00:56")
        self.assertEqual(ic.para_data_convite(""), "")
        self.assertIsNone(ic.para_data_convite("lixo"))

    def test_preparar_regras_da_pwa(self):
        linhas = [
            ["Ana e Rui", 2, 2, "1ª fase", "Confirmado", "alergia #mesa:7", "", "912 345 678", 46281.5],   # mesa legada -> coluna Mesa
            ["", "", "", "", "Por convidar"],                                                             # resto de modelo: ignora
            ["Sem estado certo", "3", "1", "2ª fase", "Convidado", "", "4"],                               # mesa mas não Confirmado
            ["Tel esquisito", 1, 0, "", "Por convidar", "", "", "Tel: 912abc"],
            ["Mesa lixo", 1, 0, "", "Confirmado", "", "99"],
            ["Data má", 1, 0, "", "Por convidar", "", "", "", "ontem"],
        ]
        gs, sem_nome, avisos, prob = ic.preparar(linhas)
        self.assertEqual([g["nome"] for g in gs], ["Ana e Rui", "Sem estado certo", "Tel esquisito", "Mesa lixo", "Data má"])
        self.assertEqual(sem_nome, 1)
        a = gs[0]
        self.assertEqual((a["mesa"], a["notas"], a["dataConvite"][:10], a["linha"]), ("7", "alergia", "2026-09-16", 2))
        self.assertEqual(gs[1]["mesa"], "")           # não Confirmado: larga a mesa
        self.assertEqual(gs[1]["pessoas"], 3)         # "3" (texto) -> 3
        self.assertEqual(gs[2]["telefone"], "912")    # sanitizado
        self.assertEqual(gs[3]["mesa"], "")           # mesa inválida ignorada
        self.assertEqual(gs[4]["dataConvite"], "")
        self.assertEqual(len(prob), 3)
        self.assertTrue(any("formato antigo" in x for x in avisos) and any("não Confirmado" in x for x in avisos))

    def test_qualidade(self):
        gs = [{"nome": "A", "pessoas": 6, "confirmados": 7, "fase": "X", "estado": "Confirmado", "mesa": "1"},
              {"nome": "a", "pessoas": 6, "confirmados": 0, "fase": "1ª fase", "estado": "", "mesa": "1"}]
        texto = " | ".join(ic.qualidade(gs, ["1ª fase"], ["Confirmado"]))
        for esperado in ("repetido", "confirmados >", "não está na lista de Fases", "sem estado", "capacidade 10"):
            self.assertIn(esperado, texto)


if __name__ == "__main__":
    unittest.main()
