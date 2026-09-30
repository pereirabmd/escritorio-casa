"""API HTTP da base de dados do Pi — serviço atrás do nginx (127.0.0.1:8898).

Segurança, por camadas (o nginx trata de TLS, HSTS, limit_req e do access log
para o fail2ban; aqui trata-se de tudo o que só a aplicação sabe):
- só escuta em 127.0.0.1; nunca expõe SQL — só endpoints com propósito, com
  validação estrita e SQL parametrizado;
- TODOS os pedidos (menos /saude e o preflight CORS) exigem `Authorization:
  Bearer <access token Google>` validado em auth.py, e o e-mail tem de estar na
  lista da app (`ACL_<APP>` no .env; sem lista = ninguém entra);
- o backend do Pulse (mesma máquina) entra sem token Google: `X-Pulse-Key` (segredo
  `PULSE_SERVICE_KEY`, ≥ 32 caracteres) + `X-Pulse-User` (e-mail). Só vale numa ligação
  direta em loopback — o nginx acrescenta sempre `X-Real-IP`, por isso um pedido vindo da
  Internet com estes cabeçalhos nunca chega lá; o e-mail continua sujeito a `ACL_<APP>`;
- CORS só para as origens de CORS_ORIGINS (por omissão o GitHub Pages);
  sem cookies, por isso não há CSRF;
- limites: corpo ≤ 16 KB, só application/json, timeout de socket, rate limit
  por IP e por utilizador, tokens inválidos contados à parte;
- erros genéricos (nunca stack traces nem SQL); tokens nunca vão para logs;
- 401 = credencial má (o fail2ban conta-os); 503 = a Google não respondeu (não conta).
"""

from __future__ import annotations

import hmac
import importlib
import json
import logging
import logging.handlers
import os
import re
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

import db
from auth import AuthError, TokenVerifier, Unauthorized

MAX_BODY = 16 * 1024
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
APPS = ["peso", "rto", "convidados", "bilhetes", "tarefas", "financas"]  # módulos em apps/ com NAME e ROUTES
LOG = logging.getLogger("dados.api")


class ApiError(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, headers: dict | None = None):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem, self.headers = status, codigo, mensagem, headers or {}


class RateLimiter:
    """Contador por janela fixa, com memória limitada."""

    def __init__(self, limite: int, janela: float = 60.0, now=time.monotonic):
        self.limite, self.janela, self.now = limite, janela, now
        self._c: dict[str, tuple[float, int]] = {}

    def allow(self, chave: str) -> bool:
        t = self.now()
        ini, n = self._c.get(chave, (t, 0))
        if t - ini >= self.janela:
            ini, n = t, 0
        if len(self._c) > 10000:
            self._c = {k: v for k, v in self._c.items() if t - v[0] < self.janela}
        self._c[chave] = (ini, n + 1)
        return n < self.limite


def _split(valor: str) -> set[str]:
    return {x.strip().lower() for x in valor.split(",") if x.strip()}


class Settings:
    def __init__(self, environ=None):
        e = environ if environ is not None else os.environ
        self.client_ids = {x.strip() for x in e.get("GOOGLE_CLIENT_IDS", "").split(",") if x.strip()}
        self.cors = {x.strip() for x in e.get("CORS_ORIGINS", "https://pereirabmd.github.io").split(",") if x.strip()}
        # ACL_<APP>=e-mail1,e-mail2 — qualquer app nova só precisa da sua linha no .env
        self.acl = {k[4:].lower(): _split(v) for k, v in e.items() if k.startswith("ACL_")}
        for a in APPS:
            self.acl.setdefault(a, set())
        chave = e.get("PULSE_SERVICE_KEY", "").strip()
        self.service_key = chave if len(chave) >= 32 else ""   # curta demais = desligado (falha fechado)
        # PULSE_ACL_DELEGADA=1: os pedidos do backend do Pulse (chave de serviço, loopback) não passam pelas listas ACL_<APP>, porque é o Pulse
        # que decide que pessoa tem que módulo (ADR-063). Os pedidos com token Google (as apps dedicadas) continuam sujeitos às listas.
        self.acl_delegada = e.get("PULSE_ACL_DELEGADA", "") == "1"
        self.dono_inicial = e.get("DONO_DADOS_INICIAL", "").strip().lower()
        self.host, self.port = "127.0.0.1", int(e.get("DADOS_API_PORT", "8898"))
        self.tz = ZoneInfo(e.get("TZ", "Europe/Lisbon"))
        self.limite_ip = int(e.get("RATE_IP_POR_MIN", "120"))
        self.limite_user = int(e.get("RATE_USER_POR_MIN", "300"))
        self.limite_falhas = int(e.get("RATE_FALHAS_POR_MIN", "10"))


APP_DB: dict[str, str] = {}   # app -> base de dados (módulo pode declarar DB = "bilhetes"; por omissão "dados")


def carregar_rotas() -> list[tuple[str, re.Pattern, str, object]]:
    rotas = []
    for nome in APPS:
        mod = importlib.import_module(f"apps.{nome}")
        APP_DB[mod.NAME] = getattr(mod, "DB", "dados")
        for metodo, padrao, fn in mod.ROUTES:
            rotas.append((metodo, re.compile(padrao), mod.NAME, fn))
    return rotas


class Contexto(SimpleNamespace):
    def db(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = db.connect_named(self._dbname)
        return self._conn

    def fechar(self):
        if self._conn is not None:
            self._conn.close()


def make_handler(settings: Settings, verifier: TokenVerifier, rotas):
    limite_ip = RateLimiter(settings.limite_ip)
    limite_user = RateLimiter(settings.limite_user)
    limite_falhas = RateLimiter(settings.limite_falhas)

    class Handler(BaseHTTPRequestHandler):
        timeout = 15  # contra clientes lentos (slowloris)
        server_version = "dados"
        sys_version = ""

        def version_string(self):
            return "dados"

        def log_message(self, fmt, *args):  # o log de acesso é feito em _fim()
            pass

        # -- métodos --------------------------------------------------------
        def do_GET(self): self._tratar()
        def do_POST(self): self._tratar()
        def do_PUT(self): self._tratar()
        def do_DELETE(self): self._tratar()
        def do_OPTIONS(self): self._tratar()
        def do_PATCH(self): self._tratar()
        def do_HEAD(self): self._tratar()

        def send_error(self, code, message=None, explain=None):  # erros do próprio http.server, em JSON
            self._enviar(code, {"erro": {"codigo": "pedido_invalido", "mensagem": "pedido inválido"}})

        # -- utilitários ----------------------------------------------------
        def _ip(self) -> str:
            peer = self.client_address[0]
            if peer in ("127.0.0.1", "::1"):  # só confiamos no nginx (loopback)
                return self.headers.get("X-Real-IP", peer)[:64]
            return peer

        def _headers_base(self) -> dict:
            h = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'",
                 "Cross-Origin-Resource-Policy": "cross-origin"}
            origem = self.headers.get("Origin")
            if origem and origem in settings.cors:
                h.update({"Access-Control-Allow-Origin": origem, "Vary": "Origin"})
            else:
                h["Vary"] = "Origin"
            return h

        def _enviar(self, status: int, corpo: dict | None, extra: dict | None = None):
            self._status = status
            dados = b"" if corpo is None or self.command == "HEAD" else json.dumps(corpo, ensure_ascii=False).encode()
            self.send_response(status)
            for k, v in {**self._headers_base(), **(extra or {})}.items():
                self.send_header(k, v)
            if corpo is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _ler_corpo(self) -> dict:
            if "Transfer-Encoding" in self.headers:
                raise ApiError(411, "sem_tamanho", "Transfer-Encoding não é aceite")
            cl = self.headers.get("Content-Length")
            if cl is None or not cl.isdigit():
                raise ApiError(411, "sem_tamanho", "Content-Length obrigatório")
            n = int(cl)
            if n > MAX_BODY:
                raise ApiError(413, "corpo_grande", f"corpo acima de {MAX_BODY} bytes")
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise ApiError(415, "tipo_invalido", "Content-Type tem de ser application/json")
            bruto = self.rfile.read(n)

            def _rejeitar(c):
                raise ValueError(c)
            try:
                corpo = json.loads(bruto.decode("utf-8"), parse_constant=_rejeitar)
            except (ValueError, UnicodeDecodeError, RecursionError):
                raise ApiError(400, "json_invalido", "corpo não é JSON válido") from None
            if not isinstance(corpo, dict):
                raise ApiError(400, "json_invalido", "o corpo tem de ser um objeto JSON")
            return corpo

        # -- fluxo principal ------------------------------------------------
        def _tratar(self):
            self._t0, self._status, self._user = time.monotonic(), 0, "-"
            ctx = Contexto(_conn=None, _dbname="dados")
            try:
                self._fluxo(ctx)
            except ApiError as e:
                self._enviar(e.status, {"erro": {"codigo": e.codigo, "mensagem": e.mensagem}}, e.headers)
            except AuthError as e:
                extra = {"WWW-Authenticate": 'Bearer realm="dados"'} if e.status == 401 else {"Retry-After": "5"}
                self._enviar(e.status, {"erro": {"codigo": e.codigo, "mensagem": str(e)}}, extra)
            except sqlite3.IntegrityError:
                self._enviar(409, {"erro": {"codigo": "conflito", "mensagem": "viola uma restrição dos dados"}})
            except sqlite3.OperationalError as e:
                LOG.error("BD indisponível: %s", e)
                self._enviar(503, {"erro": {"codigo": "bd_ocupada", "mensagem": "tenta de novo"}}, {"Retry-After": "2"})
            except Exception:
                LOG.exception("erro interno")
                self._enviar(500, {"erro": {"codigo": "erro_interno", "mensagem": "erro interno"}})
            finally:
                ctx.fechar()
                LOG.info("%s %s %s %s %s %dms", self._ip(), self._user, self.command,
                         urlsplit(self.path).path[:120], self._status, (time.monotonic() - self._t0) * 1000)

        def _fluxo(self, ctx):
            ip = self._ip()
            if not limite_ip.allow(ip):
                raise ApiError(429, "demasiados_pedidos", "abranda", {"Retry-After": "30"})
            partes = urlsplit(self.path)
            if len(self.path) > 1024:
                raise ApiError(414, "url_grande", "URL demasiado longo")
            caminho = partes.path

            if self.command == "OPTIONS":  # preflight CORS: sem auth, só responde se a origem for permitida
                ok = self.headers.get("Origin") in settings.cors
                extra = {"Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
                         "Access-Control-Allow-Headers": "Authorization, Content-Type",
                         "Access-Control-Max-Age": "600"} if ok else {}
                return self._enviar(204 if ok else 403, None, extra)
            if caminho == "/saude" and self.command in ("GET", "HEAD"):
                return self._enviar(200, {"ok": True})

            # 1) autenticação — antes de revelar se a rota existe
            chave = self.headers.get("X-Pulse-Key")
            por_servico = chave is not None
            if chave is not None:
                email = self._servico(ip, chave)
            else:
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("Bearer "):
                    limite_falhas.allow(ip) or self._raise_429()
                    raise Unauthorized("falta o token")
                try:
                    email = verifier.verify(auth[7:].strip())
                except Unauthorized:
                    if not limite_falhas.allow(ip):
                        self._raise_429()
                    raise
            self._user = email
            if not limite_user.allow(email):
                self._raise_429()

            # 2) rota + autorização da app
            permitidos, encontrada = [], None
            for metodo, padrao, app, fn in rotas:
                m = padrao.match(caminho)
                if m:
                    permitidos.append(metodo)
                    if metodo == self.command:
                        encontrada = (app, fn, m)
            if not permitidos:
                raise ApiError(404, "nao_encontrado", "recurso inexistente")
            if not encontrada:
                raise ApiError(405, "metodo_invalido", "método não permitido", {"Allow": ", ".join(sorted(set(permitidos)))})
            app, fn, m = encontrada
            if not (por_servico and settings.acl_delegada) and email not in settings.acl.get(app, set()):
                raise ApiError(403, "sem_acesso", "sem acesso a esta aplicação")

            # 3) pedido
            ctx.user, ctx.tz, ctx.groups, ctx.ip = email, settings.tz, m.groups(), ip
            ctx._dbname = APP_DB.get(app, "dados")
            ctx.query = dict(parse_qsl(partes.query, keep_blank_values=True, max_num_fields=20))
            ctx.body = self._ler_corpo() if self.command in ("POST", "PUT") else {}
            status, corpo = fn(ctx)
            self._enviar(status, corpo)

        def _servico(self, ip: str, chave: str) -> str:
            """Autenticação do backend do Pulse: chave de serviço + e-mail do utilizador, só em loopback direto."""
            direto = self.client_address[0] in ("127.0.0.1", "::1") and "X-Real-IP" not in self.headers \
                and "X-Forwarded-For" not in self.headers
            email = self.headers.get("X-Pulse-User", "").strip().lower()
            if not (direto and settings.service_key and email and _EMAIL_RE.match(email)
                    and hmac.compare_digest(chave.encode(), settings.service_key.encode())):
                if not limite_falhas.allow(ip):
                    self._raise_429()
                raise Unauthorized("credencial de serviço recusada")
            return email

        def _raise_429(self):
            raise ApiError(429, "demasiados_pedidos", "abranda", {"Retry-After": "60"})

    return Handler


def criar_servidor(settings: Settings, verifier: TokenVerifier | None = None, porta: int | None = None):
    verifier = verifier or TokenVerifier(settings.client_ids)
    srv = ThreadingHTTPServer((settings.host, settings.port if porta is None else porta),
                              make_handler(settings, verifier, carregar_rotas()))
    srv.daemon_threads = True
    return srv


def _configurar_logs():
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        (db.BASE_DIR / "logs").mkdir(exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            db.BASE_DIR / "logs" / "api.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"))
    except OSError as e:
        print(f"AVISO: sem log em ficheiro ({e})", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        LOG.addHandler(h)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def _adotar_orfaos(settings: Settings) -> None:
    """Peso e RTO ganharam dono (migração 009): o que já existia fica para o dono inicial, que é `DONO_DADOS_INICIAL` ou, se só uma pessoa
    tem acesso a Peso/RTO, essa. Com várias e sem indicação não se atribui nada (e avisa-se): ninguém veria esses dados por engano."""
    candidatos = settings.acl.get("peso", set()) | settings.acl.get("rto", set())
    dono = settings.dono_inicial or (next(iter(candidatos)) if len(candidatos) == 1 else "")
    conn = db.connect_named("dados")
    try:
        n = db.adotar_orfaos(conn, dono) if dono else None
        pendentes = db.contar_orfaos(conn)
    finally:
        conn.close()
    if n:
        LOG.info("Peso/RTO: %d linhas sem dono passaram para %s", n, dono)
    if pendentes and not dono:
        LOG.warning("Peso/RTO: %d linhas sem dono e sem DONO_DADOS_INICIAL (há várias pessoas com acesso): ninguém as vê", pendentes)


def main() -> int:
    _configurar_logs()
    settings = Settings()
    if not settings.client_ids:
        print("ERRO: GOOGLE_CLIENT_IDS não definido no .env", file=sys.stderr)
        return 1
    for app in APPS:
        if not settings.acl[app]:
            LOG.warning("ACL_%s vazia: ninguém tem acesso à app %s", app.upper(), app)
    db.migrate_all()  # o serviço arranca sempre com o esquema em dia (todas as bases)
    _adotar_orfaos(settings)
    for nome in db.DATABASES:
        db.manter_aberta(db.db_path(nome))     # sem isto cada escrita fecha a última ligação e paga um checkpoint no cartão SD
    srv = criar_servidor(settings)
    LOG.info("a escutar em %s:%d", settings.host, settings.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    # Corrido como `python3 api.py`, este ficheiro é `__main__`; os módulos de apps/ fazem `from api import ApiError` e
    # sem isto importariam uma SEGUNDA cópia (com outra classe ApiError) que o handler não apanha: 400/403/404/409 viravam 500.
    sys.modules.setdefault("api", sys.modules[__name__])
    sys.exit(main())
