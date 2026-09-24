"""Acesso à base de dados SQLite do Raspberry Pi (partilhada pelas apps migradas).

- Um único ficheiro (`data/dados.db`), modo WAL (menos escritas no cartão SD,
  leitores não bloqueiam o escritor) e chaves estrangeiras ligadas.
- Migrações numeradas em `migrations/NNN_nome.sql`, aplicadas por ordem e uma
  só vez; a versão aplicada fica em `PRAGMA user_version`. Cada migração corre
  numa transação: ou entra por inteiro ou não entra.

Uso:  python db.py init | status
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(os.environ.get("DADOS_HOME") or Path(__file__).resolve().parent)
MIGRATIONS_DIR = BASE_DIR / "migrations"

# Bases de dados: nome -> (variável de ambiente com o caminho, ficheiro por omissão, pasta das migrações).
# `bilhetes` é separada de propósito: a compra com hora certa nunca espera por um lock de outra app.
DATABASES = {
    "dados": ("DADOS_DB", "dados.db", "migrations"),
    "bilhetes": ("BILHETES_DB", "bilhetes.db", "migrations_bilhetes"),
}


def load_env(path: Path | None = None) -> None:
    path = path or (BASE_DIR / ".env")
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env()


def db_path(name: str = "dados") -> Path:
    var, ficheiro, _ = DATABASES[name]
    return Path(os.environ.get(var) or BASE_DIR / "data" / ficheiro)


def connect_named(name: str) -> sqlite3.Connection:
    """Liga a uma das bases conhecidas (`dados` ou `bilhetes`)."""
    return connect(db_path(name))


def migrate_all() -> dict[str, list[str]]:
    """Aplica as migrações em falta a todas as bases. Devolve, por base, o que aplicou."""
    out = {}
    for name, (_, _, pasta) in DATABASES.items():
        conn = connect_named(name)
        try:
            out[name] = migrate(conn, BASE_DIR / pasta)
        finally:
            conn.close()
    return out


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Liga (criando o ficheiro e a pasta se preciso) com os PRAGMAs certos."""
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    novo = not path.exists()
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # commit manual
    if novo:
        os.chmod(path, 0o600)  # dados pessoais: só o dono lê (o -wal/-shm herdam estas permissões)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _migrations(directory: Path) -> list[tuple[int, Path]]:
    found = []
    for f in sorted(directory.glob("*.sql")):
        m = re.match(r"(\d+)_", f.name)
        if not m:
            raise ValueError(f"migração sem número à frente: {f.name}")
        found.append((int(m.group(1)), f))
    numeros = [n for n, _ in found]
    if len(set(numeros)) != len(numeros):
        raise ValueError("números de migração repetidos")
    return found


def versao(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection, directory: Path | None = None) -> list[str]:
    """Aplica as migrações em falta. Devolve os nomes das que aplicou."""
    aplicadas = []
    atual = versao(conn)
    for numero, ficheiro in _migrations(directory or MIGRATIONS_DIR):
        if numero <= atual:
            continue
        sql = ficheiro.read_text(encoding="utf-8")
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _statements(sql):
                conn.execute(stmt)
            conn.execute(f"PRAGMA user_version={numero}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        aplicadas.append(ficheiro.name)
    return aplicadas


def _statements(sql: str) -> list[str]:
    """Divide um script em instruções completas (sqlite3.complete_statement
    respeita ';' dentro de strings/triggers)."""
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip() and not all(l.strip().startswith("--") or not l.strip()
                                       for l in buf.splitlines()):
                out.append(buf.strip())
            buf = ""
    if buf.strip() and not all(l.strip().startswith("--") or not l.strip()
                               for l in buf.splitlines()):
        raise ValueError("instrução SQL incompleta no fim da migração")
    return out


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "init":
        conn = connect()
        novas = migrate(conn)
        print(f"{db_path()}: versão {versao(conn)}; aplicadas: {', '.join(novas) or 'nenhuma'}")
        return 0
    if cmd == "status":
        conn = connect()
        tabelas = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        print(f"{db_path()}: versão {versao(conn)}")
        for t in tabelas:
            print(f"  {t}: {conn.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]} linhas")
        return 0
    print("uso: python db.py init | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
