"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from squant.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url.get_secret_value(),
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session with auto-commit for dependency injection.

    Use this for write operations. The session will automatically commit
    on success or rollback on exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session_readonly() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session without auto-commit for read-only operations.

    Use this for read-only queries where no transaction management is needed.
    The session is automatically closed when the context exits.
    """
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session as context manager."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database connection (for startup)."""
    async with engine.begin() as conn:
        # Test connection
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connections (for shutdown)."""
    await engine.dispose()
