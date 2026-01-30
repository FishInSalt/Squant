"""Unit tests for paper trading schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.schemas.paper_trading import (
    PaperTradingListItem,
    PaperTradingRunResponse,
    PaperTradingStatusResponse,
    PendingOrderInfo,
    PositionInfo,
    StartPaperTradingRequest,
)


class TestStartPaperTradingRequest:
    """Tests for StartPaperTradingRequest schema."""

    def test_valid_minimal_request(self):
        """Test creating request with required fields."""
        request = StartPaperTradingRequest(
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )

        assert request.symbol == "BTC/USDT"
        assert request.exchange == "okx"
        assert request.timeframe == "1m"
        assert request.initial_capital == Decimal("10000")
        assert request.commission_rate == Decimal("0.001")
        assert request.slippage == Decimal("0")

    def test_full_request(self):
        """Test creating request with all fields."""
        request = StartPaperTradingRequest(
            strategy_id=uuid4(),
            symbol="ETH/USDT",
            exchange="binance",
            timeframe="5m",
            initial_capital=Decimal("50000"),
            commission_rate=Decimal("0.0005"),
            slippage=Decimal("0.001"),
            params={"fast_ma": 10, "slow_ma": 20},
        )

        assert request.commission_rate == Decimal("0.0005")
        assert request.slippage == Decimal("0.001")
        assert request.params == {"fast_ma": 10, "slow_ma": 20}

    def test_initial_capital_must_be_positive(self):
        """Test initial capital must be greater than 0."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1m",
                initial_capital=Decimal("0"),
            )

    def test_initial_capital_negative(self):
        """Test negative initial capital fails."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1m",
                initial_capital=Decimal("-100"),
            )

    def test_commission_rate_range(self):
        """Test commission rate must be between 0 and 1."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1m",
                initial_capital=Decimal("10000"),
                commission_rate=Decimal("1.5"),
            )

    def test_slippage_range(self):
        """Test slippage must be between 0 and 1."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="1m",
                initial_capital=Decimal("10000"),
                slippage=Decimal("-0.01"),
            )

    def test_symbol_validation(self):
        """Test symbol field validation."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="",
                exchange="okx",
                timeframe="1m",
                initial_capital=Decimal("10000"),
            )

    def test_exchange_validation(self):
        """Test exchange field validation."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="",
                timeframe="1m",
                initial_capital=Decimal("10000"),
            )

    def test_timeframe_validation(self):
        """Test timeframe field validation."""
        with pytest.raises(ValidationError):
            StartPaperTradingRequest(
                strategy_id=uuid4(),
                symbol="BTC/USDT",
                exchange="okx",
                timeframe="",
                initial_capital=Decimal("10000"),
            )


class TestPaperTradingRunResponse:
    """Tests for PaperTradingRunResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(timezone.utc)
        response = PaperTradingRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="paper",
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

        assert response.mode == "paper"
        assert response.status == "running"

    def test_error_response(self):
        """Test response with error."""
        now = datetime.now(timezone.utc)
        response = PaperTradingRunResponse(
            id=uuid4(),
            strategy_id=uuid4(),
            mode="paper",
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1m",
            status="error",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            error_message="Strategy execution failed",
            started_at=now,
            stopped_at=now,
            created_at=now,
            updated_at=now,
        )

        assert response.status == "error"
        assert response.error_message is not None

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert PaperTradingRunResponse.model_config.get("from_attributes") is True


class TestPositionInfo:
    """Tests for PositionInfo schema."""

    def test_long_position(self):
        """Test long position info."""
        position = PositionInfo(
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("50000"),
        )

        assert position.amount == Decimal("0.5")
        assert position.avg_entry_price == Decimal("50000")

    def test_short_position(self):
        """Test short position (negative amount)."""
        position = PositionInfo(
            amount=Decimal("-0.5"),
            avg_entry_price=Decimal("50000"),
        )

        assert position.amount == Decimal("-0.5")

    def test_zero_position(self):
        """Test zero position."""
        position = PositionInfo(
            amount=Decimal("0"),
            avg_entry_price=Decimal("0"),
        )

        assert position.amount == Decimal("0")


class TestPendingOrderInfo:
    """Tests for PendingOrderInfo schema."""

    def test_limit_order(self):
        """Test pending limit order."""
        now = datetime.now(timezone.utc)
        order = PendingOrderInfo(
            id="order-123",
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            amount=Decimal("0.1"),
            price=Decimal("49000"),
            status="pending",
            created_at=now,
        )

        assert order.id == "order-123"
        assert order.type == "limit"
        assert order.price == Decimal("49000")

    def test_market_order(self):
        """Test pending market order."""
        order = PendingOrderInfo(
            id="order-456",
            symbol="BTC/USDT",
            side="sell",
            type="market",
            amount=Decimal("0.1"),
            price=None,
            status="submitted",
            created_at=None,
        )

        assert order.type == "market"
        assert order.price is None


class TestPaperTradingStatusResponse:
    """Tests for PaperTradingStatusResponse schema."""

    def test_running_status(self):
        """Test running session status."""
        now = datetime.now(timezone.utc)
        response = PaperTradingStatusResponse(
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
            positions={"BTC": PositionInfo(amount=Decimal("0.1"), avg_entry_price=Decimal("55000"))},
            pending_orders=[],
            completed_orders_count=20,
            trades_count=15,
        )

        assert response.is_running is True
        assert response.equity == Decimal("10500")
        assert "BTC" in response.positions

    def test_stopped_status(self):
        """Test stopped session status."""
        now = datetime.now(timezone.utc)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="ETH/USDT",
            timeframe="5m",
            is_running=False,
            started_at=now,
            stopped_at=now,
            error_message=None,
            bar_count=500,
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0"),
            positions={},
            pending_orders=[],
            completed_orders_count=0,
            trades_count=0,
        )

        assert response.is_running is False
        assert response.positions == {}

    def test_with_pending_orders(self):
        """Test status with pending orders."""
        now = datetime.now(timezone.utc)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=100,
            cash=Decimal("9000"),
            equity=Decimal("10200"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("10"),
            positions={},
            pending_orders=[
                PendingOrderInfo(
                    id="o1",
                    symbol="BTC/USDT",
                    side="buy",
                    type="limit",
                    amount=Decimal("0.1"),
                    price=Decimal("48000"),
                    status="pending",
                    created_at=now,
                )
            ],
            completed_orders_count=5,
            trades_count=3,
        )

        assert len(response.pending_orders) == 1


class TestPaperTradingListItem:
    """Tests for PaperTradingListItem schema."""

    def test_list_item(self):
        """Test paper trading list item."""
        now = datetime.now(timezone.utc)
        item = PaperTradingListItem(
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
        assert item.equity == Decimal("10500")

    def test_not_started_item(self):
        """Test list item for session not yet started."""
        item = PaperTradingListItem(
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
