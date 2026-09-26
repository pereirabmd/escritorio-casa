"""Endpoints da app financas. Tabelas: financas_categorias, financas_lancamentos, financas_meses.

Nada aqui sabe de HTTP: cada handler recebe `ctx` (ctx.db(), ctx.user, ctx.query,
ctx.body, ctx.groups) e devolve (status, dicionário). Todo o SQL é parametrizado.

Modelo: uma tabela unificada de lançamentos (`despesa` | `rendimento`). Os estados
(pendente / vencido / pago) não se guardam — a PWA deriva-os de data_pagamento e
data_vencimento. O ciclo mensal é `mes_referencia` ('AAAA-MM').
"""

from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime

from api import ApiError

NAME = "financas"

_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_COR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# cores para categorias novas (a paleta das iniciais está na migração)
CORES_NOVAS = ["#B5651D", "#5B8DB8", "#9A6FB0", "#C0728A", "#6E9B5B", "#3F7F93", "#B08D57", "#7A6F9B"]

CAMPOS_LANC = {"tipo", "descricao", "valor", "categoria_id", "data_vencimento", "data_pagamento",
               "recorrente", "mes_referencia", "cid"}

SELECT_LANC = ("SELECT l.id, l.tipo, l.descricao, l.valor, l.categoria_id, c.nome AS categoria, "
               "l.data_vencimento, l.data_pagamento, l.recorrente, l.mes_referencia "
               "FROM financas_lancamentos l JOIN financas_categorias c ON c.id = l.categoria_id")


# --- validação --------------------------------------------------------------

def _so_campos(body: dict, permitidos: set[str]) -> None:
    extra = set(body) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


def _data(v: object, campo: str) -> str:
    if not isinstance(v, str) or not _DATA_RE.match(v):
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ser AAAA-MM-DD")
    try:
        d = datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: data inexistente") from None
    if not 2000 <= d.year <= 2100:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: ano fora de 2000-2100")
    return v


def _mes(v: object, campo: str = "mes") -> str:
    if not isinstance(v, str) or not _MES_RE.match(v) or not 2000 <= int(v[:4]) <= 2100:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser AAAA-MM")
    return v


def _texto(v: object, campo: str, maximo: int) -> str:
    if not isinstance(v, str):
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser texto")
    v = _CTRL_RE.sub("", v).strip()
    if not 1 <= len(v) <= maximo:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ter 1 a {maximo} caracteres")
    return v


def _valor(v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ApiError(400, "valor_invalido", "valor tem de ser um número")
    v = round(float(v), 2)
    if not 0 < v <= 10_000_000:
        raise ApiError(400, "valor_invalido", "valor tem de estar entre 0,01 e 10 000 000")
    return v


def _tipo(v: object) -> str:
    if v not in ("despesa", "rendimento"):
        raise ApiError(400, "tipo_invalido", "tipo tem de ser 'despesa' ou 'rendimento'")
    return v


def _bool01(v: object) -> int:
    if not isinstance(v, bool):
        raise ApiError(400, "recorrente_invalido", "recorrente tem de ser verdadeiro ou falso")
    return int(v)


def _cor(v: object) -> str:
    if not isinstance(v, str) or not _COR_RE.match(v):
        raise ApiError(400, "cor_invalida", "cor tem de ser #RRGGBB")
    return v.upper()


def _cid(v: object) -> str:
    if not isinstance(v, str) or not _CID_RE.match(v):
        raise ApiError(400, "cid_invalido", "cid tem de ter 8-64 caracteres [A-Za-z0-9-]")
    return v


def _categoria_existe(conn, cid_: object) -> int:
    if isinstance(cid_, bool) or not isinstance(cid_, int):
        raise ApiError(400, "categoria_invalida", "categoria_id tem de ser um inteiro")
    if not conn.execute("SELECT 1 FROM financas_categorias WHERE id=?", (cid_,)).fetchone():
        raise ApiError(400, "categoria_invalida", "categoria inexistente")
    return cid_


def _lancamento(row) -> dict:
    d = dict(row)
    d["recorrente"] = bool(d["recorrente"])
    return d


def _transacao(conn):
    """Contexto simples BEGIN IMMEDIATE/COMMIT/ROLLBACK."""
    class _T:
        def __enter__(self):
            conn.execute("BEGIN IMMEDIATE")

        def __exit__(self, et, ev, tb):
            conn.execute("ROLLBACK" if et else "COMMIT")
            return False
    return _T()


# --- categorias -------------------------------------------------------------

def _categorias(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, nome, cor FROM financas_categorias ORDER BY id")]


def listar_categorias(ctx):
    return 200, {"categorias": _categorias(ctx.db())}


def criar_categoria(ctx):
    b = ctx.body
    _so_campos(b, {"nome", "cor"})
    nome = _texto(b.get("nome"), "nome", 40)
    conn = ctx.db()
    if "cor" in b:
        cor = _cor(b["cor"])
    else:
        n = conn.execute("SELECT COUNT(*) FROM financas_categorias").fetchone()[0]
        cor = CORES_NOVAS[n % len(CORES_NOVAS)]
    if conn.execute("SELECT COUNT(*) FROM financas_categorias").fetchone()[0] >= 60:
        raise ApiError(400, "demasiadas_categorias", "limite de 60 categorias")
    cur = conn.execute("INSERT INTO financas_categorias (nome, cor) VALUES (?, ?)", (nome, cor))  # UNIQUE -> 409
    return 201, {"id": cur.lastrowid, "nome": nome, "cor": cor}


def atualizar_categoria(ctx):
    cid_ = int(ctx.groups[0])
    b = ctx.body
    _so_campos(b, {"nome", "cor"})
    if not b:
        raise ApiError(400, "sem_alteracoes", "nada para alterar")
    conn = ctx.db()
    atual = conn.execute("SELECT id, nome, cor FROM financas_categorias WHERE id=?", (cid_,)).fetchone()
    if not atual:
        raise ApiError(404, "nao_encontrado", "categoria inexistente")
    nome = _texto(b["nome"], "nome", 40) if "nome" in b else atual["nome"]
    cor = _cor(b["cor"]) if "cor" in b else atual["cor"]
    conn.execute("UPDATE financas_categorias SET nome=?, cor=? WHERE id=?", (nome, cor, cid_))
    return 200, {"id": cid_, "nome": nome, "cor": cor}


def eliminar_categoria(ctx):
    """Só apaga categorias sem lançamentos (a BD recusa com 409 se estiver em uso)."""
    cid_ = int(ctx.groups[0])
    cur = ctx.db().execute("DELETE FROM financas_categorias WHERE id=?", (cid_,))
    if cur.rowcount == 0:
        raise ApiError(404, "nao_encontrado", "categoria inexistente")
    return 200, {"id": cid_}


# --- lançamentos ------------------------------------------------------------

def listar(ctx):
    """Filtros (todos opcionais, combináveis): mes (mes_referencia), de/ate (data_vencimento),
    pendentes=1 (sem data_pagamento), tipo. Pelo menos um filtro de período ou pendentes."""
    q = ctx.query
    _so_campos(q, {"mes", "de", "ate", "pendentes", "tipo"})
    onde, args = [], []
    if "mes" in q:
        onde.append("l.mes_referencia = ?"); args.append(_mes(q["mes"]))
    if "de" in q:
        onde.append("l.data_vencimento >= ?"); args.append(_data(q["de"], "de"))
    if "ate" in q:
        onde.append("l.data_vencimento <= ?"); args.append(_data(q["ate"], "ate"))
    if "tipo" in q:
        onde.append("l.tipo = ?"); args.append(_tipo(q["tipo"]))
    if q.get("pendentes") == "1":
        onde.append("l.data_pagamento IS NULL")
    elif "pendentes" in q:
        raise ApiError(400, "pendentes_invalido", "pendentes só aceita 1")
    if not any(k in q for k in ("mes", "de", "ate", "pendentes")):
        raise ApiError(400, "sem_filtro", "indica mes, de/ate ou pendentes")
    sql = SELECT_LANC + " WHERE " + " AND ".join(onde) + " ORDER BY l.data_vencimento, l.id LIMIT 5000"
    return 200, {"lancamentos": [_lancamento(r) for r in ctx.db().execute(sql, args)]}


def criar(ctx):
    b = ctx.body
    _so_campos(b, CAMPOS_LANC)
    for obrigatorio in ("tipo", "descricao", "valor", "categoria_id", "data_vencimento"):
        if obrigatorio not in b:
            raise ApiError(400, f"{obrigatorio}_em_falta", f"{obrigatorio} é obrigatório")
    conn = ctx.db()
    tipo, descricao, valor = _tipo(b["tipo"]), _texto(b["descricao"], "descricao", 100), _valor(b["valor"])
    venc = _data(b["data_vencimento"], "data_vencimento")
    pag = _data(b["data_pagamento"], "data_pagamento") if b.get("data_pagamento") is not None else None
    rec = _bool01(b["recorrente"]) if "recorrente" in b else 0
    mes = _mes(b["mes_referencia"], "mes_referencia") if "mes_referencia" in b else venc[:7]
    cid_ = _cid(b["cid"]) if b.get("cid") is not None else None
    with _transacao(conn):
        categoria = _categoria_existe(conn, b["categoria_id"])
        if cid_:
            ja = conn.execute(SELECT_LANC + " WHERE l.cid = ?", (cid_,)).fetchone()
            if ja:  # repetição do mesmo pedido: devolve o lançamento já criado
                return 200, _lancamento(ja)
        cur = conn.execute(
            "INSERT INTO financas_lancamentos (tipo, descricao, valor, categoria_id, data_vencimento, "
            "data_pagamento, recorrente, mes_referencia, cid) VALUES (?,?,?,?,?,?,?,?,?)",
            (tipo, descricao, valor, categoria, venc, pag, rec, mes, cid_))
        novo = conn.execute(SELECT_LANC + " WHERE l.id = ?", (cur.lastrowid,)).fetchone()
    return 201, _lancamento(novo)


def atualizar(ctx):
    """Só altera os campos enviados. Mudar a data de vencimento volta a armar o aviso do ntfy."""
    lid = int(ctx.groups[0])
    b = ctx.body
    _so_campos(b, CAMPOS_LANC - {"cid"})
    if not b:
        raise ApiError(400, "sem_alteracoes", "nada para alterar")
    conn = ctx.db()
    sets, args = [], []
    validadores = {"tipo": _tipo, "valor": _valor, "recorrente": _bool01,
                   "descricao": lambda v: _texto(v, "descricao", 100),
                   "data_vencimento": lambda v: _data(v, "data_vencimento"),
                   "mes_referencia": lambda v: _mes(v, "mes_referencia")}
    with _transacao(conn):
        atual = conn.execute("SELECT data_vencimento FROM financas_lancamentos WHERE id=?", (lid,)).fetchone()
        if not atual:
            raise ApiError(404, "nao_encontrado", "lançamento inexistente")
        for campo, v in b.items():
            if campo == "categoria_id":
                v = _categoria_existe(conn, v)
            elif campo == "data_pagamento":
                v = None if v is None else _data(v, "data_pagamento")
            else:
                v = validadores[campo](v)
            sets.append(f"{campo} = ?"); args.append(v)
        if "data_vencimento" in b and b["data_vencimento"] != atual["data_vencimento"]:
            sets.append("notificado_em = NULL")
        conn.execute(f"UPDATE financas_lancamentos SET {', '.join(sets)} WHERE id = ?", args + [lid])
        novo = conn.execute(SELECT_LANC + " WHERE l.id = ?", (lid,)).fetchone()
    return 200, _lancamento(novo)


def eliminar(ctx):
    """Devolve o lançamento apagado (a PWA usa-o para o 'desfazer', voltando a criá-lo)."""
    lid = int(ctx.groups[0])
    conn = ctx.db()
    with _transacao(conn):
        row = conn.execute(SELECT_LANC + " WHERE l.id = ?", (lid,)).fetchone()
        if row:
            conn.execute("DELETE FROM financas_lancamentos WHERE id = ?", (lid,))
    if not row:
        raise ApiError(404, "nao_encontrado", "lançamento inexistente")
    return 200, _lancamento(row)


# --- ciclo mensal -----------------------------------------------------------

def _indice_mes(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:7]) - 1


def _somar_meses(d: str, delta: int) -> str:
    """Desloca uma data ISO `delta` meses, mantendo o dia (ou o último dia do mês, se não existir)."""
    i = int(d[:4]) * 12 + int(d[5:7]) - 1 + delta
    ano, mes = divmod(i, 12)
    mes += 1
    dia = min(int(d[8:10]), calendar.monthrange(ano, mes)[1])
    return f"{ano:04d}-{mes:02d}-{dia:02d}"


def preparar_mes(ctx):
    """Prepara o mês a partir do último mês anterior com lançamentos recorrentes: mesma lista, mesmos
    valores, `data_pagamento` em branco e o vencimento deslocado para o novo mês. Só acontece uma vez
    por mês (fica em financas_meses) e nunca sobre um mês que já tenha lançamentos — apagar de propósito
    o que não se aplica não faz a lista voltar. Pontuais (recorrente=0) não se copiam."""
    mes = _mes(ctx.groups[0])
    hoje = datetime.now(ctx.tz).date()
    if _indice_mes(mes) > hoje.year * 12 + hoje.month:  # no máximo o mês seguinte
        raise ApiError(400, "mes_invalido", "só se prepara até ao mês seguinte")
    conn = ctx.db()
    with _transacao(conn):
        if conn.execute("SELECT 1 FROM financas_meses WHERE mes=?", (mes,)).fetchone():
            return 200, {"mes": mes, "criados": 0, "origem": None, "ja_preparado": True}
        origem, criados = None, 0
        vazio = not conn.execute("SELECT 1 FROM financas_lancamentos WHERE mes_referencia=?", (mes,)).fetchone()
        if vazio:
            r = conn.execute("SELECT MAX(mes_referencia) FROM financas_lancamentos "
                             "WHERE recorrente = 1 AND mes_referencia < ?", (mes,)).fetchone()
            origem = r[0]
        if origem:
            delta = _indice_mes(mes) - _indice_mes(origem)
            for l in conn.execute("SELECT tipo, descricao, valor, categoria_id, data_vencimento FROM financas_lancamentos "
                                  "WHERE mes_referencia = ? AND recorrente = 1 ORDER BY data_vencimento, id", (origem,)).fetchall():
                conn.execute(
                    "INSERT INTO financas_lancamentos (tipo, descricao, valor, categoria_id, data_vencimento, "
                    "data_pagamento, recorrente, mes_referencia) VALUES (?,?,?,?,?,NULL,1,?)",
                    (l["tipo"], l["descricao"], l["valor"], l["categoria_id"],
                     _somar_meses(l["data_vencimento"], delta), mes))
                criados += 1
        conn.execute("INSERT INTO financas_meses (mes, preparado_em) VALUES (?, ?)",
                     (mes, datetime.now(ctx.tz).strftime("%Y-%m-%d %H:%M:%S")))
    return 200, {"mes": mes, "criados": criados, "origem": origem, "ja_preparado": False}


# --- relatórios -------------------------------------------------------------

def agregado(ctx):
    """Totais por mês de referência / tipo / categoria / descrição num intervalo de meses (inclusivo).
    Serve os relatórios mensal, anual, homólogo e o histórico de uma conta (ex.: a luz ao longo dos meses)."""
    q = ctx.query
    _so_campos(q, {"de", "ate"})
    de, ate = _mes(q.get("de"), "de"), _mes(q.get("ate"), "ate")
    if de > ate or _indice_mes(ate) - _indice_mes(de) > 60:
        raise ApiError(400, "intervalo_invalido", "intervalo inválido (máximo 61 meses)")
    rows = ctx.db().execute(
        "SELECT l.mes_referencia AS mes, l.tipo, c.id AS categoria_id, c.nome AS categoria, l.descricao, "
        "ROUND(SUM(l.valor), 2) AS total, COUNT(*) AS n "
        "FROM financas_lancamentos l JOIN financas_categorias c ON c.id = l.categoria_id "
        "WHERE l.mes_referencia BETWEEN ? AND ? "
        "GROUP BY l.mes_referencia, l.tipo, c.id, l.descricao COLLATE NOCASE "
        "ORDER BY l.mes_referencia, l.tipo, c.id LIMIT 5000", (de, ate)).fetchall()
    return 200, {"linhas": [dict(r) for r in rows]}


ROUTES = [
    ("GET", r"^/financas/categorias$", listar_categorias),
    ("POST", r"^/financas/categorias$", criar_categoria),
    ("PUT", r"^/financas/categorias/(\d{1,9})$", atualizar_categoria),
    ("DELETE", r"^/financas/categorias/(\d{1,9})$", eliminar_categoria),
    ("GET", r"^/financas/lancamentos$", listar),
    ("POST", r"^/financas/lancamentos$", criar),
    ("PUT", r"^/financas/lancamentos/(\d{1,12})$", atualizar),
    ("DELETE", r"^/financas/lancamentos/(\d{1,12})$", eliminar),
    ("POST", r"^/financas/meses/(\d{4}-\d{2})/preparar$", preparar_mes),
    ("GET", r"^/financas/agregado$", agregado),
]
