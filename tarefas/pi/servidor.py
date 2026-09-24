"""servidor.py — porta de WebApp.gs (doPost) para um serviço HTTP no Pi.

Não existe equivalente no bilhetes_cp (lá o Pi só faz chamadas de saída);
aqui a PWA e a ação "Marcar feita"/"Daqui a 1h" da própria notificação ntfy
chamam este serviço. Fica atrás de um `location` novo no MESMO nginx/
domínio/TLS já montado para o ntfy — nunca exposto diretamente.

Autenticação (desde a migração para SQLite, 24/09/2026 — antes estes endpoints eram públicos, protegidos só por o
URL "não ser divulgado", num repositório público):
- `gerar`, `recalcularAgora`, `configurarNtfy`, `testar` — os que a PWA chama — exigem `Authorization: Bearer <token
  Google>` de um e-mail em `ACL_TAREFAS` (a mesma validação da API dos dados: `dados/auth.py`); sem isso, 401/403.
  Fecham-se por defeito: sem `GOOGLE_CLIENT_IDS`/`ACL_TAREFAS` configurados respondem 503, nunca "abertos".
- CORS só para `CORS_ORIGINS` (por omissão o GitHub Pages): até aqui a PWA nem conseguia ler as respostas.
- `marcarFeita`/`snooze` continuam a aceitar a assinatura HMAC `s` das ações `http` embutidas nas notificações ntfy
  (que correm sem contexto Google nenhum) — é o único caminho sem token, e a assinatura é obrigatória quando presente.
- `saude` é público (versão e contagens, nada sensível).

    python servidor.py
"""

from __future__ import annotations

import hmac
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import common
import instancias
import recalcular
from common import SheetsClient, get_logger

log = get_logger("servidor")

VERSAO = "RPi v1"

# Ao tocar na notificação (fora dos botões de ação), o ntfy abre este URL em
# vez do próprio ecrã de detalhe do ntfy — mesmo URL usado em recalcular.py.
URL_APP = common.env("TAREFAS_APP_URL", "https://pereirabmd.github.io/escritorio-casa/tarefas/")


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
    instancias.marcar_atrasadas(sheets)
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
    try:
        import provisionar_ntfy
        provisionar_ntfy.validar({"user": ntfy_user, "password": ntfy_password})   # as mesmas regras do serviço que cria a conta
    except ValueError as e:
        return {"ok": False, "erro": f"{e} — utilizador: letras minúsculas, números, _ ou - (2 a 40); password: 6 a 100 caracteres"}
    n = _numero_pessoa(sheets.read_objects("Config"), pessoa)
    if n is None:
        return {"ok": False, "erro": f'pessoa "{pessoa}" não encontrada em Config (Pessoa{{N}}_Nome)'}
    cifrado = common.encrypt(ntfy_password)
    # Duas escritas separadas (idioma find-or-append já existente) — nunca
    # em paralelo, sempre sequenciais, para não repetir o bug da Beta 35.
    sheets.set_config(f"Pessoa{n}_NtfyUser", ntfy_user)
    sheets.set_config(f"Pessoa{n}_NtfyPasswordEnc", cifrado)
    # o utilizador/password da app passam a ser a conta ntfy da pessoa (só lê o tópico dela): pedido para o serviço root
    try:
        common.pedir_provisionamento_ntfy(ntfy_user, ntfy_password)
        aviso = "Conta ntfy criada/atualizada em segundos; subscreve o tópico " + (common.topico_da_pessoa({f"Pessoa{n}_Nome": pessoa, f"Pessoa{n}_NtfyUser": ntfy_user}, pessoa) or "") + " na app ntfy."
    except OSError:
        log.exception("não consegui deixar o pedido de conta ntfy")
        aviso = "Guardado, mas a conta ntfy não foi criada (ver logs do Pi)."
    return {"ok": True, "aviso": aviso}


def handle_testar(sheets: SheetsClient, params: dict[str, Any]) -> dict[str, Any]:
    pessoa = str(params.get("pessoa") or "").strip()
    if not pessoa:
        return {"ok": False, "erro": "pessoa é obrigatória"}
    config = {str(r.get("Chave", "")).strip(): r.get("Valor") for r in sheets.read_objects("Config")}
    topico = common.topico_da_pessoa(config, pessoa)
    resp = common.ntfy_publish(
        title="Teste", message=f"Notificação de teste para {pessoa} — Tarefas de Casa 👋",
        tags=["test_tube"], click=URL_APP, topic=topico,
    )
    if resp is None:
        return {"ok": False, "erro": "Falha ao publicar no ntfy — ver logs do Pi."}
    onde = f"tópico {topico}" if topico else f"tópico partilhado {common.env('NTFY_TOPIC', common.TOPICO_LEGADO)} ({pessoa} ainda não tem utilizador ntfy)"
    return {"ok": True, "aviso": f"Publicado no {onde} — confirma na app ntfy de {pessoa}."}


# ---------------------------------------------------------------------------
# Autenticação dos endpoints da PWA (token Google, via dados/auth.py — só biblioteca padrão)
# ---------------------------------------------------------------------------

ENDPOINTS_PWA = {"/gerar", "/recalcularAgora", "/configurarNtfy", "/testar"}
MAX_CORPO = 16 * 1024
_VERIFICADOR: Any = None


class CorpoGrande(Exception):
    pass


def _verificador():
    """O TokenVerifier (partilhado com a API dos dados). None se não estiver configurado — e então falha fechado."""
    global _VERIFICADOR
    if _VERIFICADOR is None:
        ids = {x.strip() for x in common.env("GOOGLE_CLIENT_IDS").split(",") if x.strip()}
        if not ids:
            return None
        dados = Path(common.env("DADOS_HOME") or (common.BASE_DIR.parents[1] / "dados"))
        if str(dados) not in sys.path:
            sys.path.append(str(dados))
        import auth
        _VERIFICADOR = auth.TokenVerifier(ids)
    return _VERIFICADOR


def _acl() -> set[str]:
    return {x.strip().lower() for x in common.env("ACL_TAREFAS").split(",") if x.strip()}


def autenticar(cabecalho: str) -> tuple[int, str]:
    """(status, motivo): 200 se o token é válido e o e-mail está em ACL_TAREFAS."""
    acl, ver = _acl(), _verificador()
    if ver is None or not acl:
        return 503, "autenticação não configurada"
    if not cabecalho.startswith("Bearer "):
        return 401, "falta o token"
    try:
        email = ver.verify(cabecalho[7:].strip())
    except Exception as e:  # Unauthorized (401) / Unavailable (503, a Google não respondeu: não é culpa do cliente)
        return getattr(e, "status", 401), str(e)
    return (200, email) if email in acl else (403, "sem acesso")


def _origens_cors() -> set[str]:
    return {x.strip() for x in common.env("CORS_ORIGINS", "https://pereirabmd.github.io").split(",") if x.strip()}


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
        if length > MAX_CORPO:
            raise CorpoGrande()
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
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        origem = self.headers.get("Origin")
        self.send_header("Vary", "Origin")
        if origem and origem in _origens_cors():
            self.send_header("Access-Control-Allow-Origin", origem)
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:   # preflight CORS: sem autenticação, só responde a origens permitidas
        origem = self.headers.get("Origin")
        ok = bool(origem) and origem in _origens_cors()
        self.send_response(204 if ok else 403)
        self.send_header("Vary", "Origin")
        if ok:
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _tratar(self) -> None:
        caminho = urlsplit(self.path).path.rstrip("/") or "/"
        rota = _ROTAS.get(caminho)
        if rota is None:
            self._responder({"ok": False, "erro": "endpoint desconhecido"}, status=404)
            return
        if caminho in ENDPOINTS_PWA:
            estado, motivo = autenticar(self.headers.get("Authorization", ""))
            if estado != 200:
                self._responder({"ok": False, "erro": motivo}, status=estado)
                return
        try:
            params = self._params()
            corpo = rota(self.server.sheets_factory(), params)
        except CorpoGrande:
            self._responder({"ok": False, "erro": "corpo demasiado grande"}, status=413)
            return
        except Exception:  # nunca deixar a ligação sem resposta — nem revelar detalhes internos ao cliente
            log.exception("Erro a tratar %s", caminho)
            self._responder({"ok": False, "erro": "erro interno"}, status=500)
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


def criar_servidor(porta: int, sheets_factory: Any = common.get_store) -> ThreadingHTTPServer:
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
