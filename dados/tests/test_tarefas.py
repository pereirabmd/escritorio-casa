import sqlite3
import unittest

import db
from tests.test_api import ApiBase


def tarefa(**kw):
    base = {"nome": "Limpar WC", "categoria": "Limpeza", "recorrencia": "Semanal", "diasSemana": "Sab",
            "horaNotificacao": "09:00", "pessoaPadrao": "Bruno"}
    base.update(kw)
    return base


class TarefasApiTest(ApiBase):
    def bd(self):
        return db.connect_named("dados")

    def setUp(self):
        c = self.bd()
        for t in ("tarefas_instancias", "tarefas_tarefas", "tarefas_config", "tarefas_piscina", "tarefas_auditoria"):
            c.execute(f"DELETE FROM {t}")
        c.close()

    def nova(self, **kw):
        s, b, _ = self.pedir("POST", "/tarefas/tarefas", tarefa(**kw))
        self.assertEqual(s, 201, b)
        return b

    def inst(self, tid, data="2035-06-01", pessoa="Bruno", estado="Pendente"):
        c = self.bd()
        c.execute("INSERT INTO tarefas_instancias (id, tarefa_id, data, pessoa, estado) VALUES (?, ?, ?, ?, ?)",
                  ("I%04d" % (c.execute("select count(*)+1 from tarefas_instancias").fetchone()[0]), tid, data, pessoa, estado))
        c.close()

    def dados(self):
        return self.pedir("GET", "/tarefas/dados")[1]

    def test_acesso(self):
        self.assertEqual(self.pedir("GET", "/tarefas/dados", token="t" * 30 + "outro")[0], 403)
        self.assertEqual(self.pedir("GET", "/tarefas/dados", token=None)[0], 401)

    def test_criar_tarefa_ids_sequenciais_e_valores_por_omissao(self):
        a = self.nova()["tarefa"]
        b = self.nova(nome="Aspirar", recorrencia="Diaria", diasSemana="")["tarefa"]
        self.assertEqual((a["id"], b["id"]), ("T001", "T002"))
        self.assertEqual((a["ativa"], a["prioridade"], a["rotacaoPessoas"], a["diaMes"]), (True, "Media", "", None))
        self.assertEqual(self.nova(nome="X")["tarefa"]["id"], "T003")

    def test_id_continua_acima_do_maior_mesmo_com_buracos(self):
        c = self.bd(); c.execute("INSERT INTO tarefas_tarefas (id, nome, recorrencia) VALUES ('T1144', 'antiga', 'Diaria')"); c.close()
        self.assertEqual(self.nova()["tarefa"]["id"], "T1145")

    def test_pontual_cria_a_unica_ocorrencia_na_data_escolhida(self):
        r = self.nova(nome="Lavar telhados", recorrencia="Pontual", diasSemana="2035-07-04", pessoaPadrao="Camila")
        self.assertEqual((r["instancia"]["data"], r["instancia"]["pessoa"], r["instancia"]["estado"]), ("2035-07-04", "Camila", "Pendente"))
        self.assertRegex(r["instancia"]["id"], r"^I\d{4,}$")
        self.assertIsNone(self.nova(nome="Semanal")["instancia"])

    def test_validacao_da_recorrencia(self):
        casos = [tarefa(recorrencia="Anual"), tarefa(diasSemana=""), tarefa(diasSemana="Segunda"), tarefa(diasSemana="Seg,Seg"),
                 tarefa(recorrencia="Mensal"), tarefa(recorrencia="Mensal", diaMes=32), tarefa(recorrencia="Mensal", diaMes="5"),
                 tarefa(recorrencia="Pontual", diasSemana="04/07/2035"), tarefa(recorrencia="Pontual", diasSemana=""),
                 tarefa(recorrencia="Trimestral", diasSemana="2035-13-01"),
                 tarefa(nome=""), tarefa(nome="x" * 201), tarefa(horaNotificacao="25:00"), tarefa(horaNotificacao="9:00"),
                 tarefa(prioridade="Urgente"), tarefa(ativa="sim"), tarefa(dependeDe="T999"), {"nome": "só nome"}, tarefa(extra=1)]
        for c in casos:
            self.assertEqual(self.pedir("POST", "/tarefas/tarefas", c)[0], 400, c)
        self.assertEqual(self.dados()["tarefas"], [])
        self.assertEqual(self.pedir("POST", "/tarefas/tarefas", tarefa(recorrencia="Mensal", diaMes=15, diasSemana="ignorado"))[0], 201)

    def test_atualizar_so_o_enviado_e_revalidar_o_conjunto(self):
        tid = self.nova()["tarefa"]["id"]
        s, r, _ = self.pedir("PUT", f"/tarefas/tarefas/{tid}", {"horaNotificacao": "10:30", "prioridade": "Alta"})
        self.assertEqual((s, r["tarefa"]["horaNotificacao"], r["tarefa"]["prioridade"], r["tarefa"]["nome"]), (200, "10:30", "Alta", "Limpar WC"))
        # mudar a recorrência sem dar os dados novos é recusado (o conjunto tem de ser válido)
        self.assertEqual(self.pedir("PUT", f"/tarefas/tarefas/{tid}", {"recorrencia": "Pontual"})[0], 400)
        s, r, _ = self.pedir("PUT", f"/tarefas/tarefas/{tid}", {"recorrencia": "Pontual", "diasSemana": "2035-07-04"})
        self.assertEqual((s, r["tarefa"]["diasSemana"]), (200, "2035-07-04"))
        self.assertEqual(self.pedir("PUT", f"/tarefas/tarefas/{tid}", {"dependeDe": tid})[0], 400)         # de si própria
        self.assertEqual(self.pedir("PUT", "/tarefas/tarefas/T9999", {"nome": "x"})[0], 404)
        self.assertEqual(self.pedir("PUT", f"/tarefas/tarefas/{tid}", {})[0], 400)

    def test_apagar_desativa_e_salta_o_pendente_mas_guarda_o_historico(self):
        tid = self.nova()["tarefa"]["id"]
        self.inst(tid, "2035-06-01", estado="Feita"); self.inst(tid, "2035-06-08"); self.inst(tid, "2035-06-15", estado="Atrasada")
        s, r, _ = self.pedir("DELETE", f"/tarefas/tarefas/{tid}")
        self.assertEqual((s, r["saltadas"]), (200, 2))
        d = self.dados()
        self.assertFalse(d["tarefas"][0]["ativa"])
        self.assertEqual(sorted(i["estado"] for i in d["instancias"]), ["Feita", "Saltada", "Saltada"])
        self.assertEqual(self.pedir("DELETE", "/tarefas/tarefas/T9999")[0], 404)

    def test_instancia_atualizar_parcial_e_validacao(self):
        tid = self.nova()["tarefa"]["id"]; self.inst(tid)
        iid = self.dados()["instancias"][0]["id"]
        s, r, _ = self.pedir("PUT", f"/tarefas/instancias/{iid}", {"estado": "Feita", "dataConclusao": "2035-06-01 21:05"})
        self.assertEqual((s, r["instancia"]["estado"], r["instancia"]["dataConclusao"], r["instancia"]["pessoa"]), (200, "Feita", "2035-06-01 21:05", "Bruno"))
        s, r, _ = self.pedir("PUT", f"/tarefas/instancias/{iid}", {"estado": "Pendente", "dataConclusao": ""})
        self.assertEqual((r["instancia"]["estado"], r["instancia"]["dataConclusao"]), ("Pendente", ""))
        s, r, _ = self.pedir("PUT", f"/tarefas/instancias/{iid}", {"data": "2035-06-02"})
        self.assertEqual(r["instancia"]["data"], "2035-06-02")
        for c in ({"estado": "Quase"}, {"dataConclusao": "ontem"}, {"data": "2035-02-30"}, {"x": 1}, {}):
            self.assertEqual(self.pedir("PUT", f"/tarefas/instancias/{iid}", c)[0], 400, c)
        self.assertEqual(self.pedir("PUT", "/tarefas/instancias/I9999", {"estado": "Feita"})[0], 404)

    def test_nunca_duas_ocorrencias_da_mesma_tarefa_no_mesmo_dia(self):
        tid = self.nova()["tarefa"]["id"]
        s, _, _ = self.pedir("POST", "/tarefas/instancias", {"tarefaId": tid, "data": "2035-06-01", "pessoa": "Bruno"})
        self.assertEqual(s, 201)
        self.assertEqual(self.pedir("POST", "/tarefas/instancias", {"tarefaId": tid, "data": "2035-06-01", "pessoa": "Camila"})[0], 409)
        s, o, _ = self.pedir("POST", "/tarefas/instancias", {"tarefaId": tid, "data": "2035-06-08", "pessoa": "Bruno"})
        self.assertEqual(self.pedir("PUT", f"/tarefas/instancias/{o['instancia']['id']}", {"data": "2035-06-01"})[0], 409)   # reagendar para um dia ocupado
        self.assertEqual(self.pedir("POST", "/tarefas/instancias", {"tarefaId": "T999", "data": "2035-06-01"})[0], 404)

    def test_lote_de_instancias_e_atomico(self):
        tid = self.nova()["tarefa"]["id"]
        for d in ("2035-06-01", "2035-06-08", "2035-06-15"):
            self.pedir("POST", "/tarefas/instancias", {"tarefaId": tid, "data": d, "pessoa": "Bruno"})
        ids = [i["id"] for i in self.dados()["instancias"]]
        s, r, _ = self.pedir("PUT", "/tarefas/instancias", {"atualizacoes": [{"id": i, "estado": "Feita", "dataConclusao": "2035-06-20 10:00"} for i in ids]})
        self.assertEqual((s, len(r["instancias"])), (200, 3))
        # um item mau => nada muda
        antes = self.dados()["instancias"]
        s, _, _ = self.pedir("PUT", "/tarefas/instancias", {"atualizacoes": [{"id": ids[0], "estado": "Pendente", "dataConclusao": ""}, {"id": "I9999", "estado": "Feita"}]})
        self.assertEqual(s, 404)
        self.assertEqual(self.dados()["instancias"], antes)
        self.assertEqual(self.pedir("PUT", "/tarefas/instancias", {"atualizacoes": []})[0], 400)

    def test_reatribuir_e_renomear_pessoa(self):
        a = self.nova(pessoaPadrao="Bruno", rotacaoPessoas="Bruno,Camila")["tarefa"]["id"]
        b = self.nova(nome="Outra", pessoaPadrao="Camila")["tarefa"]["id"]
        for tid, d, est in ((a, "2035-06-01", "Feita"), (a, "2035-06-08", "Pendente"), (b, "2035-06-01", "Pendente")):
            self.pedir("POST", "/tarefas/instancias", {"tarefaId": tid, "data": d, "pessoa": "Bruno"})
            self.pedir("PUT", f"/tarefas/instancias/{self.dados()['instancias'][-1]['id']}", {"estado": est})
        s, r, _ = self.pedir("POST", "/tarefas/pessoas/reatribuir", {"de": "Bruno", "para": "Camila", "apenasPendentes": True})
        self.assertEqual((s, r), (200, {"tarefas": 1, "instancias": 2}))          # a Feita ficou com o Bruno (histórico)
        d = self.dados()
        self.assertEqual(sorted(i["pessoa"] for i in d["instancias"]), ["Bruno", "Camila", "Camila"])
        self.assertEqual({t["id"]: t["rotacaoPessoas"] for t in d["tarefas"]}[a], "Camila")     # 'Bruno,Camila' sem repetir
        # renomear (com a chave da Config no mesmo passo)
        self.pedir("PUT", "/tarefas/config", {"valores": {"Pessoa1_Nome": "Camila"}})
        s, r, _ = self.pedir("POST", "/tarefas/pessoas/reatribuir", {"de": "Camila", "para": "Cami", "apenasPendentes": False, "configChave": "Pessoa1_Nome"})
        self.assertEqual(s, 200)
        d = self.dados()
        self.assertFalse(any(t["pessoaPadrao"] == "Camila" for t in d["tarefas"]) or any(i["pessoa"] == "Camila" for i in d["instancias"]))
        self.assertEqual({c["chave"]: c["valor"] for c in d["config"]}["Pessoa1_Nome"], "Cami")
        for c in ({"de": "A", "para": "A"}, {"de": "", "para": "B"}, {"de": "A", "para": "B", "configChave": "x y"}, {"de": "A", "para": "B", "x": 1}):
            self.assertEqual(self.pedir("POST", "/tarefas/pessoas/reatribuir", c)[0], 400, c)

    def test_config_upsert_apagar_e_segredos(self):
        s, r, _ = self.pedir("PUT", "/tarefas/config", {"valores": {"HoraPadrao": "08:00", "Pessoa1_Nome": "Bruno", "NaoIncomodarInicio": "22:00"}})
        self.assertEqual(s, 200)
        self.pedir("PUT", "/tarefas/config", {"valores": {"HoraPadrao": "09:00"}, "apagar": ["NaoIncomodarInicio", "NaoExiste"]})
        m = {c["chave"]: c["valor"] for c in self.dados()["config"]}
        self.assertEqual(m, {"HoraPadrao": "09:00", "Pessoa1_Nome": "Bruno"})
        # a password ntfy cifrada nunca sai (só a máscara) e nunca se escreve nem apaga por aqui
        c = self.bd(); c.execute("INSERT INTO tarefas_config (chave, valor) VALUES ('Pessoa1_NtfyPasswordEnc', 'gAAAA-segredo')"); c.close()
        d = {c["chave"]: c["valor"] for c in self.dados()["config"]}
        self.assertEqual(d["Pessoa1_NtfyPasswordEnc"], "********")
        self.assertNotIn("gAAAA", str(self.dados()))
        self.assertEqual(self.pedir("PUT", "/tarefas/config", {"valores": {"Pessoa1_NtfyPasswordEnc": "x"}})[0], 400)
        self.assertEqual(self.pedir("PUT", "/tarefas/config", {"apagar": ["Pessoa1_NtfyPasswordEnc"]})[0], 200)      # remover a pessoa apaga-a
        self.assertNotIn("Pessoa1_NtfyPasswordEnc", {c["chave"] for c in self.dados()["config"]})
        for c in ({}, {"valores": {"chave com espaço": "x"}}, {"valores": {"1a": "x"}}, {"valores": {"K": "x" * 501}}, {"valores": []}, {"outra": 1}):
            self.assertEqual(self.pedir("PUT", "/tarefas/config", c)[0], 400, c)

    def test_piscina(self):
        s, r, _ = self.pedir("POST", "/tarefas/piscina/catalogo", {"itens": [{"id": "P01", "nome": "Cloro rápido"}, {"id": "P08", "nome": "Areia", "avisoLongo": True}]})
        self.assertEqual((s, r["criados"]), (200, 2))
        s, r, _ = self.pedir("POST", "/tarefas/piscina/catalogo", {"itens": [{"id": "P01", "nome": "outro nome"}, {"id": "P02", "nome": "pH"}]})
        self.assertEqual((r["criados"], len(r["piscina"])), (1, 3))                               # nunca toca no que existe
        self.assertEqual([p["nome"] for p in r["piscina"] if p["id"] == "P01"], ["Cloro rápido"])
        s, r, _ = self.pedir("PUT", "/tarefas/piscina/P01", {"ultimaData": "2035-06-01", "proximaData": "2035-06-08", "notificacaoEnviada": False, "usarIntervaloLongo": True})
        self.assertEqual((s, r["item"]["ultimaData"], r["item"]["usarIntervaloLongo"]), (200, "2035-06-01", True))
        s, r, _ = self.pedir("PUT", "/tarefas/piscina/P01", {"proximaData": None})
        self.assertIsNone(r["item"]["proximaData"])
        for c in ({"ultimaData": "hoje"}, {"notificacaoEnviada": "TRUE"}, {}, {"x": 1}):
            self.assertEqual(self.pedir("PUT", "/tarefas/piscina/P01", c)[0], 400, c)
        self.assertEqual(self.pedir("PUT", "/tarefas/piscina/P99", {"ultimaData": "2035-06-01"})[0], 404)
        self.assertEqual(self.pedir("POST", "/tarefas/piscina/catalogo", {"itens": [{"id": "../x", "nome": "x"}]})[0], 400)

    def test_auditoria(self):
        for i in range(12):
            self.assertEqual(self.pedir("POST", "/tarefas/auditoria", {"acao": "piscina_feita", "tarefa": f"t{i}", "pessoa": "Bruno", "instanciaId": ""})[0], 201)
        s, r, _ = self.pedir("GET", "/tarefas/auditoria")
        self.assertEqual((s, len(r["entradas"]), r["entradas"][0]["tarefa"]), (200, 10, "t11"))     # as mais recentes primeiro
        self.assertRegex(r["entradas"][0]["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
        self.assertEqual(len(self.pedir("GET", "/tarefas/auditoria?limite=3")[1]["entradas"]), 3)
        for q in ("limite=0", "limite=201", "limite=x"):
            self.assertEqual(self.pedir("GET", "/tarefas/auditoria?" + q)[0], 400, q)
        self.assertEqual(self.pedir("POST", "/tarefas/auditoria", {"acao": ""})[0], 400)

    def test_injecao_e_html_ficam_como_texto(self):
        r = self.nova(nome="x'); DROP TABLE tarefas_tarefas;--<script>", categoria="<b>")
        self.assertIn("DROP TABLE", self.dados()["tarefas"][0]["nome"])


if __name__ == "__main__":
    unittest.main()
