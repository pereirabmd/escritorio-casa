"""Contas Google ligadas (ADR-049): ligar (OAuth), listar, remover e o estado de cada uma.

Cada conta Pulse liga as suas contas Google; ninguém vê as de outro utilizador (um id alheio é 404). O refresh token entra e sai
cifrado por `Cofre`; as funções que o devolvem em claro só o entregam a quem vai falar com a Google, nunca à interface.
"""

from __future__ import annotations

import secrets
import sqlite3
import time

from pulse import google_api as g
from pulse.accounts import ContaErro


def _agora(agora: int | None) -> int:
    return agora if agora is not None else int(time.time())


def _json(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "email": r["email"], "nome": r["nome"], "servicos": [s for s in r["servicos"].split(",") if s], "estado": r["estado"]}


def listar(conn: sqlite3.Connection, uid: int) -> list[dict]:
    return [_json(r) for r in conn.execute("SELECT * FROM google_accounts WHERE user_id = ? ORDER BY id", (uid,))]


def com_servico(conn: sqlite3.Connection, uid: int, servico: str, conta: int | None = None) -> list[dict]:
    """As contas do utilizador com esse serviço (incluindo as que pedem nova autorização: a interface avisa). Traz o refresh cifrado."""
    q, args = "SELECT * FROM google_accounts WHERE user_id = ? AND (',' || servicos || ',') LIKE ?", [uid, f"%,{servico},%"]
    if conta is not None:
        q, args = q + " AND id = ?", args + [conta]
    return [{**_json(r), "refresh": r["refresh_token"]} for r in conn.execute(q + " ORDER BY id", args)]


def obter(conn: sqlite3.Connection, uid: int, conta: int, servico: str) -> dict:
    r = com_servico(conn, uid, servico, conta)
    if not r:
        raise ContaErro(404, "nao_encontrado", "conta Google inexistente ou sem esse serviço")
    return r[0]


def marcar_estado(conn: sqlite3.Connection, conta: int, estado: str, agora: int | None = None) -> None:
    conn.execute("UPDATE google_accounts SET estado = ?, atualizado = ? WHERE id = ?", (estado, _agora(agora), conta))


def iniciar(conn: sqlite3.Connection, api: g.GoogleApi, uid: int, servicos: list[str], login_hint: str = "", agora: int | None = None) -> str:
    """Devolve o URL do ecrã de consentimento da Google. Guarda o `state` (um só uso, 10 min) e o verificador PKCE."""
    servicos = [s for s in dict.fromkeys(servicos)]
    if not servicos or any(s not in g.SERVICOS for s in servicos):
        raise ContaErro(400, "servicos_invalidos", "escolhe Gmail e/ou Calendário")
    t = _agora(agora)
    conn.execute("DELETE FROM google_oauth_states WHERE criado < ?", (t - g.ESTADO_TTL_S,))
    state = secrets.token_urlsafe(32)
    verificador, desafio = g.pkce()
    conn.execute("INSERT INTO google_oauth_states (state, user_id, servicos, code_verifier, criado) VALUES (?,?,?,?,?)", (state, uid, ",".join(servicos), verificador, t))
    return api.url_autorizacao(servicos, state, desafio, login_hint)


def concluir(conn: sqlite3.Connection, api: g.GoogleApi, state: str, code: str, agora: int | None = None) -> dict:
    """O regresso do Google: valida o `state`, troca o código, lê o perfil e guarda a conta (cifrada). Levanta ContaErro com o motivo."""
    t = _agora(agora)
    r = conn.execute("SELECT * FROM google_oauth_states WHERE state = ?", (state,)).fetchone()
    if r is None or t - r["criado"] > g.ESTADO_TTL_S:
        conn.execute("DELETE FROM google_oauth_states WHERE state = ?", (state,))
        raise ContaErro(400, "estado_invalido", "o pedido de ligação expirou ou é inválido: tenta de novo")
    conn.execute("DELETE FROM google_oauth_states WHERE state = ?", (state,))          # um só uso
    try:
        tokens = api.trocar_codigo(code, r["code_verifier"])
        perfil = api.perfil(tokens["access_token"])
    except g.GoogleErro as e:
        raise ContaErro(502, "google_recusou", str(e)) from e
    servicos = [s for s in g.servicos_de_scopes(tokens.get("scope", "")) if s in r["servicos"].split(",")]
    if not servicos:
        raise ContaErro(400, "sem_permissoes", "a conta não deu as permissões pedidas")
    refresh = tokens.get("refresh_token")
    existente = conn.execute("SELECT id, refresh_token FROM google_accounts WHERE user_id = ? AND email = ?", (r["user_id"], perfil["email"])).fetchone()
    if not refresh and not existente:
        raise ContaErro(400, "sem_refresh_token", "a Google não devolveu acesso duradouro: remove a app em myaccount.google.com/permissions e liga de novo")
    cifrado = api.cofre.cifrar(refresh) if refresh else existente["refresh_token"]
    if existente:
        conn.execute("UPDATE google_accounts SET refresh_token = ?, servicos = ?, nome = ?, estado = 'ok', atualizado = ? WHERE id = ?", (cifrado, ",".join(servicos), perfil["nome"], t, existente["id"]))
        conta = existente["id"]
        api.esquecer(conta)
    else:
        conta = conn.execute("INSERT INTO google_accounts (user_id, email, nome, refresh_token, servicos, criado, atualizado) VALUES (?,?,?,?,?,?,?)",
                             (r["user_id"], perfil["email"], perfil["nome"], cifrado, ",".join(servicos), t, t)).lastrowid
    return {"conta": conta, "email": perfil["email"], "servicos": servicos, "user_id": r["user_id"]}


def remover(conn: sqlite3.Connection, api: g.GoogleApi | None, uid: int, conta: int) -> dict:
    r = conn.execute("SELECT * FROM google_accounts WHERE id = ? AND user_id = ?", (conta, uid)).fetchone()
    if r is None:
        raise ContaErro(404, "nao_encontrado", "conta Google inexistente")
    if api is not None:
        try:
            api.revogar(api.cofre.decifrar(r["refresh_token"]))
        except Exception:                                        # noqa: BLE001 - revogar é melhor esforço; a conta apaga-se sempre
            pass
        api.esquecer(conta)
    conn.execute("DELETE FROM google_accounts WHERE id = ?", (conta,))
    return {"id": conta, "email": r["email"]}
