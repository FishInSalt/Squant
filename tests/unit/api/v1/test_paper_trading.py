"""Unit tests for paper trading API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.infra.redis import get_redis
from squant.main import app
from squant.models.enums import RunMode, RunStatus
from squant.services.paper_trading import (
    PaperTradingError,
    SessionNotFoundError,
    StrategyInstantiationError,
)
from squant.services.strategy import StrategyNotFoundError


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked Redis dependency."""

    async def _mock_redis():
        yield MagicMock()

    app.dependency_overrides[get_redis] = _mock_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def mock_run():
    """Create a mock paper trading run."""
    run = MagicMock()
    run.id = uuid4()
    run.strategy_id = str(uuid4())  # Must be string for UUID() conversion in endpoint
    run.strategy_name = "Test Strategy"
    run.mode = RunMode.PAPER.value
    run.symbol = "BTC/USDT"
    run.exchange = "okx"
    run.timeframe = "1m"
    run.status = RunStatus.RUNNING.value
    run.initial_capital = Decimal("10000")
    run.commission_rate = Decimal("0.001")
    run.slippage = Decimal("0")
    run.params = {}
    run.error_message = None
    run.started_at = datetime.now(UTC)
    run.stopped_at = None
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    return run


@pytest.fixture
def valid_start_request() -> dict[str, Any]:
    """Create a valid paper trading start request."""
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange": "okx",
        "timeframe": "1m",
        "initial_capital": "10000",
        "commission_rate": "0.001",
        "slippage": "0",
    }


class TestStartPaperTrading:
    """Tests for POST /api/v1/paper-trading endpoint."""

    @pytest.mark.asyncio
    async def test_start_paper_trading_success(
        self, client: AsyncClient, valid_start_request: dict, mock_run
    ) -> None:
        """Test successful paper trading start."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper", json=valid_start_request)

            assert response.status_code == 201
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["symbol"] == "BTC/USDT"
            assert data["data"]["mode"] == "paper"

    @pytest.mark.asyncio
    async def test_start_paper_trading_strategy_not_found(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting paper trading with non-existent strategy."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyNotFoundError(valid_start_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper", json=valid_start_request)

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_paper_trading_instantiation_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting paper trading with strategy instantiation error."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyInstantiationError("Strategy instantiation failed")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper", json=valid_start_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_paper_trading_general_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting paper trading with general error."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(side_effect=PaperTradingError("General error"))
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper", json=valid_start_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_paper_trading_missing_fields(self, client: AsyncClient) -> None:
        """Test starting paper trading with missing required fields."""
        response = await client.post(
            "/api/v1/paper",
            json={"symbol": "BTC/USDT"},
        )

        assert response.status_code == 422


class TestStopPaperTrading:
    """Tests for POST /api/v1/paper-trading/{run_id}/stop endpoint."""

    @pytest.mark.asyncio
    async def test_stop_paper_trading_success(self, client: AsyncClient, mock_run) -> None:
        """Test successful paper trading stop."""
        mock_run.status = RunStatus.STOPPED.value
        mock_run.stopped_at = datetime.now(UTC)

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/paper/{mock_run.id}/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_paper_trading_not_found(self, client: AsyncClient) -> None:
        """Test stopping non-existent paper trading session."""
        run_id = uuid4()

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/paper/{run_id}/stop")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_paper_trading_invalid_uuid(self, client: AsyncClient) -> None:
        """Test stopping with invalid UUID format."""
        response = await client.post("/api/v1/paper/invalid-uuid/stop")

        assert response.status_code == 422


class TestGetPaperTradingStatus:
    """Tests for GET /api/v1/paper-trading/{run_id}/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting paper trading status."""
        mock_status = {
            "run_id": str(mock_run.id),
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 100,
            "cash": "9000",
            "equity": "10500",
            "initial_capital": "10000",
            "total_fees": "5.5",
            "unrealized_pnl": "500",
            "realized_pnl": "200",
            "positions": {"BTC/USDT": {"amount": "0.1", "avg_entry_price": "50000"}},
            "pending_orders": [],
            "completed_orders_count": 5,
            "trades_count": 10,
        }

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(return_value=mock_status)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{mock_run.id}/status")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["is_running"] is True
            assert data["data"]["bar_count"] == 100
            assert data["data"]["unrealized_pnl"] == 500.0
            assert data["data"]["realized_pnl"] == 200.0

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client: AsyncClient) -> None:
        """Test getting status for non-existent session."""
        run_id = uuid4()

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{run_id}/status")

            assert response.status_code == 404


class TestListActiveSessions:
    """Tests for GET /api/v1/paper-trading endpoint."""

    @pytest.mark.asyncio
    async def test_list_active_sessions_success(self, client: AsyncClient, mock_run) -> None:
        """Test listing active paper trading sessions."""
        mock_sessions = [
            {
                "run_id": str(mock_run.id),
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "is_running": True,
                "started_at": datetime.now(UTC),
                "bar_count": 50,
                "equity": "10500",
                "cash": "9000",
            }
        ]

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active = MagicMock(return_value=mock_sessions)
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_list_active_sessions_empty(self, client: AsyncClient) -> None:
        """Test listing active sessions when none exist."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active = MagicMock(return_value=[])
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper")

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []


class TestListPaperTradingRuns:
    """Tests for GET /api/v1/paper/runs endpoint."""

    @pytest.mark.asyncio
    async def test_list_runs_success(self, client: AsyncClient, mock_run) -> None:
        """Test listing paper trading runs with pagination."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper/runs")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 1
            assert len(data["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_runs_with_pagination(self, client: AsyncClient, mock_run) -> None:
        """Test listing runs with pagination params."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_run], 50))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper/runs?page=2&page_size=10")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["page"] == 2
            assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_runs_with_status_filter(self, client: AsyncClient, mock_run) -> None:
        """Test listing runs with status filter."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper/runs?status=running")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_runs_invalid_status(self, client: AsyncClient) -> None:
        """Test listing runs with invalid status."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/paper/runs?status=invalid")

            assert response.status_code == 400


class TestGetPaperTradingRun:
    """Tests for GET /api/v1/paper-trading/{run_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_run_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting a paper trading run by ID."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{mock_run.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent run."""
        run_id = uuid4()

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{run_id}")

            assert response.status_code == 404


class TestGetEquityCurve:
    """Tests for GET /api/v1/paper-trading/{run_id}/equity-curve endpoint."""

    @pytest.mark.asyncio
    async def test_get_equity_curve_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting equity curve."""
        mock_point = MagicMock()
        mock_point.time = datetime.now(UTC)
        mock_point.equity = Decimal("10500")
        mock_point.cash = Decimal("9000")
        mock_point.position_value = Decimal("1500")
        mock_point.unrealized_pnl = Decimal("500")
        mock_point.benchmark_equity = None
        mock_curve = [mock_point]

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(return_value=mock_curve)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{mock_run.id}/equity-curve")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_equity_curve_not_found(self, client: AsyncClient) -> None:
        """Test getting equity curve for non-existent run."""
        run_id = uuid4()

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{run_id}/equity-curve")

            assert response.status_code == 404


class TestPersistEquitySnapshots:
    """Tests for POST /api/v1/paper-trading/{run_id}/persist endpoint."""

    @pytest.mark.asyncio
    async def test_persist_success(self, client: AsyncClient, mock_run) -> None:
        """Test persisting equity snapshots."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(return_value=10)
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/paper/{mock_run.id}/persist")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["persisted_count"] == 10

    @pytest.mark.asyncio
    async def test_persist_not_found(self, client: AsyncClient) -> None:
        """Test persisting snapshots for non-existent session."""
        run_id = uuid4()

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(
                side_effect=SessionNotFoundError(str(run_id))
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/paper/{run_id}/persist")

            assert response.status_code == 404


class TestStopAllPaperTrading:
    """Tests for POST /api/v1/paper/stop-all endpoint."""

    @pytest.mark.asyncio
    async def test_stop_all_success(self, client: AsyncClient) -> None:
        """Test stopping all paper trading sessions."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop_all = AsyncMock(return_value=3)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper/stop-all")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["stopped_count"] == 3

    @pytest.mark.asyncio
    async def test_stop_all_no_sessions(self, client: AsyncClient) -> None:
        """Test stop-all when no sessions are running."""
        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop_all = AsyncMock(return_value=0)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/paper/stop-all")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["stopped_count"] == 0


class TestGetStatusWithTradesAndLogs:
    """Tests for trades and logs in status response."""

    @pytest.mark.asyncio
    async def test_status_includes_trades_and_logs(
        self, client: AsyncClient, mock_run
    ) -> None:
        """Test that status response includes trades and logs fields."""
        now = datetime.now(UTC)
        mock_status = {
            "run_id": str(mock_run.id),
            "symbol": "BTC/USDT",
            "timeframe": "1m",
            "is_running": True,
            "started_at": now,
            "stopped_at": None,
            "error_message": None,
            "bar_count": 50,
            "cash": "9000",
            "equity": "10100",
            "initial_capital": "10000",
            "total_fees": "0.1",
            "unrealized_pnl": "0",
            "realized_pnl": "100",
            "positions": {},
            "pending_orders": [],
            "completed_orders_count": 1,
            "trades_count": 1,
            "trades": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "entry_time": now.isoformat(),
                    "entry_price": "50000",
                    "exit_time": now.isoformat(),
                    "exit_price": "51000",
                    "amount": "0.1",
                    "pnl": "100",
                    "pnl_pct": "2.0",
                    "fees": "0.1",
                }
            ],
            "open_trade": None,
            "logs": ["[2024-01-01] Buy triggered", "[2024-01-01] Order filled"],
        }

        with patch("squant.api.v1.paper_trading.PaperTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(return_value=mock_status)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/paper/{mock_run.id}/status")

            assert response.status_code == 200
            data = response.json()["data"]
            assert len(data["trades"]) == 1
            assert data["trades"][0]["symbol"] == "BTC/USDT"
            assert data["trades"][0]["pnl"] == 100.0
            assert len(data["logs"]) == 2
            assert "Buy triggered" in data["logs"][0]
