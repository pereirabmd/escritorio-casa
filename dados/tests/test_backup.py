import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backup
import db


MIGRACOES = db._migrations(db.MIGRATIONS_DIR)
ULTIMA_VERSAO = max(n for n, _ in MIGRACOES)


def bd_de_teste(path):
    conn = db.connect(path)
    db.migrate(conn)
    conn.execute("INSERT INTO peso_registos (quando, peso, nota) VALUES ('2026-09-01 08:00:00', 80.5, 'a;b')")
    conn.execute("INSERT INTO peso_config (chave, valor) VALUES ('altura', '180')")
    conn.execute("CREATE TABLE logs_x (id INTEGER PRIMARY KEY, msg TEXT)")
    conn.execute("INSERT INTO logs_x (msg) VALUES ('ruido')")
    return conn


class MigracoesTest(unittest.TestCase):
    def test_idempotente_e_versao(self):
        with tempfile.TemporaryDirectory() as d:
            conn = db.connect(Path(d) / "a.db")
            self.assertEqual(db.migrate(conn), [f.name for _, f in MIGRACOES])
            self.assertEqual(db.migrate(conn), [])
            self.assertEqual(db.versao(conn), ULTIMA_VERSAO)

    def test_migracao_falhada_faz_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            mig = Path(d) / "m"; mig.mkdir()
            (mig / "001_ok.sql").write_text("CREATE TABLE t (a);")
            (mig / "002_mal.sql").write_text("CREATE TABLE u (a); INSERT INTO nao_existe VALUES (1);")
            conn = db.connect(Path(d) / "a.db")
            with self.assertRaises(sqlite3.Error):
                db.migrate(conn, mig)
            self.assertEqual(db.versao(conn), 1)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='u'").fetchone())

    def test_check_rejeita_peso_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            conn = bd_de_teste(Path(d) / "a.db")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO peso_registos (quando, peso) VALUES ('x', 0)")


class DumpTest(unittest.TestCase):
    def test_deterministico_exclui_e_recarrega(self):
        with tempfile.TemporaryDirectory() as d:
            conn = bd_de_teste(Path(d) / "a.db")
            t1 = backup.dump_text(conn, {"logs_x"})
            t2 = backup.dump_text(conn, {"logs_x"})
            self.assertEqual(t1, t2)
            self.assertNotIn("logs_x", t1)
            self.assertNotIn("ruido", t1)
            backup.verificar(t1, conn, {"logs_x"})
            novo = sqlite3.connect(":memory:")
            novo.executescript(t1)
            self.assertEqual(novo.execute("SELECT nota FROM peso_registos").fetchone()[0], "a;b")
            self.assertEqual(novo.execute("PRAGMA user_version").fetchone()[0], ULTIMA_VERSAO)

    def test_verificar_apanha_export_truncado(self):
        with tempfile.TemporaryDirectory() as d:
            conn = bd_de_teste(Path(d) / "a.db")
            texto = backup.dump_text(conn, {"logs_x"})
            truncado = texto.replace("INSERT INTO \"peso_registos\"", "-- INSERT INTO \"peso_registos\"")
            with self.assertRaises(backup.BackupError):
                backup.verificar(truncado, conn, {"logs_x"})


class FluxoTest(unittest.TestCase):
    def _correr(self, d, **extra):
        env = {"DADOS_DB": str(Path(d) / "a.db"), "BACKUP_EXCLUIR": "logs_x", **extra}
        return mock.patch.dict("os.environ", env)

    def test_sem_alteracoes_nao_volta_a_publicar(self):
        with tempfile.TemporaryDirectory() as d, self._correr(d), \
                mock.patch.object(backup, "STATE_DIR", Path(d) / "state"), \
                mock.patch.object(backup, "HASH_FILE", Path(d) / "state" / "h"), \
                mock.patch.object(backup, "publicar", return_value=True) as pub:
            bd_de_teste(Path(d) / "a.db").close()
            self.assertEqual(backup.fazer_backup(), "backup publicado")
            self.assertEqual(backup.fazer_backup(), "sem alterações desde o último backup")
            self.assertEqual(pub.call_count, 1)
            conn = db.connect(); conn.execute("INSERT INTO peso_config VALUES ('sexo','M')"); conn.close()
            backup.fazer_backup()
            self.assertEqual(pub.call_count, 2)
            backup.fazer_backup(force=True)
            self.assertEqual(pub.call_count, 3)

    def test_falha_de_publicacao_nao_grava_hash(self):
        with tempfile.TemporaryDirectory() as d, self._correr(d), \
                mock.patch.object(backup, "STATE_DIR", Path(d) / "state"), \
                mock.patch.object(backup, "HASH_FILE", Path(d) / "state" / "h"), \
                mock.patch.object(backup, "publicar", side_effect=backup.BackupError("x")):
            bd_de_teste(Path(d) / "a.db").close()
            with self.assertRaises(backup.BackupError):
                backup.fazer_backup()
            self.assertFalse((Path(d) / "state" / "h").exists())

    def test_nunca_publica_sem_cifra(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"AGE_RECIPIENT": ""}):
            with self.assertRaises(backup.BackupError):
                backup.cifrar("segredo", Path(d) / "x.age")
            self.assertFalse((Path(d) / "x.age").exists())


if __name__ == "__main__":
    unittest.main()
