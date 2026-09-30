"""Comboios favoritos dos Bilhetes CP (ADR-078): por conta, em `pulse.db`. Um favorito é «comboio + hora + origem → destino» (e um apelido opcional).

Preenchem o seletor «Favoritos» do editor e dão às ações por voz um nome curto para marcar uma viagem («o comboio da manhã»).
Na primeira vez que a conta abre os Bilhetes sem favoritos, juntam-se os comboios que já usou (`semear`), uma só vez.
"""

from __future__ import annotations

import sqlite3
import time

from pulse.accounts import ContaErro

MAX_FAVORITOS = 30
SEMEAR_ATE = 8


def _json(r) -> dict:
    return {"id": r["id"], "apelido": r["apelido"], "comboio": r["comboio"], "hora": r["hora"], "origem": r["origem"], "destino": r["destino"]}


def listar(conn: sqlite3.Connection, uid: int) -> list[dict]:
    return [_json(r) for r in conn.execute("SELECT * FROM bilhetes_favoritos WHERE user_id = ? ORDER BY hora, comboio, id", (uid,))]


def guardar(conn: sqlite3.Connection, uid: int, comboio: int, hora: str, origem: str, destino: str, apelido: str = "", agora: int | None = None) -> dict:
    """Guarda um favorito (repetir o mesmo não duplica: só atualiza o apelido, se vier um)."""
    origem, destino, apelido = " ".join(origem.split()), " ".join(destino.split()), " ".join(apelido.split())
    if origem.lower() == destino.lower():
        raise ContaErro(400, "percurso_invalido", "a origem e o destino são iguais")
    if len(apelido) > 40:
        raise ContaErro(400, "apelido_grande", "o apelido tem no máximo 40 caracteres")
    if conn.execute("SELECT COUNT(*) FROM bilhetes_favoritos WHERE user_id = ?", (uid,)).fetchone()[0] >= MAX_FAVORITOS:
        ja = conn.execute("SELECT 1 FROM bilhetes_favoritos WHERE user_id = ? AND comboio = ? AND hora = ? AND origem = ? AND destino = ?", (uid, comboio, hora, origem, destino)).fetchone()
        if not ja:
            raise ContaErro(409, "demasiados_favoritos", f"já tens {MAX_FAVORITOS} favoritos; remove algum")
    conn.execute("INSERT INTO bilhetes_favoritos (user_id, apelido, comboio, hora, origem, destino, criado) VALUES (?,?,?,?,?,?,?) "
                 "ON CONFLICT(user_id, comboio, hora, origem, destino) DO UPDATE SET apelido = CASE WHEN excluded.apelido != '' THEN excluded.apelido ELSE apelido END",
                 (uid, apelido, comboio, hora, origem, destino, agora if agora is not None else int(time.time())))
    return _json(conn.execute("SELECT * FROM bilhetes_favoritos WHERE user_id = ? AND comboio = ? AND hora = ? AND origem = ? AND destino = ?", (uid, comboio, hora, origem, destino)).fetchone())


def obter(conn: sqlite3.Connection, uid: int, favorito: int) -> dict:
    r = conn.execute("SELECT * FROM bilhetes_favoritos WHERE id = ? AND user_id = ?", (favorito, uid)).fetchone()
    if r is None:
        raise ContaErro(404, "nao_encontrado", "favorito inexistente")
    return _json(r)


def apagar(conn: sqlite3.Connection, uid: int, favorito: int) -> dict:
    f = obter(conn, uid, favorito)
    conn.execute("DELETE FROM bilhetes_favoritos WHERE id = ? AND user_id = ?", (favorito, uid))
    return f


def semear(conn: sqlite3.Connection, uid: int, historico: list[dict]) -> None:
    """Primeira abertura: junta os comboios que a conta já usou (`historico`, do mais recente para o mais antigo). Só corre uma vez por conta."""
    chave = f"favoritos_semeado:{uid}"
    if conn.execute("SELECT 1 FROM pulse_settings WHERE chave = ?", (chave,)).fetchone():
        return
    if not conn.execute("SELECT 1 FROM bilhetes_favoritos WHERE user_id = ?", (uid,)).fetchone():
        for h in historico[:SEMEAR_ATE]:
            try:
                guardar(conn, uid, h["comboio"], h["hora"], h["origem"], h["destino"])
            except ContaErro:
                continue
    conn.execute("INSERT INTO pulse_settings (chave, valor) VALUES (?, '1') ON CONFLICT(chave) DO NOTHING", (chave,))
