"""Notificações (ADR-044): registo de dispositivos FCM, caixa de eventos do utilizador e entrada de eventos das apps de origem.

`/internal/events` é só para a mesma máquina (bilhetes_cp, futuras apps): chave de serviço + e-mail do dono, e apenas em loopback
direto (o nginx acrescenta sempre `X-Real-IP`, por isso nunca é alcançável a partir da Internet).
"""

from __future__ import annotations

import hmac
import json
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from pulse import notifications
from pulse.accounts import ContaErro, normalizar_email
from pulse.api.v1.auth import Sessao, get_conn, sessao_ativa

router = APIRouter(tags=["notificações"])
internal = APIRouter(prefix="/internal", tags=["interno"])


class DispositivoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=4096, pattern=r"^[A-Za-z0-9_:\-.]+$")
    nome: str = Field(default="", max_length=80)
    plataforma: str = Field(default="android", pattern="^(android|web)$")


@router.post("/devices", status_code=201)
def registar_dispositivo(d: DispositivoIn, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Regista (ou renova) o token FCM deste dispositivo. Um token pertence a um só utilizador: se mudou de dono, passa para este."""
    agora = int(time.time())
    conn.execute("INSERT INTO pulse_devices (user_id, fcm_token, plataforma, nome, criado, ultimo_uso, ativo) VALUES (?,?,?,?,?,?,1) "
                 "ON CONFLICT(fcm_token) DO UPDATE SET user_id = excluded.user_id, nome = excluded.nome, plataforma = excluded.plataforma, "
                 "ultimo_uso = excluded.ultimo_uso, ativo = 1", (s.user["id"], d.token, d.plataforma, d.nome.strip(), agora, agora))
    r = conn.execute("SELECT id FROM pulse_devices WHERE fcm_token = ?", (d.token,)).fetchone()
    return {"id": r["id"]}


@router.delete("/devices/{dispositivo}")
def remover_dispositivo(dispositivo: int, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    if conn.execute("DELETE FROM pulse_devices WHERE id = ? AND user_id = ?", (dispositivo, s.user["id"])).rowcount == 0:
        raise ContaErro(404, "nao_encontrado", "dispositivo inexistente")
    return {"ok": True}


def _evento_json(r) -> dict:
    return {"id": r["id"], "criado": r["criado"], "modulo": r["modulo"], "tipo": r["tipo"], "titulo": r["titulo"], "corpo": r["corpo"],
            "dados": json.loads(r["dados"] or "{}"), "estado": r["estado"], "lido": bool(r["lido"])}


@router.get("/notifications")
def listar(desde: int = 0, limite: int = 50, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Os eventos do utilizador, do mais recente para o mais antigo (`desde` = id: só os mais novos que esse, para o Android ir buscar o que perdeu)."""
    limite = max(1, min(limite, 200))
    visivel = "user_id = ? AND estado != 'agendado'"                # o que ainda vai ser entregue não aparece na caixa
    rows = conn.execute(f"SELECT * FROM pulse_events WHERE {visivel} AND id > ? ORDER BY id DESC LIMIT ?", (s.user["id"], max(desde, 0), limite)).fetchall()
    naolidas = conn.execute(f"SELECT COUNT(*) FROM pulse_events WHERE {visivel} AND lido = 0", (s.user["id"],)).fetchone()[0]
    return {"eventos": [_evento_json(r) for r in rows], "naoLidas": naolidas}


class LidasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[int] | None = Field(default=None, max_length=200)      # omitido = todas


@router.post("/notifications/read")
def marcar_lidas(d: LidasIn, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    if d.ids is None:
        n = conn.execute("UPDATE pulse_events SET lido = 1 WHERE user_id = ? AND lido = 0", (s.user["id"],)).rowcount
    else:
        n = conn.execute(f"UPDATE pulse_events SET lido = 1 WHERE user_id = ? AND lido = 0 AND id IN ({','.join('?' * len(d.ids))})",
                         (s.user["id"], *d.ids)).rowcount if d.ids else 0
    return {"marcadas": n}


@router.post("/notifications/test")
def testar(request: Request, s: Sessao = Depends(sessao_ativa), conn=Depends(get_conn)):
    """Envia uma notificação de teste aos dispositivos do utilizador (botão das Definições): mostra se o FCM, o token e o telemóvel funcionam."""
    canais = request.app.state.canais
    aparelhos = conn.execute("SELECT COUNT(*) FROM pulse_devices WHERE user_id = ? AND ativo = 1", (s.user["id"],)).fetchone()[0]
    if not canais:
        raise ContaErro(409, "fcm_desligado", "as notificações ainda não estão ligadas no servidor")
    if aparelhos == 0:
        raise ContaErro(409, "sem_dispositivo", "este telemóvel ainda não está registado para notificações")
    agora = int(time.time())
    id_, _ = notifications.guardar(conn, s.user["id"], "teste", "teste", "Notificação de teste", "Se estás a ler isto, as notificações do Pulse funcionam.", {}, f"teste:{s.user['id']}:{agora}")
    estado = notifications.despachar(conn, id_, canais)
    return {"id": id_, "estado": estado, "dispositivos": aparelhos}


# --- entrada de eventos das apps de origem ------------------------------------------------------------------------------------

class EventoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modulo: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    tipo: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,59}$")
    titulo: str = Field(min_length=1, max_length=200)
    corpo: str = Field(default="", max_length=1000)
    dados: dict[str, str] = Field(default_factory=dict, max_length=20)
    chave: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:\-]{8,80}$")
    entregarEm: int | None = Field(default=None, ge=0, le=4_102_444_800)      # segundos Unix; no futuro = agendado


def servico(request: Request, conn=Depends(get_conn)):
    """Chave de serviço + `X-Pulse-User`, só em loopback direto. Devolve a linha do utilizador."""
    chave = request.app.state.settings.service_key
    direto = request.client is not None and request.client.host in ("127.0.0.1", "::1") \
        and "x-real-ip" not in request.headers and "x-forwarded-for" not in request.headers
    dada = request.headers.get("x-pulse-key", "")
    if len(chave) < 32 or not direto or not hmac.compare_digest(dada.encode(), chave.encode()):
        raise ContaErro(401, "nao_autenticado", "não autenticado")
    try:
        email = normalizar_email(request.headers.get("x-pulse-user", ""))
    except ContaErro:
        raise ContaErro(401, "nao_autenticado", "não autenticado") from None
    u = conn.execute("SELECT * FROM pulse_users WHERE email = ? AND ativo = 1", (email,)).fetchone()
    if u is None:
        raise ContaErro(403, "sem_acesso", "utilizador desconhecido")
    return u


@internal.post("/events", status_code=201)
def receber(e: EventoIn, request: Request, u=Depends(servico), conn=Depends(get_conn)):
    """Guarda o evento (idempotente por `chave`) e entrega-o pelos canais ligados. O evento fica guardado mesmo que a entrega falhe."""
    if len(json.dumps(e.dados, ensure_ascii=False)) > 1900:
        raise ContaErro(400, "dados_grandes", "dados demasiado grandes")
    canais = request.app.state.canais
    id_, novo = notifications.guardar(conn, u["id"], e.modulo, e.tipo, e.titulo, e.corpo, e.dados, e.chave, entregar_em=e.entregarEm)
    estado = conn.execute("SELECT estado FROM pulse_events WHERE id = ?", (id_,)).fetchone()[0]
    if novo and estado == "novo":
        estado = notifications.despachar(conn, id_, canais)
        notifications.repetir_pendentes(conn, canais)
    return {"id": id_, "novo": novo, "estado": estado}


@internal.delete("/events/{chave}")
def cancelar(chave: str, u=Depends(servico), conn=Depends(get_conn)):
    """Cancela um aviso ainda **agendado** do dono (a tarefa foi feita ou adiada antes da hora). Um aviso já enviado não se toca; cancelar
    um inexistente não é erro (`cancelado: false`), para quem chama poder repetir sem medo."""
    n = conn.execute("DELETE FROM pulse_events WHERE chave = ? AND user_id = ? AND estado = 'agendado'", (chave, u["id"])).rowcount
    return {"cancelado": n > 0}
