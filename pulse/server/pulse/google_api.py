"""Cliente das APIs da Google para o Pulse (ADR-049): OAuth (código + PKCE), refresh tokens cifrados, Calendar e Gmail.

- Só biblioteca padrão para a rede (`urllib`), como o resto do servidor; a cifra dos refresh tokens usa `cryptography` (Fernet),
  importada só quando a integração está ligada (`requirements-google.txt`).
- O `transporte` é injetável `(metodo, url, cabecalhos, corpo_bytes) -> (status, corpo_bytes)`: os testes nunca falam com a Google.
- Os access tokens (1 h) guardam-se só em memória; os refresh tokens só cifrados na base. Nada disto é registado em logs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CALENDAR = "https://www.googleapis.com/calendar/v3"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"

# scopes mínimos por serviço
SCOPES = {
    "gmail": ("https://www.googleapis.com/auth/gmail.modify",),        # ler e organizar (lida, arquivar, estrela); nunca enviar nem apagar
    "calendar": ("https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"),
}
SCOPES_BASE = ("openid", "email", "profile")
SERVICOS = tuple(SCOPES)
ESTADO_TTL_S = 600


class GoogleErro(Exception):
    """`reautorizar`: o Google recusou o refresh token (revogado/expirado): a conta tem de ser ligada de novo."""

    def __init__(self, mensagem: str, status: int = 0, codigo: str = "erro_google", reautorizar: bool = False, temporario: bool = False):
        super().__init__(mensagem)
        self.status, self.codigo, self.reautorizar, self.temporario = status, codigo, reautorizar, temporario


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    chave: str


class Cofre:
    """Cifra/decifra os refresh tokens (Fernet). Sem `cryptography` ou com chave inválida, não existe."""

    def __init__(self, chave: str):
        from cryptography.fernet import Fernet      # import tardio: dependência opcional
        self._f = Fernet(chave.encode())

    def cifrar(self, texto: str) -> str:
        return self._f.encrypt(texto.encode()).decode()

    def decifrar(self, cifrado: str) -> str:
        return self._f.decrypt(cifrado.encode()).decode()


def criar_cofre(chave: str) -> Cofre | None:
    if not chave:
        return None
    try:
        return Cofre(chave)
    except (ImportError, ValueError, TypeError):
        return None


def servicos_de_scopes(scope: str) -> list[str]:
    """Os serviços que o Google realmente concedeu (o utilizador pode desmarcar permissões no ecrã de consentimento)."""
    dados = set(scope.split())
    return [s for s, req in SCOPES.items() if all(r in dados for r in req)]


def pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, desafio


def _http(metodo: str, url: str, cabecalhos: dict, corpo: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GoogleErro(f"sem ligação à Google ({type(e).__name__})", temporario=True) from e


def _json(bruto: bytes):
    try:
        return json.loads(bruto.decode("utf-8")) if bruto else None
    except (ValueError, UnicodeDecodeError):
        return None


class GoogleApi:
    def __init__(self, cfg: GoogleConfig, cofre: Cofre, transporte=None, agora=time.time):
        self.cfg, self.cofre, self.agora = cfg, cofre, agora
        self.transporte = transporte or _http
        self._tokens: dict[int, tuple[str, float]] = {}      # id da conta -> (access token, expira)
        self._trinco = threading.Lock()

    # --- OAuth ------------------------------------------------------------------------------------------------------------------
    def url_autorizacao(self, servicos: list[str], state: str, desafio: str, login_hint: str = "") -> str:
        scopes = [*SCOPES_BASE, *(s for sv in servicos for s in SCOPES[sv])]
        q = {"client_id": self.cfg.client_id, "redirect_uri": self.cfg.redirect_uri, "response_type": "code", "scope": " ".join(scopes),
             "access_type": "offline", "prompt": "select_account consent", "include_granted_scopes": "false", "state": state,
             "code_challenge": desafio, "code_challenge_method": "S256"}
        if login_hint:
            q["login_hint"] = login_hint
        return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"

    def _form(self, url: str, campos: dict) -> tuple[int, dict]:
        status, raw = self.transporte("POST", url, {"Content-Type": "application/x-www-form-urlencoded"}, urllib.parse.urlencode(campos).encode())
        return status, _json(raw) or {}

    def trocar_codigo(self, code: str, verificador: str) -> dict:
        status, r = self._form(TOKEN_URL, {"code": code, "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
                                           "redirect_uri": self.cfg.redirect_uri, "grant_type": "authorization_code", "code_verifier": verificador})
        if status != 200 or "access_token" not in r:
            raise GoogleErro("a Google recusou o código de autorização", status, r.get("error", "erro_google"))
        return r

    def perfil(self, access_token: str) -> dict:
        status, raw = self.transporte("GET", USERINFO_URL, {"Authorization": f"Bearer {access_token}"}, None)
        r = _json(raw) or {}
        if status != 200 or not r.get("email"):
            raise GoogleErro("não foi possível ler o perfil da conta Google", status)
        return {"email": r["email"], "nome": r.get("name", "")}

    def revogar(self, token: str) -> None:
        try:
            self._form(REVOKE_URL, {"token": token})
        except GoogleErro:
            pass                                        # melhor esforço: apagar a conta localmente é o que interessa

    def access_token(self, conta: int, refresh_cifrado: str) -> str:
        with self._trinco:
            t = self._tokens.get(conta)
        if t and t[1] - 60 > self.agora():
            return t[0]
        status, r = self._form(TOKEN_URL, {"client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
                                           "refresh_token": self.cofre.decifrar(refresh_cifrado), "grant_type": "refresh_token"})
        if status == 200 and "access_token" in r:
            with self._trinco:
                self._tokens[conta] = (r["access_token"], self.agora() + int(r.get("expires_in", 3600)))
            return r["access_token"]
        if r.get("error") == "invalid_grant" or status in (400, 401):
            self.esquecer(conta)
            raise GoogleErro("a autorização desta conta Google terminou: liga-a de novo", status, "invalid_grant", reautorizar=True)
        raise GoogleErro("a Google não deu um novo acesso", status, r.get("error", "erro_google"), temporario=status >= 500 or status == 429)

    def esquecer(self, conta: int) -> None:
        with self._trinco:
            self._tokens.pop(conta, None)

    # --- pedidos às APIs -------------------------------------------------------------------------------------------------------
    def pedir(self, conta: int, refresh_cifrado: str, metodo: str, url: str, query: dict | None = None, corpo: dict | None = None):
        """(status, json). 401 renova o acesso uma vez; 4xx/5xx → GoogleErro com o motivo; 204/404-em-delete dependem de quem chama."""
        for tentativa in (1, 2):
            cab = {"Authorization": f"Bearer {self.access_token(conta, refresh_cifrado)}", "Accept": "application/json"}
            dados = None
            if corpo is not None:
                dados = json.dumps(corpo).encode()
                cab["Content-Type"] = "application/json"
            alvo = url + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
            status, raw = self.transporte(metodo, alvo, cab, dados)
            if status == 401 and tentativa == 1:
                self.esquecer(conta)
                continue
            r = _json(raw)
            if 200 <= status < 300:
                return status, r
            erro = (r or {}).get("error", {}) if isinstance(r, dict) else {}
            motivo = erro.get("message", "") if isinstance(erro, dict) else str(erro)
            if status == 401:
                raise GoogleErro(motivo or "a Google recusou o acesso", status, "sem_permissao", reautorizar=True)
            if status == 403:
                raise GoogleErro(motivo or "sem permissão para este serviço", status, "sem_permissao")
            raise GoogleErro(motivo or f"a Google respondeu HTTP {status}", status, "erro_google", temporario=status >= 500 or status == 429)
        raise GoogleErro("a Google recusou o acesso", 401, "sem_permissao", reautorizar=True)
