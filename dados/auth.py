"""Validação do token Google enviado pelas PWAs (`Authorization: Bearer <access_token>`).

As apps usam o Google Identity Services (token client), que dá *access tokens*
— não ID tokens. Valida-se com o endpoint oficial `oauth2.googleapis.com/tokeninfo`
(só biblioteca padrão, sem verificar assinaturas à mão). Regras:

- o token tem de ter sido emitido para UM dos nossos CLIENT_ID (`aud`); um token
  válido de outra app Google qualquer é recusado;
- tem de trazer o e-mail verificado (a PWA pede os scopes `openid email`);
- só se aceita o que ainda não expirou;
- o token vai no CORPO de um POST para a Google, nunca num URL (não fica em logs);
- resultados ficam em cache (por hash do token, nunca o token) para não fazer
  uma chamada à Google por pedido; tokens inválidos também (curto), para que
  lixo repetido não se transforme em tráfego para a Google;
- se a Google estiver inacessível, é 503 (tentar de novo) e NÃO 401 — assim o
  fail2ban não bane utilizadores legítimos por uma falha de rede.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{20,2048}$")


class AuthError(Exception):
    status = 401
    codigo = "nao_autenticado"


class Unauthorized(AuthError):
    pass


class Unavailable(AuthError):
    status = 503
    codigo = "verificacao_indisponivel"


def _fetch_google(token: str) -> tuple[int, dict]:
    data = urllib.parse.urlencode({"access_token": token}).encode()
    req = urllib.request.Request(TOKENINFO_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read(65536))
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            return e.code, {}
        raise Unavailable("a Google respondeu com erro") from e
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise Unavailable("não foi possível contactar a Google") from e


class TokenVerifier:
    def __init__(self, client_ids: set[str], fetch: Callable[[str], tuple[int, dict]] = _fetch_google,
                 now: Callable[[], float] = time.time, ok_ttl: int = 300, bad_ttl: int = 60,
                 cache_max: int = 512):
        if not client_ids:
            raise ValueError("é preciso pelo menos um CLIENT_ID")
        self.client_ids, self.fetch, self.now = client_ids, fetch, now
        self.ok_ttl, self.bad_ttl, self.cache_max = ok_ttl, bad_ttl, cache_max
        self._cache: dict[str, tuple[float, str | None]] = {}  # hash -> (expira, email|None)

    def verify(self, token: str) -> str:
        """Devolve o e-mail (minúsculas) ou levanta Unauthorized/Unavailable."""
        if not _TOKEN_RE.match(token or ""):
            raise Unauthorized("token com formato inválido")
        key = hashlib.sha256(token.encode()).hexdigest()
        t = self.now()
        hit = self._cache.get(key)
        if hit and hit[0] > t:
            if hit[1] is None:
                raise Unauthorized("token recusado")
            return hit[1]
        try:
            email, expira = self._check(token, t)
        except Unauthorized:
            self._guardar(key, t + self.bad_ttl, None)
            raise
        self._guardar(key, min(t + self.ok_ttl, expira), email)
        return email

    def _check(self, token: str, t: float) -> tuple[str, float]:
        status, info = self.fetch(token)
        if status != 200 or not isinstance(info, dict):
            raise Unauthorized("token recusado")
        if info.get("aud") not in self.client_ids:
            raise Unauthorized("token emitido para outra aplicação")
        if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
            raise Unauthorized("token sem e-mail verificado")
        try:
            restante = int(info.get("expires_in", 0))
        except (TypeError, ValueError):
            restante = 0
        if restante <= 0:
            raise Unauthorized("token expirado")
        return str(info["email"]).lower(), t + restante

    def _guardar(self, key: str, expira: float, email: str | None) -> None:
        if len(self._cache) >= self.cache_max:
            agora = self.now()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > agora}
            while len(self._cache) >= self.cache_max:
                self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (expira, email)
