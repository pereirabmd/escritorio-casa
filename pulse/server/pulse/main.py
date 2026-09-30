"""Aplicação FastAPI do Pulse. Correr no Pi: `uvicorn pulse.asgi:app --host 127.0.0.1 --port 8897`."""

from __future__ import annotations

import os
import time
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pulse import VERSION, config, db, logging_setup, notifications
from pulse.services import compras
from pulse.accounts import ContaErro
from datetime import datetime

from pulse.api.v1 import actions, auth, dashboard, calendar, finance, google as google_rotas, health, mail, modules, notifications as notificacoes, rto, shopping, tasks, tickets, weight
from pulse.google_api import GoogleApi, GoogleConfig, criar_cofre
from pulse.notifications import FcmCanal
from pulse.ratelimit import RateLimiter
from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel
from pulse.clients.tarefas_api import TarefasApiClient

LOG = logging.getLogger("pulse")


async def _agendador(app: FastAPI) -> None:
    """Todos os `scheduler_s` segundos entrega os eventos agendados que já venceram (ADR-032: o FCM não agenda, o Pulse espera)."""
    def uma_volta() -> None:
        conn = app.state.db()
        try:
            notifications.despachar_vencidos(conn, app.state.canais)
        finally:
            conn.close()
    while True:
        await asyncio.sleep(app.state.settings.scheduler_s)
        try:
            await asyncio.to_thread(uma_volta)
        except Exception:      # uma volta falhada nunca mata o agendador
            LOG.exception("falha no agendador de notificações")


def _google(settings: config.Settings) -> GoogleApi | None:
    """A integração Google só liga com cliente OAuth, redirect, chave de cifra válida e a biblioteca `cryptography`."""
    if not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri and settings.google_key):
        return None
    cofre = criar_cofre(settings.google_key)
    if cofre is None:
        LOG.error("Google desligado: chave de cifra inválida ou `cryptography` não instalada")
        return None
    LOG.info("Google ligado (Gmail/Calendar)")
    return GoogleApi(GoogleConfig(settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri, settings.google_key), cofre)


def _canais(settings: config.Settings) -> list:
    """FCM só liga se houver ficheiro de credenciais e ele for válido; uma falha nunca impede o Pulse de arrancar."""
    if settings.fcm_credentials is None:
        return []
    try:
        canal = FcmCanal.de_ficheiro(settings.fcm_credentials, settings.fcm_project, so_dados=os.environ.get("PULSE_FCM_SO_DADOS", "") == "1")
    except (OSError, ValueError) as e:
        LOG.error("FCM desligado: credenciais inválidas (%s)", type(e).__name__)
        return []
    LOG.info("FCM ligado (projeto %s)", canal.cred["project_id"])
    return [canal]


class PedidosLentos:
    """Regista os pedidos que demoram mais de meio segundo (diagnóstico de lentidão; o log de acesso do uvicorn não tem tempos).
    ASGI puro: um `BaseHTTPMiddleware` corre o endpoint noutra thread e rebentava o fecho das ligações SQLite (`get_conn`)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t, estado = time.monotonic(), {}

        async def enviar(msg):
            if msg["type"] == "http.response.start":
                estado["status"] = msg["status"]
            await send(msg)
        try:
            await self.app(scope, receive, enviar)
        finally:
            dt = time.monotonic() - t
            if dt > 0.5:
                logging.getLogger("pulse.lento").warning("%s %s demorou %.2fs (%s)", scope["method"], scope["path"], dt, estado.get("status"))


def create_app(settings: config.Settings | None = None, dados: DadosClient | None = None, avisos: TarefasApiClient | None = None, canais: list | None = None,
               google: GoogleApi | None = None) -> FastAPI:
    settings = settings or config.load()
    logging_setup.configurar(settings.log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(settings.db_path)
        try:
            aplicadas = db.migrate(conn)
        finally:
            conn.close()
        if aplicadas:
            LOG.info("migrações aplicadas: %s", ", ".join(aplicadas))
        conn = db.connect(settings.db_path)
        try:
            novos = compras.sincronizar_catalogo(conn)              # produtos de série novos entram sozinhos a cada arranque
        finally:
            conn.close()
        if novos:
            LOG.info("catálogo de compras: %d produtos de série novos", novos)
        agendador = asyncio.create_task(_agendador(app)) if settings.scheduler_s > 0 else None
        mantida = db.manter_aberta(settings.db_path)
        try:
            yield
        finally:
            mantida.close()
            if agendador:
                agendador.cancel()

    app = FastAPI(title="Pulse", version=VERSION, lifespan=lifespan,
                  docs_url=None if settings.production else "/api/docs", redoc_url=None,
                  openapi_url=None if settings.production else "/api/openapi.json")
    app.state.settings = settings
    app.state.dados = dados or DadosClient(settings.dados_url, settings.service_key)
    app.state.avisos = avisos or TarefasApiClient(settings.tarefas_url, settings.service_key)   # recálculo imediato dos avisos das tarefas
    app.state.google = google if google is not None else _google(settings)                    # Gmail/Calendar: None = não configurado
    app.state.canais = canais if canais is not None else _canais(settings)      # canais de entrega das notificações (FCM, se configurado)
    app.state.db = lambda: db.connect(settings.db_path)   # uma ligação por uso: os endpoints correm em threads
    app.state.agora = lambda: datetime.now(settings.tz)     # substituível nos testes
    app.state.limite_login = RateLimiter(10)   # tentativas de login por IP e minuto (o nginx limita antes)

    app.add_middleware(PedidosLentos)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(actions.router, prefix="/api/v1")
    app.include_router(weight.router, prefix="/api/v1")
    app.include_router(rto.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(finance.router, prefix="/api/v1")
    app.include_router(tickets.router, prefix="/api/v1")
    app.include_router(modules.router, prefix="/api/v1")
    app.include_router(shopping.router, prefix="/api/v1")
    app.include_router(google_rotas.router, prefix="/api/v1")
    app.include_router(calendar.router, prefix="/api/v1")
    app.include_router(mail.router, prefix="/api/v1")
    app.include_router(notificacoes.router, prefix="/api/v1")
    app.include_router(notificacoes.internal, prefix="/api/v1")

    @app.exception_handler(ContaErro)
    async def _conta(_, exc: ContaErro):
        return JSONResponse(status_code=exc.status, content={"erro": {"codigo": exc.codigo, "mensagem": exc.mensagem}})

    @app.exception_handler(RequestValidationError)
    async def _validacao(_, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"erro": {"codigo": "pedido_invalido", "mensagem": "pedido inválido"}})

    @app.exception_handler(ModuloIndisponivel)
    async def _indisponivel(_, exc: ModuloIndisponivel):
        return JSONResponse(status_code=503, content={"erro": {"codigo": "modulo_indisponivel", "mensagem": str(exc)}})

    @app.exception_handler(ErroDoModulo)
    async def _erro_modulo(_, exc: ErroDoModulo):
        return JSONResponse(status_code=exc.status, content={"erro": {"codigo": exc.codigo, "mensagem": exc.mensagem}})

    return app
