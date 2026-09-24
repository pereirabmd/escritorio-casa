import json
import unittest

from tests.test_api import ApiBase, OUTRO


class RtoApiTest(ApiBase):
    def test_acesso_so_para_a_acl_da_app(self):
        self.assertEqual(self.pedir("GET", "/rto/dias", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/rto/dias", token=None)[0], 401)

    def test_dias_marcar_limpar_e_listar(self):
        self.assertEqual(self.pedir("PUT", "/rto/dias/2031-03-04", {"marca": "T"})[0], 200)
        self.assertEqual(self.pedir("PUT", "/rto/dias/2031-03-05", {"marca": "C"})[0], 200)
        _, b, _ = self.pedir("GET", "/rto/dias?desde=2031-03-01&ate=2031-03-31")
        self.assertEqual(b["dias"], {"2031-03-04": "T", "2031-03-05": "C"})
        self.assertEqual(self.pedir("PUT", "/rto/dias/2031-03-04", {"marca": "C"})[0], 200)   # troca
        self.assertEqual(self.pedir("PUT", "/rto/dias/2031-03-05", {"marca": ""})[0], 200)    # limpa
        _, b, _ = self.pedir("GET", "/rto/dias?desde=2031-03-01&ate=2031-03-31")
        self.assertEqual(b["dias"], {"2031-03-04": "C"})

    def test_dias_validacao(self):
        for caminho, corpo in [("/rto/dias/2031-02-30", {"marca": "T"}), ("/rto/dias/1999-01-01", {"marca": "T"}),
                               ("/rto/dias/2031-03-04", {"marca": "X"}), ("/rto/dias/2031-03-04", {"marca": None}),
                               ("/rto/dias/2031-03-04", {}), ("/rto/dias/2031-03-04", {"marca": "T", "x": 1})]:
            self.assertEqual(self.pedir("PUT", caminho, corpo)[0], 400, (caminho, corpo))
        self.assertEqual(self.pedir("GET", "/rto/dias?desde=abc")[0], 400)
        self.assertEqual(self.pedir("PUT", "/rto/dias/2031-3-4", {"marca": "T"})[0], 404)  # rota nem existe

    def test_lote_de_dias_e_atomico(self):
        s, b, _ = self.pedir("PUT", "/rto/dias", {"dias": {"2032-01-01": "T", "2032-01-02": "C"}})
        self.assertEqual(s, 200)
        # um valor mau => nada é gravado
        s, _, _ = self.pedir("PUT", "/rto/dias", {"dias": {"2032-01-03": "T", "2032-01-04": "Z"}})
        self.assertEqual(s, 400)
        _, b, _ = self.pedir("GET", "/rto/dias?desde=2032-01-01&ate=2032-01-31")
        self.assertEqual(b["dias"], {"2032-01-01": "T", "2032-01-02": "C"})
        self.assertEqual(self.pedir("PUT", "/rto/dias", {"dias": {}})[0], 400)
        self.assertEqual(self.pedir("PUT", "/rto/dias", {"dias": {f"2033-01-{i:02d}": "T" for i in range(1, 29)} | {f"2033-02-{i:02d}": "T" for i in range(1, 29)} | {f"2033-0{m}-{i:02d}": "T" for m in range(3, 10) for i in range(1, 29)} | {f"2034-{m:02d}-{i:02d}": "T" for m in range(1, 13) for i in range(1, 29)}})[0], 400)  # > 400

    def test_notas_crud_e_desfazer_com_o_mesmo_id(self):
        s, n, _ = self.pedir("POST", "/rto/notas", {"dataInicio": "2035-06-26", "dataFim": "2035-07-14", "categoria": "Férias", "descricao": "verão"})
        self.assertEqual(s, 201)
        nid = n["id"]
        s, b, _ = self.pedir("PUT", f"/rto/notas/{nid}", {"dataInicio": "2035-06-27", "dataFim": "2035-07-14", "categoria": "Férias", "descricao": "verão"})
        self.assertEqual((s, b["dataInicio"]), (200, "2035-06-27"))
        s, apagada, _ = self.pedir("DELETE", f"/rto/notas/{nid}")
        self.assertEqual((s, apagada["id"]), (200, nid))
        self.assertEqual(self.pedir("DELETE", f"/rto/notas/{nid}")[0], 404)
        # Desfazer: repõe com o MESMO id
        corpo = {k: apagada[k] for k in ("dataInicio", "dataFim", "categoria", "descricao")}
        self.assertEqual(self.pedir("PUT", f"/rto/notas/{nid}", corpo)[0], 200)
        _, lista, _ = self.pedir("GET", "/rto/notas")
        self.assertIn(nid, [x["id"] for x in lista["notas"]])
        # o id apagado nunca é reutilizado por uma nota nova
        self.pedir("DELETE", f"/rto/notas/{nid}")
        _, nova, _ = self.pedir("POST", "/rto/notas", {"categoria": "outra"})
        self.assertGreater(nova["id"], nid)

    def test_notas_validacao(self):
        casos = [{}, {"dataInicio": "2035-13-01"}, {"dataInicio": "2035-07-14", "dataFim": "2035-07-01"},
                 {"categoria": "x" * 101}, {"descricao": 5}, {"categoria": "a", "extra": 1}, {"dataInicio": "26/06/2035"}]
        for c in casos:
            self.assertEqual(self.pedir("POST", "/rto/notas", c)[0], 400, c)
        self.assertEqual(self.pedir("POST", "/rto/notas", {"dataFim": "2036-01-01"})[0], 201)  # só uma das datas é aceite

    def test_lote_de_notas_devolve_ids_pela_ordem(self):
        itens = [{"dataInicio": f"2037-01-{d:02d}", "dataFim": f"2037-01-{d:02d}", "categoria": "Validação"} for d in (5, 19)]
        s, b, _ = self.pedir("POST", "/rto/notas/lote", {"notas": itens})
        self.assertEqual((s, [n["dataInicio"] for n in b["notas"]]), (201, ["2037-01-05", "2037-01-19"]))
        self.assertLess(b["notas"][0]["id"], b["notas"][1]["id"])
        # atómico: um item mau => nenhum criado
        antes = len(self.pedir("GET", "/rto/notas")[1]["notas"])
        self.assertEqual(self.pedir("POST", "/rto/notas/lote", {"notas": itens + [{"dataInicio": "lixo"}]})[0], 400)
        self.assertEqual(len(self.pedir("GET", "/rto/notas")[1]["notas"]), antes)
        self.assertEqual(self.pedir("POST", "/rto/notas/lote", {"notas": []})[0], 400)
        self.assertEqual(self.pedir("POST", "/rto/notas/lote", {"notas": [{"categoria": "x"}] * 101})[0], 400)

    def test_cid_idempotente(self):
        c = {"categoria": "Astreinte", "dataInicio": "2038-02-02", "dataFim": "2038-02-02", "cid": "imp-nota-000001"}
        s1, a, _ = self.pedir("POST", "/rto/notas", c)
        s2, b, _ = self.pedir("POST", "/rto/notas", c)
        self.assertEqual((s1, s2, a["id"] == b["id"]), (201, 200, True))

    def test_injecao_sql_fica_como_texto(self):
        s, n, _ = self.pedir("POST", "/rto/notas", {"categoria": "x'); DROP TABLE rto_notas;--", "dataInicio": "2039-01-01"})
        self.assertEqual(s, 201)
        _, lista, _ = self.pedir("GET", "/rto/notas")
        self.assertTrue(any("DROP TABLE" in x["categoria"] for x in lista["notas"]))


if __name__ == "__main__":
    unittest.main()
