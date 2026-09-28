from __future__ import annotations

import threading
import time


class RateLimiter:
    """Contador por janela fixa, com memória limitada (por processo)."""

    def __init__(self, limite: int, janela: float = 60.0, now=time.monotonic):
        self.limite, self.janela, self.now = limite, janela, now
        self._c: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, chave: str) -> bool:
        with self._lock:
            t = self.now()
            ini, n = self._c.get(chave, (t, 0))
            if t - ini >= self.janela:
                ini, n = t, 0
            if len(self._c) > 10000:
                self._c = {k: v for k, v in self._c.items() if t - v[0] < self.janela}
            self._c[chave] = (ini, n + 1)
            return n < self.limite
