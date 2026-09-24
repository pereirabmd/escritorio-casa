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


class PublicarTest(unittest.TestCase):
    """Percurso git completo contra um remoto local (sem rede): repositório vazio, e depois alterações."""

    def _git(self, *a, cwd=None):
        import subprocess
        return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout

    def test_repo_vazio_e_depois_so_se_mudou(self):
        import os, stat, subprocess
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            age = d / "bin" / "age"
            age.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\ncat > "$out"\n')
            age.chmod(age.stat().st_mode | stat.S_IEXEC)
            self._git("init", "-q", "--bare", "-b", "main", str(d / "remoto.git"))
            self._git("clone", "-q", str(d / "remoto.git"), str(d / "clone"))     # clone vazio, como no Pi
            env = {"PATH": f"{d / 'bin'}:{os.environ['PATH']}", "BACKUP_REPO_DIR": str(d / "clone"),
                   "AGE_RECIPIENT": "age1teste", "BACKUP_SSH_KEY": "/dev/null",
                   "GIT_CONFIG_GLOBAL": "/dev/null"}
            with mock.patch.dict("os.environ", env):
                self.assertTrue(backup.publicar({"dados": "texto v1"}))                        # 1º backup num repo vazio
                self.assertFalse(backup.publicar({"dados": "texto v1"}))                       # igual: nada a commitar
                self.assertTrue(backup.publicar({"dados": "texto v2"}))
            log = self._git("log", "--format=%s", cwd=d / "remoto.git").splitlines()
            self.assertEqual(len(log), 2)
            self.assertEqual(self._git("show", "main:dados.sql.age", cwd=d / "remoto.git"), "texto v2")
            self.assertEqual(self._git("ls-tree", "--name-only", "main", cwd=d / "remoto.git").split(), ["dados.sql.age"])
            with mock.patch.dict("os.environ", env):                                # várias bases num só commit
                self.assertTrue(backup.publicar({"dados": "texto v2", "bilhetes": "b1"}))
            self.assertEqual(self._git("ls-tree", "--name-only", "main", cwd=d / "remoto.git").split(), ["bilhetes.sql.age", "dados.sql.age"])
            self.assertEqual(len(self._git("log", "--format=%s", cwd=d / "remoto.git").splitlines()), 3)


class VariasBasesTest(unittest.TestCase):
    """As duas bases (dados e bilhetes) vão no mesmo backup; só se republica a que mudou."""

    def test_backup_de_ambas_e_so_a_que_mudou(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            env = {"DADOS_DB": str(d / "dados.db"), "BILHETES_DB": str(d / "bilhetes.db"), "BACKUP_EXCLUIR": ""}
            with mock.patch.dict("os.environ", env), \
                    mock.patch.object(backup, "STATE_DIR", d / "state"), \
                    mock.patch.object(backup, "HASH_FILE", d / "state" / "dados.h"), \
                    mock.patch.object(backup, "publicar", return_value=True) as pub:
                for nome in ("dados", "bilhetes"):
                    c = db.connect_named(nome)
                    db.migrate(c, db.BASE_DIR / db.DATABASES[nome][2])
                    c.close()
                self.assertEqual(backup.fazer_backup(), "backup publicado (bilhetes, dados)")
                self.assertEqual(sorted(pub.call_args[0][0]), ["bilhetes", "dados"])
                self.assertEqual(backup.fazer_backup(), "sem alterações desde o último backup")
                c = db.connect_named("bilhetes")
                c.execute("UPDATE bilhetes_passe SET data_ultima_compra='2026-09-21' WHERE id=1")
                c.close()
                backup.fazer_backup()
                self.assertEqual(sorted(pub.call_args[0][0]), ["bilhetes"])          # a base dos dados não mudou
                dump = pub.call_args[0][0]["bilhetes"]
                novo = sqlite3.connect(":memory:")
                novo.executescript(dump)                                              # o dump recarrega
                self.assertEqual(novo.execute("SELECT data_ultima_compra FROM bilhetes_passe").fetchone()[0], "2026-09-21")
                self.assertEqual(novo.execute("SELECT seq FROM sqlite_sequence WHERE name='bilhetes_viagens'").fetchone()[0], 99)


class FluxoTest(unittest.TestCase):
    def _correr(self, d, **extra):
        env = {"DADOS_DB": str(Path(d) / "a.db"), "BILHETES_DB": str(Path(d) / "inexistente.db"), "BACKUP_EXCLUIR": "logs_x", **extra}
        return mock.patch.dict("os.environ", env)

    def test_sem_alteracoes_nao_volta_a_publicar(self):
        with tempfile.TemporaryDirectory() as d, self._correr(d), \
                mock.patch.object(backup, "STATE_DIR", Path(d) / "state"), \
                mock.patch.object(backup, "HASH_FILE", Path(d) / "state" / "h"), \
                mock.patch.object(backup, "publicar", return_value=True) as pub:
            bd_de_teste(Path(d) / "a.db").close()
            self.assertEqual(backup.fazer_backup(), "backup publicado (dados)")
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
