"""Módulos do Pulse e quais estão ativos (administração, ADR-046).

O administrador pode desativar módulos para **todos** os utilizadores: deixam de aparecer no Hoje e em Mais, e a API e as ações
recusam-nos (403 `modulo_desativado`). Guarda-se só o que está desativado (`pulse_settings`), por isso um módulo novo nasce ativo.
Os módulos «Em breve» (Calendário, Email, Compras) não se ativam nem desativam: ainda não existem.
"""

from __future__ import annotations

import sqlite3

from pulse.accounts import ContaErro

CHAVE = "modulos_desativados"
# (id, nome, tem ecrã e API)
MODULOS: tuple[tuple[str, str, bool], ...] = (
    ("tarefas", "Tarefas", True), ("bilhetes", "Bilhetes CP", True), ("rto", "RTO", True), ("peso", "Peso", True), ("financas", "Finanças", True),
    ("compras", "Compras", True), ("calendario", "Calendário", True), ("email", "Email", True),
)
DISPONIVEIS = {m[0] for m in MODULOS if m[2]}


def desativados(conn: sqlite3.Connection) -> set[str]:
    r = conn.execute("SELECT valor FROM pulse_settings WHERE chave = ?", (CHAVE,)).fetchone()
    return {x for x in (r["valor"].split(",") if r else []) if x in DISPONIVEIS}


def permitidos(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """Os módulos a que esta conta tem acesso (dado pelo administrador)."""
    return {r["modulo"] for r in conn.execute("SELECT modulo FROM pulse_user_modulos WHERE user_id = ?", (user_id,)) if r["modulo"] in DISPONIVEIS}


def indisponiveis_para(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """Desativados para todos ou sem acesso desta conta: o Hoje nem os pede, Mais não os mostra, a API recusa-os."""
    return desativados(conn) | (DISPONIVEIS - permitidos(conn, user_id))


def lista(conn: sqlite3.Connection, user_id: int | None = None) -> list[dict]:
    """`ativo` = o módulo está ligado para todos **e** (com `user_id`) esta conta tem acesso; `ativoGlobal` é só o interruptor do administrador."""
    off = desativados(conn)
    meus = permitidos(conn, user_id) if user_id is not None else DISPONIVEIS
    return [{"id": i, "nome": n, "disponivel": d, "ativo": i not in off and i in meus, "ativoGlobal": i not in off, "permitido": i in meus} for i, n, d in MODULOS]


def definir_permitidos(conn: sqlite3.Connection, user_id: int, modulos: list[str]) -> list[str]:
    """Substitui o acesso desta conta (atómico). Módulos desconhecidos são recusados."""
    desconhecidos = sorted(set(modulos) - DISPONIVEIS)
    if desconhecidos:
        raise ContaErro(400, "modulo_invalido", f"módulo desconhecido: {', '.join(desconhecidos)}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM pulse_user_modulos WHERE user_id = ?", (user_id,))
        conn.executemany("INSERT INTO pulse_user_modulos (user_id, modulo) VALUES (?, ?)", [(user_id, m) for m in sorted(set(modulos))])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return sorted(set(modulos))


def alterar(conn: sqlite3.Connection, alteracoes: dict[str, bool]) -> list[dict]:
    """`alteracoes`: módulo → ativo. Só módulos que existem; guarda de forma atómica."""
    desconhecidos = sorted(set(alteracoes) - DISPONIVEIS)
    if desconhecidos:
        raise ContaErro(400, "modulo_invalido", f"módulo desconhecido ou ainda não disponível: {', '.join(desconhecidos)}")
    off = desativados(conn)
    for m, ativo in alteracoes.items():
        (off.discard if ativo else off.add)(m)
    valor = ",".join(sorted(off))
    conn.execute("INSERT INTO pulse_settings (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
                 "atualizado = strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')", (CHAVE, valor))
    return lista(conn)


def exigir(conn: sqlite3.Connection, modulo: str, user_id: int | None = None, email: str | None = None) -> None:
    """Recusa se o módulo está desativado para todos (`modulo_desativado`) ou se esta conta não tem acesso (`sem_acesso`)."""
    if modulo in desativados(conn):
        raise ContaErro(403, "modulo_desativado", "este módulo foi desativado pelo administrador")
    if user_id is None and email:
        r = conn.execute("SELECT id FROM pulse_users WHERE email = ?", (email,)).fetchone()
        user_id = r["id"] if r else None
    if user_id is not None and modulo in DISPONIVEIS and modulo not in permitidos(conn, user_id):
        raise ContaErro(403, "sem_acesso", "não tens acesso a este módulo")
