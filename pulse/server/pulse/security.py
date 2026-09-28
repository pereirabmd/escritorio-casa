"""Passwords e tokens. Só biblioteca padrão: scrypt (hashlib) para as passwords, SHA-256 para os tokens de sessão."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2 ** 14, 8, 1          # ~16 MB e uma fração de segundo no Pi
_DUMMY: str | None = None


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(h)}"


def verify_password(password: str, guardado: str) -> bool:
    try:
        esquema, n, r, p, sal, h = guardado.split("$")
        if esquema != "scrypt":
            return False
        esperado = base64.b64decode(h)
        obtido = hashlib.scrypt(password.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p), dklen=len(esperado))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(obtido, esperado)


def verify_dummy(password: str) -> None:
    """Gasta o mesmo tempo quando o utilizador não existe (não revelar que e-mails existem pelo tempo de resposta)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("dummy-" + secrets.token_hex(4))
    verify_password(password, _DUMMY)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
