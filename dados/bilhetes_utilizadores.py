"""Utilizadores do `bilhetes_cp` (tabela `bilhetes_utilizadores` da `bilhetes.db`): validação, cifra das passwords da CP e CRUD.

Usado pela página de administração da LAN (`admin_db.py`, rota `/bilhetes`) e pela API (só o resumo, sem segredos).

    python bilhetes_utilizadores.py gerar-chave                 # imprime uma chave Fernet nova (para BILHETES_FERNET_KEY)
    python bilhetes_utilizadores.py importar-env ~/bilhetes_cp/.env [--id 1]
                                                                # copia CP_EMAIL/CP_PASSWORD/... do .env para o utilizador (sem imprimir valores)

Segredos: a password da CP guarda-se cifrada (Fernet); a chave vive só no `.env` do Pi (BILHETES_FERNET_KEY), nunca na BD nem
no Git. Nunca é devolvida por nenhuma função pública (só `cp_password_definida`).
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

import db

CAMPOS_TEXTO = ("cp_email", "passageiro_nome", "passageiro_cc", "passageiro_telemovel", "nif", "passe_verde_numero")
CAMPOS = ("nome", "email", "admin", "ativo", *CAMPOS_TEXTO, "passe_data_ultima_compra", "passe_validade_dias")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_CC = re.compile(r"^[0-9A-Z]{8,12}$")
_TEL = re.compile(r"^(PT|\+\d{1,3})?\d{9,12}$")
_PASSE = re.compile(r"^[0-9A-Za-z-]{4,30}$")
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class UtilizadorErro(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


class SemChave(UtilizadorErro):
    def __init__(self):
        super().__init__(500, "BILHETES_FERNET_KEY em falta no .env: sem ela não posso cifrar nem decifrar passwords")


# -- cifra -----------------------------------------------------------------

def _fernet(chave: str | None = None):
    from cryptography.fernet import Fernet
    chave = chave or os.environ.get("BILHETES_FERNET_KEY", "")
    if not chave:
        raise SemChave()
    try:
        return Fernet(chave.encode())
    except ValueError:
        raise UtilizadorErro(500, "BILHETES_FERNET_KEY inválida") from None


def cifrar(texto: str, chave: str | None = None) -> str:
    return _fernet(chave).encrypt(texto.encode()).decode()


def decifrar(cifrado: str, chave: str | None = None) -> str:
    """Só para os scripts de compra (fase 2). Nunca chamar a partir da API/página."""
    from cryptography.fernet import InvalidToken
    try:
        return _fernet(chave).decrypt(cifrado.encode()).decode()
    except InvalidToken:
        raise UtilizadorErro(500, "password cifrada com outra chave (ou corrompida): volta a introduzi-la") from None


def gerar_chave() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# -- validação -------------------------------------------------------------

def nif_valido(nif: str) -> bool:
    """NIF português: 9 dígitos com o dígito de controlo (módulo 11)."""
    if not re.fullmatch(r"\d{9}", nif):
        return False
    soma = sum(int(d) * (9 - i) for i, d in enumerate(nif[:8]))
    controlo = 11 - soma % 11
    return int(nif[8]) == (0 if controlo >= 10 else controlo)


def _texto(v, campo: str, maximo: int) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise UtilizadorErro(400, f"{campo} tem de ser texto")
    v = _CTRL.sub("", v).strip()
    if len(v) > maximo:
        raise UtilizadorErro(400, f"{campo}: no máximo {maximo} caracteres")
    return v


def _bool(v, campo: str) -> int:
    if not isinstance(v, bool):
        raise UtilizadorErro(400, f"{campo} tem de ser verdadeiro ou falso")
    return int(v)


def validar_campo(campo: str, v):
    """Valor canónico de UM campo (levanta UtilizadorErro se for inválido)."""
    if campo == "nome":
        n = _texto(v, "nome", 40)
        if not n:
            raise UtilizadorErro(400, "nome é obrigatório")
        return n
    if campo == "email":
        e = _texto(v, "email", 120).lower()
        if not e:
            return None                      # sem login próprio
        if not _EMAIL.match(e):
            raise UtilizadorErro(400, "e-mail inválido")
        return e
    if campo in ("admin", "ativo"):
        return _bool(v, campo)
    if campo == "cp_email":
        e = _texto(v, "cp_email", 120).lower()
        if e and not _EMAIL.match(e):
            raise UtilizadorErro(400, "e-mail da CP inválido")
        return e
    if campo == "passageiro_nome":
        return _texto(v, campo, 100)
    if campo == "passageiro_cc":
        c = re.sub(r"\s+", "", _texto(v, campo, 20)).upper()
        if c and not _CC.match(c):
            raise UtilizadorErro(400, "nº do Cartão de Cidadão inválido (8 a 12 letras/dígitos)")
        return c
    if campo == "passageiro_telemovel":
        t = re.sub(r"[\s.-]+", "", _texto(v, campo, 25)).upper()
        if t and not _TEL.match(t):
            raise UtilizadorErro(400, "telemóvel inválido (ex.: 912345678, PT912345678 ou +351912345678)")
        return t
    if campo == "nif":
        n = re.sub(r"\s+", "", _texto(v, campo, 15))
        if n and not nif_valido(n):
            raise UtilizadorErro(400, "NIF inválido (9 dígitos com dígito de controlo certo)")
        return n
    if campo == "passe_verde_numero":
        p = re.sub(r"\s+", "", _texto(v, campo, 40))
        if p and not _PASSE.match(p):
            raise UtilizadorErro(400, "nº do Passe Verde inválido (4 a 30 letras, dígitos ou hífens)")
        return p
    if campo == "passe_data_ultima_compra":
        d = _texto(v, campo, 10)
        if not d:
            return None
        from datetime import date
        try:
            if not _DATA.match(d):
                raise ValueError
            date.fromisoformat(d)
        except ValueError:
            raise UtilizadorErro(400, "data do último carregamento do passe inválida (AAAA-MM-DD)") from None
        return d
    if campo == "passe_validade_dias":
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 366:
            raise UtilizadorErro(400, "validade do passe: inteiro entre 1 e 366 dias")
        return v
    raise UtilizadorErro(400, f"campo desconhecido: {campo}")


def _password(v) -> str | None:
    """None/'' = não alterar."""
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not 1 <= len(v) <= 200 or _CTRL.search(v):
        raise UtilizadorErro(400, "password inválida (1 a 200 caracteres, sem caracteres de controlo)")
    return v


# -- CRUD ------------------------------------------------------------------

_COLUNAS_PUBLICAS = "id, " + ", ".join(CAMPOS) + ", (cp_password_enc <> '') AS cp_password_definida"


def _publico(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("admin", "ativo", "cp_password_definida"):
        d[k] = bool(d[k])
    return d


def listar(conn: sqlite3.Connection) -> list[dict]:
    return [_publico(r) for r in conn.execute(f"SELECT {_COLUNAS_PUBLICAS} FROM bilhetes_utilizadores ORDER BY id")]


def obter(conn: sqlite3.Connection, uid: int) -> dict | None:
    r = conn.execute(f"SELECT {_COLUNAS_PUBLICAS} FROM bilhetes_utilizadores WHERE id = ?", (uid,)).fetchone()
    return _publico(r) if r else None


def _regras_admin(conn: sqlite3.Connection, uid: int | None, novo: dict) -> None:
    """O utilizador 1 é sempre administrador ativo; tem de sobrar pelo menos um administrador ativo."""
    if uid == 1 and (novo.get("admin") == 0 or novo.get("ativo") == 0):
        raise UtilizadorErro(400, "o utilizador 1 (Bruno) tem de continuar administrador e ativo")


def _campos_validados(dados: dict, obrigatorio_nome: bool) -> tuple[dict, str | None, bool]:
    extra = set(dados) - set(CAMPOS) - {"password", "limpar_password"}
    if extra:
        raise UtilizadorErro(400, f"campos não aceites: {sorted(extra)[:5]}")
    if obrigatorio_nome and "nome" not in dados:
        raise UtilizadorErro(400, "nome é obrigatório")
    valores = {c: validar_campo(c, dados[c]) for c in CAMPOS if c in dados}
    limpar = dados.get("limpar_password") is True
    return valores, _password(dados.get("password")), limpar


def criar(conn: sqlite3.Connection, dados: dict) -> dict:
    valores, pw, _ = _campos_validados(dados, obrigatorio_nome=True)
    if conn.execute("SELECT COUNT(*) FROM bilhetes_utilizadores").fetchone()[0] >= 20:
        raise UtilizadorErro(400, "limite de 20 utilizadores")
    if pw is not None:
        valores["cp_password_enc"] = cifrar(pw)
    cols = list(valores)
    try:
        cur = conn.execute(f"INSERT INTO bilhetes_utilizadores ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                           [valores[c] for c in cols])
    except sqlite3.IntegrityError as e:
        raise UtilizadorErro(409, _conflito(e)) from None
    return obter(conn, cur.lastrowid)


def atualizar(conn: sqlite3.Connection, uid: int, dados: dict) -> tuple[dict, list[str]]:
    """Devolve (utilizador, nomes dos campos alterados). A password só muda se vier preenchida."""
    valores, pw, limpar = _campos_validados(dados, obrigatorio_nome=False)
    if not obter(conn, uid):
        raise UtilizadorErro(404, "utilizador inexistente")
    _regras_admin(conn, uid, valores)
    if pw is not None:
        valores["cp_password_enc"] = cifrar(pw)
    elif limpar:
        valores["cp_password_enc"] = ""
    if not valores:
        raise UtilizadorErro(400, "nada para alterar")
    try:
        conn.execute(f"UPDATE bilhetes_utilizadores SET {', '.join(f'{c} = ?' for c in valores)} WHERE id = ?", [*valores.values(), uid])
    except sqlite3.IntegrityError as e:
        raise UtilizadorErro(409, _conflito(e)) from None
    return obter(conn, uid), [("cp_password" if c == "cp_password_enc" else c) for c in valores]


def apagar(conn: sqlite3.Connection, uid: int) -> dict:
    u = obter(conn, uid)
    if not u:
        raise UtilizadorErro(404, "utilizador inexistente")
    try:
        conn.execute("DELETE FROM bilhetes_utilizadores WHERE id = ?", (uid,))
    except sqlite3.IntegrityError:
        raise UtilizadorErro(409, "utilizador com dados (ou o Bruno): desativa em vez de apagar") from None
    return u


def _conflito(e: Exception) -> str:
    m = str(e)
    if "nome" in m:
        return "já existe um utilizador com esse nome"
    if "email" in m:
        return "já existe um utilizador com esse e-mail"
    return "os dados violam uma restrição"


# -- importação do .env do bilhetes_cp -------------------------------------

ENV_PARA_CAMPO = {"CP_EMAIL": "cp_email", "CP_PASSENGER_NAME": "passageiro_nome", "CP_PASSENGER_CC": "passageiro_cc",
                  "CP_PASSENGER_PHONE": "passageiro_telemovel", "CP_PASSENGER_NIF": "nif", "CP_GREEN_PASS_NUMBER": "passe_verde_numero"}


def ler_env(caminho: Path) -> dict[str, str]:
    out = {}
    for raw in caminho.read_text(encoding="utf-8").splitlines():
        linha = raw.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def importar_env(conn: sqlite3.Connection, caminho: Path, uid: int = 1) -> dict:
    """Copia as credenciais/dados do .env para o utilizador `uid`, campo a campo (um campo inválido não trava os outros).
    Devolve {"definidos": [...], "ignorados": {campo: motivo}} — nunca valores."""
    env = ler_env(caminho)
    definidos, ignorados = [], {}
    for chave, campo in ENV_PARA_CAMPO.items():
        if not env.get(chave):
            continue
        try:
            atualizar(conn, uid, {campo: env[chave]})
            definidos.append(campo)
        except UtilizadorErro as e:
            ignorados[campo] = e.mensagem
    if env.get("CP_PASSWORD"):
        try:
            atualizar(conn, uid, {"password": env["CP_PASSWORD"]})
            definidos.append("cp_password")
        except UtilizadorErro as e:
            ignorados["cp_password"] = e.mensagem
    return {"definidos": definidos, "ignorados": ignorados}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "gerar-chave":
        print(gerar_chave())
        return 0
    if cmd == "importar-env" and len(argv) >= 3:
        uid = int(argv[argv.index("--id") + 1]) if "--id" in argv else 1
        conn = db.connect_named("bilhetes")
        try:
            r = importar_env(conn, Path(argv[2]).expanduser(), uid)
        except UtilizadorErro as e:
            print("ERRO:", e.mensagem, file=sys.stderr)
            return 1
        finally:
            conn.close()
        print("definidos:", ", ".join(r["definidos"]) or "nenhum")
        for c, m in r["ignorados"].items():
            print(f"IGNORADO {c}: {m}")
        return 1 if r["ignorados"] else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
