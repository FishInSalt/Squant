"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from squant.api.router import api_router
from squant.config import get_settings
from squant.infra import close_db, close_redis, init_db, init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting application...")
    await init_db()
    logger.info("Database connection initialized")
    await init_redis()
    logger.info("Redis connection initialized")
    # TODO: Recover running strategies (NFR-013)

    yield

    # Shutdown
    logger.info("Shutting down application...")
    # TODO: Gracefully stop all strategy processes
    await close_redis()
    logger.info("Redis connection closed")
    await close_db()
    logger.info("Database connection closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Personal Quantitative Trading System for Cryptocurrency",
        version="0.1.0",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
