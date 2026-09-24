"""Endpoints da app convidados (lista do casamento). Tabelas: convidados_lista, convidados_opcoes.

Regras herdadas da PWA e agora garantidas também no servidor:
- só um convidado com Estado "Confirmado" pode ter mesa: mudar o Estado para outro larga a mesa sozinho;
- `data_convite` só se escreve pelo endpoint /convite (a hora vem do servidor), nunca pelo formulário;
- as listas Fase/Estado têm de manter "Confirmado" e "Convidado", de que a lógica da app depende.
"""

from __future__ import annotations

import re
from datetime import datetime

from api import ApiError

NAME = "convidados"

ESTADO_COM_MESA = "Confirmado"
ESTADO_APOS_ENVIO = "Convidado"
MESAS = {str(n) for n in range(1, 11)}
MAX_PESSOAS = 99
MAX_OPCOES = 50
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_TEL_RE = re.compile(r"^[0-9+()\-. ]{0,30}$")

_COLS = "id, nome, pessoas, confirmados, fase, estado, notas, mesa, telefone, data_convite"
CAMPOS = {"nome", "pessoas", "confirmados", "fase", "estado", "notas", "mesa", "telefone"}


def _texto(v: object, campo: str, maximo: int, obrigatorio: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser texto")
    v = _CTRL_RE.sub("", v).strip()
    if len(v) > maximo:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem no máximo {maximo} caracteres")
    if obrigatorio and not v:
        raise ApiError(400, f"{campo}_invalido", f"{campo} é obrigatório")
    return v


def _inteiro(v: object, campo: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_PESSOAS:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser um inteiro entre 0 e {MAX_PESSOAS}")
    return v


def _validar(campo: str, v: object):
    if campo == "nome":
        return _texto(v, "nome", 200, obrigatorio=True)
    if campo in ("pessoas", "confirmados"):
        return _inteiro(v, campo)
    if campo in ("fase", "estado"):
        return _texto(v, campo, 60)
    if campo == "notas":
        return _texto(v, "notas", 1000)
    if campo == "telefone":
        t = _texto(v, "telefone", 30)
        if not _TEL_RE.match(t):
            raise ApiError(400, "telefone_invalido", "telefone só pode ter dígitos, +, espaços, parênteses, - e .")
        return t
    if campo == "mesa":
        m = "" if v is None else v
        if m not in MESAS | {""}:
            raise ApiError(400, "mesa_invalida", "mesa tem de ser '' ou de '1' a '10'")
        return m
    raise AssertionError(campo)


def _json(r) -> dict:
    return {"id": r["id"], "nome": r["nome"], "pessoas": r["pessoas"], "confirmados": r["confirmados"],
            "fase": r["fase"], "estado": r["estado"], "notas": r["notas"], "mesa": r["mesa"],
            "telefone": r["telefone"], "dataConvite": r["data_convite"]}


def _so_campos(b: dict, permitidos: set[str]) -> None:
    extra = set(b) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


def _listar_opcoes(conn, tipo: str) -> list[str]:
    return [r["valor"] for r in conn.execute("SELECT valor FROM convidados_opcoes WHERE tipo=? ORDER BY posicao", (tipo,))]


def dados(ctx):
    conn = ctx.db()
    rows = conn.execute(f"SELECT {_COLS} FROM convidados_lista ORDER BY id").fetchall()
    return 200, {"convidados": [_json(r) for r in rows],
                 "fases": _listar_opcoes(conn, "fase"), "estados": _listar_opcoes(conn, "estado")}


def criar(ctx):
    b = ctx.body
    _so_campos(b, CAMPOS)
    if "nome" not in b:
        raise ApiError(400, "nome_invalido", "nome é obrigatório")
    v = {c: _validar(c, b[c]) for c in b}
    v.setdefault("pessoas", 0); v.setdefault("confirmados", 0)
    for c in ("fase", "estado", "notas", "telefone", "mesa"):
        v.setdefault(c, "")
    if v["mesa"] and v["estado"] != ESTADO_COM_MESA:
        v["mesa"] = ""
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute("INSERT INTO convidados_lista (nome, pessoas, confirmados, fase, estado, notas, mesa, telefone) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (v["nome"], v["pessoas"], v["confirmados"], v["fase"], v["estado"], v["notas"], v["mesa"], v["telefone"]))
        row = conn.execute(f"SELECT {_COLS} FROM convidados_lista WHERE id=?", (cur.lastrowid,)).fetchone()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 201, _json(row)


def atualizar(ctx):
    """Atualiza SÓ os campos enviados (o resto fica como está) e devolve o convidado completo."""
    gid = int(ctx.groups[0])
    b = ctx.body
    _so_campos(b, CAMPOS)
    if not b:
        raise ApiError(400, "sem_campos", "envia pelo menos um campo")
    novos = {c: _validar(c, x) for c, x in b.items()}
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        atual = conn.execute(f"SELECT {_COLS} FROM convidados_lista WHERE id=?", (gid,)).fetchone()
        if not atual:
            raise ApiError(404, "nao_encontrado", "convidado inexistente")
        m = {c: atual[c] for c in CAMPOS}
        m.update(novos)
        if m["estado"] != ESTADO_COM_MESA:
            m["mesa"] = ""   # regra: só Confirmados têm mesa; mudar o estado larga-a
        conn.execute("UPDATE convidados_lista SET nome=?, pessoas=?, confirmados=?, fase=?, estado=?, notas=?, mesa=?, telefone=? WHERE id=?",
                     (m["nome"], m["pessoas"], m["confirmados"], m["fase"], m["estado"], m["notas"], m["mesa"], m["telefone"], gid))
        row = conn.execute(f"SELECT {_COLS} FROM convidados_lista WHERE id=?", (gid,)).fetchone()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, _json(row)


def eliminar(ctx):
    gid = int(ctx.groups[0])
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(f"SELECT {_COLS} FROM convidados_lista WHERE id=?", (gid,)).fetchone()
        if row:
            conn.execute("DELETE FROM convidados_lista WHERE id=?", (gid,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    if not row:
        raise ApiError(404, "nao_encontrado", "convidado inexistente")
    return 200, _json(row)


def registar_convite(ctx):
    """Regista que o convite foi disparado (hora do servidor, no fuso de casa)."""
    gid = int(ctx.groups[0])
    agora = datetime.now(ctx.tz).strftime("%Y-%m-%d %H:%M:%S")
    cur = ctx.db().execute("UPDATE convidados_lista SET data_convite=? WHERE id=?", (agora, gid))
    if cur.rowcount == 0:
        raise ApiError(404, "nao_encontrado", "convidado inexistente")
    return 200, {"id": gid, "dataConvite": agora}


def _lista(v: object, campo: str) -> list[str]:
    if not isinstance(v, list) or not 1 <= len(v) <= MAX_OPCOES:
        raise ApiError(400, f"{campo}_invalidos", f"{campo} tem de ser uma lista de 1 a {MAX_OPCOES} itens")
    limpa = [_texto(x, campo, 60, obrigatorio=True) for x in v]
    if len({x.lower() for x in limpa}) != len(limpa):
        raise ApiError(400, f"{campo}_repetidos", f"{campo} tem itens repetidos")
    return limpa


def gravar_opcoes(ctx):
    """Substitui as listas indicadas (fases e/ou estados), atómico. Os estados têm de manter os dois de que a lógica depende."""
    _so_campos(ctx.body, {"fases", "estados"})
    if not ctx.body:
        raise ApiError(400, "sem_campos", "envia fases e/ou estados")
    novas = {}
    if "fases" in ctx.body:
        novas["fase"] = _lista(ctx.body["fases"], "fases")
    if "estados" in ctx.body:
        novas["estado"] = _lista(ctx.body["estados"], "estados")
        em_falta = {ESTADO_COM_MESA, ESTADO_APOS_ENVIO} - set(novas["estado"])
        if em_falta:
            raise ApiError(400, "estados_obrigatorios", f"os estados têm de incluir {sorted(em_falta)}")
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for tipo, valores in novas.items():
            conn.execute("DELETE FROM convidados_opcoes WHERE tipo=?", (tipo,))
            conn.executemany("INSERT INTO convidados_opcoes (tipo, posicao, valor) VALUES (?, ?, ?)",
                             [(tipo, i, v) for i, v in enumerate(valores)])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"fases": _listar_opcoes(conn, "fase"), "estados": _listar_opcoes(conn, "estado")}


ROUTES = [
    ("GET", r"^/convidados/dados$", dados),
    ("POST", r"^/convidados/lista$", criar),
    ("PUT", r"^/convidados/lista/(\d{1,12})$", atualizar),
    ("DELETE", r"^/convidados/lista/(\d{1,12})$", eliminar),
    ("POST", r"^/convidados/lista/(\d{1,12})/convite$", registar_convite),
    ("PUT", r"^/convidados/opcoes$", gravar_opcoes),
]
