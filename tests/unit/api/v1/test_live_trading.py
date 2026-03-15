"""Unit tests for live trading API endpoints."""

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

from squant.main import app
from squant.models.enums import RunMode, RunStatus
from squant.services.live_trading import (
    ExchangeAccountNotFoundError,
    LiveExchangeConnectionError,
    LiveTradingError,
    RiskConfigurationError,
    SessionNotFoundError,
    SessionNotResumableError,
    StrategyInstantiationError,
)
from squant.services.strategy import StrategyNotFoundError


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_run():
    """Create a mock live trading run."""
    run = MagicMock()
    run.id = uuid4()
    run.strategy_id = str(uuid4())  # Must be string for UUID() conversion in endpoint
    run.strategy_name = "Test Strategy"
    run.account_id = str(uuid4())
    run.mode = RunMode.LIVE.value
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
    """Create a valid live trading start request."""
    return {
        "strategy_id": str(uuid4()),
        "symbol": "BTC/USDT",
        "exchange_account_id": str(uuid4()),
        "timeframe": "1m",
        "risk_config": {
            "max_position_size": "0.1",
            "max_order_size": "0.05",
            "daily_trade_limit": 50,
            "daily_loss_limit": "0.05",
        },
        "initial_equity": "10000",
    }


class TestStartLiveTrading:
    """Tests for POST /api/v1/live endpoint."""

    @pytest.mark.asyncio
    async def test_start_live_trading_success(
        self, client: AsyncClient, valid_start_request: dict, mock_run
    ) -> None:
        """Test successful live trading start."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 201
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_start_live_trading_strategy_not_found(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting live trading with non-existent strategy."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyNotFoundError(valid_start_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_live_trading_risk_config_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting live trading with invalid risk config."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=RiskConfigurationError("Invalid risk config")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_live_trading_strategy_instantiation_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting live trading with strategy instantiation error."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyInstantiationError("Failed to instantiate")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_live_trading_exchange_connection_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting live trading with exchange connection error."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=LiveExchangeConnectionError("Cannot connect to exchange")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_start_live_trading_general_error(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """Test starting live trading with general error."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(side_effect=LiveTradingError("General error"))
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_live_trading_missing_risk_config(self, client: AsyncClient) -> None:
        """Test starting live trading without risk config."""
        response = await client.post(
            "/api/v1/live",
            json={
                "strategy_id": str(uuid4()),
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
            },
        )

        assert response.status_code == 422


class TestStopLiveTrading:
    """Tests for POST /api/v1/live/{run_id}/stop endpoint."""

    @pytest.mark.asyncio
    async def test_stop_live_trading_success(self, client: AsyncClient, mock_run) -> None:
        """Test successful live trading stop."""
        mock_run.status = RunStatus.STOPPED.value
        mock_run.stopped_at = datetime.now(UTC)

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_live_trading_with_cancel_orders(
        self, client: AsyncClient, mock_run
    ) -> None:
        """Test stopping live trading with cancel orders option."""
        mock_run.status = RunStatus.STOPPED.value

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.post(
                f"/api/v1/live/{mock_run.id}/stop",
                json={"cancel_orders": False},
            )

            assert response.status_code == 200
            mock_service.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_live_trading_not_found(self, client: AsyncClient) -> None:
        """Test stopping non-existent live trading session."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/stop")

            assert response.status_code == 404


class TestResumeLiveTrading:
    """Tests for POST /api/v1/live/{run_id}/resume endpoint."""

    @pytest.mark.asyncio
    async def test_resume_live_trading_success(self, client: AsyncClient, mock_run) -> None:
        """Test successful resume returns 200 with run data and reconciliation message."""
        mock_run.status = RunStatus.RUNNING.value

        reconciliation = {"orders_reconciled": 3, "fills_processed": 5}

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(return_value=(mock_run, reconciliation))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/resume")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["symbol"] == "BTC/USDT"
            assert data["data"]["status"] == "running"
            assert "Orders reconciled: 3" in data["message"]
            assert "fills processed: 5" in data["message"]
            mock_service.resume.assert_called_once_with(mock_run.id, warmup_bars=200)

    @pytest.mark.asyncio
    async def test_resume_live_trading_with_custom_warmup_bars(
        self, client: AsyncClient, mock_run
    ) -> None:
        """Test resume with custom warmup_bars from request body."""
        mock_run.status = RunStatus.RUNNING.value

        reconciliation = {"orders_reconciled": 0, "fills_processed": 0}

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(return_value=(mock_run, reconciliation))
            mock_service_class.return_value = mock_service

            response = await client.post(
                f"/api/v1/live/{mock_run.id}/resume",
                json={"warmup_bars": 500},
            )

            assert response.status_code == 200
            mock_service.resume.assert_called_once_with(mock_run.id, warmup_bars=500)

    @pytest.mark.asyncio
    async def test_resume_live_trading_session_not_found(self, client: AsyncClient) -> None:
        """Test resume returns 404 when session does not exist."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(
                side_effect=SessionNotFoundError(str(run_id))
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_live_trading_session_not_resumable(self, client: AsyncClient) -> None:
        """Test resume returns 409 when session is not in a resumable state."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(
                side_effect=SessionNotResumableError(run_id, "session is currently running")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_resume_live_trading_exchange_account_not_found(
        self, client: AsyncClient
    ) -> None:
        """Test resume returns 404 when exchange account is not found."""
        run_id = uuid4()
        account_id = str(uuid4())

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(
                side_effect=ExchangeAccountNotFoundError(account_id, "not found")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_live_trading_exchange_connection_error(
        self, client: AsyncClient
    ) -> None:
        """Test resume returns 503 when exchange connection fails."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(
                side_effect=LiveExchangeConnectionError("Cannot connect to exchange")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_resume_live_trading_general_error(self, client: AsyncClient) -> None:
        """Test resume returns 400 for general LiveTradingError."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(
                side_effect=LiveTradingError("Something went wrong during resume")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 400


class TestEmergencyClose:
    """Tests for POST /api/v1/live/{run_id}/emergency-close endpoint."""

    @pytest.mark.asyncio
    async def test_emergency_close_success(self, client: AsyncClient, mock_run) -> None:
        """Test successful emergency close."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                return_value={
                    "status": "completed",
                    "message": "Emergency close completed",
                    "orders_cancelled": 2,
                    "positions_closed": 1,
                }
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/emergency-close")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "completed"
            assert data["data"]["orders_cancelled"] == 2
            assert data["data"]["positions_closed"] == 1

    @pytest.mark.asyncio
    async def test_emergency_close_not_found(self, client: AsyncClient) -> None:
        """Test emergency close for non-existent session."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_emergency_close_live_trading_error(self, client: AsyncClient) -> None:
        """Test C-5: emergency close should catch LiveTradingError and return 400."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                side_effect=LiveTradingError("Cannot close: circuit breaker active")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 400
            assert "circuit breaker" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_emergency_close_unexpected_error(self, client: AsyncClient) -> None:
        """Test C-5: emergency close should catch unexpected Exception and return 500."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                side_effect=RuntimeError("Unexpected engine failure")
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 500
            assert "Emergency close failed" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_emergency_close_partial_includes_remaining_positions_and_errors(
        self, client: AsyncClient, mock_run
    ) -> None:
        """Test C-2: partial close result includes remaining_positions and errors in response."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                return_value={
                    "status": "partial",
                    "message": "Partial emergency close: 1 position could not be closed",
                    "orders_cancelled": 3,
                    "positions_closed": 2,
                    "remaining_positions": [
                        {"symbol": "ETH/USDT", "amount": "0.5", "side": "long"},
                    ],
                    "errors": [
                        {"symbol": "ETH/USDT", "error": "Insufficient liquidity"},
                    ],
                }
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/emergency-close")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "partial"
            assert data["data"]["orders_cancelled"] == 3
            assert data["data"]["positions_closed"] == 2

            remaining = data["data"]["remaining_positions"]
            assert remaining is not None
            assert len(remaining) == 1
            assert remaining[0]["symbol"] == "ETH/USDT"
            assert remaining[0]["amount"] == "0.5"
            assert remaining[0]["side"] == "long"

            errors = data["data"]["errors"]
            assert errors is not None
            assert len(errors) == 1
            assert errors[0]["symbol"] == "ETH/USDT"
            assert errors[0]["error"] == "Insufficient liquidity"


class TestGetLiveTradingStatus:
    """Tests for GET /api/v1/live/{run_id}/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting live trading status."""
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
            "live_orders": [],
            "completed_orders_count": 5,
            "trades_count": 10,
            "risk_state": {
                "daily_pnl": "500",
                "daily_trade_count": 10,
                "consecutive_losses": 0,
                "circuit_breaker_active": False,
                "max_position_size": "0.1",
                "max_order_size": "0.05",
                "daily_trade_limit": 50,
                "daily_loss_limit": "0.05",
            },
        }

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(return_value=mock_status)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{mock_run.id}/status")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["is_running"] is True
            assert data["data"]["unrealized_pnl"] == 500.0
            assert data["data"]["realized_pnl"] == 200.0
            assert data["data"]["risk_state"]["circuit_breaker_active"] is False

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client: AsyncClient) -> None:
        """Test getting status for non-existent session."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{run_id}/status")

            assert response.status_code == 404


class TestListActiveSessions:
    """Tests for GET /api/v1/live endpoint."""

    @pytest.mark.asyncio
    async def test_list_active_sessions_success(self, client: AsyncClient, mock_run) -> None:
        """Test listing active live trading sessions."""
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

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active = MagicMock(return_value=mock_sessions)
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/live")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_list_active_sessions_empty(self, client: AsyncClient) -> None:
        """Test listing active sessions when none exist."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active = MagicMock(return_value=[])
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/live")

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []


class TestListLiveTradingRuns:
    """Tests for GET /api/v1/live/runs endpoint."""

    @pytest.mark.asyncio
    async def test_list_runs_success(self, client: AsyncClient, mock_run) -> None:
        """Test listing live trading runs with pagination."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_run], 1))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/live/runs")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_list_runs_with_pagination(self, client: AsyncClient, mock_run) -> None:
        """Test listing runs with pagination params."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([mock_run], 50))
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/live/runs?page=2&page_size=10")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["page"] == 2
            assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_runs_invalid_status(self, client: AsyncClient) -> None:
        """Test listing runs with invalid status."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            response = await client.get("/api/v1/live/runs?status=invalid")

            assert response.status_code == 400


class TestGetLiveTradingRun:
    """Tests for GET /api/v1/live/{run_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_run_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting a live trading run by ID."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{mock_run.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent run."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{run_id}")

            assert response.status_code == 404


class TestGetEquityCurve:
    """Tests for GET /api/v1/live/{run_id}/equity-curve endpoint."""

    @pytest.mark.asyncio
    async def test_get_equity_curve_success(self, client: AsyncClient, mock_run) -> None:
        """Test getting equity curve."""
        mock_point = MagicMock()
        mock_point.time = datetime.now(UTC)
        mock_point.equity = Decimal("10500")
        mock_point.cash = Decimal("9000")
        mock_point.benchmark_equity = None
        mock_point.position_value = Decimal("1500")
        mock_point.unrealized_pnl = Decimal("500")
        mock_curve = [mock_point]

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(return_value=mock_curve)
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{mock_run.id}/equity-curve")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_equity_curve_not_found(self, client: AsyncClient) -> None:
        """Test getting equity curve for non-existent run."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{run_id}/equity-curve")

            assert response.status_code == 404


class TestPersistEquitySnapshots:
    """Tests for POST /api/v1/live/{run_id}/persist endpoint."""

    @pytest.mark.asyncio
    async def test_persist_success(self, client: AsyncClient, mock_run) -> None:
        """Test persisting equity snapshots."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(return_value=10)
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/persist")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["persisted_count"] == 10

    @pytest.mark.asyncio
    async def test_persist_not_found(self, client: AsyncClient) -> None:
        """Test persisting snapshots for non-existent session."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(
                side_effect=SessionNotFoundError(str(run_id))
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/persist")

            assert response.status_code == 404


# --- Bug Fix Tests ---


class TestApiErrorFormatConsistency:
    """Tests for m-5: All API error responses must use {"code", "message", "data"} format."""

    @pytest.mark.asyncio
    async def test_session_not_found_error_format(self, client: AsyncClient) -> None:
        """SessionNotFoundError should return uniform error format, not bare {"detail": ...}."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.get(f"/api/v1/live/{run_id}")

            assert response.status_code == 404
            data = response.json()
            # Must have uniform error format
            assert "code" in data, f"Response missing 'code': {data}"
            assert "message" in data, f"Response missing 'message': {data}"
            assert "data" in data, f"Response missing 'data': {data}"
            assert data["code"] == 404
            assert data["data"] is None
            # Must NOT have bare "detail" key as the only error field
            if "detail" in data:
                # If detail exists, it should be alongside code/message, not standalone
                assert "code" in data

    @pytest.mark.asyncio
    async def test_strategy_not_found_error_format(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """StrategyNotFoundError should return uniform error format."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyNotFoundError(valid_start_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 404
            data = response.json()
            assert "code" in data
            assert "message" in data
            assert "data" in data
            assert data["code"] == 404
            assert data["data"] is None

    @pytest.mark.asyncio
    async def test_exchange_connection_error_format(
        self, client: AsyncClient, valid_start_request: dict
    ) -> None:
        """ExchangeConnectionError should return uniform error format."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=LiveExchangeConnectionError("Connection timeout")
            )
            mock_service_class.return_value = mock_service

            response = await client.post("/api/v1/live", json=valid_start_request)

            assert response.status_code == 503
            data = response.json()
            assert "code" in data
            assert "message" in data
            assert "data" in data
            assert data["code"] == 503
            assert data["data"] is None

    @pytest.mark.asyncio
    async def test_stop_not_found_error_format(self, client: AsyncClient) -> None:
        """Stop endpoint SessionNotFoundError should return uniform error format."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/stop")

            assert response.status_code == 404
            data = response.json()
            assert "code" in data
            assert "message" in data
            assert "data" in data
            assert data["code"] == 404

    @pytest.mark.asyncio
    async def test_resume_not_found_error_format(self, client: AsyncClient) -> None:
        """Resume endpoint SessionNotFoundError should return uniform error format."""
        run_id = uuid4()

        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.resume = AsyncMock(side_effect=SessionNotFoundError(str(run_id)))
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{run_id}/resume")

            assert response.status_code == 404
            data = response.json()
            assert "code" in data
            assert "message" in data
            assert "data" in data
            assert data["code"] == 404


class TestEmergencyCloseApiStatus:
    """Tests for m-6: emergency_close status values must match schema."""

    @pytest.mark.asyncio
    async def test_emergency_close_returns_completed_not_closed(
        self, client: AsyncClient, mock_run
    ) -> None:
        """API emergency close should return 'completed', not 'closed'."""
        with patch("squant.api.v1.live_trading.LiveTradingService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                return_value={
                    "status": "completed",
                    "message": "Emergency close completed",
                    "orders_cancelled": 2,
                    "positions_closed": 1,
                }
            )
            mock_service_class.return_value = mock_service

            response = await client.post(f"/api/v1/live/{mock_run.id}/emergency-close")

            assert response.status_code == 200
            data = response.json()
            status = data["data"]["status"]
            valid_statuses = {"completed", "partial", "in_progress", "not_active"}
            assert status in valid_statuses, (
                f"Status '{status}' not in valid values: {valid_statuses}"
            )
