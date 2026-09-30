"""Credenciais da CP por pessoa (PLANO_FINAL 9.11, fase 2).

O Bruno marca as viagens (no Pulse ou na PWA) e a compra faz-se **com a conta CP, o NIF, o cartão de cidadão e o Passe Verde de quem viaja**.

- Utilizador 1 (Bruno): continua a usar o `.env` (`CP_EMAIL`, `CP_PASSWORD`, …), exatamente como antes: o caminho que já compra não muda.
- Os outros: lêem-se de `bilhetes_utilizadores` (bilhetes.db); a password da CP vem cifrada (Fernet) e decifra-se aqui com `BILHETES_FERNET_KEY`
  (que tem de estar no `.env` do `bilhetes_cp`). Nada disto é registado em log: só os NOMES dos campos em falta.
- Uma pessoa com dados em falta não compra: levanta `CredenciaisIncompletas` (o chamador avisa e não tenta), nunca compra com os dados de outra.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import common

UTILIZADOR_PRINCIPAL = 1


class CredenciaisIncompletas(Exception):
    """A pessoa não tem (todos) os dados da CP preenchidos, ou a password não se consegue decifrar. A mensagem nunca traz valores."""


@dataclass(frozen=True)
class Credenciais:
    utilizador_id: int
    nome: str
    cp_email: str
    cp_password: str
    passageiro_nome: str
    passageiro_cc: str
    passageiro_telemovel: str
    nif: str
    passe_numero: str

    def __repr__(self) -> str:                 # nunca deixa a password nem os documentos ir parar a um log por engano
        return f"Credenciais(utilizador_id={self.utilizador_id}, nome={self.nome!r})"


def do_ambiente() -> Credenciais:
    """O utilizador 1, a partir do `.env` (o mesmo que o `cp_ticket` sempre leu)."""
    e = os.environ.get
    return Credenciais(UTILIZADOR_PRINCIPAL, "Bruno", e("CP_EMAIL", ""), e("CP_PASSWORD", ""), e("CP_PASSENGER_NAME", ""), e("CP_PASSENGER_CC", ""),
                       e("CP_PASSENGER_PHONE", ""), e("CP_PASSENGER_NIF", ""), e("CP_GREEN_PASS_NUMBER", ""))


_CAMPOS = (("cp_email", "e-mail da CP"), ("cp_password_enc", "password da CP"), ("passageiro_nome", "nome do passageiro"), ("passageiro_cc", "cartão de cidadão"),
           ("passageiro_telemovel", "telemóvel"), ("nif", "NIF"), ("passe_verde_numero", "nº do Passe Verde"))


def _decifrar(cifrado: str) -> str:
    chave = os.environ.get("BILHETES_FERNET_KEY", "")
    if not chave:
        raise CredenciaisIncompletas("falta BILHETES_FERNET_KEY no .env dos bilhetes (não consigo decifrar a password)")
    try:
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet(chave.encode()).decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        raise CredenciaisIncompletas("a password guardada não se decifra com esta chave: volta a introduzi-la na administração") from None


def _base_de_dados() -> Path:
    import store
    return store.default_db_path()


def carregar(utilizador_id: int, base: Path | str | None = None) -> Credenciais:
    """As credenciais de quem viaja. Utilizador 1 → `.env` (sem ler a base). Levanta `CredenciaisIncompletas` se faltar algo."""
    if utilizador_id == UTILIZADOR_PRINCIPAL:
        return do_ambiente()
    caminho = Path(base) if base else _base_de_dados()
    with closing(sqlite3.connect(caminho, timeout=10)) as c:
        c.row_factory = sqlite3.Row
        u = c.execute("SELECT * FROM bilhetes_utilizadores WHERE id = ?", (utilizador_id,)).fetchone()
    if u is None:
        raise CredenciaisIncompletas(f"o utilizador {utilizador_id} não existe")
    if not u["ativo"]:
        raise CredenciaisIncompletas(f"{u['nome']} está desativado(a)")
    em_falta = [nome for campo, nome in _CAMPOS if not str(u[campo] or "").strip()]
    if em_falta:
        raise CredenciaisIncompletas(f"faltam dados de {u['nome']}: " + ", ".join(em_falta))
    return Credenciais(utilizador_id, u["nome"], u["cp_email"].strip(), _decifrar(u["cp_password_enc"]), u["passageiro_nome"].strip(), u["passageiro_cc"].strip(),
                       u["passageiro_telemovel"].strip(), u["nif"].strip(), u["passe_verde_numero"].strip())


def email_pulse(utilizador_id: int, base: Path | str | None = None) -> str | None:
    """O e-mail da conta Pulse de quem viaja (o que recebe os avisos da sua viagem); `None` se não tiver conta ou for o utilizador 1."""
    if utilizador_id == UTILIZADOR_PRINCIPAL:
        return None
    try:
        with closing(sqlite3.connect(Path(base) if base else _base_de_dados(), timeout=5)) as c:
            r = c.execute("SELECT email FROM bilhetes_utilizadores WHERE id = ?", (utilizador_id,)).fetchone()
    except (sqlite3.Error, OSError):
        return None
    return (r[0] or "").strip().lower() or None if r else None


def nome_de(utilizador_id: int, base: Path | str | None = None) -> str:
    """O nome de quem viaja, para os títulos dos avisos («(Camila)»); vazio para o utilizador 1 ou se não se souber."""
    if utilizador_id == UTILIZADOR_PRINCIPAL:
        return ""
    try:
        with closing(sqlite3.connect(Path(base) if base else _base_de_dados(), timeout=5)) as c:
            r = c.execute("SELECT nome FROM bilhetes_utilizadores WHERE id = ?", (utilizador_id,)).fetchone()
    except (sqlite3.Error, OSError):
        return ""
    return (r[0] or "") if r else ""
