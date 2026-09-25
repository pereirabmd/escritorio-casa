"""Consulta e edição das bases SQLite do Pi (`dados.db` e `bilhetes.db`) numa página web, SÓ para a rede local.

    python admin_db.py                      # serve em ADMIN_DB_BIND:ADMIN_DB_PORT (por omissão 0.0.0.0:8890)
    python admin_db.py --set-password       # pede a password (sem eco) e imprime a linha ADMIN_DB_PASSWORD_HASH=... para o .env

Desenho (é uma ferramenta que escreve em TUDO, por isso é fechada por camadas):
- só aceita ligações de endereços privados/loopback (RFC 1918); a firewall do Pi só abre a porta à LAN; nada passa pelo nginx;
- login com password (PBKDF2, no `.env`), sessão em cookie HttpOnly/SameSite=Strict, CSRF em todas as escritas,
  bloqueio por IP depois de 5 falhas;
- nomes de tabelas e colunas vêm SEMPRE do esquema (nunca do pedido); valores por parâmetros; as restrições CHECK/UNIQUE
  do SQLite recusam o que for inválido;
- segredos (`*password*`, `*token*`, `*secret*` e `Pessoa*_NtfyPasswordEnc`) aparecem mascarados e não se editam;
- antes de escrever guarda um instantâneo da base (`data/undo/`) e regista a alteração (antes/depois) em `logs/admin_edits.jsonl`
  — cada alteração de uma linha pode ser revertida se a linha ainda estiver como a deixámos;
- consola SQL só de leitura (base aberta em modo `ro` + autorizador que só deixa SELECT);
- «Backup agora» corre o `backup.py` (repositório privado `pereirabmd/backup_database`, cifrado com age).
Só usa a biblioteca padrão.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db

WEB_DIR = Path(__file__).resolve().parent / "admin_web"
LOG = logging.getLogger("admin_db")
SESSAO_SEGUNDOS = 8 * 3600
MAX_CORPO = 64 * 1024
PAGINA_MAX = 200
SQL_LINHAS_MAX = 500
SQL_SEGUNDOS_MAX = 3.0
SNAPSHOTS_MAX = 20
SNAPSHOT_INTERVALO_S = 60
_SENSIVEL = re.compile(r"(password|senha|secret|token)", re.I)
_SENSIVEL_CHAVE = re.compile(r"(Enc|Password|Secret|Token)$")
MASCARA = "••••••••"


class AdminError(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

def hash_password(password: str, iteracoes: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        alg, it, salt, h = guardado.split("$")
        if alg != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Esquema e dados
# ---------------------------------------------------------------------------

def nomes_bases() -> list[str]:
    return [n for n in db.DATABASES if db.db_path(n).is_file()]


def abrir(nome: str, so_leitura: bool = False) -> sqlite3.Connection:
    if nome not in db.DATABASES:
        raise AdminError(400, "base desconhecida")
    caminho = db.db_path(nome)
    if not caminho.is_file():
        raise AdminError(404, "a base ainda não existe")
    if so_leitura:
        conn = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn
    conn = db.connect(caminho)
    conn.row_factory = sqlite3.Row
    return conn


def tabelas(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def colunas(conn: sqlite3.Connection, tabela: str) -> list[dict]:
    if tabela not in tabelas(conn):
        raise AdminError(404, "tabela desconhecida")
    out = []
    for r in conn.execute(f'PRAGMA table_info("{tabela}")'):
        out.append({"nome": r["name"], "tipo": (r["type"] or "").upper(), "obrigatoria": bool(r["notnull"]),
                    "por_omissao": r["dflt_value"], "pk": r["pk"]})
    return out


def info_tabela(conn: sqlite3.Connection, tabela: str) -> dict:
    """{'sem_rowid': bool, 'pk': [colunas da chave primária, por ordem]}. As tabelas WITHOUT ROWID (rto_dias, convidados_opcoes)
    não têm `rowid`: as linhas identificam-se pela chave primária (lista de valores)."""
    colunas(conn, tabela)                                    # valida o nome
    wr = next((r["wr"] for r in conn.execute("PRAGMA table_list") if r["name"] == tabela), 0)
    pk = [c["nome"] for c in sorted((c for c in colunas(conn, tabela) if c["pk"]), key=lambda c: c["pk"])]
    return {"sem_rowid": bool(wr), "pk": pk}


def _ident_sql(info: dict, ident) -> tuple[str, list]:
    """Cláusula WHERE e argumentos que identificam uma linha: `rowid` (inteiro) ou a chave primária (lista)."""
    if not info["sem_rowid"]:
        try:
            return "rowid=?", [int(ident)]
        except (TypeError, ValueError):
            raise AdminError(400, "identificador de linha inválido") from None
    if not isinstance(ident, list) or len(ident) != len(info["pk"]):
        raise AdminError(400, "identificador de linha inválido (esperava a chave primária)")
    return " AND ".join(f'"{c}"=?' for c in info["pk"]), list(ident)


def esquema(conn: sqlite3.Connection) -> list[dict]:
    res = []
    for t in tabelas(conn):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
        res.append({"nome": t, "linhas": conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0],
                    "colunas": colunas(conn, t), "sql": sql, "sem_rowid": info_tabela(conn, t)["sem_rowid"],
                    "indices": [r["name"] for r in conn.execute(f'PRAGMA index_list("{t}")')]})
    return res


def celula_protegida(tabela: str, coluna: str, linha: dict | None) -> bool:
    if _SENSIVEL.search(coluna):
        return True
    return bool(tabela == "tarefas_config" and coluna == "valor" and linha
                and _SENSIVEL_CHAVE.search(str(linha.get("chave", ""))))


def _mascarar(tabela: str, linha: dict) -> dict:
    return {k: (MASCARA if k != "_rowid_" and v not in (None, "") and celula_protegida(tabela, k, linha) else v) for k, v in linha.items()}


OPERADORES = {"contem": "contém", "eq": "=", "ne": "≠", "gt": ">", "lt": "<", "ge": "≥", "le": "≤", "vazio": "vazio", "nvazio": "não vazio"}


def _cond_filtro(col: dict, op: str, valor: str) -> tuple[str, list]:
    """Condição SQL de UM filtro (coluna do esquema, operador da lista branca, valor por parâmetro)."""
    n = col["nome"]
    if op == "vazio":
        return f'("{n}" IS NULL OR CAST("{n}" AS TEXT) = \'\')', []
    if op == "nvazio":
        return f'("{n}" IS NOT NULL AND CAST("{n}" AS TEXT) <> \'\')', []
    if op == "contem":
        like = "%" + valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        return f'CAST("{n}" AS TEXT) LIKE ? ESCAPE \'\\\'', [like]
    simbolo = {"eq": "=", "ne": "<>", "gt": ">", "lt": "<", "ge": ">=", "le": "<="}[op]
    tipo = col["tipo"]
    if any(x in tipo for x in ("INT", "REAL", "FLOA", "DOUB")):          # colunas numéricas comparam-se como números
        try:
            v = float(valor.replace(",", "."))
        except ValueError:
            raise AdminError(400, f'"{n}" é numérica: "{valor}" não é um número') from None
        return f'"{n}" {simbolo} ?', [v]
    return f'CAST("{n}" AS TEXT) {simbolo} ?', [valor]          # texto (datas ISO ordenam-se como texto)


def linhas(conn: sqlite3.Connection, tabela: str, *, pagina: int = 1, tamanho: int = 50, ordem: str | None = None,
           sentido: str = "asc", q: str = "", filtros: dict[str, str] | list[dict] | None = None) -> dict:
    cols = colunas(conn, tabela)
    info = info_tabela(conn, tabela)
    nomes = [c["nome"] for c in cols]
    tamanho = max(1, min(int(tamanho), PAGINA_MAX))
    pagina = max(1, int(pagina))
    where, args = [], []
    pesquisaveis = [n for n in nomes if not _SENSIVEL.search(n)]
    if q and pesquisaveis:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(" + " OR ".join(f'CAST("{n}" AS TEXT) LIKE ? ESCAPE \'\\\'' for n in pesquisaveis) + ")")
        args += [like] * len(pesquisaveis)
    if isinstance(filtros, dict):                             # forma antiga: {coluna: texto} = «contém»
        filtros = [{"c": k, "o": "contem", "v": v} for k, v in filtros.items()]
    por_nome = {c["nome"]: c for c in cols}
    for f in filtros or []:
        col, op, v = f.get("c"), f.get("o", "contem"), str(f.get("v", ""))
        if col not in por_nome or _SENSIVEL.search(col) or op not in OPERADORES:
            raise AdminError(400, "filtro inválido")
        if op not in ("vazio", "nvazio") and v == "":
            continue                                          # filtro ainda sem valor: ignora
        cond_f, args_f = _cond_filtro(por_nome[col], op, v)
        where.append(cond_f)
        args += args_f
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f'SELECT COUNT(*) FROM "{tabela}"{cond}', args).fetchone()[0]
    desempate = ", ".join(f'"{c}"' for c in info["pk"]) if info["sem_rowid"] else "rowid"
    if ordem in nomes:
        order_sql = f' ORDER BY "{ordem}" {"DESC" if str(sentido).lower() == "desc" else "ASC"}, {desempate}'
    else:
        order_sql = f" ORDER BY {desempate}"
    sel = "*" if info["sem_rowid"] else "rowid AS _rowid_, *"
    rows = conn.execute(f'SELECT {sel} FROM "{tabela}"{cond}{order_sql} LIMIT ? OFFSET ?',
                        args + [tamanho, (pagina - 1) * tamanho]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if info["sem_rowid"]:
            d["_rowid_"] = [d[c] for c in info["pk"]]           # identificador = valores da chave primária
        out.append(_mascarar(tabela, d))
    return {"colunas": cols, "linhas": out, "total": total, "pagina": pagina, "tamanho": tamanho, "sem_rowid": info["sem_rowid"], "pk": info["pk"]}


# Formatos que as apps esperam em colunas de data/hora e que a base, por si, não verifica (só a API das apps o faz).
_FORMATOS = {
    **{c: "%Y-%m-%d %H:%M:%S" for c in ("quando",)},
    **{c: "%Y-%m-%d" for c in ("data", "data_inicio", "data_fim", "data_convite", "ultima_data", "proxima_data",
                                "data_ultima_compra", "data_viagem")},
    **{c: "%H:%M" for c in ("hora", "hora_partida", "hora_notificacao", "hora_inicio", "hora_fim")},
}
_LEGENDA = {"%Y-%m-%d %H:%M:%S": "AAAA-MM-DD HH:MM:SS", "%Y-%m-%d": "AAAA-MM-DD", "%H:%M": "HH:MM"}


def _validar_formato(nome: str, valor) -> None:
    fmt = _FORMATOS.get(nome)
    if fmt and isinstance(valor, str) and valor != "":
        try:
            if datetime.strptime(valor, fmt).strftime(fmt) != valor:
                raise ValueError
        except ValueError:
            raise AdminError(400, f'"{nome}" tem de ter o formato {_LEGENDA[fmt]}') from None


def _converter(col: dict, valor):
    """Converte o valor do formulário para o tipo da coluna; '' e null → NULL se a coluna aceitar NULL."""
    if valor is None or (valor == "" and col["tipo"] not in ("TEXT", "")):
        if col["obrigatoria"] and col["por_omissao"] is None and not col["pk"]:
            raise AdminError(400, f'"{col["nome"]}" não aceita vazio')
        return None
    tipo = col["tipo"]
    try:
        if "INT" in tipo:
            if isinstance(valor, bool):
                return int(valor)
            return int(str(valor).strip())
        if any(x in tipo for x in ("REAL", "FLOA", "DOUB")):
            return float(str(valor).strip().replace(",", "."))
    except ValueError:
        raise AdminError(400, f'"{col["nome"]}" tem de ser um número ({tipo.lower()})') from None
    if not isinstance(valor, str):
        valor = str(valor)
    if len(valor) > 20_000:
        raise AdminError(400, f'"{col["nome"]}" é demasiado longo')
    _validar_formato(col["nome"], valor)
    return valor


def _valores(conn, tabela: str, valores: dict, linha_atual: dict | None) -> dict:
    cols = {c["nome"]: c for c in colunas(conn, tabela)}
    out = {}
    for nome, v in (valores or {}).items():
        if nome not in cols:
            raise AdminError(400, f'coluna desconhecida: "{nome}"')
        if celula_protegida(tabela, nome, linha_atual or valores):
            raise AdminError(403, f'"{nome}" é um segredo: não se edita aqui')
        out[nome] = _converter(cols[nome], v)
    return out


def _linha(conn, tabela: str, ident) -> dict | None:
    info = info_tabela(conn, tabela)
    where, args = _ident_sql(info, ident)
    r = conn.execute(f'SELECT {"*" if info["sem_rowid"] else "rowid AS _rowid_, *"} FROM "{tabela}" WHERE {where}', args).fetchone()
    if r is None:
        return None
    d = dict(r)
    d.pop("_rowid_", None)
    return d


class Editor:
    """Escritas com instantâneo, registo de auditoria e reversão. Uma instância por processo."""

    def __init__(self, undo_dir: Path, log_path: Path):
        self.undo_dir, self.log_path = undo_dir, log_path
        self.lock = threading.Lock()
        self._ultimo_snap: dict[str, float] = {}

    # -- instantâneos --------------------------------------------------------
    def snapshot(self, nome: str, conn: sqlite3.Connection, razao: str) -> None:
        agora = time.time()
        if agora - self._ultimo_snap.get(nome, 0) < SNAPSHOT_INTERVALO_S:
            return
        self.undo_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        destino = self.undo_dir / f"{nome}-{time.strftime('%Y%m%d-%H%M%S')}.db"
        dst = sqlite3.connect(destino)
        try:
            conn.backup(dst)
        finally:
            dst.close()
        os.chmod(destino, 0o600)
        self._ultimo_snap[nome] = agora
        antigos = sorted(self.undo_dir.glob(f"{nome}-*.db"))
        for f in antigos[:-SNAPSHOTS_MAX]:
            f.unlink(missing_ok=True)

    def snapshots(self) -> list[dict]:
        if not self.undo_dir.is_dir():
            return []
        return [{"ficheiro": f.name, "bytes": f.stat().st_size, "quando": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime))}
                for f in sorted(self.undo_dir.glob("*.db"), reverse=True)]

    # -- auditoria -----------------------------------------------------------
    def _ler_log(self) -> list[dict]:
        if not self.log_path.is_file():
            return []
        out = []
        for i, linha in enumerate(self.log_path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                d = json.loads(linha)
                d["id"] = i
                out.append(d)
            except ValueError:
                continue
        return out

    def _registar(self, entrada: dict) -> int:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False, default=str) + "\n")
        os.chmod(self.log_path, 0o600)
        with open(self.log_path, encoding="utf-8") as f:
            return sum(1 for _ in f)

    def alteracoes(self, limite: int = 100) -> list[dict]:
        log = self._ler_log()
        revertidos = {e.get("reverte") for e in log if e.get("reverte")}
        for e in log:
            e["revertida"] = e["id"] in revertidos
        return list(reversed(log))[:limite]

    # -- escritas --------------------------------------------------------------
    def inserir(self, nome: str, tabela: str, valores: dict, quem: str) -> dict:
        with self.lock:
            conn = abrir(nome)
            try:
                v = _valores(conn, tabela, valores, None)
                if not v:
                    raise AdminError(400, "nada para inserir")
                info = info_tabela(conn, tabela)
                self.snapshot(nome, conn, "inserir")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    cols = ", ".join(f'"{c}"' for c in v)
                    cur = conn.execute(f'INSERT INTO "{tabela}" ({cols}) VALUES ({", ".join("?" * len(v))})', list(v.values()))
                    rid = [v.get(c) for c in info["pk"]] if info["sem_rowid"] else cur.lastrowid
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    conn.execute("ROLLBACK")
                    raise
                depois = _linha(conn, tabela, rid)
            except sqlite3.Error as e:
                raise AdminError(400, f"a base recusou: {e}") from None
            finally:
                conn.close()
            self._registar({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "quem": quem, "base": nome, "tabela": tabela, "op": "inserir",
                            "rowid": rid, "antes": None, "depois": depois})
            return {"rowid": rid, "linha": _mascarar(tabela, depois)}

    def atualizar(self, nome: str, tabela: str, rowid: int, valores: dict, quem: str) -> dict:
        with self.lock:
            conn = abrir(nome)
            try:
                antes = _linha(conn, tabela, rowid)
                if antes is None:
                    raise AdminError(404, "linha inexistente")
                v = _valores(conn, tabela, valores, antes)
                v = {k: x for k, x in v.items() if antes.get(k) != x}
                if not v:
                    return {"rowid": rowid, "linha": _mascarar(tabela, antes), "alterada": False}
                info = info_tabela(conn, tabela)
                where, wargs = _ident_sql(info, rowid)
                self.snapshot(nome, conn, "atualizar")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    sets = ", ".join(f'"{c}"=?' for c in v)
                    conn.execute(f'UPDATE "{tabela}" SET {sets} WHERE {where}', list(v.values()) + wargs)
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    conn.execute("ROLLBACK")
                    raise
                if info["sem_rowid"]:                       # a chave primária pode ter mudado
                    rowid = [v.get(c, antes[c]) for c in info["pk"]]
                depois = _linha(conn, tabela, rowid)
            except sqlite3.Error as e:
                raise AdminError(400, f"a base recusou: {e}") from None
            finally:
                conn.close()
            self._registar({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "quem": quem, "base": nome, "tabela": tabela, "op": "atualizar",
                            "rowid": rowid, "antes": {k: antes[k] for k in v}, "depois": {k: depois[k] for k in v}})
            return {"rowid": rowid, "linha": _mascarar(tabela, depois), "alterada": True}

    def apagar(self, nome: str, tabela: str, rowid: int, quem: str) -> dict:
        with self.lock:
            conn = abrir(nome)
            try:
                antes = _linha(conn, tabela, rowid)
                if antes is None:
                    raise AdminError(404, "linha inexistente")
                where, wargs = _ident_sql(info_tabela(conn, tabela), rowid)
                self.snapshot(nome, conn, "apagar")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(f'DELETE FROM "{tabela}" WHERE {where}', wargs)
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    conn.execute("ROLLBACK")
                    raise
            except sqlite3.Error as e:
                raise AdminError(400, f"a base recusou: {e}") from None
            finally:
                conn.close()
            self._registar({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "quem": quem, "base": nome, "tabela": tabela, "op": "apagar",
                            "rowid": rowid, "antes": antes, "depois": None})
            return {"rowid": rowid}

    def reverter(self, id_: int, quem: str) -> dict:
        """Desfaz uma alteração de UMA linha, se a linha ainda estiver como a alteração a deixou (nunca por cima de alterações posteriores)."""
        with self.lock:
            log = self._ler_log()
            e = next((x for x in log if x["id"] == id_), None)
            if e is None:
                raise AdminError(404, "alteração desconhecida")
            if any(x.get("reverte") == id_ for x in log):
                raise AdminError(409, "esta alteração já foi revertida")
            if e.get("reverte"):
                raise AdminError(400, "não se reverte uma reversão")
            nome, tabela, rowid, op = e["base"], e["tabela"], e["rowid"], e["op"]
            conn = abrir(nome)
            try:
                info = info_tabela(conn, tabela)
                atual = _linha(conn, tabela, rowid)
                self.snapshot(nome, conn, "reverter")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if op == "inserir":
                        if atual != e["depois"]:
                            raise AdminError(409, "a linha mudou depois desta inserção: não a apago")
                        where, wargs = _ident_sql(info, rowid)
                        conn.execute(f'DELETE FROM "{tabela}" WHERE {where}', wargs)
                    elif op == "atualizar":
                        if atual is None or any(atual.get(k) != v for k, v in e["depois"].items()):
                            raise AdminError(409, "a linha mudou depois desta alteração: não a desfaço")
                        where, wargs = _ident_sql(info, rowid)
                        sets = ", ".join(f'"{c}"=?' for c in e["antes"])
                        conn.execute(f'UPDATE "{tabela}" SET {sets} WHERE {where}', list(e["antes"].values()) + wargs)
                    elif op == "apagar":
                        if atual is not None:
                            raise AdminError(409, "já existe uma linha com este identificador")
                        if info["sem_rowid"]:
                            cols = ", ".join(f'"{c}"' for c in e["antes"])
                            conn.execute(f'INSERT INTO "{tabela}" ({cols}) VALUES ({", ".join("?" * len(e["antes"]))})', list(e["antes"].values()))
                        else:
                            cols = ", ".join(["rowid"] + [f'"{c}"' for c in e["antes"]])
                            conn.execute(f'INSERT INTO "{tabela}" ({cols}) VALUES ({", ".join("?" * (len(e["antes"]) + 1))})',
                                         [rowid] + list(e["antes"].values()))
                    else:
                        raise AdminError(400, "operação desconhecida")
                    conn.execute("COMMIT")
                except (sqlite3.Error, AdminError) as exc:
                    conn.execute("ROLLBACK")
                    if isinstance(exc, AdminError):
                        raise
                    raise AdminError(400, f"a base recusou: {exc}") from None
            finally:
                conn.close()
            self._registar({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "quem": quem, "base": nome, "tabela": tabela, "op": "reverter",
                            "rowid": rowid, "antes": e["depois"], "depois": e["antes"], "reverte": id_})
            return {"revertida": id_}


# ---------------------------------------------------------------------------
# Consola SQL (só leitura)
# ---------------------------------------------------------------------------

def _autorizador(acao, arg1, arg2, dbnome, origem):
    permitidos = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    if acao == sqlite3.SQLITE_READ and arg2 and _SENSIVEL.search(arg2):
        return sqlite3.SQLITE_IGNORE          # a coluna sai a NULL
    return sqlite3.SQLITE_OK if acao in permitidos else sqlite3.SQLITE_DENY


def sql_leitura(nome: str, sql: str) -> dict:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql or len(sql) > 5000:
        raise AdminError(400, "escreve uma consulta (até 5000 caracteres)")
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        raise AdminError(400, "só consultas SELECT")
    conn = abrir(nome, so_leitura=True)
    try:
        conn.set_authorizer(_autorizador)
        limite = time.monotonic() + SQL_SEGUNDOS_MAX
        conn.set_progress_handler(lambda: 1 if time.monotonic() > limite else 0, 10_000)
        try:
            cur = conn.execute(sql)
            cabecalho = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(SQL_LINHAS_MAX + 1)
        except sqlite3.Error as e:
            raise AdminError(400, str(e)) from None
        return {"colunas": cabecalho, "linhas": [list(r) for r in rows[:SQL_LINHAS_MAX]], "truncado": len(rows) > SQL_LINHAS_MAX}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def info_backup() -> dict:
    repo = Path(os.environ.get("BACKUP_REPO_DIR", "")) if os.environ.get("BACKUP_REPO_DIR") else Path("/nonexistent")
    out = {"repositorio": "pereirabmd/backup_database (privado, cifrado com age)", "ficheiros": []}
    if repo.is_dir() and (repo / ".git").is_dir():
        try:
            r = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%cI|%h|%s"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                quando, h, msg = r.stdout.strip().split("|", 2)
                out.update({"ultimo": quando, "commit": h, "mensagem": msg})
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        out["ficheiros"] = [{"nome": f.name, "bytes": f.stat().st_size} for f in sorted(repo.glob("*.age"))]
    try:                                                   # última execução do backup (mesmo sem nada a publicar)
        out["execucao"] = json.loads((db.BASE_DIR / "state" / "backup_execucao.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out["execucao"] = None
    return out


_BACKUP_LOCK = threading.Lock()


def correr_backup(forcar: bool = False) -> dict:
    if not _BACKUP_LOCK.acquire(blocking=False):
        raise AdminError(409, "já há um backup a correr")
    try:
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "backup.py")] + (["--force"] if forcar else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(Path(__file__).resolve().parent))
        return {"ok": r.returncode == 0, "saida": (r.stdout + r.stderr).strip()[-800:]}
    except subprocess.TimeoutExpired:
        raise AdminError(504, "o backup demorou demasiado") from None
    finally:
        _BACKUP_LOCK.release()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Estado:
    def __init__(self, password_hash: str, editor: Editor, redes: list[str] | None = None):
        self.password_hash = password_hash
        self.editor = editor
        self.sessoes: dict[str, tuple[float, str]] = {}
        self.falhas: dict[str, list[float]] = {}
        self.redes = [ipaddress.ip_network(r, strict=False) for r in (redes or [])]
        self.lock = threading.Lock()

    def ip_permitido(self, ip: str) -> bool:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if a.is_loopback:
            return True
        if self.redes:
            return any(a in n for n in self.redes)
        return a.is_private

    def bloqueado(self, ip: str) -> bool:
        agora = time.time()
        with self.lock:
            recentes = [t for t in self.falhas.get(ip, []) if agora - t < 600]
            self.falhas[ip] = recentes
            return len(recentes) >= 5

    def falhou(self, ip: str) -> None:
        with self.lock:
            self.falhas.setdefault(ip, []).append(time.time())

    def nova_sessao(self) -> tuple[str, str]:
        tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.lock:
            self.sessoes = {k: v for k, v in self.sessoes.items() if v[0] > time.time()}
            self.sessoes[tok] = (time.time() + SESSAO_SEGUNDOS, csrf)
        return tok, csrf

    def sessao(self, tok: str | None) -> str | None:
        with self.lock:
            s = self.sessoes.get(tok or "")
        return s[1] if s and s[0] > time.time() else None


TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
CSP = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


def _json_ou_texto(txt: str):
    try:
        return json.loads(txt)
    except ValueError:
        raise AdminError(400, "identificador de linha inválido") from None


def make_handler(estado: Estado):
    class H(BaseHTTPRequestHandler):
        timeout = 15
        server_version = "admin-db"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass

        # -- utilitários ---------------------------------------------------
        def _ip(self) -> str:
            return self.client_address[0]

        def _enviar(self, status: int, corpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)
            LOG.info("%s %s %s %s -> %s", self._ip(), self.command, self.path.split("?")[0], getattr(self, "_quem", "-"), status)

        def _json(self, status: int, dados, extra: dict | None = None):
            self._enviar(status, json.dumps(dados, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8", extra)

        def _corpo(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_CORPO:
                raise AdminError(413, "corpo demasiado grande")
            if n == 0:
                return {}
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise AdminError(415, "usa application/json")
            try:
                d = json.loads(self.rfile.read(n))
            except ValueError:
                raise AdminError(400, "JSON inválido") from None
            if not isinstance(d, dict):
                raise AdminError(400, "esperava um objeto JSON")
            return d

        def _cookie(self) -> str | None:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c["adb_sess"].value if "adb_sess" in c else None

        # -- despacho ---------------------------------------------------------
        def _tratar(self):
            try:
                if not estado.ip_permitido(self._ip()):
                    return self._json(403, {"erro": "só a rede local"})
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path.startswith("/api/"):
                    return self._api(url.path, q)
                return self._estatico(url.path)
            except AdminError as e:
                self._json(e.status, {"erro": e.mensagem})
            except Exception:  # noqa: BLE001
                LOG.exception("erro inesperado")
                self._json(500, {"erro": "erro interno"})

        def _estatico(self, path: str):
            nome = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/app.css": "app.css"}.get(path)
            if not nome or self.command != "GET":
                raise AdminError(404, "não encontrado")
            f = WEB_DIR / nome
            self._enviar(200, f.read_bytes(), TIPOS[f.suffix])

        def _api(self, path: str, q: dict):
            if path == "/api/login" and self.command == "POST":
                return self._login()
            csrf = estado.sessao(self._cookie())
            if csrf is None:
                raise AdminError(401, "sessão inválida")
            self._quem = self._ip()
            escrita = self.command in ("POST", "PUT", "DELETE")
            if escrita and not hmac.compare_digest(self.headers.get("X-CSRF", ""), csrf):
                raise AdminError(403, "CSRF inválido")
            if path == "/api/sessao":
                return self._json(200, {"csrf": csrf, "bases": nomes_bases(), "operadores": OPERADORES})
            if path == "/api/logout" and self.command == "POST":
                estado.sessoes.pop(self._cookie() or "", None)
                return self._json(200, {"ok": True}, {"Set-Cookie": "adb_sess=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
            if path == "/api/esquema" and self.command == "GET":
                c = abrir(q.get("db", ""), so_leitura=True)
                try:
                    return self._json(200, {"tabelas": esquema(c), "versao": c.execute("PRAGMA user_version").fetchone()[0]})
                finally:
                    c.close()
            if path == "/api/linhas" and self.command == "GET":
                c = abrir(q.get("db", ""), so_leitura=True)
                try:
                    filtros = {k[2:]: v for k, v in q.items() if k.startswith("f.")}
                    if q.get("filtros"):                              # JSON: [{"c": coluna, "o": operador, "v": valor}, ...]
                        try:
                            filtros = json.loads(q["filtros"])
                        except ValueError:
                            raise AdminError(400, "filtros inválidos") from None
                        if not isinstance(filtros, list) or len(filtros) > 12 or not all(isinstance(x, dict) for x in filtros):
                            raise AdminError(400, "filtros inválidos")
                    return self._json(200, linhas(c, q.get("tabela", ""), pagina=int(q.get("pagina", 1)), tamanho=int(q.get("tamanho", 50)),
                                                  ordem=q.get("ordem"), sentido=q.get("sentido", "asc"), q=q.get("q", ""), filtros=filtros))
                finally:
                    c.close()
            if path == "/api/linha" and self.command in ("POST", "PUT", "DELETE"):
                d = self._corpo() if self.command != "DELETE" else {}
                nome, tabela = (d.get("db") or q.get("db", "")), (d.get("tabela") or q.get("tabela", ""))
                if self.command == "POST":
                    return self._json(201, estado.editor.inserir(nome, tabela, d.get("valores") or {}, self._quem))
                rid = d.get("rowid") if d.get("rowid") is not None else _json_ou_texto(q.get("rowid", "-1"))
                if self.command == "PUT":
                    return self._json(200, estado.editor.atualizar(nome, tabela, rid, d.get("valores") or {}, self._quem))
                return self._json(200, estado.editor.apagar(nome, tabela, rid, self._quem))
            if path == "/api/sql" and self.command == "POST":
                d = self._corpo()
                return self._json(200, sql_leitura(d.get("db", ""), d.get("sql", "")))
            if path == "/api/alteracoes" and self.command == "GET":
                return self._json(200, {"alteracoes": estado.editor.alteracoes(), "snapshots": estado.editor.snapshots()})
            if path == "/api/reverter" and self.command == "POST":
                return self._json(200, estado.editor.reverter(int(self._corpo().get("id", 0)), self._quem))
            if path == "/api/backup" and self.command == "GET":
                return self._json(200, info_backup())
            if path == "/api/backup/correr" and self.command == "POST":
                return self._json(200, correr_backup(bool(self._corpo().get("forcar"))))
            raise AdminError(404, "não encontrado")

        def _login(self):
            ip = self._ip()
            if estado.bloqueado(ip):
                LOG.warning("login bloqueado ip=%s", ip)
                raise AdminError(429, "demasiadas tentativas: espera 10 minutos")
            pw = str(self._corpo().get("password", ""))
            if not estado.password_hash or not verificar_password(pw, estado.password_hash):
                estado.falhou(ip)
                LOG.warning("login falhado ip=%s", ip)
                time.sleep(0.5)
                raise AdminError(401, "password errada")
            tok, csrf = estado.nova_sessao()
            LOG.info("login ok ip=%s", ip)
            self._json(200, {"csrf": csrf, "bases": nomes_bases(), "operadores": OPERADORES},
                       {"Set-Cookie": f"adb_sess={tok}; Max-Age={SESSAO_SEGUNDOS}; Path=/; HttpOnly; SameSite=Strict"})

        do_GET = do_POST = do_PUT = do_DELETE = _tratar

    return H


def criar_servidor(estado: Estado, host: str = "0.0.0.0", porta: int = 8890) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, porta), make_handler(estado))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set-password", action="store_true")
    args = ap.parse_args(argv[1:])
    if args.set_password:
        p1, p2 = getpass.getpass("Nova password: "), getpass.getpass("Repete: ")
        if p1 != p2 or len(p1) < 10:
            print("as passwords não coincidem ou têm menos de 10 caracteres", file=sys.stderr)
            return 1
        print("ADMIN_DB_PASSWORD_HASH=" + hash_password(p1))
        return 0
    env = os.environ
    log_dir = db.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(log_dir / "admin.log"), logging.StreamHandler()])
    ph = env.get("ADMIN_DB_PASSWORD_HASH", "")
    if not ph:
        LOG.error("ADMIN_DB_PASSWORD_HASH em falta no .env (python admin_db.py --set-password)")
        return 1
    redes = [x.strip() for x in env.get("ADMIN_DB_REDES", "").split(",") if x.strip()]
    estado = Estado(ph, Editor(db.BASE_DIR / "data" / "undo", log_dir / "admin_edits.jsonl"), redes)
    srv = criar_servidor(estado, env.get("ADMIN_DB_BIND", "0.0.0.0"), int(env.get("ADMIN_DB_PORT", "8890")))
    LOG.info("admin_db a escutar em %s:%s (só rede local)", *srv.server_address)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
