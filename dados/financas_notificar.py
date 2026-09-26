"""Avisos do ntfy da app financas: uma notificação no próprio dia do vencimento de cada lançamento
(despesa ou rendimento) ainda sem data de pagamento. Corre de hora a hora (financas-notificar.timer):
`notificado_em` garante um só aviso por lançamento, e um lançamento criado a meio do dia ainda avisa
nesse dia. Sem insistência: se o dia passar, não há segundo aviso (a app mostra o que está vencido).

Só biblioteca padrão. Config no .env: NTFY_SERVER_URL, NTFY_WRITE_USER, NTFY_WRITE_PASSWORD,
NTFY_FINANCAS_TOPIC (por omissão `financas`), FINANCAS_URL.
Uso:  python3 financas_notificar.py [--simular]
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import db

LOG = logging.getLogger("financas.notificar")
APP_URL = "https://pereirabmd.github.io/escritorio-casa/financas/"


def eur(v: float) -> str:
    """1234.5 -> '1 234,50 €' (espaço fino não separável, vírgula decimal)."""
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def pendentes_de_hoje(conn, hoje: str) -> list:
    return conn.execute(
        "SELECT l.id, l.tipo, l.descricao, l.valor, c.nome AS categoria FROM financas_lancamentos l "
        "JOIN financas_categorias c ON c.id = l.categoria_id "
        "WHERE l.data_vencimento = ? AND l.data_pagamento IS NULL AND l.notificado_em IS NULL "
        "ORDER BY l.id", (hoje,)).fetchall()


def montar(l) -> dict:
    if l["tipo"] == "rendimento":
        titulo, tag = f"Rendimento previsto hoje: {l['descricao']}", "moneybag"
    else:
        titulo, tag = f"Vence hoje: {l['descricao']}", "money_with_wings"
    return {"title": titulo, "message": f"{eur(l['valor'])} · {l['categoria']}", "tags": [tag]}


def publicar(msg: dict, env=os.environ) -> bool:
    base = env.get("NTFY_SERVER_URL", "").rstrip("/")
    user, senha = env.get("NTFY_WRITE_USER", ""), env.get("NTFY_WRITE_PASSWORD", "")
    if not (base and user and senha):
        LOG.error("NTFY_SERVER_URL/NTFY_WRITE_USER/NTFY_WRITE_PASSWORD em falta no .env")
        return False
    corpo = {"topic": env.get("NTFY_FINANCAS_TOPIC", "financas"), "priority": 4,   # sempre Priority high: aparece no ecrã
             "click": env.get("FINANCAS_URL", APP_URL), **msg}
    req = urllib.request.Request(
        base + "/", data=json.dumps(corpo).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Basic " + base64.b64encode(f"{user}:{senha}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError) as e:
        LOG.error("publicação no ntfy falhou: %s: %s", type(e).__name__, e)
        return False


def correr(conn, agora: datetime, enviar=publicar) -> tuple[int, int]:
    """Devolve (enviados, falhados). Marca `notificado_em` só depois de o ntfy aceitar."""
    enviados = falhados = 0
    for l in pendentes_de_hoje(conn, agora.strftime("%Y-%m-%d")):
        if enviar(montar(l)):
            conn.execute("UPDATE financas_lancamentos SET notificado_em = ? WHERE id = ?",
                         (agora.strftime("%Y-%m-%d %H:%M:%S"), l["id"]))
            enviados += 1
        else:
            falhados += 1
    return enviados, falhados


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    agora = datetime.now(ZoneInfo(os.environ.get("TZ", "Europe/Lisbon")))
    conn = db.connect_named("dados")
    try:
        if "--simular" in argv:
            for l in pendentes_de_hoje(conn, agora.strftime("%Y-%m-%d")):
                print(montar(l))
            return 0
        enviados, falhados = correr(conn, agora)
    finally:
        conn.close()
    if enviados or falhados:
        LOG.info("avisos enviados: %d, falhados: %d", enviados, falhados)
    return 1 if falhados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
