"""Tests for health check endpoints."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from squant.infra.database import get_session
from squant.main import app


def test_health_check(client: TestClient) -> None:
    """Test basic health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


def test_liveness_probe(client: TestClient) -> None:
    """Test liveness probe endpoint."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestReadinessProbe:
    """Tests for readiness probe endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_probe_healthy(self) -> None:
        """Test readiness probe returns healthy when dependencies are available."""
        # Create mock session that can execute queries
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        # Create mock Redis client
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        app.dependency_overrides[get_session] = mock_get_session

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/health/ready")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    @pytest.mark.asyncio
    async def test_readiness_probe_database_unavailable(self) -> None:
        """Test readiness probe returns 503 when database is unavailable."""
        # Create mock session that fails
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Database connection failed"))

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        app.dependency_overrides[get_session] = mock_get_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/health/ready")

        app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "Database unavailable" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_readiness_probe_redis_unavailable(self) -> None:
        """Test readiness probe returns 503 when Redis is unavailable."""
        # Create mock session that works
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        # Create mock Redis that fails
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection failed"))

        app.dependency_overrides[get_session] = mock_get_session

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/health/ready")

        app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "Redis unavailable" in response.json()["detail"]


class TestDetailedHealthCheck:
    """Tests for detailed health check endpoint."""

    @pytest.mark.asyncio
    async def test_detailed_health_all_healthy(self) -> None:
        """Test detailed health returns healthy status for all components."""
        # Create mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        # Create mock Redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        app.dependency_overrides[get_session] = mock_get_session

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/health/detailed")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["database"]["status"] == "healthy"
        assert data["components"]["redis"]["status"] == "healthy"
        assert "latency_ms" in data["components"]["database"]
        assert "latency_ms" in data["components"]["redis"]

    @pytest.mark.asyncio
    async def test_detailed_health_database_unhealthy(self) -> None:
        """Test detailed health reports unhealthy database."""
        # Create mock session that fails
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Connection timeout"))

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        # Create mock Redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()

        app.dependency_overrides[get_session] = mock_get_session

        with patch("squant.api.v1.health.get_redis_client", return_value=mock_redis):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/health/detailed")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["database"]["status"] == "unhealthy"
        assert "Connection timeout" in data["components"]["database"]["message"]

    @pytest.mark.asyncio
    async def test_detailed_health_redis_not_configured(self) -> None:
        """Test detailed health handles Redis not configured."""
        # Create mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def mock_get_session() -> AsyncGenerator:
            yield mock_session

        app.dependency_overrides[get_session] = mock_get_session

        with patch("squant.api.v1.health.get_redis_client", return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/api/v1/health/detailed")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        # Overall healthy because Redis being unconfigured is not a failure
        assert data["status"] == "healthy"
        assert data["components"]["redis"]["status"] == "not_configured"
