"""Backup diário da base de dados para um repositório GitHub PRIVADO.

Fluxo (nada disto corre no caminho crítico de nenhuma app):
  1. snapshot consistente da BD (API de backup do SQLite, mesmo com escritas a decorrer)
  2. remove as tabelas excluídas (BACKUP_EXCLUIR, ex.: logs) e exporta para texto SQL
     determinístico (o Git faz delta sobre texto; um .db binário inchava o repo)
  3. se o texto for igual ao do último backup bem sucedido, termina (sem commit vazio)
  4. verifica o export: recarrega-o numa BD em memória e compara a contagem de linhas
  5. cifra com `age` (só a chave PÚBLICA está no Pi — o Pi não consegue decifrar)
  6. commit + push com a deploy key; só então grava o hash do estado
Qualquer falha avisa no ntfy (Priority high) e termina com código != 0. Nunca se
faz push de texto por cifrar: sem `age` ou sem AGE_RECIPIENT, falha.

Uso:  python backup.py [--force]
      python backup.py restore <ficheiro.age> --identity <chave.txt> --out <novo.db>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
import base64
from datetime import datetime
from pathlib import Path

import db

BACKUP_FILE = "dados.sql.age"
STATE_DIR = db.BASE_DIR / "state"
HASH_FILE = STATE_DIR / "ultimo_backup.sha256"


class BackupError(Exception):
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# Export para texto
# ---------------------------------------------------------------------------

def _excluidas() -> set[str]:
    return {t.strip() for t in env("BACKUP_EXCLUIR").split(",") if t.strip()}


def dump_text(source: sqlite3.Connection, excluir: set[str] | None = None) -> str:
    """Texto SQL do estado atual, sem as tabelas excluídas. Mesmo estado → mesmo texto."""
    snap = sqlite3.connect(":memory:")
    source.backup(snap)  # snapshot consistente
    for t in sorted(excluir or ()):
        snap.execute(f'DROP TABLE IF EXISTS "{t}"')
    linhas = list(snap.iterdump())  # tabelas por ordem de criação, linhas por rowid
    versao = snap.execute("PRAGMA user_version").fetchone()[0]
    snap.close()
    return "\n".join(linhas) + f"\nPRAGMA user_version={versao};\n"


def contagens(conn: sqlite3.Connection) -> dict[str, int]:
    tabelas = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in sorted(tabelas)}


def verificar(texto: str, source: sqlite3.Connection, excluir: set[str] | None = None) -> None:
    """Recarrega o export numa BD vazia e compara linhas por tabela com a origem."""
    teste = sqlite3.connect(":memory:")
    try:
        teste.executescript(texto)
    except sqlite3.Error as e:
        raise BackupError(f"o export não recarrega: {e}") from e
    esperado = {t: n for t, n in contagens(source).items() if t not in (excluir or set())}
    obtido = contagens(teste)
    teste.close()
    if esperado != obtido:
        raise BackupError(f"contagens diferentes após recarregar: origem={esperado} export={obtido}")


# ---------------------------------------------------------------------------
# Cifra, git, alerta
# ---------------------------------------------------------------------------

def cifrar(texto: str, destino: Path) -> None:
    recipient = env("AGE_RECIPIENT")
    if not recipient.startswith("age1"):
        raise BackupError("AGE_RECIPIENT em falta ou inválido (tem de ser a chave pública 'age1...')")
    try:
        r = subprocess.run(["age", "-r", recipient, "-o", str(destino)],
                           input=texto.encode("utf-8"), capture_output=True, timeout=60)
    except FileNotFoundError as e:
        raise BackupError("o programa 'age' não está instalado (sudo apt install age)") from e
    if r.returncode != 0:
        raise BackupError(f"age falhou: {r.stderr.decode(errors='replace')[:300]}")


def _git(repo: Path, *args: str) -> str:
    ssh = f"ssh -i {env('BACKUP_SSH_KEY')} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "GIT_SSH_COMMAND": ssh})
    if r.returncode != 0:
        raise BackupError(f"git {args[0]} falhou: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def _tem_commits(repo: Path) -> bool:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True).returncode == 0


def publicar(texto: str) -> bool:
    """Cifra para o clone do repo privado e faz push. False se não houve alteração no Git."""
    repo = Path(env("BACKUP_REPO_DIR"))
    if not (repo / ".git").is_dir():
        raise BackupError(f"BACKUP_REPO_DIR não é um clone git: {repo}")
    if _tem_commits(repo):
        _git(repo, "pull", "--ff-only")   # num repositório ainda vazio (1º backup) não há nada para puxar
    cifrar(texto, repo / BACKUP_FILE)
    _git(repo, "add", BACKUP_FILE)
    if not _git(repo, "status", "--porcelain").strip():
        return False
    _git(repo, "-c", "user.name=dados-backup", "-c", "user.email=dados-backup@localhost",
         "commit", "-m", f"backup {datetime.now():%Y-%m-%d %H:%M}")
    _git(repo, "push", "-u", "origin", "HEAD")
    return True


def alertar(titulo: str, mensagem: str) -> None:
    """ntfy com Priority high (todas as notificações deste ecossistema fazem pop-up)."""
    base = env("NTFY_SERVER_URL").rstrip("/")
    if not base:
        print(f"[sem NTFY_SERVER_URL] {titulo}: {mensagem}", file=sys.stderr)
        return
    corpo = json.dumps({"topic": env("NTFY_BACKUP_TOPIC", "backup"), "title": titulo,
                        "message": mensagem, "priority": 4, "tags": ["warning"]}).encode()
    req = urllib.request.Request(base + "/", data=corpo, method="POST",
                                 headers={"Content-Type": "application/json"})
    user, pw = env("NTFY_WRITE_USER"), env("NTFY_WRITE_PASSWORD")
    if user:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode())
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # o alerta nunca pode esconder o erro original
        print(f"alerta ntfy falhou: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def fazer_backup(force: bool = False) -> str:
    excluir = _excluidas()
    conn = db.connect()
    try:
        texto = dump_text(conn, excluir)
        verificar(texto, conn, excluir)
    finally:
        conn.close()
    h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    if not force and HASH_FILE.is_file() and HASH_FILE.read_text().strip() == h:
        return "sem alterações desde o último backup"
    publicou = publicar(texto)
    STATE_DIR.mkdir(exist_ok=True)
    HASH_FILE.write_text(h + "\n")
    return "backup publicado" if publicou else "repositório já estava igual"


def restaurar(ficheiro: Path, identity: Path, out: Path) -> None:
    if out.exists():
        raise BackupError(f"{out} já existe — não sobrescrevo; escolhe outro destino")
    r = subprocess.run(["age", "-d", "-i", str(identity), str(ficheiro)], capture_output=True, timeout=60)
    if r.returncode != 0:
        raise BackupError(f"age -d falhou: {r.stderr.decode(errors='replace')[:300]}")
    conn = sqlite3.connect(out)
    try:
        conn.executescript(r.stdout.decode("utf-8"))
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd")
    p.add_argument("--force", action="store_true", help="publica mesmo sem alterações")
    r = sub.add_parser("restore")
    r.add_argument("ficheiro", type=Path)
    r.add_argument("--identity", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv[1:])
    try:
        if args.cmd == "restore":
            restaurar(args.ficheiro, args.identity, args.out)
            print(f"restaurado para {args.out}")
        else:
            print(fazer_backup(args.force))
        return 0
    except BackupError as e:
        alertar("Backup dos dados falhou", str(e))
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        alertar("Backup dos dados falhou", f"{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv))
