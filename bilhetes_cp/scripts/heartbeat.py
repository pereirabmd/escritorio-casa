"""Heartbeat para o healthchecks.io (PLANO_FINAL secção 6, PLANO_UP 5.3).

O ntfy corre no próprio RPi: se o RPi, o router, o DDNS ou a internet caírem, nenhum
aviso chega. Este ping de 5 em 5 minutos a um serviço EXTERNO faz o contrário: é a falta
do ping que dispara o alerta (por email ou webhook), e por isso apanha o RPi em baixo.

Inativo enquanto HEALTHCHECKS_PING_URL estiver vazio no .env: só regista isso uma vez por dia.
Para ativar: criar um check em healthchecks.io (período 5 min, tolerância 10 min) e colar o
URL de ping no .env do RPi.
"""

from __future__ import annotations

import sys
import time

import requests

import common
from common import env, get_logger

log = get_logger("heartbeat")


def main() -> int:
    url = env("HEALTHCHECKS_PING_URL")
    if not url:
        marker = common._state_file("heartbeat_unconfigured")
        if not marker.exists() or time.time() - marker.stat().st_mtime > 86400:
            log.info("HEALTHCHECKS_PING_URL vazio: heartbeat inativo (RPi em baixo NÃO gera alerta).")
            marker.touch()
        return 0
    try:
        r = requests.get(url, timeout=(5, 10))
        r.raise_for_status()
        return 0
    except requests.RequestException as e:
        log.error("Ping ao healthchecks.io falhou: %s", type(e).__name__)
        common.notify_once("heartbeat-failed", "Não consegui contactar o healthchecks.io",
                           f"O ping de vida falhou ({type(e).__name__}). Sem ele, um RPi em baixo não gera alerta.",
                           cooldown_s=6 * 3600, logger=log)
        return 1


if __name__ == "__main__":
    sys.exit(main())
