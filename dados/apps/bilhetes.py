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
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import date, datetime, timedelta

from api import ApiError

NAME = "bilhetes"
DB = "bilhetes"

MAX_VIAGENS_SEMANA = 100
MAX_LOGS = 1500
DURACAO_ESTIMADA_MIN = 180                       # a chegada não está guardada: a viagem conta como «em curso» até partida + 3 h
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

def _utilizador(ctx):
    return ctx.db().execute("SELECT id, nome, admin, ativo FROM bilhetes_utilizadores WHERE email = ?", (str(ctx.user).strip().lower(),)).fetchone()


def _e_admin(row) -> bool:
    return bool(row and row["admin"] and row["ativo"])


def _alvo(ctx, pedido: object = None) -> int:
    """De quem são os dados deste pedido (ADR-063, vários utilizadores): da conta que pede, ou (só o administrador, o Bruno) de outra pessoa ativa,
    indicada em `?utilizador=` / `utilizadorId`. Uma conta que não está registada nos Bilhetes não vê nada: nunca assume ser o Bruno."""
    eu = _utilizador(ctx)
    if eu is None or not eu["ativo"]:
        raise ApiError(403, "sem_utilizador", "esta conta não está registada nos Bilhetes")
    if pedido in (None, ""):
        return eu["id"]
    try:
        alvo = int(pedido)
    except (TypeError, ValueError):
        raise ApiError(400, "utilizador_invalido", "utilizador inválido") from None
    if alvo == eu["id"]:
        return alvo
    if not _e_admin(eu):
        raise ApiError(403, "so_admin", "só o administrador marca para outras pessoas")
    if not ctx.db().execute("SELECT 1 FROM bilhetes_utilizadores WHERE id = ? AND ativo = 1", (alvo,)).fetchone():
        raise ApiError(404, "nao_encontrado", "essa pessoa não existe ou está desativada")
    return alvo


def _passe(conn, hoje: date, uid: int = 1) -> dict:
    if uid == 1:
        p = conn.execute("SELECT data_ultima_compra, validade_dias FROM bilhetes_passe WHERE id=1").fetchone()
    else:
        p = conn.execute("SELECT passe_data_ultima_compra AS data_ultima_compra, passe_validade_dias AS validade_dias FROM bilhetes_utilizadores WHERE id=?", (uid,)).fetchone()
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
            "referencia": r["referencia"], "mensagem": r["mensagem"],
            # troca (ADR-083): este pedido troca o bilhete `trocaVenda` (CP) por este comboio, assim que houver lugar
            "trocaVenda": r["troca_venda"], "trocaReferencia": r["troca_referencia"], "trocaAntecedenciaMin": r["troca_antecedencia_min"]}


def dados(ctx):
    conn = ctx.db()
    hoje = datetime.now(ctx.tz).date()
    eu = _utilizador(ctx)
    uid = _alvo(ctx, ctx.query.get("utilizador"))
    viagens = conn.execute("SELECT id, data, origem, destino, comboio, hora, ativo FROM bilhetes_viagens WHERE utilizador_id = ? "
                           "ORDER BY data, hora, id", (uid,)).fetchall()
    compras = conn.execute("SELECT id, data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia "
                           "FROM bilhetes_compras WHERE utilizador_id = ? ORDER BY data, hora_partida, id", (uid,)).fetchall()
    pedidos = conn.execute("SELECT * FROM bilhetes_pedidos WHERE utilizador_id = ? ORDER BY id", (uid,)).fetchall()
    logs = conn.execute("SELECT ts, tipo, data_viagem, perna, comboio, status_http, resultado, referencia, mensagem_erro "
                        "FROM bilhetes_logs WHERE utilizador_id = ? ORDER BY id DESC LIMIT ?", (uid, MAX_LOGS)).fetchall()
    pessoas = [{"id": r["id"], "nome": r["nome"], "eu": r["id"] == eu["id"]} for r in conn.execute("SELECT id, nome FROM bilhetes_utilizadores WHERE ativo = 1 ORDER BY id")] if _e_admin(eu) else []
    nome = conn.execute("SELECT nome FROM bilhetes_utilizadores WHERE id = ?", (uid,)).fetchone()["nome"]
    return 200, {
        "utilizador": {"id": uid, "nome": nome, "eu": uid == eu["id"]}, "pessoas": pessoas,
        "passe": _passe(conn, hoje, uid),
        "viagens": [_viagem(r) for r in viagens],
        "compras": [{"id": r["id"], "data": r["data"], "comboio": r["comboio"], "origem": r["origem"], "destino": r["destino"],
                     "hora": r["hora_partida"], "carruagem": r["carruagem"], "lugar": r["lugar"], "referencia": r["referencia"]}
                    for r in compras],
        "pedidos": [_pedido(r) for r in pedidos],
        "logs": [{"ts": r["ts"], "tipo": r["tipo"], "data": r["data_viagem"], "perna": r["perna"], "comboio": r["comboio"],
                  "status": r["status_http"], "resultado": r["resultado"], "referencia": r["referencia"],
                  "erro": r["mensagem_erro"]} for r in reversed(logs)],   # do mais antigo para o mais recente
    }


def proximo(ctx):
    """A viagem ativa em curso (até à chegada estimada) ou, se não houver, a seguinte com a compra já feita, se houver, e o passe.
    Leve de propósito: é o que o «Hoje» do Pulse precisa, sem os logs nem os pedidos de `/bilhetes/dados`."""
    conn = ctx.db()
    uid = _alvo(ctx)                                       # o «Hoje» é sempre da própria conta
    agora = datetime.now(ctx.tz).replace(tzinfo=None)
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    v = fim = None
    for r in conn.execute("SELECT id, data, origem, destino, comboio, hora, ativo FROM bilhetes_viagens "
                          "WHERE ativo = 'SIM' AND data >= ? AND utilizador_id = ? ORDER BY data, hora, id", (ontem, uid)):
        f = datetime.fromisoformat(f"{r['data']}T{r['hora']}") + timedelta(minutes=DURACAO_ESTIMADA_MIN)
        if f >= agora:                               # ainda não terminou
            v, fim = r, f
            break
    viagem = None
    if v:
        # a compra guarda a hora de embarque e a viagem pode ter a hora a que abre a venda: casa por dia, comboio e percurso (a hora igual tem prioridade)
        c = conn.execute("SELECT carruagem, lugar, referencia FROM bilhetes_compras "
                         "WHERE data = ? AND comboio = ? AND utilizador_id = ? "
                         "AND (hora_partida = ? OR (lower(trim(origem)) = lower(trim(?)) AND lower(trim(destino)) = lower(trim(?)))) "
                         "ORDER BY (hora_partida = ?) DESC, id DESC LIMIT 1",
                         (v["data"], v["comboio"], uid, v["hora"], v["origem"], v["destino"], v["hora"])).fetchone()
        viagem = {**_viagem(v), "fimEstimado": fim.strftime("%H:%M"), "emCurso": fim - timedelta(minutes=DURACAO_ESTIMADA_MIN) <= agora,
                  "compra": {"carruagem": c["carruagem"], "lugar": c["lugar"], "referencia": c["referencia"]} if c else None}
    return 200, {"proximo": viagem, "passe": _passe(conn, agora.date(), uid)}


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
    _so_campos(ctx.body, {"inicio", "viagens", "utilizadorId"})
    uid = _alvo(ctx, ctx.body.get("utilizadorId"))         # o administrador pode marcar para outra pessoa; a compra faz-se com os dados dela
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
                              "WHERE data >= ? AND data <= ? AND utilizador_id = ? ORDER BY id", (ini, fim, uid)).fetchall()
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
                conn.execute("INSERT INTO bilhetes_viagens (data, origem, destino, comboio, hora, ativo, utilizador_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (v["data"], v["origem"], v["destino"], v["comboio"], v["hora"], v["ativo"], uid))
        for r in atuais:
            if r["id"] not in manter:
                conn.execute("DELETE FROM bilhetes_viagens WHERE id=?", (r["id"],))
        rows = conn.execute("SELECT id, data, origem, destino, comboio, hora, ativo FROM bilhetes_viagens "
                            "WHERE data >= ? AND data <= ? AND utilizador_id = ? ORDER BY data, hora, id", (ini, fim, uid)).fetchall()
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 200, {"viagens": [_viagem(r) for r in rows]}


# --- passe --------------------------------------------------------------------

def gravar_passe(ctx):
    """Atualiza a data do último carregamento do passe (antes era editar a célula na Sheet)."""
    _so_campos(ctx.body, {"dataUltimaCompra", "validadeDias", "utilizadorId"})
    uid = _alvo(ctx, ctx.body.get("utilizadorId"))
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
        if uid == 1:
            conn.execute("UPDATE bilhetes_passe SET data_ultima_compra=?, validade_dias=? WHERE id=1", (ultima, v))
        else:
            conn.execute("UPDATE bilhetes_utilizadores SET passe_data_ultima_compra=?, passe_validade_dias=? WHERE id=?", (ultima, v, uid))
    elif uid == 1:                                          # o passe do Bruno vive em `bilhetes_passe` (a base espelha-o para a tabela de utilizadores)
        conn.execute("UPDATE bilhetes_passe SET data_ultima_compra=? WHERE id=1", (ultima,))
    else:
        conn.execute("UPDATE bilhetes_utilizadores SET passe_data_ultima_compra=? WHERE id=?", (ultima, uid))
    return 200, _passe(conn, hoje, uid)


# --- pedidos ------------------------------------------------------------------

def _pedido_acessivel(ctx, pid: int) -> None:
    """O pedido é da conta que pede (ou o administrador mexe em qualquer um); o de outra pessoa responde «inexistente»."""
    eu = _utilizador(ctx)
    if eu is None or not eu["ativo"]:
        raise ApiError(403, "sem_utilizador", "esta conta não está registada nos Bilhetes")
    r = ctx.db().execute("SELECT utilizador_id FROM bilhetes_pedidos WHERE id=?", (pid,)).fetchone()
    if r is None or (r["utilizador_id"] != eu["id"] and not _e_admin(eu)):
        raise ApiError(404, "nao_encontrado", "pedido inexistente")


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
    _pedido_acessivel(ctx, pid)
    cur = conn.execute("UPDATE bilhetes_pedidos SET retry=?, intervalo_minutos=? WHERE id=?",
                       ("SIM" if ctx.body["retry"] else "NAO", minutos_sql, pid))
    if cur.rowcount == 0:
        raise ApiError(404, "nao_encontrado", "pedido inexistente")
    return 200, _pedido(conn.execute("SELECT * FROM bilhetes_pedidos WHERE id=?", (pid,)).fetchone())


def forcar_pedido(ctx):
    """"Tentar agora": marca `forcar=SIM`; o Pi (pedidos.py, a cada minuto) faz uma única tentativa e limpa-o."""
    pid = int(ctx.groups[0])
    conn = ctx.db()
    _pedido_acessivel(ctx, pid)
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
        "passe_verde_numero <> '' AS passe_verde, passageiro_cc <> '' AS cc, passageiro_tipo_doc AS tipo_doc, passe_data_ultima_compra, passe_validade_dias "
        "FROM bilhetes_utilizadores ORDER BY id").fetchall()
    us = []
    for r in rows:
        d = dict(r)
        for k in ("admin", "ativo", "cp_email", "cp_password", "nif", "passe_verde", "cc"):
            d[k] = bool(d[k])
        us.append(d)
    return 200, {"utilizadores": us, "urlAdmin": os.environ.get("ADMIN_BILHETES_URL", ADMIN_URL_PADRAO),
                      "naLan": na_lan(ctx.ip)}


# --- a conta da CP (ADR-075): bilhetes futuros, cancelar e validade do Passe Verde ------------------------------------

_cp_trinco = threading.Lock()            # um pedido à CP de cada vez: duas sessões/logins em simultâneo só dão erros
_cp_cache: dict[tuple, tuple[float, dict]] = {}
CP_CACHE_PASSE_S = 1800


def _cp_python_e_script() -> tuple[str, str]:
    casa = Path(os.environ.get("BILHETES_CP_HOME") or Path.home() / "bilhetes_cp")
    py = casa / ".venv" / "bin" / "python"
    return (str(py) if py.exists() else sys.executable), str(casa / "scripts" / "consulta_cp.py")


def _cp(uid: int, comando: str, venda: int | None = None) -> dict:
    """Corre `bilhetes_cp/scripts/consulta_cp.py` (o código que já sabe falar com a CP, com a sessão e as credenciais da pessoa)."""
    py, script = _cp_python_e_script()
    args = [py, script, "--utilizador", str(uid), comando] + (["--venda", str(venda)] if venda else [])
    with _cp_trinco:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=90, cwd=str(Path(script).parent.parent))
            saida = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except subprocess.TimeoutExpired:
            raise ApiError(409, "cp_lenta", "A CP demorou demasiado a responder. Tenta de novo daqui a pouco.") from None
        except (OSError, ValueError):
            raise ApiError(409, "cp_indisponivel", "Não consegui falar com a CP.") from None
    if saida.get("ok"):
        return saida
    codigo = saida.get("erro", "interno")
    # 4xx de propósito: o Pulse só mostra a mensagem de um 4xx (um 5xx vira «módulo indisponível»)
    raise ApiError(404 if codigo == "nao_encontrado" else 409, f"cp_{codigo}", saida.get("mensagem") or "A CP não respondeu como esperado.")


def cp_futuros(ctx):
    uid = _alvo(ctx, ctx.query.get("utilizador"))
    return 200, {"utilizadorId": uid, "bilhetes": _cp(uid, "futuros")["bilhetes"]}


def cp_passe(ctx):
    uid = _alvo(ctx, ctx.query.get("utilizador"))
    agora = time.monotonic()
    em_cache = _cp_cache.get(("passe", uid))
    if em_cache and agora - em_cache[0] < CP_CACHE_PASSE_S:
        passes = em_cache[1]
    else:
        passes = _cp(uid, "passe")["passes"]
        _cp_cache[("passe", uid)] = (agora, passes)
    hoje = datetime.now(ctx.tz).date()
    for p in passes:
        p["diasRestantes"] = (date.fromisoformat(p["validade"]) - hoje).days if p.get("validade") else None
    return 200, {"utilizadorId": uid, "passes": passes}


def cp_cancelar(ctx):
    """Devolução de um bilhete futuro (a própria pessoa, ou o administrador por ela). Só a venda indicada e só se for futura e da conta dessa pessoa."""
    _so_campos(ctx.body, {"venda", "utilizadorId"})
    uid = _alvo(ctx, ctx.body.get("utilizadorId"))
    venda = ctx.body.get("venda")
    if isinstance(venda, bool) or not isinstance(venda, int) or venda <= 0:
        raise ApiError(400, "venda_invalida", "venda inválida")
    r = _cp(uid, "cancelar", venda)
    ref = r.get("referencia") or ""
    if ref:                                           # o bilhete deixou de existir na CP: tira-o da lista (senão continuava a aparecer como comprado)
        ctx.db().execute("DELETE FROM bilhetes_compras WHERE referencia = ? AND utilizador_id = ?", (ref, uid))
    return 200, {"utilizadorId": uid, **r}


# --- troca de bilhete (ADR-083) -----------------------------------------------------------------------------------------

TROCA_INTERVALO_MIN = 15
TROCA_ANTECEDENCIA_MIN = 30


def criar_troca(ctx):
    """Ativa a troca de um bilhete futuro por outro comboio (mesma data e sentido). Cria um pedido com repetição de 15 em 15 min: o Pi
    reserva o lugar, **cancela o bilhete antigo** e só então confirma o novo; para 30 min antes da partida. Antes de ativar confirma na CP
    (só leitura) que o bilhete existe e que a CP deixa devolvê-lo."""
    _so_campos(ctx.body, {"venda", "comboio", "hora", "utilizadorId"})
    uid = _alvo(ctx, ctx.body.get("utilizadorId"))
    venda, comboio, hora = ctx.body.get("venda"), ctx.body.get("comboio"), ctx.body.get("hora")
    if isinstance(venda, bool) or not isinstance(venda, int) or venda <= 0:
        raise ApiError(400, "venda_invalida", "venda inválida")
    if isinstance(comboio, bool) or not isinstance(comboio, int) or not 1 <= comboio <= 99999:
        raise ApiError(400, "comboio_invalido", "comboio inválido")
    if not isinstance(hora, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
        raise ApiError(400, "hora_invalida", "hora inválida (HH:MM)")
    antigo = next((b for b in _cp(uid, "futuros")["bilhetes"] if b.get("venda") == venda), None)
    if antigo is None:
        raise ApiError(404, "nao_encontrado", "esse bilhete não é um bilhete futuro desta conta")
    if antigo.get("comboio") == comboio:
        raise ApiError(400, "mesmo_comboio", "o comboio novo é o mesmo do bilhete atual")
    if not antigo.get("podeCancelar"):
        raise ApiError(409, "nao_cancelavel", "este bilhete já não pode ser cancelado na CP")
    eleg = _cp(uid, "elegibilidade", venda)
    if not eleg.get("cancelavel"):
        raise ApiError(409, "nao_cancelavel", eleg.get("motivo") or "a CP não deixa devolver este bilhete; não ativei a troca")
    conn = ctx.db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM bilhetes_pedidos WHERE troca_venda = ? AND ativo = 'SIM' AND estado NOT IN ('CONFIRMADO', 'AMBIGUO', 'EXPIRADO')", (venda,)).fetchone():
            raise ApiError(409, "troca_ja_ativa", "já há uma troca ativa para este bilhete")
        cur = conn.execute("INSERT INTO bilhetes_pedidos (data, origem, destino, comboio, hora, ativo, retry, intervalo_minutos, forcar, estado, utilizador_id, "
                           "troca_venda, troca_referencia, troca_antecedencia_min) VALUES (?,?,?,?,?, 'SIM', 'SIM', ?, 'NAO', 'PENDENTE', ?, ?, ?, ?)",
                           (antigo["data"], antigo["origem"], antigo["destino"], comboio, hora, TROCA_INTERVALO_MIN, uid, venda,
                            antigo.get("referencia") or eleg.get("referencia") or "", TROCA_ANTECEDENCIA_MIN))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return 201, _pedido(conn.execute("SELECT * FROM bilhetes_pedidos WHERE id = ?", (cur.lastrowid,)).fetchone())


def desarmar_troca(ctx):
    """Desliga uma troca ainda por fazer: o pedido deixa de tentar e o bilhete antigo mantém-se (não se cancela nada)."""
    pid = int(ctx.groups[0])
    conn = ctx.db()
    _pedido_acessivel(ctx, pid)
    r = conn.execute("SELECT troca_venda, estado FROM bilhetes_pedidos WHERE id = ?", (pid,)).fetchone()
    if not r or not r["troca_venda"]:
        raise ApiError(404, "nao_encontrado", "troca inexistente")
    if r["estado"] in PEDIDO_TERMINAL:
        raise ApiError(409, "troca_concluida", "esta troca já terminou")
    conn.execute("UPDATE bilhetes_pedidos SET ativo = 'NAO', forcar = 'NAO', estado = 'DESARMADO', mensagem = 'Troca desativada: mantém-se o bilhete antigo.' WHERE id = ?", (pid,))
    return 200, _pedido(conn.execute("SELECT * FROM bilhetes_pedidos WHERE id = ?", (pid,)).fetchone())


ROUTES = [
    ("GET", r"^/bilhetes/cp/futuros$", cp_futuros),
    ("GET", r"^/bilhetes/cp/passe$", cp_passe),
    ("POST", r"^/bilhetes/cp/cancelar$", cp_cancelar),
    ("POST", r"^/bilhetes/trocas$", criar_troca),
    ("DELETE", r"^/bilhetes/trocas/(\d{1,12})$", desarmar_troca),
    ("GET", r"^/bilhetes/eu$", eu),
    ("GET", r"^/bilhetes/admin/utilizadores$", admin_utilizadores),
    ("GET", r"^/bilhetes/dados$", dados),
    ("GET", r"^/bilhetes/proximo$", proximo),
    ("PUT", r"^/bilhetes/semana$", gravar_semana),
    ("PUT", r"^/bilhetes/passe$", gravar_passe),
    ("PUT", r"^/bilhetes/pedidos/(\d{1,12})$", gravar_pedido),
    ("POST", r"^/bilhetes/pedidos/(\d{1,12})/forcar$", forcar_pedido),
]
