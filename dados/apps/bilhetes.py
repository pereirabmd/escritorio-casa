"""Endpoints da app bilhetes_cp (PWA "Bilhetes CP"). Base de dados própria: `bilhetes.db`.

O Pi (scheduler, hot_buy, pedidos, live_delay) lê e escreve estas tabelas diretamente, em SQL — só a PWA
passa por aqui. Consequências que este módulo respeita:
- o `id` de uma viagem/pedido É o número da viagem no sistema ('v<id>' / 'pedido<id>', parte da chave do
  lock de compra): guardar a semana **preserva os ids** das viagens que continuam a existir (compara por
  data+comboio+hora) — reescrever tudo faria mudar o id e arriscava uma compra dupla a meio de um disparo;
- o Pi escreve o estado dos pedidos; a PWA só mexe em `retry`, `intervalo_minutos` e `forcar`;
- as estações guardam-se pelo NOME (como sempre, ex.: "Lisboa Oriente"); quem as valida é o Pi (3.10.3).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from datetime import date, datetime, timedelta

from api import ApiError

NAME = "bilhetes"
DB = "bilhetes"

MAX_VIAGENS_SEMANA = 100
MAX_LOGS = 1500
PEDIDO_TERMINAL = {"CONFIRMADO", "AMBIGUO"}      # nunca se relançam (nem por Retry nem por Forçar)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _data(v: object, campo: str) -> str:
    if not isinstance(v, str) or not _ISO_RE.match(v):
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ser AAAA-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: data inexistente") from None
    if not 2020 <= d.year <= 2100:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: ano fora de 2020-2100")
    return v


def _estacao(v: object, campo: str) -> str:
    if not isinstance(v, str):
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ser texto")
    v = _CTRL_RE.sub("", v).strip()
    if not 1 <= len(v) <= 60:
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ter 1 a 60 caracteres")
    return v


def _comboio(v: object) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 99999:
        raise ApiError(400, "comboio_invalido", "comboio tem de ser um número inteiro positivo")
    return v


def _hora(v: object) -> str:
    if not isinstance(v, str) or not _HORA_RE.match(v):
        raise ApiError(400, "hora_invalida", "hora tem de ser HH:MM")
    return v


def _so_campos(b: dict, permitidos: set[str]) -> None:
    extra = set(b) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


# --- leitura ------------------------------------------------------------------

def _passe(conn, hoje: date) -> dict:
    p = conn.execute("SELECT data_ultima_compra, validade_dias FROM bilhetes_passe WHERE id=1").fetchone()
    ultima, validade = (p["data_ultima_compra"], p["validade_dias"]) if p else (None, 29)
    if not ultima:
        return {"dataUltimaCompra": None, "validadeDias": validade, "dataExpira": None, "diasRestantes": None}
    expira = date.fromisoformat(ultima) + timedelta(days=validade)   # 30 dias contando o dia do carregamento
    return {"dataUltimaCompra": ultima, "validadeDias": validade, "dataExpira": expira.isoformat(),
            "diasRestantes": (expira - hoje).days}


def _viagem(r) -> dict:
    return {"id": r["id"], "data": r["data"], "origem": r["origem"], "destino": r["destino"],
            "comboio": r["comboio"], "hora": r["hora"], "ativo": r["ativo"]}


def _pedido(r) -> dict:
    return {"id": r["id"], "data": r["data"], "origem": r["origem"], "destino": r["destino"], "comboio": r["comboio"],
            "hora": r["hora"], "ativo": r["ativo"], "retry": r["retry"], "intervaloMinutos": r["intervalo_minutos"],
            "forcar": r["forcar"], "estado": r["estado"], "ultimaTentativa": r["ultima_tentativa"],
            "referencia": r["referencia"], "mensagem": r["mensagem"]}


def dados(ctx):
    conn = ctx.db()
    hoje = datetime.now(ctx.tz).date()
    viagens = conn.execute("SELECT id, data, origem, destino, comboio, hora, ativo FROM bilhetes_viagens "
                           "ORDER BY data, hora, id").fetchall()
    compras = conn.execute("SELECT id, data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia "
                           "FROM bilhetes_compras ORDER BY data, hora_partida, id").fetchall()
    pedidos = conn.execute("SELECT * FROM bilhetes_pedidos ORDER BY id").fetchall()
    logs = conn.execute("SELECT ts, tipo, data_viagem, perna, comboio, status_http, resultado, referencia, mensagem_erro "
                        "FROM bilhetes_logs ORDER BY id DESC LIMIT ?", (MAX_LOGS,)).fetchall()
    return 200, {
        "passe": _passe(conn, hoje),
        "viagens": [_viagem(r) for r in viagens],
        "compras": [{"id": r["id"], "data": r["data"], "comboio": r["comboio"], "origem": r["origem"], "destino": r["destino"],
                     "hora": r["hora_partida"], "carruagem": r["carruagem"], "lugar": r["lugar"], "referencia": r["referencia"]}
                    for r in compras],
        "pedidos": [_pedido(r) for r in pedidos],
        "logs": [{"ts": r["ts"], "tipo": r["tipo"], "data": r["data_viagem"], "perna": r["perna"], "comboio": r["comboio"],
                  "status": r["status_http"], "resultado": r["resultado"], "referencia": r["referencia"],
                  "erro": r["mensagem_erro"]} for r in reversed(logs)],   # do mais antigo para o mais recente
    }


# --- semana -------------------------------------------------------------------

def _viagem_valida(v: object, ini: str, fim: str) -> dict:
    if not isinstance(v, dict):
        raise ApiError(400, "viagem_invalida", "cada viagem tem de ser um objeto")
    _so_campos(v, {"data", "origem", "destino", "comboio", "hora", "ativo"})
    d = _data(v.get("data"), "data")
    if not ini <= d <= fim:
        raise ApiError(400, "data_fora_da_semana", f"{d} não pertence à semana {ini} a {fim}")
    origem, destino = _estacao(v.get("origem"), "origem"), _estacao(v.get("destino"), "destino")
    if origem.lower() == destino.lower():
        raise ApiError(400, "origem_igual_destino", "origem e destino são iguais")
    ativo = v.get("ativo", "SIM")
    if ativo not in ("SIM", "NAO"):
        raise ApiError(400, "ativo_invalido", "ativo tem de ser 'SIM' ou 'NAO'")
    return {"data": d, "origem": origem, "destino": destino, "comboio": _comboio(v.get("comboio")),
            "hora": _hora(v.get("hora")), "ativo": ativo}


def gravar_semana(ctx):
    """Substitui as viagens de [inicio, inicio+6] pelas enviadas, ATOMICAMENTE e preservando os ids.

    Compara por (data, comboio, hora): o que continua a existir mantém o id (e só se atualizam
    origem/destino/ativo); o que desapareceu apaga-se; o que é novo recebe um id novo."""
    _so_campos(ctx.body, {"inicio", "viagens"})
    ini = _data(ctx.body.get("inicio"), "inicio")
    fim = (date.fromisoformat(ini) + timedelta(days=6)).isoformat()
    itens = ctx.body.get("viagens")
    if not isinstance(itens, list) or len(itens) > MAX_VIAGENS_SEMANA:
        raise ApiError(400, "viagens_invalidas", f"viagens tem de ser uma lista de 0 a {MAX_VIAGENS_SEMANA} itens")
    novas = [_viagem_valida(v, ini, fim) for v in itens]
    chaves = [(v["data"], v["comboio"], v["hora"]) for v in novas]
    if len(set(chaves)) != len(chaves):
        raise ApiError(400, "viagem_repetida", "há duas viagens iguais (mesma data, comboio e hora)")

    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        atuais = conn.execute("SELECT id, data, comboio, hora, origem, destino, ativo FROM bilhetes_viagens "
                              "WHERE data >= ? AND data <= ? ORDER BY id", (ini, fim)).fetchall()
        por_chave: dict[tuple, list] = {}
        for r in atuais:
            por_chave.setdefault((r["data"], r["comboio"], r["hora"]), []).append(r)
        manter: set[int] = set()
        for v in novas:
            existentes = por_chave.get((v["data"], v["comboio"], v["hora"]))
            if existentes:
                r = existentes[0]
                manter.add(r["id"])
                if (r["origem"], r["destino"], r["ativo"]) != (v["origem"], v["destino"], v["ativo"]):
                    conn.execute("UPDATE bilhetes_viagens SET origem=?, destino=?, ativo=? WHERE id=?",
                                 (v["origem"], v["destino"], v["ativo"], r["id"]))
            else:
                conn.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo) VALUES (?, ?, ?, ?, ?, ?)",
                             (v["data"], v["origem"], v["destino"], v["comboio"], v["hora"], v["ativo"]))
        for r in atuais:
            if r["id"] not in manter:
                conn.execute("DELETE FROM bilhetes_viagens WHERE id=?", (r["id"],))
        rows = conn.execute("SELECT id, data, origem, destino, comboio, hora, ativo FROM bilhetes_viagens "
                            "WHERE data >= ? AND data <= ? ORDER BY data, hora, id", (ini, fim)).fetchall()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"viagens": [_viagem(r) for r in rows]}


# --- passe --------------------------------------------------------------------

def gravar_passe(ctx):
    """Atualiza a data do último carregamento do passe (antes era editar a célula na Sheet)."""
    _so_campos(ctx.body, {"dataUltimaCompra", "validadeDias"})
    if "dataUltimaCompra" not in ctx.body:
        raise ApiError(400, "dataUltimaCompra_invalida", "dataUltimaCompra é obrigatória")
    ultima = _data(ctx.body["dataUltimaCompra"], "dataUltimaCompra")
    hoje = datetime.now(ctx.tz).date()
    if date.fromisoformat(ultima) > hoje + timedelta(days=1):
        raise ApiError(400, "dataUltimaCompra_invalida", "a data do carregamento não pode estar no futuro")
    conn = ctx.db()
    if "validadeDias" in ctx.body:
        v = ctx.body["validadeDias"]
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 366:
            raise ApiError(400, "validadeDias_invalida", "validadeDias tem de ser um inteiro entre 1 e 366")
        conn.execute("UPDATE bilhetes_passe SET data_ultima_compra=?, validade_dias=? WHERE id=1", (ultima, v))
    else:
        conn.execute("UPDATE bilhetes_passe SET data_ultima_compra=? WHERE id=1", (ultima,))
    return 200, _passe(conn, hoje)


# --- pedidos ------------------------------------------------------------------

def gravar_pedido(ctx):
    """A PWA só controla a repetição automática: `retry` (true/false) e `intervaloMinutos` (1-1440)."""
    pid = int(ctx.groups[0])
    _so_campos(ctx.body, {"retry", "intervaloMinutos"})
    if "retry" not in ctx.body or not isinstance(ctx.body["retry"], bool):
        raise ApiError(400, "retry_invalido", "retry tem de ser true ou false")
    minutos = ctx.body.get("intervaloMinutos")
    if minutos is None:
        minutos_sql = None
    elif isinstance(minutos, bool) or not isinstance(minutos, int) or not 1 <= minutos <= 1440:
        raise ApiError(400, "intervalo_invalido", "intervaloMinutos tem de ser um inteiro entre 1 e 1440")
    else:
        minutos_sql = minutos
    conn = ctx.db()
    cur = conn.execute("UPDATE bilhetes_pedidos SET retry=?, intervalo_minutos=? WHERE id=?",
                       ("SIM" if ctx.body["retry"] else "NAO", minutos_sql, pid))
    if cur.rowcount == 0:
        raise ApiError(404, "nao_encontrado", "pedido inexistente")
    return 200, _pedido(conn.execute("SELECT * FROM bilhetes_pedidos WHERE id=?", (pid,)).fetchone())


def forcar_pedido(ctx):
    """"Tentar agora": marca `forcar=SIM`; o Pi (pedidos.py, a cada minuto) faz uma única tentativa e limpa-o."""
    pid = int(ctx.groups[0])
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        r = conn.execute("SELECT estado FROM bilhetes_pedidos WHERE id=?", (pid,)).fetchone()
        if not r:
            raise ApiError(404, "nao_encontrado", "pedido inexistente")
        if r["estado"] in PEDIDO_TERMINAL:
            raise ApiError(409, "pedido_terminal", "este pedido já não se pode tentar de novo (confirmado ou por confirmar na App CP)")
        conn.execute("UPDATE bilhetes_pedidos SET forcar='SIM' WHERE id=?", (pid,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, _pedido(conn.execute("SELECT * FROM bilhetes_pedidos WHERE id=?", (pid,)).fetchone())


# --- utilizadores (fase 1: só o modelo de dados e a página de administração da LAN) -----------------------------

ADMIN_URL_PADRAO = "http://192.168.68.103:8890/bilhetes"    # a página de administração só abre na rede de casa


_casa = {"ip": None, "ate": 0.0}


def _ip_publico_de_casa() -> str | None:
    """O IP público de casa é o que o DuckDNS aponta para o domínio (o updater do Pi mantém-no). De casa, os pedidos
    ao domínio público chegam ao nginx com esse IP (NAT loopback do router), não com um IP privado."""
    if time.monotonic() > _casa["ate"]:
        try:
            _casa["ip"] = socket.gethostbyname(os.environ.get("ADMIN_BILHETES_HOST", "bmdpereira.duckdns.org"))
        except OSError:
            _casa["ip"] = None
        _casa["ate"] = time.monotonic() + 300
    return _casa["ip"]


def na_lan(ip: str) -> bool:
    """Melhor esforço: IP privado/loopback, ou o IP público de casa. Falha para clientes IPv6 (parecem «fora»)."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or ip == _ip_publico_de_casa()


def _utilizador(ctx):
    return ctx.db().execute("SELECT id, nome, admin, ativo FROM bilhetes_utilizadores WHERE email = ?", (ctx.user,)).fetchone()


def _e_admin(row) -> bool:
    return bool(row and row["admin"] and row["ativo"])


def eu(ctx):
    """Quem sou eu (pelo e-mail Google do token). A PWA só mostra o separador Admin se `admin` for verdadeiro."""
    u = _utilizador(ctx)
    return 200, {"utilizador": {"id": u["id"], "nome": u["nome"]} if u else None, "admin": _e_admin(u)}


def admin_utilizadores(ctx):
    """Resumo SEM dados pessoais nem segredos (só se estão preenchidos) — quem edita é a página da LAN."""
    if not _e_admin(_utilizador(ctx)):
        raise ApiError(403, "so_admin", "só para administradores")
    rows = ctx.db().execute(
        "SELECT id, nome, email, admin, ativo, cp_email <> '' AS cp_email, cp_password_enc <> '' AS cp_password, nif <> '' AS nif, "
        "passe_verde_numero <> '' AS passe_verde, passageiro_cc <> '' AS cc, passe_data_ultima_compra, passe_validade_dias "
        "FROM bilhetes_utilizadores ORDER BY id").fetchall()
    us = []
    for r in rows:
        d = dict(r)
        for k in ("admin", "ativo", "cp_email", "cp_password", "nif", "passe_verde", "cc"):
            d[k] = bool(d[k])
        us.append(d)
    return 200, {"utilizadores": us, "urlAdmin": os.environ.get("ADMIN_BILHETES_URL", ADMIN_URL_PADRAO),
                      "naLan": na_lan(ctx.ip)}


ROUTES = [
    ("GET", r"^/bilhetes/eu$", eu),
    ("GET", r"^/bilhetes/admin/utilizadores$", admin_utilizadores),
    ("GET", r"^/bilhetes/dados$", dados),
    ("PUT", r"^/bilhetes/semana$", gravar_semana),
    ("PUT", r"^/bilhetes/passe$", gravar_passe),
    ("PUT", r"^/bilhetes/pedidos/(\d{1,12})$", gravar_pedido),
    ("POST", r"^/bilhetes/pedidos/(\d{1,12})/forcar$", forcar_pedido),
]
