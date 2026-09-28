from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def configurar(log_dir: Path | None) -> logging.Logger:
    """Log do Pulse para o stdout (journald) e, se existir `PULSE_LOG_DIR`, para `api.log` rotativo."""
    log = logging.getLogger("pulse")
    if log.handlers:
        return log
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(
                log_dir / "api.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"))
        except OSError as e:
            print(f"AVISO: sem log em ficheiro ({e})", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log
