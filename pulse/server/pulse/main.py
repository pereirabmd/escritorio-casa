"""Aplicação FastAPI do Pulse. Correr no Pi: `uvicorn pulse.asgi:app --host 127.0.0.1 --port 8897`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pulse import VERSION, config, db, logging_setup
from pulse.accounts import ContaErro
from datetime import datetime

from pulse.api.v1 import actions, auth, dashboard, health
from pulse.ratelimit import RateLimiter
from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel

LOG = logging.getLogger("pulse")


def create_app(settings: config.Settings | None = None, dados: DadosClient | None = None) -> FastAPI:
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
        yield

    app = FastAPI(title="Pulse", version=VERSION, lifespan=lifespan,
                  docs_url=None if settings.production else "/api/docs", redoc_url=None,
                  openapi_url=None if settings.production else "/api/openapi.json")
    app.state.settings = settings
    app.state.dados = dados or DadosClient(settings.dados_url, settings.service_key)
    app.state.db = lambda: db.connect(settings.db_path)   # uma ligação por uso: os endpoints correm em threads
    app.state.agora = lambda: datetime.now(settings.tz)     # substituível nos testes
    app.state.limite_login = RateLimiter(10)   # tentativas de login por IP e minuto (o nginx limita antes)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(actions.router, prefix="/api/v1")

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
