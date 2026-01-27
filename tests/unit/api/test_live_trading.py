"""Unit tests for live trading API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from squant.main import app
from squant.models.enums import RunMode, RunStatus
from squant.services.live_trading import (
    ExchangeConnectionError,
    RiskConfigurationError,
    SessionNotFoundError,
    StrategyInstantiationError,
)
from squant.services.strategy import StrategyNotFoundError


class TestStartLiveTrading:
    """Tests for POST /api/v1/live endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def valid_request(self) -> dict[str, Any]:
        """Create valid start request."""
        return {
            "strategy_id": str(uuid4()),
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "risk_config": {
                "max_position_size": "0.5",
                "max_order_size": "0.1",
                "daily_trade_limit": 100,
                "daily_loss_limit": "0.05",
            },
            "initial_equity": "10000",
            "params": {"fast_period": 10},
        }

    def test_start_success(self, client: TestClient, valid_request: dict) -> None:
        """Test successful start."""
        mock_run = MagicMock()
        mock_run.id = str(uuid4())
        mock_run.strategy_id = valid_request["strategy_id"]
        mock_run.mode = RunMode.LIVE.value
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1m"
        mock_run.status = RunStatus.RUNNING.value
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0")
        mock_run.slippage = Decimal("0")
        mock_run.params = {"fast_period": 10}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(timezone.utc)
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(timezone.utc)
        mock_run.updated_at = datetime.now(timezone.utc)

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/live", json=valid_request)

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["symbol"] == "BTC/USDT"

    def test_start_strategy_not_found(
        self, client: TestClient, valid_request: dict
    ) -> None:
        """Test error when strategy not found."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyNotFoundError(valid_request["strategy_id"])
            )
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/live", json=valid_request)

            assert response.status_code == 404

    def test_start_risk_configuration_error(
        self, client: TestClient, valid_request: dict
    ) -> None:
        """Test error with invalid risk configuration."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=RiskConfigurationError("max_position_size must be positive")
            )
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/live", json=valid_request)

            assert response.status_code == 400
            assert "Risk configuration error" in response.json()["detail"]

    def test_start_strategy_instantiation_error(
        self, client: TestClient, valid_request: dict
    ) -> None:
        """Test error when strategy instantiation fails."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=StrategyInstantiationError("No Strategy subclass found")
            )
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/live", json=valid_request)

            assert response.status_code == 400

    def test_start_exchange_connection_error(
        self, client: TestClient, valid_request: dict
    ) -> None:
        """Test error when exchange connection fails."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.start = AsyncMock(
                side_effect=ExchangeConnectionError("Connection refused")
            )
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/live", json=valid_request)

            assert response.status_code == 503


class TestStopLiveTrading:
    """Tests for POST /api/v1/live/{run_id}/stop endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_stop_success(self, client: TestClient) -> None:
        """Test successful stop."""
        run_id = uuid4()
        mock_run = MagicMock()
        mock_run.id = str(run_id)
        mock_run.strategy_id = str(uuid4())
        mock_run.mode = RunMode.LIVE.value
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1m"
        mock_run.status = RunStatus.STOPPED.value
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(timezone.utc)
        mock_run.stopped_at = datetime.now(timezone.utc)
        mock_run.created_at = datetime.now(timezone.utc)
        mock_run.updated_at = datetime.now(timezone.utc)

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "stopped"

    def test_stop_with_cancel_orders_false(self, client: TestClient) -> None:
        """Test stop without cancelling orders."""
        run_id = uuid4()
        mock_run = MagicMock()
        mock_run.id = str(run_id)
        mock_run.strategy_id = str(uuid4())
        mock_run.mode = RunMode.LIVE.value
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1m"
        mock_run.status = RunStatus.STOPPED.value
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(timezone.utc)
        mock_run.stopped_at = datetime.now(timezone.utc)
        mock_run.created_at = datetime.now(timezone.utc)
        mock_run.updated_at = datetime.now(timezone.utc)

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/live/{run_id}/stop", json={"cancel_orders": False}
            )

            assert response.status_code == 200
            mock_service.stop.assert_called_once_with(run_id, cancel_orders=False)

    def test_stop_not_found(self, client: TestClient) -> None:
        """Test error when session not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.stop = AsyncMock(side_effect=SessionNotFoundError(run_id))
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/stop")

            assert response.status_code == 404


class TestEmergencyClose:
    """Tests for POST /api/v1/live/{run_id}/emergency-close endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_emergency_close_success(self, client: TestClient) -> None:
        """Test successful emergency close."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                return_value={
                    "run_id": str(run_id),
                    "status": "closed",
                    "orders_cancelled": 2,
                    "positions_closed": 1,
                }
            )
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "closed"
            assert data["data"]["orders_cancelled"] == 2
            assert data["data"]["positions_closed"] == 1

    def test_emergency_close_not_active(self, client: TestClient) -> None:
        """Test emergency close on inactive session."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                return_value={
                    "run_id": str(run_id),
                    "status": "not_active",
                    "message": "Session is not currently running",
                }
            )
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "not_active"

    def test_emergency_close_not_found(self, client: TestClient) -> None:
        """Test error when session not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.emergency_close = AsyncMock(
                side_effect=SessionNotFoundError(run_id)
            )
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/emergency-close")

            assert response.status_code == 404


class TestGetStatus:
    """Tests for GET /api/v1/live/{run_id}/status endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_get_status_active_session(self, client: TestClient) -> None:
        """Test getting status of active session."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(
                return_value={
                    "run_id": str(run_id),
                    "symbol": "BTC/USDT",
                    "timeframe": "1m",
                    "is_running": True,
                    "started_at": datetime.now(timezone.utc),
                    "stopped_at": None,
                    "error_message": None,
                    "bar_count": 100,
                    "cash": "5000",
                    "equity": "10500",
                    "initial_capital": "10000",
                    "total_fees": "50",
                    "positions": {"BTC/USDT": {"amount": "1.5", "avg_entry_price": "45000"}},
                    "pending_orders": [],
                    "live_orders": [
                        {
                            "internal_id": "order-1",
                            "exchange_order_id": "ex-123",
                            "symbol": "BTC/USDT",
                            "side": "buy",
                            "type": "limit",
                            "amount": "0.1",
                            "filled_amount": "0",
                            "price": "44000",
                            "avg_fill_price": None,
                            "status": "submitted",
                            "created_at": None,
                            "updated_at": None,
                        }
                    ],
                    "completed_orders_count": 10,
                    "trades_count": 5,
                    "risk_state": {
                        "daily_pnl": "500",
                        "daily_trade_count": 5,
                        "consecutive_losses": 0,
                        "circuit_breaker_active": False,
                        "max_position_size": "0.5",
                        "max_order_size": "0.1",
                        "daily_trade_limit": 100,
                        "daily_loss_limit": "0.05",
                    },
                }
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}/status")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["is_running"] is True
            assert data["data"]["equity"] == "10500"
            assert len(data["data"]["live_orders"]) == 1
            assert data["data"]["risk_state"]["daily_trade_count"] == 5

    def test_get_status_not_found(self, client: TestClient) -> None:
        """Test error when session not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_status = AsyncMock(
                side_effect=SessionNotFoundError(run_id)
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}/status")

            assert response.status_code == 404


class TestListActiveSessions:
    """Tests for GET /api/v1/live endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_list_active_empty(self, client: TestClient) -> None:
        """Test listing with no active sessions."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active.return_value = []
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/live")

            assert response.status_code == 200
            data = response.json()
            assert data["data"] == []

    def test_list_active_with_sessions(self, client: TestClient) -> None:
        """Test listing with active sessions."""
        run_id = uuid4()
        strategy_id = uuid4()

        mock_run = MagicMock()
        mock_run.strategy_id = str(strategy_id)

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_active.return_value = [
                {
                    "run_id": str(run_id),
                    "symbol": "BTC/USDT",
                    "timeframe": "1m",
                    "is_running": True,
                    "started_at": datetime.now(timezone.utc),
                    "bar_count": 50,
                    "equity": "10500",
                    "cash": "5000",
                }
            ]
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/live")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["symbol"] == "BTC/USDT"


class TestListRuns:
    """Tests for GET /api/v1/live/runs endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_list_runs_default_pagination(self, client: TestClient) -> None:
        """Test listing runs with default pagination."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/live/runs")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["items"] == []
            assert data["data"]["total"] == 0

    def test_list_runs_with_status_filter(self, client: TestClient) -> None:
        """Test listing runs with status filter."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_runs = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/live/runs?status=running")

            assert response.status_code == 200

    def test_list_runs_invalid_status(self, client: TestClient) -> None:
        """Test error with invalid status filter."""
        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service_class.return_value = MagicMock()

            response = client.get("/api/v1/live/runs?status=invalid")

            assert response.status_code == 400


class TestGetRun:
    """Tests for GET /api/v1/live/{run_id} endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_get_run_success(self, client: TestClient) -> None:
        """Test successful get run."""
        run_id = uuid4()
        mock_run = MagicMock()
        mock_run.id = str(run_id)
        mock_run.strategy_id = str(uuid4())
        mock_run.mode = RunMode.LIVE.value
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1m"
        mock_run.status = RunStatus.RUNNING.value
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(timezone.utc)
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(timezone.utc)
        mock_run.updated_at = datetime.now(timezone.utc)

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(return_value=mock_run)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["symbol"] == "BTC/USDT"

    def test_get_run_not_found(self, client: TestClient) -> None:
        """Test error when run not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(side_effect=SessionNotFoundError(run_id))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}")

            assert response.status_code == 404


class TestGetEquityCurve:
    """Tests for GET /api/v1/live/{run_id}/equity-curve endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_get_equity_curve_success(self, client: TestClient) -> None:
        """Test successful get equity curve."""
        run_id = uuid4()

        mock_curve = MagicMock()
        mock_curve.time = datetime.now(timezone.utc)
        mock_curve.equity = Decimal("10000")
        mock_curve.cash = Decimal("5000")
        mock_curve.position_value = Decimal("5000")
        mock_curve.unrealized_pnl = Decimal("0")

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(return_value=[mock_curve])
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}/equity-curve")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1

    def test_get_equity_curve_not_found(self, client: TestClient) -> None:
        """Test error when run not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_equity_curve = AsyncMock(
                side_effect=SessionNotFoundError(run_id)
            )
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/live/{run_id}/equity-curve")

            assert response.status_code == 404


class TestPersistSnapshots:
    """Tests for POST /api/v1/live/{run_id}/persist endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_persist_snapshots_success(self, client: TestClient) -> None:
        """Test successful persist snapshots."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(return_value=5)
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/persist")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["persisted_count"] == 5

    def test_persist_snapshots_not_found(self, client: TestClient) -> None:
        """Test error when session not found."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.live_trading.LiveTradingService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.persist_snapshots = AsyncMock(
                side_effect=SessionNotFoundError(run_id)
            )
            mock_service_class.return_value = mock_service

            response = client.post(f"/api/v1/live/{run_id}/persist")

            assert response.status_code == 404
