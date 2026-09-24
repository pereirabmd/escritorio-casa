"""Endpoints da app peso (piloto). Tabelas: peso_registos, peso_config.

Nada aqui sabe de HTTP: cada handler recebe `ctx` (ctx.db(), ctx.user, ctx.query,
ctx.body, ctx.groups) e devolve (status, dicionário). Todo o SQL é parametrizado.
"""

from __future__ import annotations

import math
import re
from datetime import datetime

from api import ApiError

NAME = "peso"

_QUANDO_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_IMPORTAR = 100  # 100 itens cabem folgadamente nos 16 KB de corpo
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _quando(v: object) -> str:
    if not isinstance(v, str) or not _QUANDO_RE.match(v):
        raise ApiError(400, "quando_invalido", "quando tem de ser 'AAAA-MM-DD HH:MM:SS'")
    try:
        datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ApiError(400, "quando_invalido", "data/hora inexistente") from None
    return v


def _numero(v: object, campo: str, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser um número")
    if not lo <= v <= hi:
        raise ApiError(400, f"{campo}_invalido", f"{campo} fora do intervalo [{lo}, {hi}]")
    return float(v)


def _nota(v: object) -> str:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > 500:
        raise ApiError(400, "nota_invalida", "nota tem de ser texto até 500 caracteres")
    return _CTRL_RE.sub("", v).strip()


def _so_campos(body: dict, permitidos: set[str]) -> None:
    extra = set(body) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


def _registo(row) -> dict:
    return {"id": row["id"], "quando": row["quando"], "peso": row["peso"], "nota": row["nota"]}


def listar(ctx):
    desde, ate = ctx.query.get("desde"), ctx.query.get("ate")
    for nome, v in (("desde", desde), ("ate", ate)):
        if v is not None and not _DATA_RE.match(v):
            raise ApiError(400, f"{nome}_invalido", f"{nome} tem de ser AAAA-MM-DD")
    sql, args = "SELECT id, quando, peso, nota FROM peso_registos WHERE 1=1", []
    if desde:
        sql, args = sql + " AND quando >= ?", args + [desde + " 00:00:00"]
    if ate:
        sql, args = sql + " AND quando <= ?", args + [ate + " 23:59:59"]
    rows = ctx.db().execute(sql + " ORDER BY quando, id LIMIT 20000", args).fetchall()
    return 200, {"registos": [_registo(r) for r in rows]}


def criar(ctx):
    b = ctx.body
    _so_campos(b, {"quando", "peso", "nota", "cid"})
    quando = _quando(b["quando"]) if "quando" in b else datetime.now(ctx.tz).strftime("%Y-%m-%d %H:%M:%S")
    peso = _numero(b.get("peso"), "peso", 1, 1000)
    nota = _nota(b.get("nota"))
    cid = b.get("cid")
    if cid is not None and (not isinstance(cid, str) or not _CID_RE.match(cid)):
        raise ApiError(400, "cid_invalido", "cid tem de ter 8-64 caracteres [A-Za-z0-9-]")
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if cid:
            ja = conn.execute("SELECT id, quando, peso, nota FROM peso_registos WHERE cid = ?", (cid,)).fetchone()
            if ja:  # repetição do mesmo pedido: devolve o registo já criado
                conn.execute("COMMIT")
                return 200, _registo(ja)
        cur = conn.execute("INSERT INTO peso_registos (quando, peso, nota, cid) VALUES (?, ?, ?, ?)",
                           (quando, peso, nota, cid))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 201, {"id": cur.lastrowid, "quando": quando, "peso": peso, "nota": nota}


def atualizar(ctx):
    rid = int(ctx.groups[0])
    b = ctx.body
    _so_campos(b, {"quando", "peso", "nota"})
    quando, peso, nota = _quando(b.get("quando")), _numero(b.get("peso"), "peso", 1, 1000), _nota(b.get("nota"))
    cur = ctx.db().execute("UPDATE peso_registos SET quando=?, peso=?, nota=? WHERE id=?", (quando, peso, nota, rid))
    if cur.rowcount == 0:
        raise ApiError(404, "nao_encontrado", "registo inexistente")
    return 200, {"id": rid, "quando": quando, "peso": peso, "nota": nota}


def eliminar(ctx):
    """Devolve o registo apagado: a PWA usa-o para o 'desfazer' (volta a criá-lo)."""
    rid = int(ctx.groups[0])
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT id, quando, peso, nota FROM peso_registos WHERE id=?", (rid,)).fetchone()
        if row:
            conn.execute("DELETE FROM peso_registos WHERE id=?", (rid,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    if not row:
        raise ApiError(404, "nao_encontrado", "registo inexistente")
    return 200, _registo(row)


def importar(ctx):
    """Importação em lote (migração a partir do Google Sheets), idempotente:
    cada item leva um `cid`, por isso repetir o pedido nunca duplica. Um item
    inválido é recusado sozinho (devolvido em `rejeitados`) sem travar os outros."""
    _so_campos(ctx.body, {"registos"})
    itens = ctx.body.get("registos")
    if not isinstance(itens, list) or not 1 <= len(itens) <= MAX_IMPORTAR:
        raise ApiError(400, "registos_invalidos", f"registos tem de ser uma lista de 1 a {MAX_IMPORTAR} itens")
    validos, rejeitados = [], []
    for i, it in enumerate(itens):
        try:
            if not isinstance(it, dict):
                raise ApiError(400, "item_invalido", "item não é um objeto")
            _so_campos(it, {"quando", "peso", "nota", "cid"})
            cid = it.get("cid")
            if not isinstance(cid, str) or not _CID_RE.match(cid):
                raise ApiError(400, "cid_invalido", "cid obrigatório (8-64 caracteres [A-Za-z0-9-])")
            validos.append((_quando(it.get("quando")), _numero(it.get("peso"), "peso", 1, 1000), _nota(it.get("nota")), cid))
        except ApiError as e:
            rejeitados.append({"indice": i, "codigo": e.codigo})
    criados = existentes = 0
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for quando, peso, nota, cid in validos:
            cur = conn.execute("INSERT OR IGNORE INTO peso_registos (quando, peso, nota, cid) VALUES (?, ?, ?, ?)",
                               (quando, peso, nota, cid))
            criados += cur.rowcount
        existentes = len(validos) - criados
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"criados": criados, "existentes": existentes, "rejeitados": rejeitados}


# --- Config: chave -> validador (devolve o valor canónico em texto) ---------

def _cfg_num(lo, hi):
    return lambda v: repr(_numero(v, "valor", lo, hi))


def _cfg_dia(v):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 6:
        raise ApiError(400, "valor_invalido", "diaControlo tem de ser um inteiro 0-6")
    return str(v)


def _cfg_data(v):
    if not isinstance(v, str) or not _DATA_RE.match(v):
        raise ApiError(400, "valor_invalido", "nascimento tem de ser AAAA-MM-DD")
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, "valor_invalido", "data inexistente") from None
    return v


def _cfg_sexo(v):
    if v not in ("M", "F"):
        raise ApiError(400, "valor_invalido", "sexo tem de ser 'M' ou 'F'")
    return v


CONFIG = {  # chave -> (validador, conversor para a resposta)
    "altura": (_cfg_num(50, 260), float),
    "nascimento": (_cfg_data, str),
    "sexo": (_cfg_sexo, str),
    "pesoAlvo": (_cfg_num(1, 1000), float),
    "atividade": (_cfg_num(1, 3), float),
    "diaControlo": (_cfg_dia, int),
    "pesoMin": (_cfg_num(1, 1000), float),
    "pesoMax": (_cfg_num(1, 1000), float),
}


def ler_config(ctx):
    rows = ctx.db().execute("SELECT chave, valor FROM peso_config").fetchall()
    return 200, {r["chave"]: CONFIG[r["chave"]][1](r["valor"]) for r in rows if r["chave"] in CONFIG}


def gravar_config(ctx):
    """Corpo: {chave: valor}; valor null apaga a chave. Tudo ou nada."""
    b = ctx.body
    desconhecidas = set(b) - set(CONFIG)
    if desconhecidas:
        raise ApiError(400, "chave_desconhecida", f"chaves não aceites: {sorted(desconhecidas)[:5]}")
    limpo = {}
    for k, v in b.items():  # valida tudo antes de escrever
        try:
            limpo[k] = None if v is None else CONFIG[k][0](v)
        except ApiError as e:
            raise ApiError(400, e.codigo, f"{k}: {e.mensagem}") from None
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for k, v in limpo.items():
            if v is None:
                conn.execute("DELETE FROM peso_config WHERE chave=?", (k,))
            else:
                conn.execute("INSERT INTO peso_config (chave, valor) VALUES (?, ?) "
                             "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, v))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return ler_config(ctx)


ROUTES = [
    ("GET", r"^/peso/registos$", listar),
    ("POST", r"^/peso/registos$", criar),
    ("PUT", r"^/peso/registos/(\d{1,12})$", atualizar),
    ("DELETE", r"^/peso/registos/(\d{1,12})$", eliminar),
    ("POST", r"^/peso/importar$", importar),
    ("GET", r"^/peso/config$", ler_config),
    ("PUT", r"^/peso/config$", gravar_config),
]
