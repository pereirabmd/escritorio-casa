"""Endpoints da app RTO. Tabelas: rto_dias (marca T/C por dia), rto_notas.

Datas na API sempre em ISO 'AAAA-MM-DD' (a PWA converte de/para o formato pt
que mostra ao utilizador). Todo o SQL é parametrizado.
"""

from __future__ import annotations

import re
from datetime import date

from api import ApiError

NAME = "rto"

MAX_LOTE = 100
MAX_DIAS_LOTE = 400
_CID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data(v: object, campo: str = "data", opcional: bool = False) -> str | None:
    if v is None or v == "":
        if opcional:
            return None
        raise ApiError(400, f"{campo}_invalida", f"{campo} obrigatória")
    if not isinstance(v, str) or not _ISO_RE.match(v):
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ser AAAA-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: data inexistente") from None
    if not 2000 <= d.year <= 2100:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: ano fora de 2000-2100")
    return v


def _marca(v: object) -> str:
    if v not in ("T", "C", ""):
        raise ApiError(400, "marca_invalida", "marca tem de ser 'T', 'C' ou '' (limpar)")
    return v


def _texto(v: object, campo: str, maximo: int) -> str:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > maximo:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser texto até {maximo} caracteres")
    return _CTRL_RE.sub("", v).strip()


def _so_campos(b: dict, permitidos: set[str]) -> None:
    extra = set(b) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


def _nota_valida(b: object, com_cid: bool = False) -> dict:
    if not isinstance(b, dict):
        raise ApiError(400, "nota_invalida", "a nota tem de ser um objeto")
    _so_campos(b, {"dataInicio", "dataFim", "categoria", "descricao"} | ({"cid"} if com_cid else set()))
    ini = _data(b.get("dataInicio"), "dataInicio", opcional=True)
    fim = _data(b.get("dataFim"), "dataFim", opcional=True)
    cat, desc = _texto(b.get("categoria"), "categoria", 100), _texto(b.get("descricao"), "descricao", 500)
    if not (ini or fim or cat or desc):
        raise ApiError(400, "nota_vazia", "a nota não pode estar vazia")
    if ini and fim and fim < ini:
        raise ApiError(400, "intervalo_invalido", "dataFim anterior a dataInicio")
    cid = b.get("cid")
    if cid is not None and (not isinstance(cid, str) or not _CID_RE.match(cid)):
        raise ApiError(400, "cid_invalido", "cid tem de ter 8-64 caracteres [A-Za-z0-9-]")
    return {"ini": ini, "fim": fim, "cat": cat, "desc": desc, "cid": cid}


def _nota_json(r) -> dict:
    return {"id": r["id"], "dataInicio": r["data_inicio"], "dataFim": r["data_fim"],
            "categoria": r["categoria"], "descricao": r["descricao"]}


_SEL = "SELECT id, data_inicio, data_fim, categoria, descricao FROM rto_notas"


def _gravar_dia(conn, data: str, marca: str) -> None:
    if marca == "":
        conn.execute("DELETE FROM rto_dias WHERE data=?", (data,))
    else:
        conn.execute("INSERT INTO rto_dias (data, marca) VALUES (?, ?) "
                     "ON CONFLICT(data) DO UPDATE SET marca=excluded.marca", (data, marca))


# --- dias -------------------------------------------------------------------

def listar_dias(ctx):
    desde = _data(ctx.query.get("desde"), "desde", opcional=True)
    ate = _data(ctx.query.get("ate"), "ate", opcional=True)
    sql, args = "SELECT data, marca FROM rto_dias WHERE 1=1", []
    if desde:
        sql, args = sql + " AND data >= ?", args + [desde]
    if ate:
        sql, args = sql + " AND data <= ?", args + [ate]
    rows = ctx.db().execute(sql + " ORDER BY data LIMIT 20000", args).fetchall()
    return 200, {"dias": {r["data"]: r["marca"] for r in rows}}


def marcar_dia(ctx):
    data = _data(ctx.groups[0])
    _so_campos(ctx.body, {"marca"})
    marca = _marca(ctx.body.get("marca"))
    _gravar_dia(ctx.db(), data, marca)
    return 200, {"data": data, "marca": marca}


def marcar_dias(ctx):
    """Lote atómico {dias: {'AAAA-MM-DD': 'T'|'C'|''}} — usado pelo Desfazer e pela fila offline."""
    _so_campos(ctx.body, {"dias"})
    dias = ctx.body.get("dias")
    if not isinstance(dias, dict) or not 1 <= len(dias) <= MAX_DIAS_LOTE:
        raise ApiError(400, "dias_invalidos", f"dias tem de ser um objeto com 1 a {MAX_DIAS_LOTE} entradas")
    limpo = {_data(k): _marca(v) for k, v in dias.items()}  # valida tudo antes de escrever
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for d, m in limpo.items():
            _gravar_dia(conn, d, m)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"dias": limpo}


# --- notas ------------------------------------------------------------------

def listar_notas(ctx):
    rows = ctx.db().execute(_SEL + " ORDER BY COALESCE(data_inicio, data_fim), id LIMIT 5000").fetchall()
    return 200, {"notas": [_nota_json(r) for r in rows]}


def _inserir(conn, n: dict, id_: int | None = None) -> int:
    cur = conn.execute("INSERT INTO rto_notas (id, data_inicio, data_fim, categoria, descricao, cid) VALUES (?, ?, ?, ?, ?, ?)",
                       (id_, n["ini"], n["fim"], n["cat"], n["desc"], n["cid"]))
    return cur.lastrowid


def criar_nota(ctx):
    n = _nota_valida(ctx.body, com_cid=True)
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if n["cid"]:
            ja = conn.execute(_SEL + " WHERE cid=?", (n["cid"],)).fetchone()
            if ja:
                conn.execute("COMMIT")
                return 200, _nota_json(ja)
        nid = _inserir(conn, n)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 201, {"id": nid, "dataInicio": n["ini"], "dataFim": n["fim"], "categoria": n["cat"], "descricao": n["desc"]}


def criar_notas_lote(ctx):
    """{notas: [...]} (≤100), atómico; devolve as notas criadas, pela mesma ordem, com os ids."""
    _so_campos(ctx.body, {"notas"})
    itens = ctx.body.get("notas")
    if not isinstance(itens, list) or not 1 <= len(itens) <= MAX_LOTE:
        raise ApiError(400, "notas_invalidas", f"notas tem de ser uma lista de 1 a {MAX_LOTE} itens")
    validas = [_nota_valida(it) for it in itens]
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        ids = [_inserir(conn, n) for n in validas]
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 201, {"notas": [{"id": i, "dataInicio": n["ini"], "dataFim": n["fim"], "categoria": n["cat"],
                            "descricao": n["desc"]} for i, n in zip(ids, validas)]}


def gravar_nota(ctx):
    """Upsert por id: atualiza, ou recria com esse id (o Desfazer repõe uma nota apagada)."""
    nid = int(ctx.groups[0])
    n = _nota_valida(ctx.body)
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        existe = conn.execute("SELECT 1 FROM rto_notas WHERE id=?", (nid,)).fetchone()
        if existe:
            conn.execute("UPDATE rto_notas SET data_inicio=?, data_fim=?, categoria=?, descricao=? WHERE id=?",
                         (n["ini"], n["fim"], n["cat"], n["desc"], nid))
        else:
            _inserir(conn, n, nid)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"id": nid, "dataInicio": n["ini"], "dataFim": n["fim"], "categoria": n["cat"], "descricao": n["desc"]}


def eliminar_nota(ctx):
    nid = int(ctx.groups[0])
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(_SEL + " WHERE id=?", (nid,)).fetchone()
        if row:
            conn.execute("DELETE FROM rto_notas WHERE id=?", (nid,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    if not row:
        raise ApiError(404, "nao_encontrado", "nota inexistente")
    return 200, _nota_json(row)


ROUTES = [
    ("GET", r"^/rto/dias$", listar_dias),
    ("PUT", r"^/rto/dias$", marcar_dias),
    ("PUT", r"^/rto/dias/(\d{4}-\d{2}-\d{2})$", marcar_dia),
    ("GET", r"^/rto/notas$", listar_notas),
    ("POST", r"^/rto/notas$", criar_nota),
    ("POST", r"^/rto/notas/lote$", criar_notas_lote),
    ("PUT", r"^/rto/notas/(\d{1,12})$", gravar_nota),
    ("DELETE", r"^/rto/notas/(\d{1,12})$", eliminar_nota),
]
