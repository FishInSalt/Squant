"""Redis connection management."""

import logging
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from squant.config import get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "get_redis",
    "get_redis_client",
    "get_redis_context",
    "get_redis_pool",
    "init_redis",
    "close_redis",
]

settings = get_settings()

# Global Redis pool and client instances.
# Note: In multi-worker deployments (uvicorn --workers N), each worker process
# will have its own independent pool and client instance. This is expected
# behavior as each process has its own memory space.
_redis_pool: redis.ConnectionPool | None = None
_redis_client: Redis | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """Get or create Redis connection pool.

    The pool is configured for long-running connections (WebSocket pubsub):
    - TCP keepalive to detect dead connections
    - Health checks to verify connection validity
    - Automatic retry with exponential backoff
    """
    global _redis_pool
    if _redis_pool is None:
        # TCP keepalive options to detect dead connections
        # TCP_KEEPIDLE: Start keepalive after 60 seconds of idle
        # TCP_KEEPINTVL: Send keepalive probes every 10 seconds
        # TCP_KEEPCNT: Close connection after 3 failed probes
        socket_keepalive_options = {}
        try:
            # These options are platform-specific (Linux)
            socket_keepalive_options = {
                socket.TCP_KEEPIDLE: 60,  # Start keepalive after 60s idle
                socket.TCP_KEEPINTVL: 10,  # Send probe every 10s
                socket.TCP_KEEPCNT: 3,  # Close after 3 failed probes
            }
        except AttributeError:
            # Windows/macOS may not have these constants
            logger.debug("TCP keepalive options not available on this platform")

        # Retry configuration for transient failures
        retry = Retry(
            backoff=ExponentialBackoff(cap=10, base=0.1),  # Max 10s backoff
            retries=3,  # Retry 3 times
        )

        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            max_connections=100,  # For WebSocket pubsub connections
            # Connection health and keepalive
            health_check_interval=30,  # Check connection health every 30s
            socket_keepalive=True,  # Enable TCP keepalive
            socket_keepalive_options=socket_keepalive_options if socket_keepalive_options else None,
            socket_timeout=5.0,  # Socket timeout for operations
            socket_connect_timeout=5.0,  # Connection timeout
            # Retry configuration
            retry=retry,
            retry_on_timeout=True,  # Retry on timeout errors
        )
        logger.info("Redis connection pool created with keepalive and health checks")
    return _redis_pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Get Redis client for dependency injection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(connection_pool=get_redis_pool())
    yield _redis_client


@asynccontextmanager
async def get_redis_context() -> AsyncGenerator[Redis, None]:
    """Get Redis client as context manager."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(connection_pool=get_redis_pool())
    yield _redis_client


async def init_redis() -> None:
    """Initialize Redis connection (for startup)."""
    global _redis_client
    _redis_client = Redis(connection_pool=get_redis_pool())
    # Test connection
    await _redis_client.ping()


async def close_redis() -> None:
    """Close Redis connections (for shutdown)."""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


def get_redis_client() -> Redis:
    """Get the global Redis client directly.

    Use this when you need to store a reference to the Redis client
    for long-lived operations (e.g., StreamManager).

    Returns:
        Redis client instance.

    Raises:
        RuntimeError: If Redis is not initialized.
    """
    global _redis_client
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client
