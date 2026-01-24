"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from squant.config import get_settings
from squant.infra.database import get_session, get_session_readonly
from squant.infra.exchange import OKXAdapter
from squant.infra.redis import get_redis

# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_session)]
DbSessionReadonly = Annotated[AsyncSession, Depends(get_session_readonly)]
RedisClient = Annotated[Redis, Depends(get_redis)]


async def get_okx_exchange() -> AsyncGenerator[OKXAdapter, None]:
    """Get OKX exchange adapter.

    Requires OKX API credentials to be configured in settings.

    Yields:
        Connected OKXAdapter instance.

    Raises:
        ValueError: If OKX credentials are not configured.
    """
    settings = get_settings()

    if not settings.okx_api_key or not settings.okx_api_secret or not settings.okx_passphrase:
        raise ValueError("OKX API credentials not configured")

    adapter = OKXAdapter(
        api_key=settings.okx_api_key.get_secret_value(),
        api_secret=settings.okx_api_secret.get_secret_value(),
        passphrase=settings.okx_passphrase.get_secret_value(),
        testnet=settings.okx_testnet,
    )

    async with adapter:
        yield adapter


OKXExchange = Annotated[OKXAdapter, Depends(get_okx_exchange)]
