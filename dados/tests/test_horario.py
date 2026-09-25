import tempfile
import unittest
from unittest import mock
from pathlib import Path

import db
import importar_horario as imp
from tests.test_api import ApiBase

CAB = "nome_aluno;ano_letivo;dia_semana;hora_inicio;hora_fim;disciplina;sala\n"


def csv(txt):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(CAB + txt)
    f.close()
    return Path(f.name)


class ImportadorTest(unittest.TestCase):
    def test_turma_dividida_nao_e_erro(self):
        aulas, prob = imp.ler(csv("Bruno;2026/2027;2ª Feira;11:35;12:25;C.D.;EB_B7\nBruno;2026/2027;2ª Feira;11:35;12:25;TIC;EB_INF\n"))
        self.assertEqual((len(aulas), prob), (2, []))

    def test_sem_sala_e_hora_com_um_digito(self):
        aulas, _ = imp.ler(csv("Bruno;2026/2027;3ª Feira;8:30;09:20;DT;Sem sala\n"))
        self.assertEqual((aulas[0]["sala"], aulas[0]["hora_inicio"], aulas[0]["dia_semana"]), ("", "08:30", 2))

    def test_problemas(self):
        _, prob = imp.ler(csv("Bruno;2026/2027;7ª Feira;08:30;09:20;X;S\nBruno;2026-27;2ª Feira;08:30;09:20;X;S\n"
                              "Bruno;2026/2027;2ª Feira;09:30;09:20;X;S\nBruno;2026/2027;2ª Feira;08:30;09:20\n"
                              "Bruno;2026/2027;2ª Feira;08:30;09:20;X;S\nBruno;2026/2027;2ª Feira;08:30;09:20;X;S\n"))
        self.assertEqual(len(prob), 5, prob)

    def test_substituir_troca_o_horario_do_aluno(self):
        db.migrate_all()
        conn = db.connect_named("dados")
        conn.execute("DELETE FROM tarefas_horario")
        antigo, _ = imp.ler(csv("Bruno;2026/2027;2ª Feira;08:30;09:20;PORT;EB_B7\nBruno;2026/2027;2ª Feira;09:30;10:20;ING;EB_B7\n"))
        novo, _ = imp.ler(csv("Bruno;2026/2027;2ª Feira;10:35;11:25;HISTGP;EB_B7\n"))
        imp.gravar(conn, antigo)
        self.assertEqual(imp.gravar(conn, novo, substituir=True), 1)
        self.assertEqual([r[0] for r in conn.execute("SELECT disciplina FROM tarefas_horario")], ["HISTGP"])
        conn.execute("DELETE FROM tarefas_horario")
        conn.close()

    def test_gravar_idempotente(self):
        db.migrate_all()
        conn = db.connect_named("dados")
        conn.execute("DELETE FROM tarefas_horario")
        aulas, _ = imp.ler(csv("Bruno;2026/2027;2ª Feira;08:30;09:20;PORT;EB_B7\nBruno;2026/2027;2ª Feira;08:30;09:20;ING;EB_B7\n"))
        self.assertEqual(imp.gravar(conn, aulas), 2)
        self.assertEqual(imp.gravar(conn, aulas), 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tarefas_horario").fetchone()[0], 2)
        conn.execute("DELETE FROM tarefas_horario")
        conn.close()


class HorarioApiTest(ApiBase):
    def test_lista_e_acesso(self):
        conn = db.connect_named("dados")
        conn.execute("DELETE FROM tarefas_horario")
        imp.gravar(conn, imp.ler(csv("Bruno;2026/2027;3ª Feira;10:35;11:25;HISTGP;EB_B7\nBruno;2026/2027;2ª Feira;08:30;09:20;PORT;EB_B7\n"))[0])
        conn.close()
        s, b, _ = self.pedir("GET", "/tarefas/horario")
        self.assertEqual(s, 200)
        self.assertEqual([(a["diaSemana"], a["disciplina"]) for a in b["aulas"]], [(1, "PORT"), (2, "HISTGP")])
        self.assertEqual(self.pedir("GET", "/tarefas/horario", token=None)[0], 401)
        conn = db.connect_named("dados"); conn.execute("DELETE FROM tarefas_horario"); conn.close()


class AdminApiTest(ApiBase):
    from tests.test_api import EU as _EU

    def setUp(self):
        c = db.connect_named("dados")
        c.execute("DELETE FROM tarefas_config"); c.execute("DELETE FROM tarefas_horario")
        for k, v in {"Pessoa1_Nome": "Bruno", "Pessoa1_Email": "bruno@x.com", "Pessoa1_NtfyUser": "tarefas_bruno",
                     "Pessoa2_Nome": "Camila", "Pessoa2_Email": "camila@x.com", "Pessoa2_NtfyUser": "camila"}.items():
            c.execute("INSERT INTO tarefas_config (chave, valor) VALUES (?, ?)", (k, v))
        c.execute("INSERT INTO tarefas_horario (aluno, ano_letivo, dia_semana, hora_inicio, hora_fim, disciplina) VALUES ('Bruno','2026/2027',1,'08:30','09:20','PORT')")
        c.close()
        self.env = mock.patch.dict("os.environ", {"ADMIN_TAREFAS": self._EU})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_so_admin_ve_e_altera(self):
        with mock.patch.dict("os.environ", {"ADMIN_TAREFAS": "outro@x.com"}):
            self.assertEqual(self.pedir("GET", "/tarefas/admin")[0], 403)
            self.assertEqual(self.pedir("PUT", "/tarefas/admin", {"admins": []})[0], 403)
            self.assertFalse(self.pedir("GET", "/tarefas/dados")[1]["souAdmin"])
        self.assertTrue(self.pedir("GET", "/tarefas/dados")[1]["souAdmin"])

    def test_painel_por_omissao(self):
        s, b, _ = self.pedir("GET", "/tarefas/admin")
        self.assertEqual(s, 200)
        n = {x["id"]: x for x in b["notificacoes"]}
        self.assertEqual((n["piscina"]["destinatarios"], n["piscina"]["padrao"]), (["Bruno", "Camila"], True))
        self.assertEqual(n["horario"]["destinatarios"], ["Bruno"])              # padrão: a pessoa com o nome do aluno
        self.assertEqual([(p["nome"], p["topico"]) for p in b["pessoas"]], [("Bruno", "tarefas_bruno"), ("Camila", "tarefas_camila")])

    def test_escolher_destinatarios_e_admins(self):
        s, b, _ = self.pedir("PUT", "/tarefas/admin", {"admins": ["camila@x.com"], "notificacoes": {"piscina": ["Camila"], "horario": []}})
        self.assertEqual(s, 200, b)
        n = {x["id"]: x for x in b["notificacoes"]}
        self.assertEqual((n["piscina"]["destinatarios"], n["horario"]["destinatarios"], n["horario"]["padrao"]), (["Camila"], [], False))
        self.assertTrue(next(p for p in b["pessoas"] if p["nome"] == "Camila")["admin"])
        c = db.connect_named("dados")
        self.assertEqual(dict(c.execute("SELECT chave, valor FROM tarefas_config WHERE chave IN ('Notif_horario','Notif_piscina','Admins')").fetchall()),
                         {"Notif_horario": "-", "Notif_piscina": "Camila", "Admins": "camila@x.com"})
        c.close()

    def test_validacao(self):
        for corpo in ({}, {"admins": ["intruso@x.com"]}, {"admins": "x"}, {"notificacoes": {"lixo": []}},
                      {"notificacoes": {"piscina": ["Fantasma"]}}, {"extra": 1}):
            self.assertEqual(self.pedir("PUT", "/tarefas/admin", corpo)[0], 400, corpo)

    def test_admin_raiz_nao_se_remove(self):
        s, b, _ = self.pedir("PUT", "/tarefas/admin", {"admins": []})
        self.assertEqual(s, 200)
        self.assertIn(self._EU, b["admins"])

    def test_config_generica_nao_toca_nas_chaves_reservadas(self):
        for corpo in ({"valores": {"Admins": "intruso@x.com"}}, {"valores": {"Notif_piscina": "-"}}, {"apagar": ["Notif_horario"]}):
            self.assertEqual(self.pedir("PUT", "/tarefas/config", corpo)[0], 403, corpo)


if __name__ == "__main__":
    unittest.main()
