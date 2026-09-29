"""Cliente do `tarefas-api` (o servidor do Pi que agenda os avisos ntfy) — só para pedir o recálculo imediato dos avisos.

Entra com a mesma chave de serviço do `dados-api` (`X-Pulse-Key`/`X-Pulse-User`), em loopback direto. É uma otimização: se falhar, o
timer de 5 minutos (`tarefas-recalcular.timer`) reconcilia na mesma, por isso nunca levanta erro nem atrasa o utilizador.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request

LOG = logging.getLogger("pulse.tarefas_api")


class TarefasApiClient:
    def __init__(self, base_url: str, service_key: str, timeout: float = 30.0):
        self.base_url, self.service_key, self.timeout = base_url.rstrip("/"), service_key, timeout

    def recalcular(self, utilizador: str) -> bool:
        """`POST /recalcularAgora`, síncrono. True se o servidor respondeu 200."""
        if not (self.base_url and self.service_key):
            return False
        req = urllib.request.Request(self.base_url + "/recalcularAgora", data=b"{}", method="POST",
                                     headers={"X-Pulse-Key": self.service_key, "X-Pulse-User": utilizador, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status == 200
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            LOG.warning("recálculo imediato dos avisos falhou (o timer de 5 min reconcilia): %s", e)
            return False

    def gerar(self, utilizador: str) -> dict | None:
        """`POST /gerar` (cria já as ocorrências dos próximos dias e marca as atrasadas). None se o servidor não respondeu."""
        return self._chamar("POST", "/gerar", utilizador)

    def saude(self) -> dict | None:
        """`GET /saude` (público): última reconciliação dos avisos no Pi. None se não respondeu."""
        return self._chamar("GET", "/saude", None)

    def _chamar(self, metodo: str, caminho: str, utilizador: str | None) -> dict | None:
        if not self.base_url or (utilizador and not self.service_key):
            return None
        cab = {"Content-Type": "application/json"}
        if utilizador:
            cab.update({"X-Pulse-Key": self.service_key, "X-Pulse-User": utilizador})
        req = urllib.request.Request(self.base_url + caminho, data=b"{}" if metodo == "POST" else None, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 10.0)) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            LOG.warning("tarefas-api %s falhou: %s", caminho, e)
            return None

    def recalcular_em_fundo(self, utilizador: str) -> None:
        """Não faz o utilizador esperar pelo agendamento no ntfy."""
        threading.Thread(target=self.recalcular, args=(utilizador,), daemon=True).start()
