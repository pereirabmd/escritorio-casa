import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import db
import importar_financas as imp

CAB = ";".join(imp.CABECALHO)
AGORA = datetime(2031, 5, 10, 9, 0, 0)


class ImportarFinancasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.conn = db.connect(self.dir / "t.db")
        db.migrate(self.conn)

    def tearDown(self):
        self.conn.close(); self.tmp.cleanup()

    def csv(self, *linhas):
        p = self.dir / "c.csv"
        p.write_text("\n".join([CAB, *linhas]) + "\n", encoding="utf-8")
        return p

    def test_le_valida_e_reporta(self):
        p = self.csv("despesa;Casa;713,10;Habitação;2031-05-02;2031-05-02;sim;",
                     "rendimento;Ordenado;1900;Rendimentos;2031-04-26;2031-04-26;sim;2031-05")
        linhas, problemas = imp.ler(p)
        self.assertEqual(problemas, [])
        self.assertEqual((linhas[0]["valor"], linhas[0]["mes_referencia"], linhas[1]["mes_referencia"]), (713.10, "2031-05", "2031-05"))
        self.assertIn("2031-05:  2 lançamentos · despesas    713.10 · rendimentos   1900.00", imp.relatorio(linhas))

    def test_problemas_impedem_tudo(self):
        p = self.csv("despesa;Casa;0;Habitação;2031-05-02;;sim;", "despesa;X;5;Y;2031-02-30;;sim;",
                     "despesa;X;5;Y;2031-05-02;;talvez;", "abc;X;5;Y;2031-05-02;;sim;", "despesa;X;5;Y")
        linhas, problemas = imp.ler(p)
        self.assertEqual((len(linhas), len(problemas)), (0, 5))

    def test_cabecalho_errado_e_duplicados(self):
        (self.dir / "e.csv").write_text("a;b\n1;2\n", encoding="utf-8")
        self.assertEqual(len(imp.ler(self.dir / "e.csv")[1]), 1)
        _, problemas = imp.ler(self.csv(*["despesa;Casa;10;Habitação;2031-05-02;;sim;"] * 2))
        self.assertTrue(problemas)

    def test_gravar_e_idempotente_cria_categorias_e_marca_meses(self):
        linhas, _ = imp.ler(self.csv("despesa;IRS 1/12;231,37;Impostos;2031-05-30;;não;", "despesa;Casa;713,10;Habitação;2031-05-02;;sim;"))
        r = imp.gravar(self.conn, linhas, ["2031-05"], AGORA)
        self.assertEqual((r["criadas"], r["existentes"], r["categorias_novas"]), (2, 0, ["Impostos"]))
        r = imp.gravar(self.conn, linhas, ["2031-05"], AGORA)
        self.assertEqual((r["criadas"], r["existentes"], r["categorias_novas"]), (0, 2, []))
        n = lambda t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        self.assertEqual((n("financas_lancamentos"), n("financas_meses")), (2, 1))
        self.assertEqual(self.conn.execute("SELECT c.nome FROM financas_lancamentos l JOIN financas_categorias c ON c.id=l.categoria_id "
                                           "WHERE l.descricao='IRS 1/12'").fetchone()[0], "Impostos")


if __name__ == "__main__":
    unittest.main()
