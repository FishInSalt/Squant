"""FastAPI dependency injection."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from squant.config import get_settings
from squant.infra.database import get_session, get_session_readonly
from squant.infra.exchange.ccxt import CCXTRestAdapter, ExchangeCredentials
from squant.infra.redis import get_redis

logger = logging.getLogger(__name__)

# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_session)]
DbSessionReadonly = Annotated[AsyncSession, Depends(get_session_readonly)]
RedisClient = Annotated[Redis, Depends(get_redis)]

# Exchange adapter cache (per exchange_id)
_exchange_cache: dict[str, CCXTRestAdapter] = {}
_exchange_cache_lock = asyncio.Lock()


async def _get_or_create_exchange_adapter(exchange_id: str) -> CCXTRestAdapter:
    """Get or create a cached exchange adapter.

    This function maintains a cache of connected exchange adapters to avoid
    the overhead of calling load_markets() on every request.

    Args:
        exchange_id: Exchange identifier (okx, binance, bybit).

    Returns:
        Connected CCXTRestAdapter instance.
    """
    async with _exchange_cache_lock:
        # Check if we have a cached adapter for this exchange
        if exchange_id in _exchange_cache:
            adapter = _exchange_cache[exchange_id]
            # Verify adapter is still connected
            if adapter._connected:
                logger.debug(f"Reusing cached adapter for {exchange_id}")
                return adapter
            else:
                # Remove stale adapter
                logger.debug(f"Removing stale adapter for {exchange_id}")
                del _exchange_cache[exchange_id]

        # Create new adapter
        logger.info(f"Creating new exchange adapter for {exchange_id}")
        adapter = CCXTRestAdapter(exchange_id, None)
        await adapter.connect()
        _exchange_cache[exchange_id] = adapter
        return adapter


async def clear_exchange_cache(exchange_id: str | None = None) -> None:
    """Clear exchange adapter cache.

    Args:
        exchange_id: Specific exchange to clear, or None to clear all.
    """
    async with _exchange_cache_lock:
        if exchange_id:
            if exchange_id in _exchange_cache:
                adapter = _exchange_cache.pop(exchange_id)
                await adapter.close()
                logger.info(f"Cleared exchange cache for {exchange_id}")
        else:
            for eid, adapter in list(_exchange_cache.items()):
                try:
                    await adapter.close()
                except Exception as e:
                    logger.warning(f"Error closing adapter for {eid}: {e}")
            _exchange_cache.clear()
            logger.info("Cleared all exchange cache")


def _get_current_exchange_id() -> str:
    """Get the current configured exchange ID.

    Returns:
        Current exchange ID (okx, binance, bybit).
    """
    # Import here to avoid circular import
    from squant.api.v1.market import get_current_exchange

    return get_current_exchange()


def _get_exchange_credentials(exchange_id: str) -> ExchangeCredentials | None:
    """Get credentials for the specified exchange.

    Args:
        exchange_id: Exchange identifier (okx, binance, bybit).

    Returns:
        ExchangeCredentials or None if not configured.
    """
    settings = get_settings()

    # TODO: sandbox flag should come from the trading session's exchange account,
    # not from global config. Defaulting to False (production) for now.
    if exchange_id == "okx":
        if settings.okx_api_key and settings.okx_api_secret:
            return ExchangeCredentials(
                api_key=settings.okx_api_key.get_secret_value(),
                api_secret=settings.okx_api_secret.get_secret_value(),
                passphrase=settings.okx_passphrase.get_secret_value()
                if settings.okx_passphrase
                else None,
                sandbox=False,
            )
    elif exchange_id == "binance":
        if settings.binance_api_key and settings.binance_api_secret:
            return ExchangeCredentials(
                api_key=settings.binance_api_key.get_secret_value(),
                api_secret=settings.binance_api_secret.get_secret_value(),
                sandbox=False,
            )
    elif exchange_id == "bybit" and settings.bybit_api_key and settings.bybit_api_secret:
        return ExchangeCredentials(
            api_key=settings.bybit_api_key.get_secret_value(),
            api_secret=settings.bybit_api_secret.get_secret_value(),
            sandbox=False,
        )
    return None


async def get_exchange() -> AsyncGenerator[CCXTRestAdapter, None]:
    """Get exchange adapter for the current configured exchange.

    Uses a cached adapter to avoid the overhead of calling load_markets()
    on every request. For market data endpoints, we use production servers
    (not sandbox/testnet) to get accurate real-time market data.

    Yields:
        Connected CCXTRestAdapter instance.
    """
    exchange_id = _get_current_exchange_id()
    # Get or create cached adapter (no credentials for market data)
    adapter = await _get_or_create_exchange_adapter(exchange_id)
    yield adapter
    # Note: We don't close the adapter here - it's cached for reuse


# Dynamic exchange adapter (uses current configured exchange)
Exchange = Annotated[CCXTRestAdapter, Depends(get_exchange)]

