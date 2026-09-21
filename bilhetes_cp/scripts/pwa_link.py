"""Gera o link que liga a PWA às chaves da CP (uma vez por telemóvel).

A PWA só precisa das chaves da CP para confirmar horários no ecrã "Configurar
semana" (o endpoint `timetable` não exige login, mas exige as chaves da app).
Estão no .env e NUNCA devem ir para o código público da PWA. Por isso este
script cria um link com as chaves no fragmento (#...): o fragmento não é enviado
a nenhum servidor, a PWA guarda-as no localStorage do telemóvel e apaga o
fragmento do endereço.

    python3 scripts/pwa_link.py

Abre o link no telemóvel (ex.: envia-o a ti próprio por uma via privada) e
depois apaga a mensagem. Não o partilhes com mais ninguém.
"""

from __future__ import annotations

import base64
import json
import sys

import common


def build_link() -> str:
    keys = {
        "t": common.env("CP_API_KEY_TRAVEL"),
        "i": common.env("CP_CONNECT_ID"),
        "s": common.env("CP_CONNECT_SECRET"),
    }
    missing = [n for n, k in (("CP_API_KEY_TRAVEL", "t"), ("CP_CONNECT_ID", "i"),
                              ("CP_CONNECT_SECRET", "s")) if not keys[k]]
    if missing:
        raise SystemExit("Faltam no .env: " + ", ".join(missing))
    payload = base64.urlsafe_b64encode(json.dumps(keys).encode("utf-8")).decode().rstrip("=")
    base = common.app_config().get("pwa_url", "https://pereirabmd.github.io/escritorio-casa/bilhetes_cp/")
    return f"{base}#cpkeys={payload}"


if __name__ == "__main__":
    print("Abre este link UMA VEZ no telemóvel (contém as chaves da CP; não o partilhes):\n")
    print(build_link())
    print("\nDepois de abrir, a PWA guarda as chaves só nesse telemóvel e limpa o endereço.",
          file=sys.stderr)
