"""FastAPI application factory.

A factory function (rather than a module-level `app = FastAPI()` with imports
executing side effects) means tests can build a fresh app with overridden
settings, and nothing heavy happens at import time.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, health, research, retrieve, search
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook. Later phases attach expensive resources here
    (DB engine, embedding model, Chroma client) so they are created once per
    process, not once per request."""
    settings: Settings = app.state.settings
    if settings.environment == "prod" and settings.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET must be set in production")
    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.environment)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(retrieve.router, prefix="/api")
    app.include_router(ask.router, prefix="/api")
    app.include_router(research.router, prefix="/api")
    return app


app = create_app()
