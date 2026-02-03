"""Unit tests for live trading schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.schemas.live_trading import (
    EmergencyCloseResponse,
    LiveOrderInfo,
    LivePositionInfo,
    LiveTradingListItem,
    LiveTradingRunResponse,
    LiveTradingStatusResponse,
    RiskConfigRequest,
    RiskStateResponse,
    StartLiveTradingRequest,
    StopLiveTradingRequest,
)


class TestRiskConfigRequest:
    """Tests for RiskConfigRequest schema."""

    def test_valid_config(self):
        """Test creating valid risk config."""
        config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        assert config.max_position_size == Decimal("0.5")
        assert config.max_order_size == Decimal("0.1")
        assert config.daily_trade_limit == 100
        assert config.daily_loss_limit == Decimal("0.05")
        assert config.price_deviation_limit == Decimal("0.02")
        assert config.circuit_breaker_threshold == 3

    def test_full_config(self):
        """Test creating config with all fields."""
        config = RiskConfigRequest(
            max_position_size=Decimal("0.8"),
            max_order_size=Decimal("0.2"),
            daily_trade_limit=500,
            daily_loss_limit=Decimal("0.1"),
            price_deviation_limit=Decimal("0.05"),
            circuit_breaker_threshold=5,
        )

        assert config.price_deviation_limit == Decimal("0.05")
        assert config.circuit_breaker_threshold == 5

    def test_max_position_size_range(self):
        """Test max_position_size must be between 0 and 1."""
        # Zero should fail (gt=0)
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0.05"),
            )

        # > 1 should fail
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("1.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0.05"),
            )

    def test_max_order_size_range(self):
        """Test max_order_size must be between 0 and 1."""
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0.05"),
            )

    def test_daily_trade_limit_range(self):
        """Test daily_trade_limit range (1-1000)."""
        # Zero should fail
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=0,
                daily_loss_limit=Decimal("0.05"),
            )

        # > 1000 should fail
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=1001,
                daily_loss_limit=Decimal("0.05"),
            )

    def test_daily_loss_limit_range(self):
        """Test daily_loss_limit must be between 0 and 1."""
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0"),
            )

    def test_circuit_breaker_threshold_range(self):
        """Test circuit_breaker_threshold range (1-10)."""
        # < 1 should fail
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0.05"),
                circuit_breaker_threshold=0,
            )

        # > 10 should fail
        with pytest.raises(ValidationError):
            RiskConfigRequest(
                max_position_size=Decimal("0.5"),
                max_order_size=Decimal("0.1"),
                daily_trade_limit=100,
                daily_loss_limit=Decimal("0.05"),
                circuit_breaker_threshold=11,
            )

    def test_boundary_values(self):
        """Test boundary values are accepted."""
        config = RiskConfigRequest(
            max_position_size=Decimal("1"),
            max_order_size=Decimal("1"),
            daily_trade_limit=1000,
            daily_loss_limit=Decimal("1"),
            price_deviation_limit=Decimal("1"),
            circuit_breaker_threshold=10,
        )

        assert config.max_position_size == Decimal("1")
        assert config.daily_trade_limit == 1000


class TestStartLiveTradingRequest:
    """Tests for StartLiveTradingRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        risk_config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        request = StartLiveTradingRequest(
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange_account_id=uuid4(),
            timeframe="1m",
            risk_config=risk_config,
        )

        assert request.symbol == "BTC/USDT"
        assert request.exchange_account_id is not None
        assert request.initial_equity is None
        assert request.params is None

    def test_full_request(self):
        """Test creating request with all fields."""
        risk_config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        request = StartLiveTradingRequest(
            strategy_id=uuid4(),
            symbol="ETH/USDT",
            exchange_account_id=uuid4(),
            timeframe="5m",
            risk_config=risk_config,
            initial_equity=Decimal("10000"),
            params={"fast_ma": 10, "slow_ma": 20},
        )

        assert request.initial_equity == Decimal("10000")
        assert request.params == {"fast_ma": 10, "slow_ma": 20}

    def test_symbol_validation(self):
        """Test symbol field validation."""
        risk_config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        with pytest.raises(ValidationError):
            StartLiveTradingRequest(
                strategy_id=uuid4(),
                symbol="",
                exchange_account_id=uuid4(),
                timeframe="1m",
                risk_config=risk_config,
            )

    def test_exchange_account_id_required(self):
        """Test exchange_account_id field is required."""
        risk_config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        with pytest.raises(ValidationError):
            StartLiveTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                # Missing exchange_account_id
                timeframe="1m",
                risk_config=risk_config,
            )

    def test_initial_equity_must_be_positive(self):
        """Test initial_equity must be positive if provided."""
        risk_config = RiskConfigRequest(
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        with pytest.raises(ValidationError):
            StartLiveTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange_account_id=uuid4(),
                timeframe="1m",
                risk_config=risk_config,
                initial_equity=Decimal("-100"),
            )


class TestLiveTradingRunResponse:
    """Tests for LiveTradingRunResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(UTC)
        response = LiveTradingRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="live",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1m",
            status="running",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            error_message=None,
            started_at=now,
            stopped_at=None,
            created_at=now,
            updated_at=now,
        )

        assert response.mode == "live"
        assert response.status == "running"

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert LiveTradingRunResponse.model_config.get("from_attributes") is True


class TestLivePositionInfo:
    """Tests for LivePositionInfo schema."""

    def test_long_position(self):
        """Test long position info."""
        position = LivePositionInfo(
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("50000"),
        )

        assert position.amount == Decimal("0.5")
        assert position.avg_entry_price == Decimal("50000")

    def test_short_position(self):
        """Test short position (negative amount)."""
        position = LivePositionInfo(
            amount=Decimal("-0.5"),
            avg_entry_price=Decimal("50000"),
        )

        assert position.amount == Decimal("-0.5")


class TestLiveOrderInfo:
    """Tests for LiveOrderInfo schema."""

    def test_pending_order(self):
        """Test pending order info."""
        now = datetime.now(UTC)
        order = LiveOrderInfo(
            internal_id="int-123",
            exchange_order_id="exc-456",
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            amount=Decimal("0.1"),
            filled_amount=Decimal("0"),
            price=Decimal("49000"),
            avg_fill_price=None,
            status="pending",
            created_at=now,
            updated_at=now,
        )

        assert order.internal_id == "int-123"
        assert order.exchange_order_id == "exc-456"
        assert order.filled_amount == Decimal("0")

    def test_partially_filled_order(self):
        """Test partially filled order."""
        order = LiveOrderInfo(
            internal_id="int-789",
            exchange_order_id="exc-012",
            symbol="BTC/USDT",
            side="sell",
            type="limit",
            amount=Decimal("1.0"),
            filled_amount=Decimal("0.5"),
            price=Decimal("51000"),
            avg_fill_price=Decimal("51005"),
            status="partially_filled",
            created_at=None,
            updated_at=None,
        )

        assert order.filled_amount == Decimal("0.5")
        assert order.avg_fill_price == Decimal("51005")


class TestRiskStateResponse:
    """Tests for RiskStateResponse schema."""

    def test_normal_state(self):
        """Test normal risk state."""
        state = RiskStateResponse(
            daily_pnl=Decimal("500"),
            daily_trade_count=25,
            consecutive_losses=0,
            circuit_breaker_active=False,
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        assert state.daily_pnl == Decimal("500")
        assert state.circuit_breaker_active is False

    def test_circuit_breaker_active(self):
        """Test risk state with circuit breaker active."""
        state = RiskStateResponse(
            daily_pnl=Decimal("-600"),
            daily_trade_count=50,
            consecutive_losses=3,
            circuit_breaker_active=True,
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        assert state.consecutive_losses == 3
        assert state.circuit_breaker_active is True


class TestLiveTradingStatusResponse:
    """Tests for LiveTradingStatusResponse schema."""

    def test_running_status(self):
        """Test running session status."""
        now = datetime.now(UTC)
        risk_state = RiskStateResponse(
            daily_pnl=Decimal("100"),
            daily_trade_count=10,
            consecutive_losses=0,
            circuit_breaker_active=False,
            max_position_size=Decimal("0.5"),
            max_order_size=Decimal("0.1"),
            daily_trade_limit=100,
            daily_loss_limit=Decimal("0.05"),
        )

        response = LiveTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=1000,
            cash=Decimal("5000"),
            equity=Decimal("10500"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("50"),
            positions={
                "BTC": LivePositionInfo(amount=Decimal("0.1"), avg_entry_price=Decimal("55000"))
            },
            pending_orders=[],
            live_orders=[],
            completed_orders_count=20,
            trades_count=15,
            risk_state=risk_state,
        )

        assert response.is_running is True
        assert "BTC" in response.positions
        assert response.risk_state is not None

    def test_status_without_risk_state(self):
        """Test status without risk state."""
        now = datetime.now(UTC)
        response = LiveTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=False,
            started_at=now,
            stopped_at=now,
            error_message=None,
            bar_count=100,
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0"),
            positions={},
            pending_orders=[],
            live_orders=[],
            completed_orders_count=0,
            trades_count=0,
            risk_state=None,
        )

        assert response.risk_state is None


class TestLiveTradingListItem:
    """Tests for LiveTradingListItem schema."""

    def test_list_item(self):
        """Test live trading list item."""
        now = datetime.now(UTC)
        item = LiveTradingListItem(
            run_id=uuid4(),
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            bar_count=500,
            equity=Decimal("10500"),
            cash=Decimal("5000"),
        )

        assert item.symbol == "BTC/USDT"
        assert item.is_running is True

    def test_not_started_item(self):
        """Test list item for session not yet started."""
        item = LiveTradingListItem(
            run_id=uuid4(),
            strategy_id=uuid4(),
            symbol="ETH/USDT",
            timeframe="5m",
            is_running=False,
            started_at=None,
            bar_count=0,
            equity=Decimal("10000"),
            cash=Decimal("10000"),
        )

        assert item.started_at is None
        assert item.bar_count == 0


class TestStopLiveTradingRequest:
    """Tests for StopLiveTradingRequest schema."""

    def test_default_cancel_orders(self):
        """Test default cancel_orders is True."""
        request = StopLiveTradingRequest()

        assert request.cancel_orders is True

    def test_cancel_orders_false(self):
        """Test cancel_orders set to False."""
        request = StopLiveTradingRequest(cancel_orders=False)

        assert request.cancel_orders is False


class TestEmergencyCloseResponse:
    """Tests for EmergencyCloseResponse schema."""

    def test_successful_close(self):
        """Test successful emergency close."""
        response = EmergencyCloseResponse(
            run_id=uuid4(),
            status="closed",
            message="All positions closed successfully",
            orders_cancelled=5,
            positions_closed=2,
        )

        assert response.status == "closed"
        assert response.orders_cancelled == 5
        assert response.positions_closed == 2

    def test_minimal_response(self):
        """Test minimal response."""
        response = EmergencyCloseResponse(
            run_id=uuid4(),
            status="no_positions",
        )

        assert response.status == "no_positions"
        assert response.message is None
        assert response.orders_cancelled is None
