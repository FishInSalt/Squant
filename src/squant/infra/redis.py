"""Redis connection management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis

from squant.config import get_settings

settings = get_settings()

# Global Redis pool and client instances.
# Note: In multi-worker deployments (uvicorn --workers N), each worker process
# will have its own independent pool and client instance. This is expected
# behavior as each process has its own memory space.
_redis_pool: redis.ConnectionPool | None = None
_redis_client: Redis | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """Get or create Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            max_connections=10,
        )
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
