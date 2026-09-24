import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
