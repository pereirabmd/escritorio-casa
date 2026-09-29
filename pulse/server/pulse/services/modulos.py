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
    ("calendario", "Calendário", False), ("email", "Email", False), ("compras", "Compras", False),
)
DISPONIVEIS = {m[0] for m in MODULOS if m[2]}


def desativados(conn: sqlite3.Connection) -> set[str]:
    r = conn.execute("SELECT valor FROM pulse_settings WHERE chave = ?", (CHAVE,)).fetchone()
    return {x for x in (r["valor"].split(",") if r else []) if x in DISPONIVEIS}


def lista(conn: sqlite3.Connection) -> list[dict]:
    off = desativados(conn)
    return [{"id": i, "nome": n, "disponivel": d, "ativo": i not in off} for i, n, d in MODULOS]


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


def exigir(conn: sqlite3.Connection, modulo: str) -> None:
    if modulo in desativados(conn):
        raise ContaErro(403, "modulo_desativado", "este módulo foi desativado pelo administrador")
