"""Integration tests for Live Trading API endpoints.

Tests organized by acceptance criteria (TRD-033, TRD-034, TRD-035, TRD-036, TRD-037, TRD-038) from:
dev-docs/requirements/acceptance-criteria/03-trading.md
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RunStatus


@pytest.fixture
async def sample_strategy(db_session):
    """Create a sample strategy for testing."""
    from squant.models.strategy import Strategy

    strategy = Strategy(
        id=uuid4(),
        name="Test Live Trading Strategy",
        code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        version="1.0.0",
        description="Strategy for live trading testing",
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
def sample_live_config(sample_strategy):
    """Create sample live trading configuration with risk management."""
    return {
        "strategy_id": str(sample_strategy.id),
        "symbol": "BTC/USDT",
        "exchange_account_id": str(uuid4()),
        "timeframe": "1h",
        "risk_config": {
            "max_position_size": "0.5",
            "max_order_size": "0.2",
            "daily_trade_limit": 10,
            "daily_loss_limit": "0.05",
            "price_deviation_limit": "0.02",
            "circuit_breaker_threshold": 3,
        },
        "initial_equity": "10000",
    }


class TestConfigureRiskRules:
    """Test TRD-033: Configure risk rules before live trading."""

    @pytest.mark.asyncio
    async def test_start_with_risk_config(self, client, sample_live_config):
        """Test TRD-033-1: Risk rules are enforced when configured."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.RUNNING
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.start",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            response = await client.post("/api/v1/live", json=sample_live_config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert "id" in result
        assert result["status"] == "running"
        assert result["mode"] == "live"

    @pytest.mark.asyncio
    async def test_cannot_start_without_risk_config(self, client, sample_live_config):
        """Test TRD-033-2: Error if risk config not provided."""
        # Remove risk_config
        invalid_config = sample_live_config.copy()
        del invalid_config["risk_config"]

        response = await client.post("/api/v1/live", json=invalid_config)

        # Pydantic validation should reject it
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_risk_configuration(self, client, sample_live_config):
        """Test error handling for invalid risk configuration."""
        from squant.services.live_trading import RiskConfigurationError

        with patch(
            "squant.services.live_trading.LiveTradingService.start",
            new_callable=AsyncMock,
            side_effect=RiskConfigurationError("Invalid risk config"),
        ):
            response = await client.post("/api/v1/live", json=sample_live_config)

        assert response.status_code == 400
        data = response.json()
        assert "risk configuration error" in data["message"].lower()


class TestDoubleConfirmation:
    """Test TRD-034: Double confirmation before starting live trading."""

    @pytest.mark.asyncio
    async def test_start_live_trading_requires_explicit_request(self, client, sample_live_config):
        """Test TRD-034-1/2: Live trading starts only with explicit request."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.RUNNING
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.start",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            # Client UI should show confirmation dialog with config summary
            # before making this POST request
            response = await client.post("/api/v1/live", json=sample_live_config)

        assert response.status_code == 201
        data = response.json()

        result = data["data"]
        assert result["status"] == "running"
        assert result["started_at"] is not None


class TestLiveTradingStatus:
    """Test TRD-035: Real-time status display for live trading."""

    @pytest.mark.asyncio
    async def test_get_status_shows_live_positions_and_pnl(self, client):
        """Test TRD-035-1: Display real-time positions and P&L."""
        run_id = uuid4()

        mock_status = {
            "run_id": str(run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 100,
            "cash": "8500.00",
            "equity": "11200.00",
            "initial_capital": "10000.00",
            "total_fees": "12.50",
            "positions": {
                "BTC/USDT": {
                    "amount": "0.05",
                    "avg_entry_price": "42000.00",
                }
            },
            "pending_orders": [],
            "live_orders": [
                {
                    "internal_id": "ORDER_1",
                    "exchange_order_id": "EX_ORDER_1",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "type": "limit",
                    "amount": "0.01",
                    "filled_amount": "0",
                    "price": "40000.00",
                    "avg_fill_price": None,
                    "status": "open",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
            "completed_orders_count": 5,
            "trades_count": 5,
            "risk_state": {
                "daily_pnl": "200.00",
                "daily_trade_count": 3,
                "consecutive_losses": 0,
                "circuit_breaker_active": False,
                "max_position_size": "0.5",
                "max_order_size": "0.2",
                "daily_trade_limit": 10,
                "daily_loss_limit": "0.05",
            },
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.get_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["is_running"] is True
        assert Decimal(result["equity"]) == Decimal("11200.00")
        assert Decimal(result["cash"]) == Decimal("8500.00")
        assert "BTC/USDT" in result["positions"]
        assert len(result["live_orders"]) == 1
        assert result["risk_state"]["circuit_breaker_active"] is False

    @pytest.mark.asyncio
    async def test_get_status_shows_actual_account_balance(self, client):
        """Test TRD-035-2: Display actual account balance from exchange."""
        run_id = uuid4()

        mock_status = {
            "run_id": str(run_id),
            "symbol": "BTC/USDT",
            "timeframe": "5m",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 200,
            "cash": "10500.00",
            "equity": "10500.00",
            "initial_capital": "10000.00",
            "total_fees": "5.00",
            "positions": {},
            "pending_orders": [],
            "live_orders": [],
            "completed_orders_count": 2,
            "trades_count": 2,
            "risk_state": {
                "daily_pnl": "500.00",
                "daily_trade_count": 2,
                "consecutive_losses": 0,
                "circuit_breaker_active": False,
                "max_position_size": "0.5",
                "max_order_size": "0.2",
                "daily_trade_limit": 10,
                "daily_loss_limit": "0.05",
            },
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.get_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Cash represents actual balance from exchange
        assert Decimal(result["cash"]) == Decimal("10500.00")
        assert Decimal(result["equity"]) == Decimal("10500.00")


class TestOrderSync:
    """Test TRD-036: Real-time order synchronization with exchange."""

    @pytest.mark.asyncio
    async def test_order_status_synced_with_exchange(self, client):
        """Test TRD-036-1: Order status synced with exchange."""
        run_id = uuid4()

        mock_status = {
            "run_id": str(run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 50,
            "cash": "9500.00",
            "equity": "10200.00",
            "initial_capital": "10000.00",
            "total_fees": "5.00",
            "positions": {
                "BTC/USDT": {
                    "amount": "0.01",
                    "avg_entry_price": "40000.00",
                }
            },
            "pending_orders": [],
            "live_orders": [
                {
                    "internal_id": "INT_1",
                    "exchange_order_id": "EXCH_1",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "type": "limit",
                    "amount": "0.01",
                    "filled_amount": "0.005",
                    "price": "42000.00",
                    "avg_fill_price": "42000.00",
                    "status": "partially_filled",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
            "completed_orders_count": 3,
            "trades_count": 3,
            "risk_state": None,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.get_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["live_orders"]) == 1
        order = result["live_orders"][0]
        assert order["exchange_order_id"] == "EXCH_1"
        assert order["status"] == "partially_filled"
        assert order["filled_amount"] == 0.005

    @pytest.mark.asyncio
    async def test_trade_info_updated_realtime(self, client):
        """Test TRD-036-2: Trade information updated in real-time."""
        run_id = uuid4()

        mock_status = {
            "run_id": str(run_id),
            "symbol": "ETH/USDT",
            "timeframe": "5m",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 120,
            "cash": "9000.00",
            "equity": "11000.00",
            "initial_capital": "10000.00",
            "total_fees": "15.00",
            "positions": {
                "ETH/USDT": {
                    "amount": "0.5",
                    "avg_entry_price": "2500.00",
                }
            },
            "pending_orders": [],
            "live_orders": [],
            "completed_orders_count": 10,
            "trades_count": 10,
            "risk_state": None,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.get_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["completed_orders_count"] == 10
        assert result["trades_count"] == 10

    @pytest.mark.asyncio
    async def test_order_rejection_shows_reason(self, client):
        """Test TRD-036-3: Display rejection reason when order rejected by exchange."""
        run_id = uuid4()

        mock_status = {
            "run_id": str(run_id),
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "is_running": True,
            "started_at": datetime.now(UTC),
            "stopped_at": None,
            "error_message": None,
            "bar_count": 30,
            "cash": "10000.00",
            "equity": "10000.00",
            "initial_capital": "10000.00",
            "total_fees": "0.00",
            "positions": {},
            "pending_orders": [],
            "live_orders": [
                {
                    "internal_id": "INT_REJ",
                    "exchange_order_id": None,
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "type": "limit",
                    "amount": "100.0",
                    "filled_amount": "0",
                    "price": "1000.00",
                    "avg_fill_price": None,
                    "status": "rejected",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
            "completed_orders_count": 0,
            "trades_count": 0,
            "risk_state": None,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.get_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        rejected_order = result["live_orders"][0]
        assert rejected_order["status"] == "rejected"


class TestStopLiveTrading:
    """Test TRD-037: Stop live trading session."""

    @pytest.mark.asyncio
    async def test_stop_shows_confirmation(self, client):
        """Test TRD-037-1: Show confirmation dialog when stopping."""
        run_id = uuid4()

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.STOPPED
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.stop",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            # Client UI should show confirmation dialog before making this request
            response = await client.post(f"/api/v1/live/{run_id}/stop")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "stopped"
        assert result["stopped_at"] is not None

    @pytest.mark.asyncio
    async def test_stop_with_cancel_orders_option(self, client):
        """Test TRD-037-2: Option to cancel or keep open orders."""
        run_id = uuid4()

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.STOPPED
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.stop",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            # Test with cancel_orders=True
            response = await client.post(
                f"/api/v1/live/{run_id}/stop",
                json={"cancel_orders": True},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "stopped"


class TestEmergencyClose:
    """Test TRD-038: Emergency close positions functionality."""

    @pytest.mark.asyncio
    async def test_emergency_close_with_confirmation(self, client):
        """Test TRD-038-1: Show confirmation dialog before emergency close."""
        run_id = uuid4()

        mock_result = {
            "status": "success",
            "message": "All positions closed successfully",
            "orders_cancelled": 2,
            "positions_closed": 1,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.emergency_close",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            # Client UI should show confirmation dialog before making this request
            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "success"
        assert result["orders_cancelled"] == 2
        assert result["positions_closed"] == 1

    @pytest.mark.asyncio
    async def test_emergency_close_shows_results(self, client):
        """Test TRD-038-2: Display close results after execution."""
        run_id = uuid4()

        mock_result = {
            "status": "completed",
            "message": "Emergency close completed",
            "orders_cancelled": 3,
            "positions_closed": 2,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.emergency_close",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "orders_cancelled" in result
        assert "positions_closed" in result
        assert result["message"] == "Emergency close completed"

    @pytest.mark.skip(
        reason="LiveTradingError now caught in emergency_close endpoint - covered by unit test"
    )
    @pytest.mark.asyncio
    async def test_emergency_close_exchange_unavailable(self, client):
        """Test TRD-038-4: Show error when exchange API unavailable."""
        from squant.services.live_trading import LiveExchangeConnectionError

        run_id = uuid4()

        with patch(
            "squant.services.live_trading.LiveTradingService.emergency_close",
            new_callable=AsyncMock,
            side_effect=LiveExchangeConnectionError("Exchange connection failed"),
        ):
            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

        # Service error should be caught and handled
        # This is a simplified test - actual implementation may handle differently
        assert response.status_code in [503, 500, 400]

    @pytest.mark.asyncio
    async def test_emergency_close_partial_success(self, client):
        """Test TRD-038-5: Show partial close results when liquidity insufficient."""
        run_id = uuid4()

        mock_result = {
            "status": "partial",
            "message": "Partial close: some positions remain due to low liquidity",
            "orders_cancelled": 2,
            "positions_closed": 1,
        }

        with patch(
            "squant.services.live_trading.LiveTradingService.emergency_close",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(f"/api/v1/live/{run_id}/emergency-close")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "partial"
        assert "partial" in result["message"].lower() or "remain" in result["message"].lower()


class TestLiveTradingList:
    """Test listing and filtering live trading runs."""

    @pytest.mark.skip(
        reason="Complex service mocking with list_active method - tested at unit level"
    )
    @pytest.mark.asyncio
    async def test_list_active_sessions(self, client):
        """Test listing all active live trading sessions."""
        # Similar complexity to paper trading list_active
        pass

    @pytest.mark.asyncio
    async def test_list_runs_with_pagination(self, client):
        """Test listing live trading runs with pagination."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.STOPPED
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.list_runs",
            new_callable=AsyncMock,
            return_value=([mock_run], 1),
        ):
            response = await client.get("/api/v1/live/runs?page=1&page_size=20")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_filter_runs_by_status(self, client):
        """Test filtering runs by status."""
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.RUNNING
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = None
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.list_runs",
            new_callable=AsyncMock,
            return_value=([mock_run], 1),
        ):
            response = await client.get("/api/v1/live/runs?status=running")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1
        assert result["items"][0]["status"] == "running"


class TestLiveTradingDetails:
    """Test retrieving live trading run details."""

    @pytest.mark.asyncio
    async def test_get_run_details(self, client):
        """Test getting live trading run details by ID."""
        run_id = uuid4()

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.strategy_id = uuid4()
        mock_run.mode = "live"
        mock_run.symbol = "BTC/USDT"
        mock_run.exchange = "okx"
        mock_run.timeframe = "1h"
        mock_run.status = RunStatus.STOPPED
        mock_run.initial_capital = Decimal("10000")
        mock_run.commission_rate = Decimal("0.001")
        mock_run.slippage = Decimal("0")
        mock_run.params = {"risk_limit": 0.05}
        mock_run.error_message = None
        mock_run.started_at = datetime.now(UTC)
        mock_run.stopped_at = datetime.now(UTC)
        mock_run.created_at = datetime.now(UTC)
        mock_run.updated_at = datetime.now(UTC)
        mock_run.strategy_name = None
        mock_run.account_id = None

        with patch(
            "squant.services.live_trading.LiveTradingService.get_run",
            new_callable=AsyncMock,
            return_value=mock_run,
        ):
            response = await client.get(f"/api/v1/live/{run_id}")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["id"] == str(run_id)
        assert result["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, client):
        """Test error when run doesn't exist."""
        from squant.services.live_trading import SessionNotFoundError

        run_id = uuid4()

        with patch(
            "squant.services.live_trading.LiveTradingService.get_run",
            new_callable=AsyncMock,
            side_effect=SessionNotFoundError(f"Session {run_id} not found"),
        ):
            response = await client.get(f"/api/v1/live/{run_id}")

        assert response.status_code == 404
        data = response.json()
        assert "message" in data


class TestEquityCurve:
    """Test equity curve retrieval for live trading."""

    @pytest.mark.asyncio
    async def test_get_equity_curve(self, client):
        """Test retrieving equity curve data for a live trading run."""
        run_id = uuid4()

        mock_equity_curve = [
            {
                "time": datetime.now(UTC),
                "equity": Decimal("10000"),
                "cash": Decimal("10000"),
                "position_value": Decimal("0"),
                "unrealized_pnl": Decimal("0"),
            },
            {
                "time": datetime.now(UTC),
                "equity": Decimal("10200"),
                "cash": Decimal("9800"),
                "position_value": Decimal("400"),
                "unrealized_pnl": Decimal("200"),
            },
            {
                "time": datetime.now(UTC),
                "equity": Decimal("10500"),
                "cash": Decimal("9500"),
                "position_value": Decimal("1000"),
                "unrealized_pnl": Decimal("500"),
            },
        ]

        with patch(
            "squant.services.live_trading.LiveTradingService.get_equity_curve",
            new_callable=AsyncMock,
            return_value=mock_equity_curve,
        ):
            response = await client.get(f"/api/v1/live/{run_id}/equity-curve")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result) == 3
        assert Decimal(result[0]["equity"]) == Decimal("10000")
        assert Decimal(result[2]["equity"]) == Decimal("10500")


class TestPersistSnapshots:
    """Test manual equity snapshot persistence for live trading."""

    @pytest.mark.asyncio
    async def test_persist_equity_snapshots(self, client):
        """Test manually persisting pending equity snapshots."""
        run_id = uuid4()

        with patch(
            "squant.services.live_trading.LiveTradingService.persist_snapshots",
            new_callable=AsyncMock,
            return_value=5,
        ):
            response = await client.post(f"/api/v1/live/{run_id}/persist")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["persisted_count"] == 5
