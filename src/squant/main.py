"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from squant.api.router import api_router
from squant.config import get_settings
from squant.infra import close_db, close_redis, init_db, init_redis
from squant.websocket import close_stream_manager, init_stream_manager

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
    await init_stream_manager()
    logger.info("Stream manager initialized")

    # Recover orphaned paper trading sessions (NFR-013)
    from squant.infra.database import get_session_context
    from squant.services.paper_trading import StrategyRunRepository

    async with get_session_context() as session:
        repo = StrategyRunRepository(session)
        count = await repo.mark_orphaned_sessions()
        if count > 0:
            logger.warning(f"Marked {count} orphaned paper trading sessions as ERROR")

    # Start background tasks for paper trading
    from squant.services.background import get_task_manager

    settings = get_settings()
    task_manager = get_task_manager()
    task_manager.start(
        persist_interval=settings.paper_persist_interval_seconds,
        health_check_interval=settings.paper_health_check_interval_seconds,
    )
    logger.info("Background tasks started")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop background tasks first
    await task_manager.stop()
    logger.info("Background tasks stopped")

    # Gracefully stop all paper trading sessions
    from squant.engine.paper.manager import get_session_manager

    session_manager = get_session_manager()
    await session_manager.stop_all(reason="application shutdown")
    logger.info("Paper trading sessions stopped")

    await close_stream_manager()
    logger.info("Stream manager closed")
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
