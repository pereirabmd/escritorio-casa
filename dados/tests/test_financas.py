import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.financas import _somar_meses
from tests.test_api import ApiBase


def lanc(**kw):
    base = {"tipo": "despesa", "descricao": "Luz", "valor": 45.5, "categoria_id": 1, "data_vencimento": "2031-03-10"}
    base.update(kw)
    return base


class FinancasApiTest(ApiBase):
    def test_acesso_so_para_a_acl_da_app(self):
        self.assertEqual(self.pedir("GET", "/financas/categorias", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/financas/categorias", token=None)[0], 401)

    def test_categorias_iniciais_e_crud(self):
        _, b, _ = self.pedir("GET", "/financas/categorias")
        nomes = [c["nome"] for c in b["categorias"]]
        self.assertEqual(nomes[:6], ["Habitação", "Alimentação", "Transportes", "Lazer", "Saúde", "Rendimentos"])
        self.assertEqual(b["categorias"][0]["cor"], "#476D7C")
        s, nova, _ = self.pedir("POST", "/financas/categorias", {"nome": "Animais"})
        self.assertEqual(s, 201)
        self.assertRegex(nova["cor"], r"^#[0-9A-F]{6}$")
        self.assertEqual(self.pedir("POST", "/financas/categorias", {"nome": "animais"})[0], 409)  # nome único, sem distinguir maiúsculas
        s, b, _ = self.pedir("PUT", f"/financas/categorias/{nova['id']}", {"nome": "Bichos", "cor": "#112233"})
        self.assertEqual((s, b["nome"], b["cor"]), (200, "Bichos", "#112233"))
        self.assertEqual(self.pedir("DELETE", f"/financas/categorias/{nova['id']}")[0], 200)
        self.assertEqual(self.pedir("DELETE", f"/financas/categorias/{nova['id']}")[0], 404)

    def test_categoria_em_uso_nao_se_apaga(self):
        _, c, _ = self.pedir("POST", "/financas/categorias", {"nome": "Em uso"})
        self.assertEqual(self.pedir("POST", "/financas/lancamentos", lanc(categoria_id=c["id"]))[0], 201)
        self.assertEqual(self.pedir("DELETE", f"/financas/categorias/{c['id']}")[0], 409)

    def test_categoria_validacao(self):
        for corpo in [{}, {"nome": ""}, {"nome": "x" * 41}, {"nome": "a", "cor": "vermelho"}, {"nome": "a", "x": 1}, {"nome": 5}]:
            self.assertEqual(self.pedir("POST", "/financas/categorias", corpo)[0], 400, corpo)

    def test_lancamento_criar_listar_pagar_apagar(self):
        s, l, _ = self.pedir("POST", "/financas/lancamentos", lanc(descricao="Renda", valor=650, recorrente=True))
        self.assertEqual(s, 201)
        self.assertEqual((l["categoria"], l["mes_referencia"], l["data_pagamento"], l["recorrente"]),
                         ("Habitação", "2031-03", None, True))
        _, b, _ = self.pedir("GET", "/financas/lancamentos?mes=2031-03")
        self.assertIn(l["id"], [x["id"] for x in b["lancamentos"]])
        s, p, _ = self.pedir("PUT", f"/financas/lancamentos/{l['id']}", {"data_pagamento": "2031-03-09"})
        self.assertEqual((s, p["data_pagamento"], p["valor"]), (200, "2031-03-09", 650.0))
        _, b, _ = self.pedir("GET", "/financas/lancamentos?mes=2031-03&pendentes=1")
        self.assertNotIn(l["id"], [x["id"] for x in b["lancamentos"]])
        s, p, _ = self.pedir("PUT", f"/financas/lancamentos/{l['id']}", {"data_pagamento": None})   # desfazer o pagamento
        self.assertIsNone(p["data_pagamento"])
        s, apagado, _ = self.pedir("DELETE", f"/financas/lancamentos/{l['id']}")
        self.assertEqual((s, apagado["descricao"]), (200, "Renda"))
        self.assertEqual(self.pedir("DELETE", f"/financas/lancamentos/{l['id']}")[0], 404)

    def test_criar_e_idempotente_por_cid(self):
        c = lanc(cid="abcdef123456", descricao="Net", data_vencimento="2031-04-01")
        s1, a, _ = self.pedir("POST", "/financas/lancamentos", c)
        s2, b, _ = self.pedir("POST", "/financas/lancamentos", c)
        self.assertEqual((s1, s2, a["id"]), (201, 200, b["id"]))

    def test_mes_de_referencia_pode_diferir_do_vencimento(self):
        _, l, _ = self.pedir("POST", "/financas/lancamentos", lanc(data_vencimento="2031-06-02", mes_referencia="2031-05"))
        self.assertEqual(l["mes_referencia"], "2031-05")

    def test_lancamento_validacao(self):
        casos = [{}, lanc(tipo="x"), lanc(valor=0), lanc(valor=-3), lanc(valor="4"), lanc(valor=True), lanc(descricao=""),
                 lanc(descricao="x" * 101), lanc(categoria_id=99999), lanc(categoria_id="1"), lanc(data_vencimento="2031-02-30"),
                 lanc(data_vencimento="10/03/2031"), lanc(data_pagamento="ontem"), lanc(recorrente="sim"),
                 lanc(mes_referencia="2031-13"), lanc(extra=1), lanc(cid="curto")]
        for c in casos:
            self.assertEqual(self.pedir("POST", "/financas/lancamentos", c)[0], 400, c)
        self.assertEqual(self.pedir("PUT", "/financas/lancamentos/1", {})[0], 400)
        self.assertEqual(self.pedir("PUT", "/financas/lancamentos/999999", {"valor": 1})[0], 404)
        for corpo in [{"valor": "x"}, {"cid": "abcdef123456"}, {"categoria_id": 99999}]:
            self.assertEqual(self.pedir("PUT", "/financas/lancamentos/1", corpo)[0], 400, corpo)
        self.assertEqual(self.pedir("GET", "/financas/lancamentos")[0], 400)   # sem filtro
        self.assertEqual(self.pedir("GET", "/financas/lancamentos?mes=2031-3")[0], 400)

    def test_filtros_por_vencimento(self):
        for d in ("2032-01-05", "2032-01-20", "2032-02-03"):
            self.pedir("POST", "/financas/lancamentos", lanc(data_vencimento=d, descricao="F" + d))
        _, b, _ = self.pedir("GET", "/financas/lancamentos?de=2032-01-10&ate=2032-02-28")
        self.assertEqual([x["data_vencimento"] for x in b["lancamentos"]], ["2032-01-20", "2032-02-03"])

    def test_mudar_vencimento_rearma_o_aviso(self):
        _, l, _ = self.pedir("POST", "/financas/lancamentos", lanc(data_vencimento="2033-01-10"))
        import db
        c = db.connect_named("dados")
        try:
            c.execute("UPDATE financas_lancamentos SET notificado_em='x' WHERE id=?", (l["id"],))
            self.pedir("PUT", f"/financas/lancamentos/{l['id']}", {"valor": 3})     # não mexe no vencimento
            self.assertEqual(c.execute("SELECT notificado_em FROM financas_lancamentos WHERE id=?", (l["id"],)).fetchone()[0], "x")
            self.pedir("PUT", f"/financas/lancamentos/{l['id']}", {"data_vencimento": "2033-01-12"})
            self.assertIsNone(c.execute("SELECT notificado_em FROM financas_lancamentos WHERE id=?", (l["id"],)).fetchone()[0])
        finally:
            c.close()

    def test_preparar_mes_copia_so_recorrentes_sem_pagamento(self):
        hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
        mes = f"{hoje.year:04d}-{hoje.month:02d}"
        ant = _somar_meses(f"{mes}-01", -1)[:7]
        # a BD de testes é partilhada entre testes: usa um mês anterior próprio para a origem
        import db
        c = db.connect_named("dados")
        try:
            c.execute("DELETE FROM financas_lancamentos WHERE mes_referencia >= ?", (ant,))
            c.execute("DELETE FROM financas_meses WHERE mes >= ?", (ant,))
        finally:
            c.close()
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Luz", valor=40, data_vencimento=f"{ant}-31" if ant[5:] in ("01", "03", "05", "07", "08", "10", "12") else f"{ant}-28",
                                                          recorrente=True, data_pagamento=f"{ant}-20"))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Salário", tipo="rendimento", categoria_id=6, valor=1500,
                                                          data_vencimento=f"{ant}-25", recorrente=True))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Dentista", valor=90, data_vencimento=f"{ant}-12"))   # pontual
        s, r, _ = self.pedir("POST", f"/financas/meses/{mes}/preparar", {})
        self.assertEqual((s, r["criados"], r["origem"], r["ja_preparado"]), (200, 2, ant, False))
        _, b, _ = self.pedir("GET", f"/financas/lancamentos?mes={mes}")
        self.assertEqual(sorted(x["descricao"] for x in b["lancamentos"]), ["Luz", "Salário"])
        self.assertTrue(all(x["data_pagamento"] is None and x["recorrente"] for x in b["lancamentos"]))
        self.assertTrue(all(x["data_vencimento"].startswith(mes) for x in b["lancamentos"]))
        # segunda chamada: nada de novo, mesmo que se apague tudo
        for x in b["lancamentos"]:
            self.pedir("DELETE", f"/financas/lancamentos/{x['id']}")
        s, r, _ = self.pedir("POST", f"/financas/meses/{mes}/preparar", {})
        self.assertEqual((r["criados"], r["ja_preparado"]), (0, True))

    def test_preparar_mes_com_lancamentos_recebe_recorrentes_sem_duplicar(self):
        hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
        mes = f"{hoje.year:04d}-{hoje.month:02d}"
        ant = _somar_meses(f"{mes}-01", -1)[:7]
        import db
        c = db.connect_named("dados")
        try:
            c.execute("DELETE FROM financas_lancamentos WHERE mes_referencia >= ?", (ant,))
            c.execute("DELETE FROM financas_meses WHERE mes >= ?", (ant,))
        finally:
            c.close()
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Luz", data_vencimento=f"{ant}-10", recorrente=True))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Renda", valor=650, data_vencimento=f"{ant}-02", recorrente=True))
        # mês já com lançamentos (ex.: prestações pré-carregadas), incluindo uma "luz" com outra grafia
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="LUZ", valor=99, data_vencimento=f"{mes}-11"))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="IRS", valor=231, data_vencimento=f"{mes}-28"))
        s, r, _ = self.pedir("POST", f"/financas/meses/{mes}/preparar", {})
        self.assertEqual((s, r["criados"]), (200, 1))   # só a Renda; a Luz já existe
        _, b, _ = self.pedir("GET", f"/financas/lancamentos?mes={mes}")
        self.assertEqual(sorted(x["descricao"] for x in b["lancamentos"]), ["IRS", "LUZ", "Renda"])

    def test_preparar_mes_futuro_recusado(self):
        self.assertEqual(self.pedir("POST", "/financas/meses/2099-01/preparar", {})[0], 400)
        self.assertEqual(self.pedir("POST", "/financas/meses/2031-13/preparar", {})[0], 400)

    def test_agregado(self):
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Água", valor=10, data_vencimento="2040-05-05"))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Água", valor=12.25, data_vencimento="2040-05-20"))
        self.pedir("POST", "/financas/lancamentos", lanc(descricao="Salário", tipo="rendimento", categoria_id=6, valor=1000, data_vencimento="2040-05-25"))
        s, b, _ = self.pedir("GET", "/financas/agregado?de=2040-05&ate=2040-06")
        self.assertEqual(s, 200)
        agua = [x for x in b["linhas"] if x["descricao"] == "Água"][0]
        self.assertEqual((agua["total"], agua["n"], agua["mes"], agua["tipo"]), (22.25, 2, "2040-05", "despesa"))
        for q in ["", "?de=2040-05", "?de=2040-06&ate=2040-05", "?de=2030-01&ate=2040-01", "?de=x&ate=y"]:
            self.assertEqual(self.pedir("GET", "/financas/agregado" + q)[0], 400, q)


class LembretesApiTest(ApiBase):
    def test_acesso_so_para_a_acl_da_app(self):
        self.assertEqual(self.pedir("GET", "/financas/lembretes", token="t" * 30 + "outro")[0], 403)

    def test_crud(self):
        s, l, _ = self.pedir("POST", "/financas/lembretes", {"titulo": "Transferir para a conta da casa", "data": "2031-06-05", "hora": "09:00", "repeticao": "mensal", "nota": "500 €"})
        self.assertEqual((s, l["ativo"], l["ultimo_aviso"], l["repeticao"]), (201, True, None, "mensal"))
        _, b, _ = self.pedir("GET", "/financas/lembretes")
        self.assertIn(l["id"], [x["id"] for x in b["lembretes"]])
        s, p, _ = self.pedir("PUT", f"/financas/lembretes/{l['id']}", {"hora": "10:30"})
        self.assertEqual((s, p["hora"], p["titulo"]), (200, "10:30", "Transferir para a conta da casa"))
        s, p, _ = self.pedir("PUT", f"/financas/lembretes/{l['id']}", {"ativo": False})
        self.assertFalse(p["ativo"])
        self.assertEqual(self.pedir("DELETE", f"/financas/lembretes/{l['id']}")[0], 200)
        self.assertEqual(self.pedir("DELETE", f"/financas/lembretes/{l['id']}")[0], 404)
        self.assertEqual(self.pedir("PUT", "/financas/lembretes/999999", {"hora": "10:00"})[0], 404)

    def test_mudar_agendamento_rearma_o_aviso(self):
        _, l, _ = self.pedir("POST", "/financas/lembretes", {"titulo": "X", "data": "2031-06-05", "hora": "09:00", "repeticao": "unica"})
        import db
        c = db.connect_named("dados")
        try:
            c.execute("UPDATE financas_lembretes SET ultimo_aviso='2031-06-05' WHERE id=?", (l["id"],))
            self.pedir("PUT", f"/financas/lembretes/{l['id']}", {"titulo": "Y"})   # não mexe no agendamento
            self.assertEqual(c.execute("SELECT ultimo_aviso FROM financas_lembretes WHERE id=?", (l["id"],)).fetchone()[0], "2031-06-05")
            self.pedir("PUT", f"/financas/lembretes/{l['id']}", {"data": "2031-06-06"})
            self.assertIsNone(c.execute("SELECT ultimo_aviso FROM financas_lembretes WHERE id=?", (l["id"],)).fetchone()[0])
        finally:
            c.close()

    def test_validacao(self):
        ok = {"titulo": "X", "data": "2031-06-05", "hora": "09:00", "repeticao": "unica"}
        for extra in [{"titulo": ""}, {"titulo": "x" * 101}, {"data": "2031-02-30"}, {"hora": "24:00"}, {"hora": "9:00"},
                      {"repeticao": "semanal"}, {"nota": "x" * 301}, {"ativo": "sim"}, {"x": 1}]:
            self.assertEqual(self.pedir("POST", "/financas/lembretes", {**ok, **extra})[0], 400, extra)
        for falta in ok:
            self.assertEqual(self.pedir("POST", "/financas/lembretes", {k: v for k, v in ok.items() if k != falta})[0], 400, falta)
        self.assertEqual(self.pedir("PUT", "/financas/lembretes/1", {})[0], 400)


class SomarMesesTest(unittest.TestCase):
    def test_dia_ajusta_ao_fim_do_mes(self):
        self.assertEqual(_somar_meses("2031-01-31", 1), "2031-02-28")
        self.assertEqual(_somar_meses("2032-01-31", 1), "2032-02-29")
        self.assertEqual(_somar_meses("2031-12-15", 1), "2032-01-15")
        self.assertEqual(_somar_meses("2031-01-15", -1), "2030-12-15")


if __name__ == "__main__":
    unittest.main()
