"""Contas e sessões do Pulse (ADR-037). Funções sobre uma ligação SQLite; nada aqui sabe de HTTP."""

from __future__ import annotations

import re
import sqlite3
import time

from pulse import security

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
MAX_FALHAS = 5
BLOQUEIO_S = 10 * 60
PASSWORD_MIN = 10
_FRACAS = {"1234567890", "password12", "qwertyuiop", "1234qwer12", "passw0rd12"}


class ContaErro(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem = status, codigo, mensagem


def normalizar_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise ContaErro(400, "email_invalido", "e-mail inválido")
    return e


def validar_password_nova(password: str, email: str) -> None:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN or len(password) > 200:
        raise ContaErro(400, "password_fraca", f"a palavra-passe tem de ter entre {PASSWORD_MIN} e 200 caracteres")
    if password.lower() in _FRACAS or password.lower() == email.lower() or password.lower() == email.split("@")[0].lower():
        raise ContaErro(400, "password_fraca", "palavra-passe demasiado previsível")
    if len({c for c in password}) < 5:
        raise ContaErro(400, "password_fraca", "palavra-passe demasiado repetitiva")


def criar_utilizador(conn: sqlite3.Connection, email: str, password: str, nome: str = "", admin: bool = False,
                     must_change: bool = True, agora: int | None = None, modulos: list[str] | None = None) -> int:
    """Cria uma conta (o administrador garante o e-mail). A password inicial não passa pela política — obriga-se a mudá-la
    no primeiro acesso (`must_change`)."""
    email = normalizar_email(email)
    if not password:
        raise ContaErro(400, "password_vazia", "password inicial em falta")
    try:
        cur = conn.execute("INSERT INTO pulse_users (email, nome, password_hash, must_change_password, admin, criado) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (email, nome.strip()[:80], security.hash_password(password), int(must_change), int(admin),
                            agora or int(time.time())))
    except sqlite3.IntegrityError:
        raise ContaErro(409, "email_existente", "já existe uma conta com esse e-mail") from None
    # `modulos=None` (a linha de comandos, os testes): todos; a administração do Pulse dá só os que escolher
    from pulse.services import modulos as mods
    mods.definir_permitidos(conn, cur.lastrowid, sorted(mods.DISPONIVEIS) if modulos is None else modulos)
    return cur.lastrowid


def autenticar(conn: sqlite3.Connection, email: str, password: str, agora: int | None = None) -> sqlite3.Row:
    """Utilizador se o e-mail e a password estiverem certos. Erro genérico igual para 'não existe', 'password errada' e
    'desativada' (não revelar que contas existem); bloqueio temporário depois de falhas seguidas."""
    agora = agora or int(time.time())
    generico = ContaErro(401, "credenciais_invalidas", "e-mail ou palavra-passe incorretos")
    try:
        e = normalizar_email(email)
    except ContaErro:
        security.verify_dummy(password or "")
        raise generico from None
    u = conn.execute("SELECT * FROM pulse_users WHERE email = ?", (e,)).fetchone()
    if u is None:
        security.verify_dummy(password or "")
        raise generico
    if u["bloqueado_ate"] > agora:
        raise ContaErro(429, "conta_bloqueada", "demasiadas tentativas; tenta de novo dentro de alguns minutos")
    if not security.verify_password(password or "", u["password_hash"]) or not u["ativo"]:
        falhas = u["falhas"] + 1
        bloqueio = agora + BLOQUEIO_S if falhas >= MAX_FALHAS else 0
        conn.execute("UPDATE pulse_users SET falhas=?, bloqueado_ate=? WHERE id=?",
                     (0 if bloqueio else falhas, bloqueio, u["id"]))
        raise generico
    conn.execute("UPDATE pulse_users SET falhas=0, bloqueado_ate=0, ultimo_login=? WHERE id=?", (agora, u["id"]))
    return u


def criar_sessao(conn: sqlite3.Connection, user_id: int, dispositivo: str, ip: str, cliente: str, dias: int,
                 agora: int | None = None) -> str:
    agora = agora or int(time.time())
    token = security.new_token()
    conn.execute("INSERT INTO pulse_sessions (user_id, token_hash, criado, ultimo_uso, expira, dispositivo, ip, cliente) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (user_id, security.token_hash(token), agora, agora, agora + dias * 86400,
                  dispositivo[:120], ip[:64], cliente if cliente in ("web", "android") else "web"))
    return token


def resolver_sessao(conn: sqlite3.Connection, token: str, dias: int, agora: int | None = None):
    """(utilizador, sessão) se o token for válido, não revogado nem expirado e a conta estiver ativa. Renova a validade
    (deslizante) no máximo uma vez por hora, para não escrever na base a cada pedido."""
    agora = agora or int(time.time())
    if not token:
        return None
    s = conn.execute("SELECT * FROM pulse_sessions WHERE token_hash = ?", (security.token_hash(token),)).fetchone()
    if s is None or s["revogada"] or s["expira"] <= agora:
        return None
    u = conn.execute("SELECT * FROM pulse_users WHERE id = ? AND ativo = 1", (s["user_id"],)).fetchone()
    if u is None:
        return None
    if agora - s["ultimo_uso"] >= 3600:
        conn.execute("UPDATE pulse_sessions SET ultimo_uso=?, expira=? WHERE id=?", (agora, agora + dias * 86400, s["id"]))
    return u, s


def revogar_sessao(conn: sqlite3.Connection, session_id: int, user_id: int) -> bool:
    return conn.execute("UPDATE pulse_sessions SET revogada=1 WHERE id=? AND user_id=? AND revogada=0",
                        (session_id, user_id)).rowcount > 0


def revogar_todas(conn: sqlite3.Connection, user_id: int, exceto: int | None = None) -> int:
    return conn.execute("UPDATE pulse_sessions SET revogada=1 WHERE user_id=? AND revogada=0 AND id IS NOT ?",
                        (user_id, exceto)).rowcount


def listar_sessoes(conn: sqlite3.Connection, user_id: int, agora: int | None = None) -> list[sqlite3.Row]:
    agora = agora or int(time.time())
    return conn.execute("SELECT id, criado, ultimo_uso, expira, dispositivo, ip, cliente FROM pulse_sessions "
                        "WHERE user_id=? AND revogada=0 AND expira>? ORDER BY ultimo_uso DESC", (user_id, agora)).fetchall()


def alterar_password(conn: sqlite3.Connection, user: sqlite3.Row, atual: str, nova: str, sessao_atual: int | None) -> None:
    if not security.verify_password(atual or "", user["password_hash"]):
        raise ContaErro(401, "password_atual_errada", "a palavra-passe atual não está certa")
    validar_password_nova(nova, user["email"])
    if security.verify_password(nova, user["password_hash"]):
        raise ContaErro(400, "password_igual", "a palavra-passe nova tem de ser diferente da atual")
    conn.execute("UPDATE pulse_users SET password_hash=?, must_change_password=0, falhas=0, bloqueado_ate=0 WHERE id=?",
                 (security.hash_password(nova), user["id"]))
    revogar_todas(conn, user["id"], exceto=sessao_atual)   # as outras sessões deixam de valer


def repor_password(conn: sqlite3.Connection, email: str, password: str) -> None:
    """Reposição pelo administrador (CLI): nova password provisória, obriga a mudá-la e termina todas as sessões."""
    e = normalizar_email(email)
    u = conn.execute("SELECT id FROM pulse_users WHERE email=?", (e,)).fetchone()
    if u is None:
        raise ContaErro(404, "nao_existe", "não existe essa conta")
    conn.execute("UPDATE pulse_users SET password_hash=?, must_change_password=1, falhas=0, bloqueado_ate=0 WHERE id=?",
                 (security.hash_password(password), u["id"]))
    revogar_todas(conn, u["id"])
