import sqlite3

import pytest

from pulse import db


def test_migra_do_zero_e_e_idempotente(tmp_path):
    conn = db.connect(tmp_path / "teste-x.db")
    assert db.migrate(conn) == ["001_base.sql", "002_auth.sql", "003_notificacoes.sql", "004_compras.sql", "005_compras_sugestoes.sql", "006_google.sql", "007_google_cliente.sql"]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert db.migrate(conn) == []
    nomes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"pulse_settings", "pulse_activity", "pulse_users", "pulse_sessions", "pulse_devices", "pulse_events", "shop_products", "shop_lists", "shop_items", "shop_history", "shop_user_categories", "google_accounts", "google_oauth_states"} <= nomes
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_esquema_igual_em_duas_bases(tmp_path):
    def esquema(nome):
        c = db.connect(tmp_path / nome); db.migrate(c)
        return sorted(r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
    assert esquema("teste-a.db") == esquema("teste-b.db")


def test_migracao_falhada_faz_rollback(tmp_path):
    pasta = tmp_path / "m"; pasta.mkdir()
    (pasta / "001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    (pasta / "002_b.sql").write_text("CREATE TABLE b (x INTEGER); CREATE TABLE a (x INTEGER);")
    conn = db.connect(tmp_path / "teste-y.db")
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(conn, pasta)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='b'").fetchone()


def test_numeracao_com_falhas_e_recusada(tmp_path):
    pasta = tmp_path / "m"; pasta.mkdir()
    (pasta / "001_a.sql").write_text("SELECT 1;"); (pasta / "003_c.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError):
        db.migrate(db.connect(tmp_path / "teste-z.db"), pasta)


def test_atividade_valida_origem_e_resultado(tmp_path):
    conn = db.connect(tmp_path / "teste-w.db"); db.migrate(conn)
    conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao) VALUES ('a@b.pt', 'rto', 'marcar')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO pulse_activity (utilizador, modulo, acao, origem) VALUES ('a@b.pt', 'rto', 'x', 'robo')")


def test_base_nova_so_o_dono_le(tmp_path):
    db.connect(tmp_path / "teste-perm.db").close()
    assert ((tmp_path / "teste-perm.db").stat().st_mode & 0o777) == 0o600
