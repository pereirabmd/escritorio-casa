"""Pre-flight formal antes de cada disparo (PLANO_FINAL.md 3.10.4).

Ordem: internet -> DNS da CP -> relógio sincronizado (3.10.1) -> credenciais ->
config local válida (3.10.2) -> CP alcançável + cross-check do `Date` (3.11.1)
-> ntfy operacional (publica mesmo uma mensagem e confirma 2xx).

O login na CP (o único do disparo) é feito a seguir, pelo processo de compra, a T-5 min (3.1).

Também se pode correr à mão para diagnosticar o RPi:
    python scripts/pre_flight.py            # publica uma mensagem de teste no ntfy
    python scripts/pre_flight.py --no-ntfy  # não publica
"""

from __future__ import annotations

import argparse
import email.utils
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date

import requests

import common
from common import BASE_DIR, Leg, app_config, env, get_logger

log = get_logger("preflight")

REQUIRED_ENV = (
    "CP_EMAIL", "CP_PASSWORD", "CP_PASSENGER_NAME", "CP_PASSENGER_CC", "CP_PASSENGER_PHONE",
    "CP_PASSENGER_NIF", "CP_GREEN_PASS_NUMBER", "CP_CONNECT_ID", "CP_CONNECT_SECRET",
    "CP_API_KEY_TRAVEL", "CP_API_KEY_TICKETING", "GOOGLE_SHEET_ID",
    "NTFY_SERVER_URL", "NTFY_TOPIC", "NTFY_USERNAME", "NTFY_PASSWORD",
)
CP_HOSTS = ("api-gateway.cp.pt", "login.cp.pt")
CP_API = "https://api-gateway.cp.pt/cp/services/"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = True

    def __str__(self) -> str:
        mark = "OK " if self.ok else ("FALHA" if self.critical else "AVISO")
        return f"[{mark}] {self.name}: {self.detail}"


# -- verificações individuais ------------------------------------------------

def check_internet() -> Check:
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 443), timeout=3):
                return Check("internet", True, f"ligação a {host}:443 ok")
        except OSError:
            continue
    return Check("internet", False, "sem ligação TCP a 1.1.1.1 nem 8.8.8.8")


def check_dns() -> Check:
    bad = []
    for host in CP_HOSTS:
        try:
            socket.getaddrinfo(host, 443)
        except socket.gaierror:
            bad.append(host)
    return Check("dns_cp", not bad, "resolve " + ", ".join(CP_HOSTS) if not bad
                 else "não resolve: " + ", ".join(bad))


def parse_chrony_tracking(text: str) -> tuple[float | None, str, str]:
    """(desvio em segundos com sinal, leap status, reference id) a partir de `chronyc tracking`."""
    offset = None
    m = re.search(r"System time\s*:\s*([\d.]+) seconds (fast|slow)", text)
    if m:
        offset = float(m.group(1)) * (1 if m.group(2) == "fast" else -1)
    leap = (re.search(r"Leap status\s*:\s*(.+)", text) or [None, ""])[1].strip()
    ref = (re.search(r"Reference ID\s*:\s*(\S+)", text) or [None, ""])[1].strip()
    return offset, leap, ref


def check_clock() -> Check:
    max_ms = float(app_config().get("purchase", {}).get("clock_max_offset_ms", 150))
    if not shutil.which("chronyc"):
        return Check("relogio", False, "chronyc não está instalado (o chrony é a referência do disparo)")
    try:
        out = subprocess.run(["chronyc", "tracking"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        return Check("relogio", False, f"chronyc falhou: {type(e).__name__}")
    offset, leap, ref = parse_chrony_tracking(out.stdout)
    if out.returncode != 0 or offset is None:
        return Check("relogio", False, "não consegui ler `chronyc tracking`")
    if leap != "Normal" or ref in ("", "00000000"):
        return Check("relogio", False, f"chrony não sincronizado (leap={leap!r}, ref={ref})")
    ms = offset * 1000
    if abs(ms) > max_ms:
        return Check("relogio", False, f"desvio de {ms:+.1f} ms acima do limite de ±{max_ms:.0f} ms")
    return Check("relogio", True, f"chrony sincronizado, desvio {ms:+.3f} ms (limite ±{max_ms:.0f} ms)")


def check_credentials() -> Check:
    missing = [k for k in REQUIRED_ENV if not env(k)]
    sa = env("GOOGLE_SERVICE_ACCOUNT_FILE", "./config/service-account.json")
    sa_path = BASE_DIR / sa if not sa.startswith("/") else __import__("pathlib").Path(sa)
    if not sa_path.is_file():
        missing.append("service-account.json")
    return Check("credenciais", not missing,
                 "variáveis e service account presentes" if not missing
                 else "em falta: " + ", ".join(missing))


def check_config(leg: Leg | None, today: date | None = None) -> Check:
    """A cache local (3.10.2) existe, é válida e contém a perna a comprar."""
    cache = common.load_config_cache()
    if cache is None:
        return Check("config_local", False, "config_cache.json em falta ou ilegível")
    legs, issues = common.parse_config_rows(cache["weekly"], today or common.now_local().date())
    if leg is None:
        return Check("config_local", True, f"cache válida: {len(legs)} perna(s), {len(issues)} problema(s)")
    match = [l for l in legs if l.key == leg.key]
    if not match:
        return Check("config_local", False, f"a perna {leg.key} já não consta da config válida")
    if (match[0].train, match[0].hhmm) != (leg.train, leg.hhmm):
        return Check("config_local", False,
                     f"a perna {leg.key} mudou (comboio {match[0].train}, {match[0].hhmm})")
    return Check("config_local", True, f"perna {leg.key} presente e válida na cache")


def check_cp_reachable(samples: int = 3, spacing_s: float = 1.5) -> Check:
    """A CP responde e o seu `Date` está grosseiramente alinhado com o relógio local.

    Poucas amostras espaçadas (não rajadas): só apanha desvios grosseiros de
    segundos ou mais — não calibra ao milissegundo (3.11.1).
    """
    max_s = float(app_config().get("purchase", {}).get("cp_date_max_offset_s", 3.0))
    offsets: list[float] = []
    reached = False
    for i in range(samples):
        if i:
            time.sleep(spacing_s)
        try:
            t0 = time.time()
            r = requests.head(CP_API, timeout=(4, 6), allow_redirects=False)
            t1 = time.time()
        except requests.RequestException:
            continue
        reached = True
        hdr = r.headers.get("Date")
        if hdr:
            server = email.utils.parsedate_to_datetime(hdr).timestamp()
            # o Date é truncado ao segundo: o instante real está em [server, server+1)
            offsets.append(server + 0.5 - (t0 + t1) / 2)
    if not reached:
        return Check("cp_alcancavel", False, "sem resposta de api-gateway.cp.pt")
    if not offsets:
        return Check("cp_alcancavel", True, "CP responde, mas sem header Date", critical=False)
    worst = max(offsets, key=abs)
    if abs(worst) > max_s:
        return Check("cp_date", False, f"relógio da CP vs local desviado {worst:+.1f}s (limite ±{max_s:.0f}s)")
    return Check("cp_alcancavel", True, f"CP responde; Date alinhado (desvio grosseiro {worst:+.1f}s, {len(offsets)} amostras)")


def check_ntfy(title: str, message: str) -> Check:
    ok = common.notify(title, message, tags=["train"], logger=log)
    return Check("ntfy", ok, "mensagem publicada (2xx)" if ok else "não consegui publicar no ntfy")


# -- orquestração -------------------------------------------------------------

def run_preflight(leg: Leg | None = None, ntfy: tuple[str, str] | None = None) -> list[Check]:
    """Corre as verificações na ordem do plano. Continua mesmo que uma falhe."""
    checks = [check_internet(), check_dns(), check_clock(), check_credentials(),
              check_config(leg), check_cp_reachable()]
    if ntfy:
        checks.append(check_ntfy(*ntfy))
    for c in checks:
        (log.info if c.ok else log.error)("%s", c)
    return checks


def failed(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.ok and c.critical]


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico pre-flight do RPi")
    ap.add_argument("--no-ntfy", action="store_true", help="não publicar mensagem de teste")
    args = ap.parse_args()
    checks = run_preflight(None, None if args.no_ntfy else
                           ("Pre-flight manual", "Diagnóstico do RPi a correr (teste manual)."))
    print()
    for c in checks:
        print(c)
    bad = failed(checks)
    print(f"\n{'TUDO OK' if not bad else f'{len(bad)} verificação(ões) crítica(s) falhada(s)'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
