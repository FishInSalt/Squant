"""Unit tests for health check endpoints."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.infra.database import get_session
from squant.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


class TestHealthCheck:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_basic_health(self, client: AsyncClient) -> None:
        """Test basic health check returns healthy status."""
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "0.1.0"


class TestLivenessProbe:
    """Tests for GET /health/live endpoint."""

    @pytest.mark.asyncio
    async def test_liveness(self, client: AsyncClient) -> None:
        """Test liveness probe always returns ok."""
        response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestReadinessProbe:
    """Tests for GET /health/ready endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_success(self, client: AsyncClient) -> None:
        """Test readiness probe succeeds when DB and Redis are available."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        with patch(
            "squant.api.v1.health.get_redis_client",
            return_value=AsyncMock(ping=AsyncMock()),
        ):
            response = await client.get("/api/v1/health/ready")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_readiness_db_unavailable(self, client: AsyncClient) -> None:
        """Test readiness probe fails when database is unavailable."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Connection refused"))

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        response = await client.get("/api/v1/health/ready")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_readiness_redis_unavailable(self, client: AsyncClient) -> None:
        """Test readiness probe fails when Redis is unavailable."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        with patch(
            "squant.api.v1.health.get_redis_client",
            return_value=AsyncMock(ping=AsyncMock(side_effect=Exception("Redis down"))),
        ):
            response = await client.get("/api/v1/health/ready")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 503


class TestDetailedHealthCheck:
    """Tests for GET /health/detailed endpoint."""

    @pytest.mark.asyncio
    async def test_detailed_all_healthy(self, client: AsyncClient) -> None:
        """Test detailed health when all components are healthy."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            response = await client.get("/api/v1/health/detailed")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["database"]["latency_ms"] is not None
        assert data["components"]["redis"]["status"] == "healthy"
        assert data["components"]["redis"]["latency_ms"] is not None

    @pytest.mark.asyncio
    async def test_detailed_db_unhealthy(self, client: AsyncClient) -> None:
        """Test detailed health with unhealthy database."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            response = await client.get("/api/v1/health/detailed")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["database"]["status"] == "unhealthy"
        assert data["components"]["database"]["message"] == "DB error"

    @pytest.mark.asyncio
    async def test_detailed_redis_not_configured(self, client: AsyncClient) -> None:
        """Test detailed health when Redis is not configured."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def override_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        app.dependency_overrides[get_session] = override_session

        with patch("squant.api.v1.health.get_redis_client", return_value=None):
            response = await client.get("/api/v1/health/detailed")

        app.dependency_overrides.pop(get_session, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"  # not_configured != unhealthy
        assert data["components"]["redis"]["status"] == "not_configured"
