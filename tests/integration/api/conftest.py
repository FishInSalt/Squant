"""
Configuration for API integration tests.

Uses httpx.AsyncClient for testing async FastAPI routes.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create async HTTP client for FastAPI testing.

    Overrides:
    - Database session: uses test session

    Note: We import squant modules inside the fixture to ensure
    environment variables are set correctly by conftest.py first.
    """
    # Delayed import to ensure env vars are set
    from squant.infra.database import get_session
    from squant.main import app

    # Override database dependency
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Create async client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
