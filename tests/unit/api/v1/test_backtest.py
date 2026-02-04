"""Unit tests for backtest API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.engine.backtest.runner import BacktestError
from squant.main import app
from squant.models.enums import RunStatus
from squant.services.backtest import (
    BacktestNotFoundError,
    IncompleteDataError,
    InsufficientDataError,
)
from squant.services.strategy import StrategyNotFoundError


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_backtest_run():
    """Create a mock backtest run."""
    run = MagicMock()
    run.id = uuid4()
    run.strategy_id = uuid4()
    run.mode = "backtest"
    run.symbol = "BTC/USDT"
    run.exchange = "okx"
    run.timeframe = "1h"
    run.backtest_start = datetime(2024, 1, 1, tzinfo=UTC)
    run.backtest_end = datetime(2024, 6, 1, tzinfo=UTC)
    run.initial_capital = 10000.0
    run.commission_rate = 0.001
    run.slippage = 0.0005
    run.params = {}
    run.status = RunStatus.COMPLETED.value
    run.result = {"total_return": 0.2, "max_drawdown": 0.1}
    run.error_message = None
    run.started_at = datetime.now(UTC)
    run.stopped_at = datetime.now(UTC)
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


@pytest.fixture
def valid_run_request() -> dict:
    """Create a valid backtest run request."""
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1h",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-06-01T00:00:00Z",
        "initial_capital": 10000.0,
        "commission_rate": 0.001,
        "slippage": 0.0005,
    }


class TestRunBacktest:
    """Tests for POST /api/v1/backtest endpoint."""

    @pytest.mark.asyncio
    async def test_run_backtest_success(
        self, client: AsyncClient, valid_run_request: dict, mock_backtest_run
    ) -> None:
        """Test successful synchronous backtest run."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_run = AsyncMock(return_value=mock_backtest_run)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest", json=valid_run_request)

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_run_backtest_strategy_not_found(
        self, client: AsyncClient, valid_run_request: dict
    ) -> None:
        """Test backtest with non-existent strategy."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_run = AsyncMock(
                side_effect=StrategyNotFoundError(valid_run_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest", json=valid_run_request)

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_run_backtest_insufficient_data(
        self, client: AsyncClient, valid_run_request: dict
    ) -> None:
        """Test backtest with insufficient historical data."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_run = AsyncMock(
                side_effect=InsufficientDataError("Not enough data for backtest")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest", json=valid_run_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_run_backtest_execution_error(
        self, client: AsyncClient, valid_run_request: dict
    ) -> None:
        """Test backtest with execution error."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_and_run = AsyncMock(
                side_effect=BacktestError("Strategy execution failed")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest", json=valid_run_request)

            assert response.status_code == 400


class TestCreateBacktestAsync:
    """Tests for POST /api/v1/backtest/async endpoint."""

    @pytest.mark.asyncio
    async def test_create_backtest_success(
        self, client: AsyncClient, valid_run_request: dict, mock_backtest_run
    ) -> None:
        """Test successful async backtest creation."""
        mock_backtest_run.status = RunStatus.PENDING

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(return_value=mock_backtest_run)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest/async", json=valid_run_request)

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_create_backtest_strategy_not_found(
        self, client: AsyncClient, valid_run_request: dict
    ) -> None:
        """Test async creation with non-existent strategy."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(
                side_effect=StrategyNotFoundError(valid_run_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/backtest/async", json=valid_run_request)

            assert response.status_code == 404


class TestExecuteBacktest:
    """Tests for POST /api/v1/backtest/{run_id}/run endpoint."""

    @pytest.mark.asyncio
    async def test_execute_backtest_success(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test successful backtest execution."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(return_value=mock_backtest_run)
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{mock_backtest_run.id}/run")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_execute_backtest_not_found(self, client: AsyncClient) -> None:
        """Test executing non-existent backtest."""
        run_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(side_effect=BacktestNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{run_id}/run")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_backtest_error(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test backtest execution failure."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(side_effect=BacktestError("Execution failed"))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{mock_backtest_run.id}/run")

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_execute_backtest_insufficient_data(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test backtest execution with insufficient data."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(
                side_effect=InsufficientDataError("Not enough data for backtest")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{mock_backtest_run.id}/run")

            assert response.status_code == 400
            assert "Not enough data" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_execute_backtest_incomplete_data(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test backtest execution with incomplete data coverage."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(
                side_effect=IncompleteDataError(
                    "Data doesn't cover the full requested range"
                )
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{mock_backtest_run.id}/run")

            assert response.status_code == 400
            assert "cover" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_execute_backtest_strategy_not_found(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test backtest execution when strategy is not found."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.run = AsyncMock(
                side_effect=StrategyNotFoundError(str(mock_backtest_run.strategy_id))
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/backtest/{mock_backtest_run.id}/run")

            assert response.status_code == 404


class TestListBacktests:
    """Tests for GET /api/v1/backtest endpoint."""

    @pytest.mark.asyncio
    async def test_list_backtests_success(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test listing backtests."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_backtest_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/backtest")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["total"] == 1
            assert len(data["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_backtests_with_pagination(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test listing backtests with pagination."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_backtest_run], 50))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/backtest?page=2&page_size=10")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["page"] == 2
            assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_backtests_with_status_filter(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test listing backtests with status filter."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_backtest_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/backtest?status=completed")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_backtests_invalid_status(self, client: AsyncClient) -> None:
        """Test listing backtests with invalid status."""
        response = await client.get("/api/v1/backtest?status=invalid")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_backtests_with_strategy_filter(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test listing backtests filtered by strategy."""
        strategy_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_backtest_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest?strategy_id={strategy_id}")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_backtests_empty(self, client: AsyncClient) -> None:
        """Test listing backtests when none exist."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/backtest")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 0
            assert data["data"]["items"] == []


class TestGetBacktest:
    """Tests for GET /api/v1/backtest/{run_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_backtest_success(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test getting a backtest by ID."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(return_value=mock_backtest_run)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{mock_backtest_run.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_get_backtest_not_found(self, client: AsyncClient) -> None:
        """Test getting a non-existent backtest."""
        run_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(side_effect=BacktestNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{run_id}")

            assert response.status_code == 404


class TestGetBacktestDetail:
    """Tests for GET /api/v1/backtest/{run_id}/detail endpoint."""

    @pytest.mark.asyncio
    async def test_get_backtest_detail_success(
        self, client: AsyncClient, mock_backtest_run
    ) -> None:
        """Test getting backtest detail."""
        mock_equity_point = MagicMock()
        mock_equity_point.time = datetime.now(UTC)
        mock_equity_point.equity = 10500.0
        mock_equity_point.cash = 5000.0
        mock_equity_point.position_value = 5500.0
        mock_equity_point.unrealized_pnl = 500.0

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(return_value=mock_backtest_run)
            mock_service.get_equity_curve = AsyncMock(return_value=[mock_equity_point])
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{mock_backtest_run.id}/detail")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "equity_curve" in data["data"]
            assert data["data"]["total_bars"] == 1

    @pytest.mark.asyncio
    async def test_get_backtest_detail_not_found(self, client: AsyncClient) -> None:
        """Test getting detail for non-existent backtest."""
        run_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(side_effect=BacktestNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{run_id}/detail")

            assert response.status_code == 404


class TestGetEquityCurve:
    """Tests for GET /api/v1/backtest/{run_id}/equity-curve endpoint."""

    @pytest.mark.asyncio
    async def test_get_equity_curve_success(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test getting equity curve."""
        mock_equity_point = MagicMock()
        mock_equity_point.time = datetime.now(UTC)
        mock_equity_point.equity = 10500.0
        mock_equity_point.cash = 5000.0
        mock_equity_point.position_value = 5500.0
        mock_equity_point.unrealized_pnl = 500.0

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(return_value=[mock_equity_point])
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{mock_backtest_run.id}/equity-curve")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_get_equity_curve_not_found(self, client: AsyncClient) -> None:
        """Test getting equity curve for non-existent backtest."""
        run_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(
                side_effect=BacktestNotFoundError(str(run_id))
            )
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/backtest/{run_id}/equity-curve")

            assert response.status_code == 404


class TestDeleteBacktest:
    """Tests for DELETE /api/v1/backtest/{run_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_backtest_success(self, client: AsyncClient, mock_backtest_run) -> None:
        """Test deleting a backtest."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            response = await client.delete(f"/api/v1/backtest/{mock_backtest_run.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Backtest deleted"

    @pytest.mark.asyncio
    async def test_delete_backtest_not_found(self, client: AsyncClient) -> None:
        """Test deleting a non-existent backtest."""
        run_id = uuid4()

        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(side_effect=BacktestNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.delete(f"/api/v1/backtest/{run_id}")

            assert response.status_code == 404


class TestCheckDataAvailability:
    """Tests for POST /api/v1/backtest/data/check endpoint."""

    @pytest.mark.asyncio
    async def test_check_data_availability_success(self, client: AsyncClient) -> None:
        """Test checking data availability."""
        with patch("squant.api.v1.backtest.BacktestService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_data_availability = AsyncMock(
                return_value={
                    "exchange": "okx",
                    "symbol": "BTC/USDT",
                    "timeframe": "1h",
                    "first_bar": "2024-01-01T00:00:00Z",
                    "last_bar": "2024-06-01T00:00:00Z",
                    "total_bars": 1000,
                    "requested_start": "2024-01-01T00:00:00Z",
                    "requested_end": "2024-06-01T00:00:00Z",
                    "has_data": True,
                    "is_complete": True,
                }
            )
            mock_service_class.return_value = mock_service

            response = await client.post(
                "/api/v1/backtest/data/check",
                json={
                    "exchange": "okx",
                    "symbol": "BTC/USDT",
                    "timeframe": "1h",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-06-01T00:00:00Z",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["has_data"] is True


class TestListAvailableSymbols:
    """Tests for GET /api/v1/backtest/data/symbols endpoint."""

    @pytest.mark.asyncio
    async def test_list_available_symbols_success(self, client: AsyncClient) -> None:
        """Test listing available symbols."""
        with patch("squant.api.v1.backtest.DataLoader") as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader.get_available_symbols = AsyncMock(
                return_value=[
                    {
                        "exchange": "okx",
                        "symbol": "BTC/USDT",
                        "timeframe": "1h",
                        "bar_count": 1000,
                        "first_bar": "2024-01-01T00:00:00Z",
                        "last_bar": "2024-06-01T00:00:00Z",
                    }
                ]
            )
            mock_loader_class.return_value = mock_loader

            response = await client.get("/api/v1/backtest/data/symbols")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_list_available_symbols_with_filters(self, client: AsyncClient) -> None:
        """Test listing symbols with filters."""
        with patch("squant.api.v1.backtest.DataLoader") as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader.get_available_symbols = AsyncMock(return_value=[])
            mock_loader_class.return_value = mock_loader

            response = await client.get("/api/v1/backtest/data/symbols?exchange=okx&timeframe=1h")

            assert response.status_code == 200
            mock_loader.get_available_symbols.assert_called_once_with(
                exchange="okx", timeframe="1h"
            )
