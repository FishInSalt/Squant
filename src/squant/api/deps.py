"""FastAPI dependency injection."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.database import get_session, get_session_readonly
from squant.infra.redis import get_redis

# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_session)]
DbSessionReadonly = Annotated[AsyncSession, Depends(get_session_readonly)]
RedisClient = Annotated[Redis, Depends(get_redis)]
