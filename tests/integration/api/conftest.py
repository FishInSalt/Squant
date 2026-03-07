"""
Configuration for API integration tests.

Uses httpx.AsyncClient for testing async FastAPI routes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _create_mock_okx_adapter():
    """Create mock OKX adapter for API tests.

    Note: This is a workaround for the architectural issue where
    OrderService requires an exchange adapter even for pure database
    operations like list_orders(). The tests mock the service layer
    anyway, so this adapter is never actually used.
    """
    mock = MagicMock()
    mock.get_balance = AsyncMock(return_value={"USDT": 10000.0})
    mock.get_ticker = AsyncMock()
    mock.create_order = AsyncMock()
    mock.cancel_order = AsyncMock()
    mock.get_order = AsyncMock()
    mock.get_open_orders = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create async HTTP client for FastAPI testing.

    Overrides:
    - Database session: uses test session
    - OKX exchange adapter: uses mock to avoid credential requirement

    Note: We import squant modules inside the fixture to ensure
    environment variables are set correctly by conftest.py first.
    """
    # Delayed import to ensure env vars are set
    from squant.api.deps import get_okx_exchange
    from squant.infra.database import get_session
    from squant.main import app

    # Override database dependency
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Override OKX exchange dependency with mock
    mock_adapter = _create_mock_okx_adapter()

    async def override_get_okx_exchange():
        yield mock_adapter

    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange

    # Create async client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
