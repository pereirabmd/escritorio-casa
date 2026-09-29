"""Configuração a partir do ambiente (`.env` carregado pelo systemd; nunca no Git).

Regra dos docs: testes e desenvolvimento nunca escrevem em bases de produção. Por isso, fora de
`PULSE_ENV=production`, o ficheiro da base tem de se chamar `teste-*.db`; e em produção não pode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    env: str
    db_path: Path
    web_base_path: str
    dados_url: str
    tarefas_url: str
    service_key: str
    log_dir: Path | None
    session_days: int
    tz: ZoneInfo
    fcm_credentials: Path | None = None       # ficheiro JSON da service account (só no Pi, fora do repositório); vazio = FCM desligado
    scheduler_s: int = 30                     # intervalo do agendador de notificações (0 = desligado)
    fcm_project: str = ""                    # projeto Firebase (por omissão o `project_id` do ficheiro)

    @property
    def production(self) -> bool:
        return self.env == "production"


def _base_path(v: str) -> str:
    miolo = v.strip().strip("/")
    return f"/{miolo}/" if miolo else "/"


def _inteiro(v: str, nome: str, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except ValueError:
        raise ConfigError(f"{nome} tem de ser um inteiro") from None
    if not lo <= n <= hi:
        raise ConfigError(f"{nome} fora do intervalo [{lo}, {hi}]")
    return n


def load(environ: dict[str, str] | None = None) -> Settings:
    e = os.environ if environ is None else environ
    env = e.get("PULSE_ENV", "development").strip().lower()
    if env not in ("development", "test", "production"):
        raise ConfigError(f"PULSE_ENV inválido: {env!r}")
    db_path = Path(e.get("PULSE_DB_PATH", "").strip() or "/var/lib/pulse-test/teste-pulse.db")
    nome = db_path.name
    if env == "production" and nome.startswith("teste-"):
        raise ConfigError("em produção a base não pode ser uma base de teste (teste-*)")
    if env != "production" and not nome.startswith("teste-"):
        raise ConfigError(f"fora de produção a base tem de se chamar teste-*.db (recebi {nome!r})")
    log_dir = e.get("PULSE_LOG_DIR", "").strip()
    return Settings(
        env=env,
        db_path=db_path,
        web_base_path=_base_path(e.get("PULSE_WEB_BASE_PATH", "/pulse/")),
        dados_url=e.get("PULSE_DADOS_URL", "http://127.0.0.1:8898").rstrip("/"),
        tarefas_url=e.get("PULSE_TAREFAS_URL", "http://127.0.0.1:8899").rstrip("/"),
        service_key=e.get("PULSE_SERVICE_KEY", "").strip(),
        log_dir=Path(log_dir) if log_dir else None,
        tz=ZoneInfo(e.get("TZ", "Europe/Lisbon")),
        session_days=_inteiro(e.get("PULSE_SESSION_DAYS", "30"), "PULSE_SESSION_DAYS", 1, 365),
        fcm_credentials=Path(e["PULSE_FCM_CREDENTIALS"].strip()) if e.get("PULSE_FCM_CREDENTIALS", "").strip() else None,
        fcm_project=e.get("PULSE_FCM_PROJECT", "").strip(),
        scheduler_s=_inteiro(e.get("PULSE_SCHEDULER_S", "30"), "PULSE_SCHEDULER_S", 0, 3600),
    )
