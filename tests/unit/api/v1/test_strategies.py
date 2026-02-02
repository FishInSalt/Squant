"""Unit tests for strategies API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.main import app
from squant.models.enums import StrategyStatus
from squant.services.strategy import (
    StrategyInUseError,
    StrategyNameExistsError,
    StrategyNotFoundError,
    StrategyValidationError,
)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_strategy():
    """Create a mock strategy object."""
    strategy = MagicMock()
    strategy.id = uuid4()
    strategy.name = "Test Strategy"
    strategy.version = "1.0.0"
    strategy.description = "A test strategy"
    strategy.code = "class Strategy:\n    def on_bar(self, bar): pass"
    strategy.params_schema = {}
    strategy.default_params = {}
    strategy.status = StrategyStatus.ACTIVE.value  # Use the string value
    strategy.created_at = datetime.now(UTC)
    strategy.updated_at = datetime.now(UTC)
    return strategy


@pytest.fixture
def valid_create_request() -> dict[str, Any]:
    """Create a valid strategy creation request."""
    return {
        "name": "Test Strategy",
        "description": "A test strategy",
        "code": "class Strategy:\n    def on_bar(self, bar): pass",
    }


class TestValidateStrategyCode:
    """Tests for POST /api/v1/strategies/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_valid_code(self, client: AsyncClient) -> None:
        """Test validating valid strategy code."""
        with patch("squant.engine.sandbox.validate_strategy_code") as mock_validate:
            mock_result = MagicMock()
            mock_result.valid = True
            mock_result.errors = []
            mock_result.warnings = []
            mock_validate.return_value = mock_result

            response = await client.post(
                "/api/v1/strategies/validate",
                json={"code": "class Strategy:\n    def on_bar(self, bar): pass"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["valid"] is True
            assert data["data"]["errors"] == []

    @pytest.mark.asyncio
    async def test_validate_invalid_code(self, client: AsyncClient) -> None:
        """Test validating invalid strategy code."""
        with patch("squant.engine.sandbox.validate_strategy_code") as mock_validate:
            mock_result = MagicMock()
            mock_result.valid = False
            mock_result.errors = ["Missing Strategy class"]
            mock_result.warnings = []
            mock_validate.return_value = mock_result

            response = await client.post(
                "/api/v1/strategies/validate",
                json={"code": "def some_function(): pass"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["valid"] is False
            assert "Missing Strategy class" in data["data"]["errors"]

    @pytest.mark.asyncio
    async def test_validate_with_warnings(self, client: AsyncClient) -> None:
        """Test validating code that produces warnings."""
        with patch("squant.engine.sandbox.validate_strategy_code") as mock_validate:
            mock_result = MagicMock()
            mock_result.valid = True
            mock_result.errors = []
            mock_result.warnings = ["Unused variable 'x'"]
            mock_validate.return_value = mock_result

            response = await client.post(
                "/api/v1/strategies/validate",
                json={"code": "class Strategy:\n    def on_bar(self, bar): x = 1"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["valid"] is True
            assert len(data["data"]["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_validate_missing_code(self, client: AsyncClient) -> None:
        """Test validation request without code."""
        response = await client.post("/api/v1/strategies/validate", json={})

        assert response.status_code == 422


class TestCreateStrategy:
    """Tests for POST /api/v1/strategies endpoint."""

    @pytest.mark.asyncio
    async def test_create_strategy_success(
        self, client: AsyncClient, valid_create_request: dict, mock_strategy
    ) -> None:
        """Test successful strategy creation."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(return_value=mock_strategy)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/strategies", json=valid_create_request)

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_create_strategy_name_exists(
        self, client: AsyncClient, valid_create_request: dict
    ) -> None:
        """Test creating strategy with existing name."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(side_effect=StrategyNameExistsError("Test Strategy"))
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/strategies", json=valid_create_request)

            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_strategy_validation_error(
        self, client: AsyncClient, valid_create_request: dict
    ) -> None:
        """Test creating strategy with validation error."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(side_effect=StrategyValidationError(["Invalid syntax"]))
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/strategies", json=valid_create_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_strategy_missing_name(self, client: AsyncClient) -> None:
        """Test creating strategy without name."""
        response = await client.post(
            "/api/v1/strategies",
            json={
                "description": "No name",
                "code": "class Strategy:\n    def on_bar(self, bar): pass",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_strategy_missing_code(self, client: AsyncClient) -> None:
        """Test creating strategy without code."""
        response = await client.post(
            "/api/v1/strategies",
            json={
                "name": "Test",
                "description": "No code",
            },
        )

        assert response.status_code == 422


class TestListStrategies:
    """Tests for GET /api/v1/strategies endpoint."""

    @pytest.mark.asyncio
    async def test_list_strategies_success(self, client: AsyncClient, mock_strategy) -> None:
        """Test listing strategies."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_strategy], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/strategies")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["total"] == 1
            assert len(data["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_strategies_with_pagination(self, client: AsyncClient, mock_strategy) -> None:
        """Test listing strategies with pagination."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_strategy], 50))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/strategies?page=2&page_size=10")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["page"] == 2
            assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_strategies_with_status_filter(self, client: AsyncClient, mock_strategy) -> None:
        """Test listing strategies with status filter."""
        mock_strategy.status = StrategyStatus.ACTIVE

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_strategy], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/strategies?status=active")

            assert response.status_code == 200
            mock_service.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_strategies_empty(self, client: AsyncClient) -> None:
        """Test listing strategies when none exist."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/strategies")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 0
            assert data["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_list_strategies_invalid_page(self, client: AsyncClient) -> None:
        """Test listing strategies with invalid page number."""
        response = await client.get("/api/v1/strategies?page=0")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_strategies_invalid_page_size(self, client: AsyncClient) -> None:
        """Test listing strategies with invalid page size."""
        response = await client.get("/api/v1/strategies?page_size=101")
        assert response.status_code == 422


class TestGetStrategy:
    """Tests for GET /api/v1/strategies/{strategy_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_strategy_success(self, client: AsyncClient, mock_strategy) -> None:
        """Test getting a strategy by ID."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(return_value=mock_strategy)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/strategies/{mock_strategy.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_get_strategy_not_found(self, client: AsyncClient) -> None:
        """Test getting a non-existent strategy."""
        strategy_id = uuid4()

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(side_effect=StrategyNotFoundError(str(strategy_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/strategies/{strategy_id}")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_strategy_invalid_id(self, client: AsyncClient) -> None:
        """Test getting strategy with invalid ID format."""
        response = await client.get("/api/v1/strategies/invalid-uuid")

        assert response.status_code == 422


class TestUpdateStrategy:
    """Tests for PUT /api/v1/strategies/{strategy_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_strategy_success(self, client: AsyncClient, mock_strategy) -> None:
        """Test updating a strategy."""
        mock_strategy.name = "Updated Strategy"

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(return_value=mock_strategy)
            mock_service_class.return_value = mock_service

            response = await client.put(
                f"/api/v1/strategies/{mock_strategy.id}",
                json={"name": "Updated Strategy"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["name"] == "Updated Strategy"

    @pytest.mark.asyncio
    async def test_update_strategy_not_found(self, client: AsyncClient) -> None:
        """Test updating a non-existent strategy."""
        strategy_id = uuid4()

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(side_effect=StrategyNotFoundError(str(strategy_id)))
            mock_service_class.return_value = mock_service

            response = await client.put(
                f"/api/v1/strategies/{strategy_id}",
                json={"name": "New Name"},
            )

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_strategy_name_exists(self, client: AsyncClient, mock_strategy) -> None:
        """Test updating strategy with existing name."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(
                side_effect=StrategyNameExistsError("Existing Strategy")
            )
            mock_service_class.return_value = mock_service

            response = await client.put(
                f"/api/v1/strategies/{mock_strategy.id}",
                json={"name": "Existing Strategy"},
            )

            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_strategy_validation_error(self, client: AsyncClient, mock_strategy) -> None:
        """Test updating strategy with invalid code."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(side_effect=StrategyValidationError(["Syntax error"]))
            mock_service_class.return_value = mock_service

            response = await client.put(
                f"/api/v1/strategies/{mock_strategy.id}",
                json={"code": "invalid code"},
            )

            assert response.status_code == 400


class TestDeleteStrategy:
    """Tests for DELETE /api/v1/strategies/{strategy_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_strategy_success(self, client: AsyncClient, mock_strategy) -> None:
        """Test deleting a strategy."""
        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            response = await client.delete(f"/api/v1/strategies/{mock_strategy.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Strategy deleted"

    @pytest.mark.asyncio
    async def test_delete_strategy_not_found(self, client: AsyncClient) -> None:
        """Test deleting a non-existent strategy."""
        strategy_id = uuid4()

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(side_effect=StrategyNotFoundError(str(strategy_id)))
            mock_service_class.return_value = mock_service

            response = await client.delete(f"/api/v1/strategies/{strategy_id}")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_running_strategy_returns_409(self, client: AsyncClient) -> None:
        """Test deleting a running strategy returns 409 conflict (STR-024)."""
        strategy_id = uuid4()

        with patch("squant.api.v1.strategies.StrategyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(
                side_effect=StrategyInUseError(str(strategy_id), running_count=2)
            )
            mock_service_class.return_value = mock_service

            response = await client.delete(f"/api/v1/strategies/{strategy_id}")

            assert response.status_code == 409
            assert "running" in response.json()["detail"].lower()
