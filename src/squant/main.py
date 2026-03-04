"""FastAPI application entry point."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from squant.api.router import api_router
from squant.config import get_settings
from squant.infra import close_db, close_redis, init_db, init_redis
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
)
from squant.websocket import close_stream_manager, init_stream_manager

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure logging from settings. Called once during create_app()."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=log_datefmt,
        force=True,
    )

    # Add rotating file handler when LOG_FILE is configured
    log_cfg = settings.logging
    if log_cfg.file:
        log_path = Path(log_cfg.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=log_cfg.max_bytes,
            backupCount=log_cfg.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
        logging.getLogger().addHandler(file_handler)

    logging.getLogger("squant").setLevel(log_level)
    # Suppress verbose third-party library logs (ccxt dumps full HTTP responses at DEBUG)
    logging.getLogger("ccxt").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup — clean up already-initialized resources on failure
    logger.info("Starting application...")
    db_initialized = False
    redis_initialized = False
    try:
        await init_db()
        db_initialized = True
        logger.info("Database connection initialized")
        await init_redis()
        redis_initialized = True
        logger.info("Redis connection initialized")

        # WebSocket stream manager — initialize in background so it doesn't block
        # the HTTP server from accepting connections. The server starts immediately;
        # when the stream manager connects to the exchange, it publishes a
        # service_ready event so WebSocket gateways can re-subscribe OKX channels.
        async def _start_stream_manager_background() -> None:
            try:
                await init_stream_manager()
                logger.info("Stream manager initialized (background)")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize stream manager: {e}. "
                    "Real-time data will be unavailable."
                )
                from squant.websocket.manager import get_stream_manager

                get_stream_manager().start_retry_loop()

        # Recover orphaned trading sessions (NFR-013)
        # Must run after stream manager init so resumed sessions can subscribe
        async def _recover_orphaned_sessions(stream_init_task: asyncio.Task) -> None:  # type: ignore[type-arg]
            """Recover orphaned sessions after stream manager is ready."""
            from squant.infra.database import get_session_context
            from squant.services.live_trading import LiveTradingService
            from squant.services.paper_trading import PaperTradingService

            # Wait for stream manager to be ready (with timeout)
            try:
                await asyncio.wait_for(asyncio.shield(stream_init_task), timeout=30.0)
            except (TimeoutError, Exception) as e:
                logger.warning(
                    f"Stream manager not ready for session recovery: {e}. "
                    "Falling back to marking orphaned sessions as INTERRUPTED."
                )
                # Fall back to mark-as-interrupted when stream not available
                async with get_session_context() as session:
                    paper_service = PaperTradingService(session)
                    paper_count = await paper_service.mark_orphaned_sessions()
                    if paper_count > 0:
                        logger.warning(
                            f"Marked {paper_count} orphaned paper sessions as INTERRUPTED"
                        )

                    live_service = LiveTradingService(session)
                    live_count = await live_service.mark_orphaned_sessions()
                    if live_count > 0:
                        logger.warning(
                            f"Marked {live_count} orphaned live sessions as INTERRUPTED"
                        )
                return

            # Stream manager ready — attempt auto-recovery
            async with get_session_context() as session:
                paper_service = PaperTradingService(session)
                paper_recovered, paper_failed = await paper_service.recover_orphaned_sessions()
                if paper_recovered > 0 or paper_failed > 0:
                    logger.info(
                        f"Paper trading orphan recovery: "
                        f"{paper_recovered} recovered, {paper_failed} marked INTERRUPTED"
                    )

                # Live trading — auto-recovery if enabled, otherwise mark INTERRUPTED
                live_service = LiveTradingService(session)
                live_recovered, live_failed = await live_service.recover_orphaned_sessions()
                if live_recovered > 0 or live_failed > 0:
                    logger.info(
                        f"Live trading orphan recovery: "
                        f"{live_recovered} recovered, {live_failed} marked INTERRUPTED/ERROR"
                    )

        stream_manager_task = asyncio.create_task(
            _start_stream_manager_background(), name="stream_manager_init"
        )

        recovery_task = asyncio.create_task(
            _recover_orphaned_sessions(stream_manager_task),
            name="orphan_recovery",
        )

        # Start background tasks for paper trading
        from squant.services.background import get_task_manager

        settings = get_settings()
        task_manager = get_task_manager()
        task_manager.start(
            persist_interval=settings.paper_persist_interval_seconds,
            health_check_interval=settings.paper_health_check_interval_seconds,
        )
        logger.info("Background tasks started")
    except Exception:
        logger.exception("Startup failed, cleaning up initialized resources")
        if redis_initialized:
            await close_redis()
        if db_initialized:
            await close_db()
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Cancel recovery task if still in progress
    if not recovery_task.done():
        recovery_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recovery_task
        logger.info("Orphan recovery task cancelled")

    # Cancel stream manager init if still in progress
    if not stream_manager_task.done():
        stream_manager_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stream_manager_task
        logger.info("Stream manager init task cancelled")

    # Stop background tasks first
    await task_manager.stop()
    logger.info("Background tasks stopped")

    # Gracefully stop all trading sessions via service layer (persists results)
    from squant.infra.database import get_session_context

    try:
        async with get_session_context() as db_session:
            from squant.services.paper_trading import PaperTradingService

            paper_service = PaperTradingService(db_session)
            paper_stopped = await paper_service.stop_all(for_shutdown=True)
            logger.info(f"Paper trading sessions stopped ({paper_stopped} sessions)")

            from squant.services.live_trading import LiveTradingService

            live_service = LiveTradingService(db_session)
            live_stopped = await live_service.stop_all(for_shutdown=True)
            logger.info(f"Live trading sessions stopped ({live_stopped} sessions)")
    except Exception:
        logger.exception("Error during graceful session shutdown, forcing stop")
        # Fallback: force stop engines directly if service layer fails
        from squant.engine.live.manager import get_live_session_manager
        from squant.engine.paper.manager import get_session_manager

        session_manager = get_session_manager()
        await session_manager.stop_all(reason="application shutdown (fallback)")
        live_session_manager = get_live_session_manager()
        await live_session_manager.stop_all(reason="application shutdown (fallback)")

    await close_stream_manager()
    logger.info("Stream manager closed")

    # Clear exchange adapter cache
    from squant.api.deps import clear_exchange_cache

    await clear_exchange_cache()
    logger.info("Exchange cache cleared")

    await close_redis()
    logger.info("Redis connection closed")
    await close_db()
    logger.info("Database connection closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    _configure_logging()
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

    # Rate limiting middleware (simple in-memory implementation)
    # For production, consider using slowapi with Redis backend or Nginx-level limiting
    if settings.rate_limit_enabled:
        from squant.api.middleware import RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=settings.rate_limit_per_minute,
            burst_limit=settings.rate_limit_burst,
        )
        logger.info(
            f"Rate limiting enabled: {settings.rate_limit_per_minute}/min, "
            f"burst={settings.rate_limit_burst}"
        )

    # Include API router
    app.include_router(api_router, prefix=settings.api_prefix)

    # Exception handlers for exchange errors (caught in dependencies)
    # Global HTTPException handler — converts all HTTPException responses to
    # the uniform {"code", "message", "data"} shape (ISSUE-605).
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        data = None
        if isinstance(exc.detail, dict) and "message" in exc.detail:
            message = exc.detail["message"]
            data = exc.detail.get("data")
        elif isinstance(exc.detail, str):
            message = exc.detail
        else:
            message = str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": message,
                "data": data,
            },
            headers=getattr(exc, "headers", None),
        )

    # Exception handlers for exchange errors (caught in dependencies)
    @app.exception_handler(ExchangeConnectionError)
    async def exchange_connection_error_handler(
        request: Request, exc: ExchangeConnectionError
    ) -> JSONResponse:
        logger.warning(f"Exchange connection error: {exc}")
        return JSONResponse(
            status_code=503,
            content={
                "code": 503,
                "message": str(exc),
                "data": None,
            },
        )

    @app.exception_handler(ExchangeAuthenticationError)
    async def exchange_auth_error_handler(
        request: Request, exc: ExchangeAuthenticationError
    ) -> JSONResponse:
        logger.warning(f"Exchange authentication error: {exc}")
        return JSONResponse(
            status_code=401,
            content={
                "code": 401,
                "message": str(exc),
                "data": None,
            },
        )

    @app.exception_handler(ExchangeRateLimitError)
    async def exchange_rate_limit_handler(
        request: Request, exc: ExchangeRateLimitError
    ) -> JSONResponse:
        logger.warning(f"Exchange rate limit error: {exc}")
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "message": str(exc),
                "data": None,
            },
            headers={"Retry-After": str(int(exc.retry_after or 1))},
        )

    @app.exception_handler(ExchangeAPIError)
    async def exchange_api_error_handler(request: Request, exc: ExchangeAPIError) -> JSONResponse:
        logger.warning(f"Exchange API error: {exc}")
        return JSONResponse(
            status_code=502,
            content={
                "code": 502,
                "message": str(exc),
                "data": None,
            },
        )

    return app


app = create_app()
