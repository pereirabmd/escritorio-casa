"""servidor.py — porta de WebApp.gs (doPost) para um serviço HTTP no Pi.

Não existe equivalente no bilhetes_cp (lá o Pi só faz chamadas de saída);
aqui a PWA e a ação "Marcar feita"/"Daqui a 1h" da própria notificação ntfy
chamam este serviço. Fica atrás de um `location` novo no MESMO nginx/
domínio/TLS já montado para o ntfy — nunca exposto diretamente.

Autenticação ao mesmo nível de risco que o `WebApp.gs` de hoje: os
endpoints de baixo risco (gerar, configurarNtfy, testar, recalcularAgora)
continuam sem segredo, protegidos só por o URL não ser divulgado — mesmo
modelo já aceite para o sistema atual. Só `marcarFeita`/`snooze` aceitam
(mas não exigem) uma assinatura `s` — obrigatória apenas quando vem da
ação `http` embutida na própria notificação ntfy (ver recalcular.py:
acoes_notificacao/assinar_instancia), que corre sem contexto Google
nenhum; a chamada feita pela própria PWA (com a Google Sheet já aberta)
continua sem segredo, tal como hoje.

    python servidor.py
"""

from __future__ import annotations

import hmac
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import common
import instancias
import recalcular
from common import SheetsClient, get_logger

log = get_logger("servidor")

VERSAO = "RPi v1"


# ---------------------------------------------------------------------------
# Núcleo dos handlers — sem nada de HTTP, para os testes chamarem direto
# com um SheetsClient falso.
# ---------------------------------------------------------------------------

def handle_saude() -> dict[str, Any]:
    estado = common._read_json(common._state_file("saude.json"), {})
    ultima = estado.get("ultima_execucao")
    if not ultima:
        return {"ok": True, "versao": VERSAO, "ultimaExecucao": None, "minutosDesde": None, "saudavel": False}
    minutos = (common.now_local() - datetime.fromisoformat(ultima)).total_seconds() / 60
    return {
        "ok": True, "versao": VERSAO, "ultimaExecucao": ultima,
        "minutosDesde": round(minutos), "saudavel": minutos < 30,
        "contagens": estado.get("contagens", {}),
    }


def handle_gerar(sheets: SheetsClient) -> dict[str, Any]:
    n = instancias.gerar_instancias(sheets)
    return {"ok": True, "criadas": n}


def handle_recalcular_agora(sheets: SheetsClient) -> dict[str, Any]:
    contagens = recalcular.recalcular(sheets)
    return {"ok": True, "contagens": contagens}


def _instancia_por_id(sheets: SheetsClient, instancia_id: str) -> dict[str, Any] | None:
    return next((r for r in sheets.read_objects("Instancias") if str(r.get("ID")) == instancia_id), None)


def _assinatura_valida(instancia_id: str, params: dict[str, Any]) -> bool:
    """A assinatura só é EXIGIDA quando está presente (chamada pela ação da
    notificação); em falta, a chamada é tratada como vinda da própria PWA
    — mesmo nível de risco do WebApp.gs de hoje (URL não divulgado)."""
    assinatura = params.get("s")
    if not assinatura:
        return True
    return hmac.compare_digest(str(assinatura), recalcular.assinar_instancia(instancia_id))


def _recalcular_em_fundo(sheets: SheetsClient) -> None:
    """Reconcilia já, sem esperar pelo próximo ciclo do cron — mas uma falha
    aqui não anula a escrita já feita na Sheet; o cron é a rede de segurança."""
    try:
        recalcular.recalcular(sheets)
    except Exception:
        log.exception("recalcular (disparado pelo servidor) falhou")


def handle_marcar_feita(sheets: SheetsClient, params: dict[str, Any]) -> dict[str, Any]:
    instancia_id = str(params.get("instanciaId") or params.get("id") or "").strip()
    if not instancia_id:
        return {"ok": False, "erro": "instanciaId é obrigatório"}
    if not _assinatura_valida(instancia_id, params):
        return {"ok": False, "erro": "assinatura inválida"}
    inst = _instancia_por_id(sheets, instancia_id)
    if inst is None:
        return {"ok": False, "erro": "instância não encontrada"}
    agora_txt = common.now_local().strftime("%Y-%m-%d %H:%M")
    sheets.update_cells("Instancias", inst["_rowIndex"], Estado="Feita", DataConclusao=agora_txt)
    _recalcular_em_fundo(sheets)
    return {"ok": True}


def handle_snooze(sheets: SheetsClient, params: dict[str, Any]) -> dict[str, Any]:
    instancia_id = str(params.get("instanciaId") or params.get("id") or "").strip()
    if not instancia_id:
        return {"ok": False, "erro": "instanciaId é obrigatório"}
    if not _assinatura_valida(instancia_id, params):
        return {"ok": False, "erro": "assinatura inválida"}
    inst = _instancia_por_id(sheets, instancia_id)
    if inst is None:
        return {"ok": False, "erro": "instância não encontrada"}
    try:
        minutos = int(params.get("minutos") or 60)
    except (TypeError, ValueError):
        minutos = 60
    # Reabre a possibilidade de notificar (o alvo_instancia ignora quem já
    # tem NotificacaoEnviada=TRUE) — a hora nova fica só no estado local,
    # não numa coluna nova da Sheet, mesmo espírito do F01 original.
    sheets.update_cells("Instancias", inst["_rowIndex"], NotificacaoEnviada="FALSE")
    ate = recalcular.registar_snooze(instancia_id, minutos)
    _recalcular_em_fundo(sheets)
    return {"ok": True, "ate": ate.isoformat()}


def _numero_pessoa(config_rows: list[dict[str, Any]], pessoa: str) -> str | None:
    import re
    for r in config_rows:
        m = re.fullmatch(r"Pessoa(\d+)_Nome", str(r.get("Chave", "")).strip())
        if m and str(r.get("Valor", "")).strip() == pessoa:
            return m.group(1)
    return None


def handle_configurar_ntfy(sheets: SheetsClient, params: dict[str, Any]) -> dict[str, Any]:
    pessoa = str(params.get("pessoa") or "").strip()
    ntfy_user = str(params.get("ntfyUser") or "").strip()
    ntfy_password = str(params.get("ntfyPassword") or "")
    if not pessoa or not ntfy_user or not ntfy_password:
        return {"ok": False, "erro": "pessoa, ntfyUser e ntfyPassword são obrigatórios"}
    n = _numero_pessoa(sheets.read_objects("Config"), pessoa)
    if n is None:
        return {"ok": False, "erro": f'pessoa "{pessoa}" não encontrada em Config (Pessoa{{N}}_Nome)'}
    cifrado = common.encrypt(ntfy_password)
    # Duas escritas separadas (idioma find-or-append já existente) — nunca
    # em paralelo, sempre sequenciais, para não repetir o bug da Beta 35.
    sheets.set_config(f"Pessoa{n}_NtfyUser", ntfy_user)
    sheets.set_config(f"Pessoa{n}_NtfyPasswordEnc", cifrado)
    return {"ok": True}


def handle_testar(sheets: SheetsClient, params: dict[str, Any]) -> dict[str, Any]:
    pessoa = str(params.get("pessoa") or "").strip()
    if not pessoa:
        return {"ok": False, "erro": "pessoa é obrigatória"}
    resp = common.ntfy_publish(
        title="Teste", message=f"Notificação de teste para {pessoa} — Tarefas de Casa 👋",
        tags=["test_tube"],
    )
    if resp is None:
        return {"ok": False, "erro": "Falha ao publicar no ntfy — ver logs do Pi."}
    return {"ok": True, "aviso": f"Publicado no tópico partilhado — confirma na app ntfy de {pessoa}."}


# ---------------------------------------------------------------------------
# Camada HTTP
# ---------------------------------------------------------------------------

_ROTAS = {
    "/saude": lambda sheets, params: handle_saude(),
    "/gerar": lambda sheets, params: handle_gerar(sheets),
    "/recalcularAgora": lambda sheets, params: handle_recalcular_agora(sheets),
    "/marcarFeita": handle_marcar_feita,
    "/snooze": handle_snooze,
    "/configurarNtfy": handle_configurar_ntfy,
    "/testar": handle_testar,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TarefasAPI/1"

    def _params(self) -> dict[str, Any]:
        query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        length = int(self.headers.get("Content-Length") or 0)
        body: dict[str, Any] = {}
        if length:
            raw = self.rfile.read(length)
            try:
                lido = json.loads(raw.decode("utf-8"))
                if isinstance(lido, dict):
                    body = lido
            except (ValueError, UnicodeDecodeError):
                pass
        return {**query, **body}

    def _responder(self, corpo: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _tratar(self) -> None:
        caminho = urlsplit(self.path).path.rstrip("/") or "/"
        rota = _ROTAS.get(caminho)
        if rota is None:
            self._responder({"ok": False, "erro": "endpoint desconhecido"}, status=404)
            return
        try:
            params = self._params()
            corpo = rota(self.server.sheets_factory(), params)
        except Exception as e:  # nunca deixar a ligação sem resposta
            log.exception("Erro a tratar %s", caminho)
            corpo = {"ok": False, "erro": str(e)}
            self._responder(corpo, status=500)
            return
        # 401 no próprio HTTP (não só no corpo) para o nginx/fail2ban conseguir
        # vigiar tentativas de assinatura inválida na ação da notificação —
        # mesmo padrão do jail ntfy-auth já montado (ver deploy/).
        status = 401 if corpo.get("erro") == "assinatura inválida" else 200
        self._responder(corpo, status=status)

    def do_GET(self) -> None:
        self._tratar()

    def do_POST(self) -> None:
        self._tratar()

    def log_message(self, fmt: str, *args: Any) -> None:  # silencia o default (stderr); vai para o logger
        log.info("%s - %s", self.address_string(), fmt % args)


def criar_servidor(porta: int, sheets_factory: Any = SheetsClient) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    servidor.sheets_factory = sheets_factory  # type: ignore[attr-defined]
    return servidor


def main() -> int:
    porta = int(common.env("TAREFAS_API_PORT", "8899"))
    servidor = criar_servidor(porta)
    log.info("servidor.py à escuta em 127.0.0.1:%d", porta)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
