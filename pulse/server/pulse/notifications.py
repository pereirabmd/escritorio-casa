"""Notificações do Pulse (ADR-044): caixa de saída de eventos + canais de entrega.

Um evento (ex.: «comboio comprado», «atraso») entra uma vez (idempotente por `chave`) e é entregue por todos os canais
ligados. O único canal real é o FCM (API HTTP v1, chave de uma service account só no Pi); sem ele, o evento fica na caixa
(`sem_canal`) e o Android pode consultá-lo em `GET /notifications`. As apps de origem (bilhetes_cp) continuam a avisar por
ntfy: a passagem para o FCM é só deixar de enviar o ntfy, sem mexer aqui.
"""

from __future__ import annotations

import base64
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

LOG = logging.getLogger("pulse.notifications")
MAX_TENTATIVAS = 5
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class Erro(Exception):
    """Erro de entrega de um canal. `token_invalido`: o dispositivo já não existe (desativar); `temporario`: vale a pena repetir."""

    def __init__(self, mensagem: str, token_invalido: bool = False, temporario: bool = False):
        super().__init__(mensagem)
        self.token_invalido, self.temporario = token_invalido, temporario


@dataclass(frozen=True)
class Evento:
    id: int
    modulo: str
    tipo: str
    titulo: str
    corpo: str
    dados: dict


class Canal(Protocol):
    nome: str

    def enviar(self, token: str, evento: Evento) -> None: ...


# --- FCM (API HTTP v1) ---------------------------------------------------------------------------------------------------------

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class FcmCanal:
    """Envia por FCM com prioridade alta (ADR-032: tudo aparece sempre no telemóvel).

    Autentica-se com um JWT (RS256) assinado pela chave privada da service account, trocado por um access token OAuth2 (1 h,
    guardado em memória). A assinatura precisa da biblioteca `cryptography` (só é importada quando o canal está ligado).
    `transporte` existe para os testes: `(metodo, url, cabecalhos, corpo_bytes) -> (status, corpo_bytes)`.
    """
    nome = "fcm"

    def __init__(self, credenciais: dict, transporte=None, agora=time.time, so_dados: bool = False):
        for campo in ("client_email", "private_key", "project_id"):
            if not credenciais.get(campo):
                raise ValueError(f"credenciais FCM sem {campo}")
        self.cred, self.agora, self.so_dados = credenciais, agora, so_dados
        self.transporte = transporte or self._http
        self._token: tuple[str, float] | None = None

    @classmethod
    def de_ficheiro(cls, caminho: Path, projeto: str = "", **kw) -> "FcmCanal":
        cred = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if projeto:
            cred["project_id"] = projeto
        return cls(cred, **kw)

    @staticmethod
    def _http(metodo: str, url: str, cabecalhos: dict, corpo: bytes | None) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Erro(f"sem ligação ao Google: {type(e).__name__}", temporario=True) from e

    def _assinar(self, mensagem: bytes) -> bytes:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as e:      # pragma: no cover - depende do ambiente
            raise Erro("falta a biblioteca `cryptography` para assinar o token FCM") from e
        chave = serialization.load_pem_private_key(self.cred["private_key"].encode(), password=None)
        return chave.sign(mensagem, padding.PKCS1v15(), hashes.SHA256())

    def _access_token(self) -> str:
        agora = self.agora()
        if self._token and self._token[1] - 60 > agora:
            return self._token[0]
        cab = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        pl = _b64url(json.dumps({"iss": self.cred["client_email"], "scope": FCM_SCOPE, "aud": "https://oauth2.googleapis.com/token",
                                 "iat": int(agora), "exp": int(agora) + 3600}).encode())
        jwt = f"{cab}.{pl}.{_b64url(self._assinar(f'{cab}.{pl}'.encode()))}"
        corpo = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}).encode()
        status, raw = self.transporte("POST", "https://oauth2.googleapis.com/token", {"Content-Type": "application/x-www-form-urlencoded"}, corpo)
        if status != 200:
            raise Erro(f"o Google recusou a autenticação FCM (HTTP {status})", temporario=status >= 500)
        r = json.loads(raw.decode())
        self._token = (r["access_token"], agora + int(r.get("expires_in", 3600)))
        return self._token[0]

    def enviar(self, token: str, evento: Evento) -> None:
        dados = {**{k: str(v) for k, v in evento.dados.items()}, "evento": str(evento.id), "modulo": evento.modulo, "tipo": evento.tipo,
                 "titulo": evento.titulo, "corpo": evento.corpo}
        if self.so_dados:
            # só `data`, sem bloco `notification`: a app recebe SEMPRE a mensagem (aberta ou não) e desenha ela o aviso, com os botões de ação
            # (Marcar feita, Daqui a 1 h) e o destino do toque. Só se liga (PULSE_FCM_SO_DADOS=1) quando as apps instaladas já sabem fazê-lo (0.2.7+).
            msg = {"message": {"token": token, "data": dados, "android": {"priority": "HIGH", "ttl": "86400s"}}}
        else:
            msg = {"message": {"token": token, "notification": {"title": evento.titulo, "body": evento.corpo}, "data": dados,
                               "android": {"priority": "HIGH", "notification": {"channel_id": f"pulse_{evento.modulo}"}}}}
        url = f"https://fcm.googleapis.com/v1/projects/{self.cred['project_id']}/messages:send"
        status, raw = self.transporte("POST", url, {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"},
                                      json.dumps(msg).encode())
        if status == 200:
            return
        try:
            detalhe = json.loads(raw.decode()).get("error", {})
        except ValueError:
            detalhe = {}
        codigo = detalhe.get("status", "")
        if status == 404 or codigo in ("NOT_FOUND", "UNREGISTERED") or any(d.get("errorCode") == "UNREGISTERED" for d in detalhe.get("details", []) if isinstance(d, dict)):
            raise Erro("dispositivo já não está registado", token_invalido=True)
        if status == 401:
            self._token = None
        raise Erro(f"FCM respondeu HTTP {status} ({codigo or 'erro'})", temporario=status in (401, 429) or status >= 500)


# --- caixa de saída ------------------------------------------------------------------------------------------------------------

def guardar(conn: sqlite3.Connection, user_id: int, modulo: str, tipo: str, titulo: str, corpo: str = "", dados: dict | None = None,
            chave: str | None = None, agora: int | None = None, entregar_em: int | None = None) -> tuple[int, bool]:
    """Guarda um evento; devolve (id, novo). Repetir a mesma `chave` devolve o evento existente (`novo=False`).
    Com `entregar_em` no futuro fica `agendado` e só sai quando chegar a hora (`despachar_vencidos`)."""
    if chave:
        ja = conn.execute("SELECT id FROM pulse_events WHERE chave = ?", (chave,)).fetchone()
        if ja:
            return ja["id"], False
    agora = agora or int(time.time())
    estado = "agendado" if entregar_em and entregar_em > agora else "novo"
    cur = conn.execute("INSERT INTO pulse_events (user_id, criado, modulo, tipo, titulo, corpo, dados, chave, entregar_em, estado) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (user_id, agora, modulo, tipo, titulo, corpo, json.dumps(dados or {}, ensure_ascii=False), chave, entregar_em, estado))
    return cur.lastrowid, True


def despachar(conn: sqlite3.Connection, evento_id: int, canais: list[Canal], agora: int | None = None) -> str:
    """Entrega o evento aos dispositivos ativos do dono por cada canal. Estado final: enviado / sem_canal / erro / novo (a repetir)."""
    e = conn.execute("SELECT * FROM pulse_events WHERE id = ?", (evento_id,)).fetchone()
    if e is None or e["estado"] in ("enviado", "sem_canal", "erro", "agendado"):
        return e["estado"] if e else "inexistente"
    if not canais:
        conn.execute("UPDATE pulse_events SET estado = 'sem_canal' WHERE id = ?", (evento_id,))
        return "sem_canal"
    ev = Evento(e["id"], e["modulo"], e["tipo"], e["titulo"], e["corpo"], json.loads(e["dados"] or "{}"))
    aparelhos = conn.execute("SELECT id, fcm_token FROM pulse_devices WHERE user_id = ? AND ativo = 1", (e["user_id"],)).fetchall()
    ok, falha, repetir = 0, 0, False
    for ap in aparelhos:
        for canal in canais:
            try:
                canal.enviar(ap["fcm_token"], ev)
                ok += 1
            except Erro as x:
                if x.token_invalido:
                    conn.execute("UPDATE pulse_devices SET ativo = 0 WHERE id = ?", (ap["id"],))
                else:
                    falha += 1; repetir = repetir or x.temporario
                    LOG.warning("entrega %s falhou (evento %s): %s", canal.nome, evento_id, x)
    tentativas = e["tentativas"] + 1
    if ok or not aparelhos:        # sem dispositivos não há nada a entregar: fica na caixa para o Android buscar quando se registar
        estado = "enviado" if ok else "sem_canal"
    elif repetir and tentativas < MAX_TENTATIVAS:
        estado = "novo"
    else:
        estado = "erro" if falha else "sem_canal"
    conn.execute("UPDATE pulse_events SET estado = ?, tentativas = ?, entregue_em = ? WHERE id = ?",
                 (estado, tentativas, (agora or int(time.time())) if estado == "enviado" else None, evento_id))
    return estado


def repetir_pendentes(conn: sqlite3.Connection, canais: list[Canal], limite: int = 50) -> int:
    """Volta a tentar os eventos que falharam por motivos temporários (chamado ao receber um evento novo)."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM pulse_events WHERE estado = 'novo' ORDER BY id LIMIT ?", (limite,))]
    for i in ids:
        despachar(conn, i, canais)
    return len(ids)


def despachar_vencidos(conn: sqlite3.Connection, canais: list[Canal], agora: int | None = None, limite: int = 100) -> int:
    """O agendador (ADR-032): entrega os eventos agendados cuja hora chegou e repete os que falharam por motivos temporários."""
    agora = agora or int(time.time())
    ids = [r["id"] for r in conn.execute("SELECT id FROM pulse_events WHERE estado = 'agendado' AND entregar_em <= ? ORDER BY entregar_em, id LIMIT ?", (agora, limite))]
    for i in ids:
        conn.execute("UPDATE pulse_events SET estado = 'novo' WHERE id = ? AND estado = 'agendado'", (i,))
        despachar(conn, i, canais, agora)
    return len(ids) + repetir_pendentes(conn, canais, limite)
