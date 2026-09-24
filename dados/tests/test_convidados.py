import unittest

from tests.test_api import ApiBase


class ConvidadosApiTest(ApiBase):
    def opcoes(self):
        return self.pedir("PUT", "/convidados/opcoes", {"fases": ["1ª fase", "2ª fase"],
                                                          "estados": ["Por convidar", "Convidado", "Confirmado", "Recusado"]})

    def novo(self, **kw):
        base = {"nome": "Ana e Rui", "pessoas": 2, "fase": "1ª fase", "estado": "Por convidar"}
        base.update(kw)
        s, b, _ = self.pedir("POST", "/convidados/lista", base)
        self.assertEqual(s, 201, b)
        return b

    def test_acesso(self):
        self.assertEqual(self.pedir("GET", "/convidados/dados", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/convidados/dados", token=None)[0], 401)

    def test_opcoes_e_dados(self):
        s, b, _ = self.opcoes()
        self.assertEqual((s, b["fases"], b["estados"][2]), (200, ["1ª fase", "2ª fase"], "Confirmado"))
        _, d, _ = self.pedir("GET", "/convidados/dados")
        self.assertEqual(d["fases"], ["1ª fase", "2ª fase"])
        # substituir só as fases não mexe nos estados
        self.pedir("PUT", "/convidados/opcoes", {"fases": ["única"]})
        _, d, _ = self.pedir("GET", "/convidados/dados")
        self.assertEqual((d["fases"], len(d["estados"])), (["única"], 4))

    def test_opcoes_validacao(self):
        for corpo in ({}, {"fases": []}, {"fases": ["a", "A"]}, {"fases": [""]}, {"fases": "x"}, {"extra": 1},
                      {"estados": ["Por convidar", "Convidado"]},          # falta Confirmado
                      {"estados": ["Confirmado", "Outro"]},                 # falta Convidado
                      {"fases": [f"f{i}" for i in range(51)]}, {"fases": ["x" * 61]}):
            self.assertEqual(self.pedir("PUT", "/convidados/opcoes", corpo)[0], 400, corpo)

    def test_crud_e_dados(self):
        g = self.novo(notas=" olá ", telefone="+351 912 345 678")
        self.assertEqual((g["nome"], g["notas"], g["mesa"], g["dataConvite"], g["confirmados"]), ("Ana e Rui", "olá", "", "", 0))
        s, g2, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"nome": "Ana, Rui e Bebé", "pessoas": 3})
        self.assertEqual((s, g2["nome"], g2["pessoas"], g2["telefone"]), (200, "Ana, Rui e Bebé", 3, "+351 912 345 678"))  # só os enviados mudam
        _, d, _ = self.pedir("GET", "/convidados/dados")
        self.assertIn(g["id"], [x["id"] for x in d["convidados"]])
        s, apagado, _ = self.pedir("DELETE", f"/convidados/lista/{g['id']}")
        self.assertEqual((s, apagado["id"]), (200, g["id"]))
        self.assertEqual(self.pedir("DELETE", f"/convidados/lista/{g['id']}")[0], 404)
        self.assertEqual(self.pedir("PUT", f"/convidados/lista/{g['id']}", {"nome": "x"})[0], 404)
        self.assertGreater(self.novo()["id"], g["id"])     # ids nunca são reutilizados

    def test_regra_so_confirmados_tem_mesa(self):
        g = self.novo(estado="Por convidar", mesa="3")
        self.assertEqual(g["mesa"], "")                                                     # criar sem ser Confirmado: mesa larga-se
        s, c, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"estado": "Confirmado", "mesa": "3", "confirmados": 2})
        self.assertEqual((c["estado"], c["mesa"]), ("Confirmado", "3"))
        s, c, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"notas": "só notas"})   # outros campos não mexem na mesa
        self.assertEqual(c["mesa"], "3")
        s, c, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"estado": "Recusado"})  # mudar o estado larga a mesa
        self.assertEqual((c["estado"], c["mesa"]), ("Recusado", ""))
        s, c, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"mesa": "5"})           # mesa sem estar Confirmado: ignorada
        self.assertEqual(c["mesa"], "")

    def test_convite_regista_hora_do_servidor(self):
        g = self.novo()
        s, r, _ = self.pedir("POST", f"/convidados/lista/{g['id']}/convite", {})
        self.assertEqual(s, 200)
        self.assertRegex(r["dataConvite"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        _, d, _ = self.pedir("GET", "/convidados/dados")
        self.assertEqual([x["dataConvite"] for x in d["convidados"] if x["id"] == g["id"]], [r["dataConvite"]])
        # a data do convite não se escreve pelo formulário e sobrevive a edições
        self.assertEqual(self.pedir("PUT", f"/convidados/lista/{g['id']}", {"dataConvite": "2020-01-01 00:00:00"})[0], 400)
        s, e, _ = self.pedir("PUT", f"/convidados/lista/{g['id']}", {"notas": "x"})
        self.assertEqual(e["dataConvite"], r["dataConvite"])
        self.assertEqual(self.pedir("POST", "/convidados/lista/999999/convite", {})[0], 404)

    def test_validacao(self):
        casos = [{}, {"nome": ""}, {"nome": "   "}, {"nome": 5}, {"nome": "x" * 201}, {"nome": "a", "pessoas": -1},
                 {"nome": "a", "pessoas": "2"}, {"nome": "a", "pessoas": 100}, {"nome": "a", "pessoas": True}, {"nome": "a", "confirmados": 1.5},
                 {"nome": "a", "mesa": "11"}, {"nome": "a", "mesa": 3}, {"nome": "a", "telefone": "abc"}, {"nome": "a", "telefone": "1" * 31},
                 {"nome": "a", "notas": "x" * 1001}, {"nome": "a", "extra": 1}, {"nome": "a", "dataConvite": "x"}]
        for c in casos:
            self.assertEqual(self.pedir("POST", "/convidados/lista", c)[0], 400, c)
        g = self.novo()
        self.assertEqual(self.pedir("PUT", f"/convidados/lista/{g['id']}", {})[0], 400)
        self.assertEqual(self.pedir("PUT", f"/convidados/lista/{g['id']}", {"pessoas": 200})[0], 400)
        # um campo mau não deixa gravar os bons
        self.assertEqual(self.pedir("PUT", f"/convidados/lista/{g['id']}", {"nome": "novo nome", "pessoas": -3})[0], 400)
        _, d, _ = self.pedir("GET", "/convidados/dados")
        self.assertEqual([x["nome"] for x in d["convidados"] if x["id"] == g["id"]], ["Ana e Rui"])

    def test_injecao_sql_e_html_ficam_como_texto(self):
        g = self.novo(nome="x'); DROP TABLE convidados_lista;--", notas="<script>alert(1)</script>")
        _, d, _ = self.pedir("GET", "/convidados/dados")
        row = [x for x in d["convidados"] if x["id"] == g["id"]][0]
        self.assertIn("DROP TABLE", row["nome"])
        self.assertEqual(row["notas"], "<script>alert(1)</script>")   # a PWA escapa ao mostrar (escapeHtml)


if __name__ == "__main__":
    unittest.main()
