"""SQLite do Pulse (`pulse.db`, só dados próprios do Pulse).

WAL, chaves estrangeiras ligadas e migrações numeradas em `migrations/NNN_nome.sql`, aplicadas por ordem e
uma só vez (a versão fica em `PRAGMA user_version`). Cada migração corre numa transação. As migrações
produzem o mesmo esquema em produção e em teste (DATA_AND_SYNC).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_NOME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    novo = not path.exists()
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)   # autocommit: as transações são explícitas
    if novo:
        os.chmod(path, 0o600)   # só o dono lê a base (o WAL/SHM herdam estas permissões)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migracoes(pasta: Path) -> list[tuple[int, Path]]:
    achadas = []
    for f in sorted(pasta.glob("*.sql")):
        m = _NOME.match(f.name)
        if not m:
            raise ValueError(f"nome de migração inválido: {f.name}")
        achadas.append((int(m.group(1)), f))
    numeros = [n for n, _ in achadas]
    if numeros != list(range(1, len(numeros) + 1)):
        raise ValueError(f"as migrações têm de ser 001, 002, … sem falhas (achei {numeros})")
    return achadas


def migrate(conn: sqlite3.Connection, pasta: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica as migrações em falta; devolve os nomes aplicados."""
    atual = conn.execute("PRAGMA user_version").fetchone()[0]
    aplicadas = []
    for numero, ficheiro in _migracoes(pasta):
        if numero <= atual:
            continue
        script = f"BEGIN IMMEDIATE;\n{ficheiro.read_text(encoding='utf-8')}\n;PRAGMA user_version={numero};\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        aplicadas.append(ficheiro.name)
    return aplicadas
