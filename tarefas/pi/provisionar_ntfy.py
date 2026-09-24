#!/usr/bin/python3
"""provisionar_ntfy.py — cria/atualiza a conta de LEITURA de uma pessoa no servidor ntfy e cancela mensagens agendadas.

Corre como ROOT, disparado por `tarefas-ntfy-provision.path` quando o `servidor.py` (utilizador normal, sandbox
sem sudo) deixa um pedido em `<pi>/state/ntfy_provision/*.json` depois de a pessoa guardar o utilizador/password na
app (Config → Notificações). O utilizador e a password escritos na app passam assim a ser os do ntfy — a pessoa
usa-os na app ntfy do telemóvel — e a conta só lê o tópico dela, `tarefas_<utilizador>`.

Também cancela mensagens AGENDADAS: o ntfy 2.11 não tem `DELETE /<tópico>/<id>` (404), por isso reagendar deixava a mensagem
antiga a disparar (duplicados). Pedido `{"cancelar": {"topic": "tarefas_x", "id": "<id>"}}` → apaga essa linha ainda por
publicar (`published=0`) da cache do ntfy (só tópicos `tarefas*`).

Instalado em /usr/local/sbin (dono root; nunca executar um ficheiro de uma pasta que o utilizador altera).
Como um utilizador normal escreve os pedidos, TUDO é validado aqui: nomes restritos, tópico sempre `tarefas_*`,
contas de sistema protegidas, ficheiros só se regulares e pequenos. Os pedidos (têm a password) apagam-se sempre.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

PEDIDOS = Path(os.environ.get("TAREFAS_PROVISION_DIR", "/home/bpereira/tarefas/pi/state/ntfy_provision"))
PROTEGIDOS = {"tarefas-pi", "bpereira", "admin", "root", "everyone", "*"}
_USER = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
MAX_BYTES = 2048
CACHE_NTFY = Path(os.environ.get("NTFY_CACHE_DB", "/var/cache/ntfy/cache.db"))
_MID = re.compile(r"^[A-Za-z0-9]{6,20}$")
_TOPICO = re.compile(r"^tarefas(_[a-z0-9_-]{1,40})?$")


def topico_de(user: str) -> str:
    return user if user.startswith("tarefas_") else f"tarefas_{user}"     # igual a common.topico_da_pessoa


def validar(pedido: object) -> tuple[str, str, str]:
    if not isinstance(pedido, dict) or set(pedido) != {"user", "password"}:
        raise ValueError("pedido mal formado")
    user, password = pedido["user"], pedido["password"]
    if not isinstance(user, str) or not isinstance(password, str):
        raise ValueError("user e password têm de ser texto")
    user = user.strip().lower()
    if not _USER.match(user) or user in PROTEGIDOS:
        raise ValueError(f"utilizador não permitido: {user!r}")
    if not 6 <= len(password) <= 100 or any(c in password for c in "\r\n\x00"):
        raise ValueError("password inválida (6 a 100 caracteres, numa linha)")
    return user, password, topico_de(user)


def validar_cancelar(pedido: object) -> tuple[str, str]:
    c = pedido.get("cancelar") if isinstance(pedido, dict) and set(pedido) == {"cancelar"} else None
    if not isinstance(c, dict) or set(c) != {"topic", "id"} or not isinstance(c["topic"], str) or not isinstance(c["id"], str):
        raise ValueError("pedido de cancelamento mal formado")
    if not _TOPICO.match(c["topic"]) or not _MID.match(c["id"]):
        raise ValueError("tópico ou id de mensagem não permitidos")
    return c["topic"], c["id"]


def cancelar_agendada(topic: str, mid: str, cache: Path = CACHE_NTFY) -> int:
    """Apaga a mensagem AINDA POR PUBLICAR (published=0). Devolve quantas linhas apagou (0 se já saiu)."""
    import sqlite3
    conn = sqlite3.connect(cache, timeout=20)
    try:
        n = conn.execute("DELETE FROM messages WHERE mid = ? AND topic = ? AND published = 0", (mid, topic)).rowcount
        conn.commit()
        return n
    finally:
        conn.close()


def ntfy(*args: str, password: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, **({"NTFY_PASSWORD": password} if password is not None else {}))
    return subprocess.run(["ntfy", *args], env=env, capture_output=True, text=True, timeout=30)


def aplicar(user: str, password: str, topico: str, run=ntfy) -> str:
    existe = re.search(rf"^user {re.escape(user)} ", run("user", "list").stdout, re.M) is not None
    r = run("user", "change-pass" if existe else "add", *(() if existe else ("--role=user",)), user, password=password)
    if r.returncode != 0:
        raise RuntimeError(f"ntfy user {'change-pass' if existe else 'add'} falhou: {r.stderr.strip()[:200]}")
    r = run("access", user, topico, "ro")
    if r.returncode != 0:
        raise RuntimeError(f"ntfy access falhou: {r.stderr.strip()[:200]}")
    return "atualizada" if existe else "criada"


def processar(pasta: Path = PEDIDOS, run=ntfy, cache: Path = CACHE_NTFY) -> list[str]:
    resultados = []
    for f in sorted(pasta.glob("*.json")):
        try:
            st = f.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
                raise ValueError("ficheiro não regular ou demasiado grande")
            bruto = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(bruto, dict) and "cancelar" in bruto:
                topic, mid = validar_cancelar(bruto)
                resultados.append(f"cancelar {topic}/{mid}: {cancelar_agendada(topic, mid, cache)} apagada(s)")
                continue
            user, password, topico = validar(bruto)
            resultados.append(f"conta {user}: {aplicar(user, password, topico, run)} (só lê {topico})")
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
            resultados.append(f"ERRO em {f.name}: {e}")
        finally:
            try:
                f.unlink()
            except OSError:
                pass
    return resultados


if __name__ == "__main__":
    saidas = processar()
    for linha in saidas:
        print(linha, flush=True)
    sys.exit(1 if any(s.startswith("ERRO") for s in saidas) else 0)
