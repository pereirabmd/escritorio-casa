"""Endpoints da app tarefas (Tarefas de Casa). Tabelas: tarefas_tarefas, tarefas_instancias, tarefas_config,
tarefas_piscina, tarefas_auditoria, tarefas_horario (só leitura).

O Pi (instancias.py, recalcular.py, manutencao.py, servidor.py) lê e escreve as MESMAS tabelas em SQL direto
(`tarefas/pi/store.py`); a notificação agendada no ntfy e os botões "Marcar feita"/"Daqui a 1h" continuam a
falar com o `servidor.py` do Pi (URLs já embutidos em mensagens agendadas). Por aqui passa só a PWA.

Regras que este módulo garante e a PWA sozinha não garantia:
- (tarefa, data) é único: nunca duas ocorrências da mesma tarefa no mesmo dia (a chave de idempotência do gerador);
- ids gerados no servidor (nunca `Date.now()` do telemóvel) e dentro de uma transação;
- a password ntfy cifrada nunca sai do servidor (a PWA só vê que "existe") nem se escreve por aqui;
- operações compostas (apagar tarefa, reatribuir/renomear pessoa, concluir várias atrasadas) são atómicas.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone

from api import ApiError

NAME = "tarefas"

DIAS = ("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab")
RECORRENCIAS = ("Diaria", "Semanal", "Dias especificos", "Mensal", "Trimestral", "Semestral", "Pontual")
COM_DATA = ("Pontual", "Trimestral", "Semestral")          # `dias_semana` guarda uma data ISO
COM_DIAS = ("Semanal", "Dias especificos")
ESTADOS = ("Pendente", "Feita", "Saltada", "Atrasada")
PRIORIDADES = ("Alta", "Media", "Baixa")
MAX_LOTE = 500
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CONCL = re.compile(r"^\d{4}-\d{2}-\d{2} ([01]\d|2[0-3]):[0-5]\d$")
_CHAVE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
_SEGREDO = re.compile(r"_NtfyPasswordEnc$")
MASCARA = "********"

# --- administração --------------------------------------------------------------
# Administrador "fixo": vem do .env (ADMIN_TAREFAS) e não se remove pela app. Os restantes ficam em Config.Admins
# (e-mails de pessoas registadas). Só admins leem/alteram estas definições, e a Config genérica não lhes toca.
ADMIN_RAIZ_PADRAO = "pereirabmd@gmail.com"
# Notificações "gerais" (sem responsável): quem recebe cada uma escolhe-se no painel. Config `Notif_<id>`:
# ausente = padrão, "-" = ninguém, "Bruno,Camila" = essas pessoas. O Pi lê as mesmas chaves (tarefas/pi/common.py:
# destinatarios_geral) — alterar aqui = alterar lá.
NOTIFICACOES_GERAIS = {
    "piscina": {"nome": "Piscina", "descricao": "Sugestão de manutenção da piscina (hora padrão do dia)."},
    "horario": {"nome": "Horário escolar", "descricao": "Aviso antes de acabar a última aula do dia."},
}
_RESERVADA = re.compile(r"^(Admins|Notif_.*)$")
_EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


# --- validação ------------------------------------------------------------------

def _txt(v, campo: str, maximo: int, obrigatorio: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser texto")
    v = _CTRL.sub("", v).strip()
    if len(v) > maximo:
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem no máximo {maximo} caracteres")
    if obrigatorio and not v:
        raise ApiError(400, f"{campo}_invalido", f"{campo} é obrigatório")
    return v


def _data(v, campo: str, opcional: bool = False):
    if v in (None, ""):
        if opcional:
            return None
        raise ApiError(400, f"{campo}_invalida", f"{campo} obrigatória")
    if not isinstance(v, str) or not _ISO.match(v):
        raise ApiError(400, f"{campo}_invalida", f"{campo} tem de ser AAAA-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: data inexistente") from None
    if not 2000 <= d.year <= 2100:
        raise ApiError(400, f"{campo}_invalida", f"{campo}: ano fora de 2000-2100")
    return v


def _bool(v, campo: str) -> int:
    if not isinstance(v, bool):
        raise ApiError(400, f"{campo}_invalido", f"{campo} tem de ser true ou false")
    return 1 if v else 0


def _so(b: dict, permitidos: set[str]) -> None:
    extra = set(b) - permitidos
    if extra:
        raise ApiError(400, "campos_desconhecidos", f"campos não aceites: {sorted(extra)[:5]}")


def _agora_local(ctx) -> str:
    return datetime.now(ctx.tz).strftime("%Y-%m-%d %H:%M")


def _tx(conn):
    """Contexto simples: BEGIN IMMEDIATE ... COMMIT/ROLLBACK."""
    class _T:
        def __enter__(s):
            conn.execute("BEGIN IMMEDIATE")
        def __exit__(s, tipo, *_):
            conn.execute("ROLLBACK" if tipo else "COMMIT")
    return _T()


# --- representações -------------------------------------------------------------

def _tarefa_json(r) -> dict:
    return {"id": r["id"], "nome": r["nome"], "categoria": r["categoria"], "icone": r["icone"],
            "recorrencia": r["recorrencia"], "diasSemana": r["dias_semana"], "diaMes": r["dia_mes"],
            "horaNotificacao": r["hora_notificacao"], "pessoaPadrao": r["pessoa_padrao"], "ativa": bool(r["ativa"]),
            "prioridade": r["prioridade"], "rotacaoPessoas": r["rotacao_pessoas"], "dependeDe": r["depende_de"]}


def _inst_json(r) -> dict:
    return {"id": r["id"], "tarefaId": r["tarefa_id"], "data": r["data"], "pessoa": r["pessoa"], "estado": r["estado"],
            "dataConclusao": r["data_conclusao"], "notificacaoEnviada": bool(r["notificacao_enviada"])}


def _piscina_json(r) -> dict:
    return {"id": r["id"], "nome": r["nome"], "avisoLongo": bool(r["aviso_longo"]), "ultimaData": r["ultima_data"],
            "proximaData": r["proxima_data"], "notificacaoEnviada": bool(r["notificacao_enviada"]),
            "usarIntervaloLongo": bool(r["usar_intervalo_longo"])}


def _config_json(r) -> dict:
    # a password ntfy cifrada nunca sai: a PWA só precisa de saber que existe
    valor = MASCARA if (_SEGREDO.search(r["chave"]) and r["valor"]) else r["valor"]
    return {"chave": r["chave"], "valor": valor, "notas": r["notas"]}


def _tarefa(conn, tid: str):
    r = conn.execute("SELECT * FROM tarefas_tarefas WHERE id=?", (tid,)).fetchone()
    if not r:
        raise ApiError(404, "nao_encontrado", "tarefa inexistente")
    return r


def _proximo(conn, tabela: str, prefixo: str, largura: int) -> str:
    maximo = 0
    for (i,) in conn.execute(f"SELECT id FROM {tabela}"):
        digitos = re.sub(r"\D", "", i)
        if digitos:
            maximo = max(maximo, int(digitos))
    return f"{prefixo}{maximo + 1:0{largura}d}"


# --- leitura --------------------------------------------------------------------

def _config(conn) -> dict[str, str]:
    return {r["chave"]: r["valor"] for r in conn.execute("SELECT chave, valor FROM tarefas_config")}


def _pessoas(cfg: dict[str, str]) -> list[dict]:
    out = []
    for k, v in cfg.items():
        m = re.fullmatch(r"Pessoa(\d+)_Nome", k)
        if m and v.strip():
            n = m.group(1)
            user = cfg.get(f"Pessoa{n}_NtfyUser", "").strip().lower()
            out.append({"num": int(n), "nome": v.strip(), "email": cfg.get(f"Pessoa{n}_Email", "").strip().lower(),
                        "ntfyUser": user, "topico": (user if user.startswith("tarefas_") else f"tarefas_{user}") if user else ""})
    return sorted(out, key=lambda p: p["num"])


def _raiz() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("ADMIN_TAREFAS", ADMIN_RAIZ_PADRAO).split(",") if e.strip()}


def _admins(cfg: dict[str, str]) -> set[str]:
    extra = {e.strip().lower() for e in cfg.get("Admins", "").split(",") if e.strip()}
    return _raiz() | extra


def _exigir_admin(ctx, cfg=None) -> dict[str, str]:
    cfg = cfg if cfg is not None else _config(ctx.db())
    if ctx.user.lower() not in _admins(cfg):
        raise ApiError(403, "so_admin", "só os administradores podem ver ou alterar isto")
    return cfg


def _destinatarios(cfg: dict[str, str], tipo: str, pessoas: list[dict]) -> tuple[list[str], bool]:
    """(nomes que recebem, é_padrão). Igual a `destinatarios_geral` do Pi."""
    bruto = cfg.get(f"Notif_{tipo}", "").strip()
    nomes = [p["nome"] for p in pessoas]
    if not bruto:
        return (nomes, True)   # padrão do painel (horário: no Pi o padrão é a pessoa do aluno; ver _painel)
    if bruto == "-":
        return ([], False)
    return ([n.strip() for n in bruto.split(",") if n.strip() in nomes], False)


def _painel(conn) -> dict:
    cfg = _config(conn)
    pessoas = _pessoas(cfg)
    admins = _admins(cfg)
    alunos = sorted({r[0] for r in conn.execute("SELECT DISTINCT aluno FROM tarefas_horario")})
    nomes = [p["nome"] for p in pessoas]
    notifs = []
    for tipo, meta in NOTIFICACOES_GERAIS.items():
        dest, padrao = _destinatarios(cfg, tipo, pessoas)
        if padrao and tipo == "horario":
            dest = [a for a in alunos if a in nomes]           # padrão do horário: a pessoa com o nome do aluno
        notifs.append({"id": tipo, "nome": meta["nome"], "descricao": meta["descricao"], "destinatarios": dest, "padrao": padrao})
    return {
        "raiz": sorted(_raiz()),
        "admins": sorted(admins),
        "pessoas": [dict(p, admin=p["email"] in admins, fixo=p["email"] in _raiz()) for p in pessoas],
        "notificacoes": notifs,
    }


def admin_ver(ctx):
    _exigir_admin(ctx)
    return 200, _painel(ctx.db())


def admin_gravar(ctx):
    b = ctx.body
    _so(b, {"admins", "notificacoes"})
    conn = ctx.db()
    cfg = _exigir_admin(ctx)
    pessoas = _pessoas(cfg)
    nomes = {p["nome"] for p in pessoas}
    if "admins" not in b and "notificacoes" not in b:
        raise ApiError(400, "vazio", "envia admins e/ou notificacoes")
    novos: dict[str, str] = {}
    if "admins" in b:
        lista = b["admins"]
        emails_pessoas = {p["email"] for p in pessoas if p["email"]}
        if not isinstance(lista, list) or not all(isinstance(e, str) for e in lista) or len(lista) > 20:
            raise ApiError(400, "admins_invalido", "admins tem de ser uma lista de e-mails")
        escolhidos = {e.strip().lower() for e in lista} - _raiz()
        desconhecidos = escolhidos - emails_pessoas
        if desconhecidos:
            raise ApiError(400, "admin_desconhecido", "só se pode escolher quem está registado com e-mail nas pessoas: " + ", ".join(sorted(desconhecidos)))
        novos["Admins"] = ",".join(sorted(escolhidos))
    if "notificacoes" in b:
        nt = b["notificacoes"]
        if not isinstance(nt, dict) or not set(nt) <= set(NOTIFICACOES_GERAIS):
            raise ApiError(400, "notificacoes_invalido", "notificacoes: objeto com " + ", ".join(NOTIFICACOES_GERAIS))
        for tipo, lista in nt.items():
            if not isinstance(lista, list) or not all(isinstance(n, str) for n in lista):
                raise ApiError(400, "notificacoes_invalido", f"{tipo}: lista de nomes")
            if set(lista) - nomes:
                raise ApiError(400, "pessoa_desconhecida", f"{tipo}: pessoa desconhecida: " + ", ".join(sorted(set(lista) - nomes)))
            if any("," in n for n in lista):
                raise ApiError(400, "nome_invalido", "nomes com vírgula não são suportados")
            novos[f"Notif_{tipo}"] = ",".join(sorted(set(lista), key=lista.index)) or "-"
    with _tx(conn):
        for k, v in novos.items():
            conn.execute("INSERT INTO tarefas_config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, v))
        conn.execute("INSERT INTO tarefas_auditoria (ts, acao, tarefa, pessoa, instancia_id) VALUES (?, ?, ?, ?, '')",
                     (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "admin", ", ".join(sorted(novos))[:200], ctx.user[:60]))
    return 200, _painel(conn)


def dados(ctx):
    conn = ctx.db()
    return 200, {
        "souAdmin": ctx.user.lower() in _admins(_config(conn)),
        "tarefas": [_tarefa_json(r) for r in conn.execute("SELECT * FROM tarefas_tarefas ORDER BY rowid")],
        "instancias": [_inst_json(r) for r in conn.execute("SELECT * FROM tarefas_instancias ORDER BY rowid")],
        "config": [_config_json(r) for r in conn.execute("SELECT * FROM tarefas_config ORDER BY rowid")],
        "piscina": [_piscina_json(r) for r in conn.execute("SELECT * FROM tarefas_piscina ORDER BY rowid")],
    }


def horario(ctx):
    """Horário escolar (só leitura: importa-se com importar_horario.py). Aulas do mesmo dia e hora são a turma dividida."""
    rows = ctx.db().execute(
        "SELECT id, aluno, ano_letivo, dia_semana, hora_inicio, hora_fim, disciplina, sala FROM tarefas_horario "
        "ORDER BY ano_letivo, aluno, dia_semana, hora_inicio, hora_fim, disciplina")
    return 200, {"aulas": [{"id": r["id"], "aluno": r["aluno"], "anoLetivo": r["ano_letivo"], "diaSemana": r["dia_semana"],
                            "horaInicio": r["hora_inicio"], "horaFim": r["hora_fim"], "disciplina": r["disciplina"],
                            "sala": r["sala"]} for r in rows]}


def auditoria(ctx):
    try:
        limite = int(ctx.query.get("limite", "10"))
    except ValueError:
        raise ApiError(400, "limite_invalido", "limite tem de ser um inteiro") from None
    if not 1 <= limite <= 200:
        raise ApiError(400, "limite_invalido", "limite entre 1 e 200")
    rows = ctx.db().execute("SELECT ts, acao, tarefa, pessoa, instancia_id FROM tarefas_auditoria ORDER BY id DESC LIMIT ?", (limite,))
    return 200, {"entradas": [{"ts": r["ts"], "acao": r["acao"], "tarefa": r["tarefa"], "pessoa": r["pessoa"],
                               "instanciaId": r["instancia_id"]} for r in rows]}


def registar_auditoria(ctx):
    b = ctx.body
    _so(b, {"acao", "tarefa", "pessoa", "instanciaId"})
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    ctx.db().execute("INSERT INTO tarefas_auditoria (ts, acao, tarefa, pessoa, instancia_id) VALUES (?, ?, ?, ?, ?)",
                     (ts, _txt(b.get("acao"), "acao", 60, True), _txt(b.get("tarefa"), "tarefa", 200),
                      _txt(b.get("pessoa"), "pessoa", 60), _txt(b.get("instanciaId"), "instanciaId", 30)))
    return 201, {"ok": True}


# --- tarefas --------------------------------------------------------------------

_CAMPOS_TAREFA = {"nome", "categoria", "icone", "recorrencia", "diasSemana", "diaMes", "horaNotificacao",
                  "pessoaPadrao", "ativa", "prioridade", "rotacaoPessoas", "dependeDe"}


def _normalizar_tarefa(conn, m: dict, propria_id: str | None) -> dict:
    """Valida o estado FINAL de uma tarefa (já fundido com o que estava) e devolve as colunas prontas."""
    rec = m["recorrencia"]
    if rec not in RECORRENCIAS:
        raise ApiError(400, "recorrencia_invalida", f"recorrencia tem de ser uma de {list(RECORRENCIAS)}")
    dias, dia_mes = "", None
    if rec in COM_DIAS:
        lista = [d.strip() for d in str(m["diasSemana"]).split(",") if d.strip()]
        if not lista or any(d not in DIAS for d in lista) or len(set(lista)) != len(lista):
            raise ApiError(400, "diasSemana_invalidos", f"escolhe dias entre {list(DIAS)}")
        dias = ",".join(lista)
    elif rec in COM_DATA:
        dias = _data(m["diasSemana"], "diasSemana")
    elif rec == "Mensal":
        d = m["diaMes"]
        if isinstance(d, bool) or not isinstance(d, int) or not 1 <= d <= 31:
            raise ApiError(400, "diaMes_invalido", "diaMes tem de ser um inteiro de 1 a 31")
        dia_mes = d
    hora = m["horaNotificacao"] or ""
    if hora and not _HORA.match(hora):
        raise ApiError(400, "horaNotificacao_invalida", "horaNotificacao tem de ser HH:MM (ou vazia)")
    prio = m["prioridade"]
    if prio not in PRIORIDADES:
        raise ApiError(400, "prioridade_invalida", f"prioridade tem de ser uma de {list(PRIORIDADES)}")
    dep = _txt(m["dependeDe"], "dependeDe", 12)
    if dep:
        if dep == propria_id:
            raise ApiError(400, "dependeDe_invalido", "uma tarefa não pode depender de si própria")
        if not conn.execute("SELECT 1 FROM tarefas_tarefas WHERE id=?", (dep,)).fetchone():
            raise ApiError(400, "dependeDe_invalido", "a tarefa de que depende não existe")
    return {"nome": _txt(m["nome"], "nome", 200, True), "categoria": _txt(m["categoria"], "categoria", 60),
            "icone": _txt(m["icone"], "icone", 8), "recorrencia": rec, "dias_semana": dias, "dia_mes": dia_mes,
            "hora": hora, "pessoa": _txt(m["pessoaPadrao"], "pessoaPadrao", 60), "ativa": _bool(m["ativa"], "ativa"),
            "prioridade": prio, "rotacao": _txt(m["rotacaoPessoas"], "rotacaoPessoas", 200), "depende": dep}


_PADRAO_TAREFA = {"categoria": "", "icone": "", "diasSemana": "", "diaMes": None, "horaNotificacao": "", "pessoaPadrao": "",
                  "ativa": True, "prioridade": "Media", "rotacaoPessoas": "", "dependeDe": ""}


def criar_tarefa(ctx):
    b = ctx.body
    _so(b, _CAMPOS_TAREFA)
    for obrigatorio in ("nome", "recorrencia"):
        if obrigatorio not in b:
            raise ApiError(400, f"{obrigatorio}_invalido", f"{obrigatorio} é obrigatório")
    conn = ctx.db()
    with _tx(conn):
        n = _normalizar_tarefa(conn, {**_PADRAO_TAREFA, **b}, None)
        tid = _proximo(conn, "tarefas_tarefas", "T", 3)
        conn.execute("INSERT INTO tarefas_tarefas (id, nome, categoria, icone, recorrencia, dias_semana, dia_mes, hora_notificacao, "
                     "pessoa_padrao, ativa, prioridade, rotacao_pessoas, depende_de) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (tid, n["nome"], n["categoria"], n["icone"], n["recorrencia"], n["dias_semana"], n["dia_mes"], n["hora"],
                      n["pessoa"], n["ativa"], n["prioridade"], n["rotacao"], n["depende"]))
        instancia = None
        if n["recorrencia"] == "Pontual" and n["ativa"]:
            # tarefas pontuais não passam pelo gerador: a única ocorrência cria-se já, na data escolhida
            iid = _proximo(conn, "tarefas_instancias", "I", 4)
            conn.execute("INSERT INTO tarefas_instancias (id, tarefa_id, data, pessoa, estado) VALUES (?, ?, ?, ?, 'Pendente')",
                         (iid, tid, n["dias_semana"], n["pessoa"]))
            instancia = _inst_json(conn.execute("SELECT * FROM tarefas_instancias WHERE id=?", (iid,)).fetchone())
        tarefa = _tarefa_json(_tarefa(conn, tid))
    return 201, {"tarefa": tarefa, "instancia": instancia}


def atualizar_tarefa(ctx):
    tid = ctx.groups[0]
    b = ctx.body
    _so(b, _CAMPOS_TAREFA)
    if not b:
        raise ApiError(400, "sem_campos", "envia pelo menos um campo")
    conn = ctx.db()
    with _tx(conn):
        atual = _tarefa_json(_tarefa(conn, tid))
        n = _normalizar_tarefa(conn, {**atual, **b}, tid)
        conn.execute("UPDATE tarefas_tarefas SET nome=?, categoria=?, icone=?, recorrencia=?, dias_semana=?, dia_mes=?, hora_notificacao=?, "
                     "pessoa_padrao=?, ativa=?, prioridade=?, rotacao_pessoas=?, depende_de=? WHERE id=?",
                     (n["nome"], n["categoria"], n["icone"], n["recorrencia"], n["dias_semana"], n["dia_mes"], n["hora"],
                      n["pessoa"], n["ativa"], n["prioridade"], n["rotacao"], n["depende"], tid))
        tarefa = _tarefa_json(_tarefa(conn, tid))
    return 200, {"tarefa": tarefa}


def apagar_tarefa(ctx):
    """"Apagar" é desativar (o histórico mantém-se) e saltar o que ainda estava por fazer, tudo de uma vez."""
    tid = ctx.groups[0]
    conn = ctx.db()
    with _tx(conn):
        _tarefa(conn, tid)
        conn.execute("UPDATE tarefas_tarefas SET ativa=0 WHERE id=?", (tid,))
        cur = conn.execute("UPDATE tarefas_instancias SET estado='Saltada' WHERE tarefa_id=? AND estado IN ('Pendente', 'Atrasada')", (tid,))
    return 200, {"id": tid, "saltadas": cur.rowcount}


# --- instâncias -----------------------------------------------------------------

_CAMPOS_INST = {"estado", "dataConclusao", "data", "pessoa"}


def _aplicar_inst(conn, iid: str, b: dict):
    r = conn.execute("SELECT * FROM tarefas_instancias WHERE id=?", (iid,)).fetchone()
    if not r:
        raise ApiError(404, "nao_encontrado", f"instância {iid} inexistente")
    estado = b.get("estado", r["estado"])
    if estado not in ESTADOS:
        raise ApiError(400, "estado_invalido", f"estado tem de ser um de {list(ESTADOS)}")
    concl = b.get("dataConclusao", r["data_conclusao"]) or ""
    if concl and not _CONCL.match(concl):
        raise ApiError(400, "dataConclusao_invalida", "dataConclusao tem de ser 'AAAA-MM-DD HH:MM' (ou vazia)")
    data = _data(b["data"], "data") if "data" in b else r["data"]
    pessoa = _txt(b["pessoa"], "pessoa", 60) if "pessoa" in b else r["pessoa"]
    try:
        conn.execute("UPDATE tarefas_instancias SET estado=?, data_conclusao=?, data=?, pessoa=? WHERE id=?",
                     (estado, concl, data, pessoa, iid))
    except Exception as e:                     # UNIQUE(tarefa_id, data): reagendar para um dia em que já há uma
        if "UNIQUE" in str(e):
            raise ApiError(409, "conflito", "essa tarefa já tem uma ocorrência nesse dia") from None
        raise


def atualizar_instancia(ctx):
    iid = ctx.groups[0]
    _so(ctx.body, _CAMPOS_INST)
    if not ctx.body:
        raise ApiError(400, "sem_campos", "envia pelo menos um campo")
    conn = ctx.db()
    with _tx(conn):
        _aplicar_inst(conn, iid, ctx.body)
        r = conn.execute("SELECT * FROM tarefas_instancias WHERE id=?", (iid,)).fetchone()
    return 200, {"instancia": _inst_json(r)}


def atualizar_instancias(ctx):
    """Lote atómico: [{id, estado?, dataConclusao?, data?, pessoa?}] — p. ex. concluir uma tarefa atrasada e as
    ocorrências atrasadas anteriores da mesma tarefa. Tudo ou nada."""
    _so(ctx.body, {"atualizacoes"})
    itens = ctx.body.get("atualizacoes")
    if not isinstance(itens, list) or not 1 <= len(itens) <= MAX_LOTE:
        raise ApiError(400, "atualizacoes_invalidas", f"atualizacoes tem de ter de 1 a {MAX_LOTE} itens")
    conn = ctx.db()
    with _tx(conn):
        for it in itens:
            if not isinstance(it, dict) or not isinstance(it.get("id"), str):
                raise ApiError(400, "atualizacao_invalida", "cada item precisa de um id")
            campos = {k: v for k, v in it.items() if k != "id"}
            _so(campos, _CAMPOS_INST)
            _aplicar_inst(conn, it["id"], campos)
        ids = [it["id"] for it in itens]
        marcas = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT * FROM tarefas_instancias WHERE id IN ({marcas})", ids).fetchall()
    return 200, {"instancias": [_inst_json(r) for r in rows]}


def criar_instancia(ctx):
    b = ctx.body
    _so(b, {"tarefaId", "data", "pessoa"})
    conn = ctx.db()
    with _tx(conn):
        tid = _txt(b.get("tarefaId"), "tarefaId", 12, True)
        _tarefa(conn, tid)
        data = _data(b.get("data"), "data")
        iid = _proximo(conn, "tarefas_instancias", "I", 4)
        try:
            conn.execute("INSERT INTO tarefas_instancias (id, tarefa_id, data, pessoa, estado) VALUES (?, ?, ?, ?, 'Pendente')",
                         (iid, tid, data, _txt(b.get("pessoa"), "pessoa", 60)))
        except Exception as e:
            if "UNIQUE" in str(e):
                raise ApiError(409, "conflito", "essa tarefa já tem uma ocorrência nesse dia") from None
            raise
        r = conn.execute("SELECT * FROM tarefas_instancias WHERE id=?", (iid,)).fetchone()
    return 201, {"instancia": _inst_json(r)}


# --- pessoas --------------------------------------------------------------------

def _trocar_na_lista(lista: str, de: str, para: str) -> str:
    nomes = [n.strip() for n in lista.split(",") if n.strip()]
    novos = []
    for n in nomes:
        n = para if n == de else n
        if n not in novos:
            novos.append(n)
    return ",".join(novos)


def reatribuir(ctx):
    """Passa tarefas e ocorrências de uma pessoa para outra (renomear, remover com substituto, reatribuir em massa).
    `apenasPendentes`: não mexe nas ocorrências já Feitas (histórico). `configChave`: no mesmo passo, o nome novo
    passa a ser o valor dessa chave (renomear a pessoa)."""
    b = ctx.body
    _so(b, {"de", "para", "apenasPendentes", "configChave"})
    de, para = _txt(b.get("de"), "de", 60, True), _txt(b.get("para"), "para", 60, True)
    if de == para:
        raise ApiError(400, "pessoas_iguais", "de e para são iguais")
    apenas = _bool(b.get("apenasPendentes", False), "apenasPendentes")
    conn = ctx.db()
    with _tx(conn):
        n_t = conn.execute("UPDATE tarefas_tarefas SET pessoa_padrao=? WHERE pessoa_padrao=?", (para, de)).rowcount
        for r in conn.execute("SELECT id, rotacao_pessoas FROM tarefas_tarefas WHERE rotacao_pessoas <> ''").fetchall():
            novo = _trocar_na_lista(r["rotacao_pessoas"], de, para)
            if novo != r["rotacao_pessoas"]:
                conn.execute("UPDATE tarefas_tarefas SET rotacao_pessoas=? WHERE id=?", (novo, r["id"]))
        sql = "UPDATE tarefas_instancias SET pessoa=? WHERE pessoa=?" + (" AND estado <> 'Feita'" if apenas else "")
        n_i = conn.execute(sql, (para, de)).rowcount
        if b.get("configChave"):
            chave = b["configChave"]
            if not isinstance(chave, str) or not _CHAVE.match(chave):
                raise ApiError(400, "configChave_invalida", "chave inválida")
            conn.execute("INSERT INTO tarefas_config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, para))
    return 200, {"tarefas": n_t, "instancias": n_i}


# --- config ---------------------------------------------------------------------

def gravar_config(ctx):
    """{valores: {chave: valor}, apagar: [chaves]} — atómico. A password ntfy cifrada não se pode ESCREVER por aqui (só o servidor.py a
    cifra e grava); pode apagar-se, ao remover uma pessoa."""
    _so(ctx.body, {"valores", "apagar"})
    valores = ctx.body.get("valores") or {}
    apagar = ctx.body.get("apagar") or []
    if not isinstance(valores, dict) or not isinstance(apagar, list) or not (valores or apagar) or len(valores) + len(apagar) > 100:
        raise ApiError(400, "config_invalida", "envia valores (objeto) e/ou apagar (lista), até 100 chaves")
    limpos = {}
    for k, v in valores.items():
        if _RESERVADA.match(k):
            raise ApiError(403, "chave_reservada", "as definições de administração alteram-se no painel de administração")
        if not _CHAVE.match(k) or _SEGREDO.search(k):
            raise ApiError(400, "chave_invalida", f"chave não permitida: {k[:40]!r}")
        limpos[k] = _txt(v if v is not None else "", "valor", 500)
    for k in apagar:
        if isinstance(k, str) and _RESERVADA.match(k):
            raise ApiError(403, "chave_reservada", "as definições de administração alteram-se no painel de administração")
    for k in apagar:                      # apagar a password cifrada é permitido (remover uma pessoa); escrevê-la não
        if not isinstance(k, str) or not _CHAVE.match(k):
            raise ApiError(400, "chave_invalida", f"chave não permitida: {str(k)[:40]!r}")
    conn = ctx.db()
    with _tx(conn):
        for k, v in limpos.items():
            conn.execute("INSERT INTO tarefas_config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (k, v))
        for k in apagar:
            conn.execute("DELETE FROM tarefas_config WHERE chave=?", (k,))
        rows = conn.execute("SELECT * FROM tarefas_config ORDER BY rowid").fetchall()
    return 200, {"config": [_config_json(r) for r in rows]}


# --- piscina --------------------------------------------------------------------

_ID_PISCINA = r"[A-Za-z][A-Za-z0-9_-]{0,19}"


def atualizar_piscina(ctx):
    pid = ctx.groups[0]
    b = ctx.body
    _so(b, {"ultimaData", "proximaData", "notificacaoEnviada", "usarIntervaloLongo"})
    if not b:
        raise ApiError(400, "sem_campos", "envia pelo menos um campo")
    conn = ctx.db()
    with _tx(conn):
        r = conn.execute("SELECT * FROM tarefas_piscina WHERE id=?", (pid,)).fetchone()
        if not r:
            raise ApiError(404, "nao_encontrado", "tarefa da piscina inexistente")
        ultima = _data(b["ultimaData"], "ultimaData", True) if "ultimaData" in b else r["ultima_data"]
        proxima = _data(b["proximaData"], "proximaData", True) if "proximaData" in b else r["proxima_data"]
        env_ = _bool(b["notificacaoEnviada"], "notificacaoEnviada") if "notificacaoEnviada" in b else r["notificacao_enviada"]
        longo = _bool(b["usarIntervaloLongo"], "usarIntervaloLongo") if "usarIntervaloLongo" in b else r["usar_intervalo_longo"]
        conn.execute("UPDATE tarefas_piscina SET ultima_data=?, proxima_data=?, notificacao_enviada=?, usar_intervalo_longo=? WHERE id=?",
                     (ultima, proxima, env_, longo, pid))
        r = conn.execute("SELECT * FROM tarefas_piscina WHERE id=?", (pid,)).fetchone()
    return 200, {"item": _piscina_json(r)}


def catalogo_piscina(ctx):
    """Acrescenta as tarefas do catálogo (da PWA) que ainda não estão na BD; nunca toca nas que já lá estão."""
    _so(ctx.body, {"itens"})
    itens = ctx.body.get("itens")
    if not isinstance(itens, list) or not 1 <= len(itens) <= 50:
        raise ApiError(400, "itens_invalidos", "itens tem de ter de 1 a 50 elementos")
    conn = ctx.db()
    novos = 0
    with _tx(conn):
        for it in itens:
            if not isinstance(it, dict):
                raise ApiError(400, "item_invalido", "cada item tem de ser um objeto")
            _so(it, {"id", "nome", "avisoLongo"})
            pid = _txt(it.get("id"), "id", 20, True)
            if not re.fullmatch(_ID_PISCINA, pid):
                raise ApiError(400, "id_invalido", "id inválido")
            novos += conn.execute("INSERT OR IGNORE INTO tarefas_piscina (id, nome, aviso_longo) VALUES (?, ?, ?)",
                                  (pid, _txt(it.get("nome"), "nome", 200, True), _bool(bool(it.get("avisoLongo")), "avisoLongo"))).rowcount
        rows = conn.execute("SELECT * FROM tarefas_piscina ORDER BY rowid").fetchall()
    return 200, {"criados": novos, "piscina": [_piscina_json(r) for r in rows]}


ROUTES = [
    ("GET", r"^/tarefas/dados$", dados),
    ("GET", r"^/tarefas/horario$", horario),
    ("GET", r"^/tarefas/admin$", admin_ver),
    ("PUT", r"^/tarefas/admin$", admin_gravar),
    ("GET", r"^/tarefas/auditoria$", auditoria),
    ("POST", r"^/tarefas/auditoria$", registar_auditoria),
    ("POST", r"^/tarefas/tarefas$", criar_tarefa),
    ("PUT", r"^/tarefas/tarefas/(T\d{1,8})$", atualizar_tarefa),
    ("DELETE", r"^/tarefas/tarefas/(T\d{1,8})$", apagar_tarefa),
    ("POST", r"^/tarefas/instancias$", criar_instancia),
    ("PUT", r"^/tarefas/instancias$", atualizar_instancias),
    ("PUT", r"^/tarefas/instancias/(I\d{1,20})$", atualizar_instancia),
    ("POST", r"^/tarefas/pessoas/reatribuir$", reatribuir),
    ("PUT", r"^/tarefas/config$", gravar_config),
    ("PUT", rf"^/tarefas/piscina/({_ID_PISCINA})$", atualizar_piscina),
    ("POST", r"^/tarefas/piscina/catalogo$", catalogo_piscina),
]
