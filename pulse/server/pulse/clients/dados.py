"""Cliente do `dados-api` (Peso, RTO, Tarefas, Finanças, Bilhetes CP) — ADR-031.

Entra com a chave de serviço + o e-mail do utilizador Pulse (`X-Pulse-Key`/`X-Pulse-User`), só em loopback direto.
Só biblioteca padrão (menos dependências no Pi). Chamadas síncronas: usar em endpoints `def` (correm numa thread).
Uma falha de rede/timeout/5xx é `ModuloIndisponivel` (modo degradado); um 4xx do módulo é `ErroDoModulo`, com o
código e a mensagem originais, para o Pulse os poder mostrar (ex.: 409 ao adiar uma tarefa).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class ModuloIndisponivel(Exception):
    pass


class ErroDoModulo(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem = status, codigo, mensagem


class DadosClient:
    def __init__(self, base_url: str, service_key: str, timeout: float = 5.0):
        self.base_url, self.service_key, self.timeout = base_url.rstrip("/"), service_key, timeout

    def pedir(self, metodo: str, caminho: str, utilizador: str, query: dict | None = None, corpo: dict | None = None, timeout: float | None = None):
        if not self.service_key:
            raise ModuloIndisponivel("PULSE_SERVICE_KEY não configurada")
        url = self.base_url + caminho + ("?" + urllib.parse.urlencode(query) if query else "")
        if corpo is None and metodo in ("POST", "PUT", "PATCH"):
            corpo = {}                      # o dados-api exige `application/json` em todo o POST/PUT, mesmo sem dados («Tentar agora»)
        dados = json.dumps(corpo).encode() if corpo is not None else None
        headers = {"X-Pulse-Key": self.service_key, "X-Pulse-User": utilizador}
        if dados is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=dados, method=metodo, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            corpo_erro = _json(e.read())
            if e.code >= 500:
                raise ModuloIndisponivel(f"dados-api respondeu {e.code}") from e
            erro = corpo_erro.get("erro", {}) if isinstance(corpo_erro, dict) else {}
            raise ErroDoModulo(e.code, erro.get("codigo", "erro"), erro.get("mensagem", "")) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ModuloIndisponivel("não foi possível contactar o dados-api") from e

    def saude(self) -> bool:
        """`/saude` do dados-api (sem credenciais); False se não responder."""
        try:
            with urllib.request.urlopen(self.base_url + "/saude", timeout=min(self.timeout, 2.0)) as r:
                return r.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


def _json(bruto: bytes):
    try:
        return json.loads(bruto.decode("utf-8")) if bruto else None
    except (ValueError, UnicodeDecodeError):
        return None
