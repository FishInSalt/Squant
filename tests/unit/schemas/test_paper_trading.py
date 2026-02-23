"""Unit tests for paper trading schemas."""

from __future__ import annotations

from datetime import UTC, datetime
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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

    def test_current_price_default_none(self):
        """Test current_price defaults to None (PP-003)."""
        position = PositionInfo(
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("50000"),
        )
        assert position.current_price is None

    def test_unrealized_pnl_default_none(self):
        """Test unrealized_pnl defaults to None (PP-003)."""
        position = PositionInfo(
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("50000"),
        )
        assert position.unrealized_pnl is None

    def test_with_price_and_pnl(self):
        """Test position with current_price and unrealized_pnl (PP-003)."""
        position = PositionInfo(
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
            unrealized_pnl=Decimal("1000"),
        )
        assert position.current_price == Decimal("52000")
        assert position.unrealized_pnl == Decimal("1000")


class TestPendingOrderInfo:
    """Tests for PendingOrderInfo schema."""

    def test_limit_order(self):
        """Test pending limit order."""
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
            positions={
                "BTC": PositionInfo(amount=Decimal("0.1"), avg_entry_price=Decimal("55000"))
            },
            pending_orders=[],
            completed_orders_count=20,
            trades_count=15,
        )

        assert response.is_running is True
        assert response.equity == Decimal("10500")
        assert "BTC" in response.positions

    def test_stopped_status(self):
        """Test stopped session status."""
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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

    def test_unrealized_pnl_default_zero(self):
        """Test unrealized_pnl defaults to 0 (PP-002)."""
        now = datetime.now(UTC)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=0,
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0"),
            positions={},
            pending_orders=[],
            completed_orders_count=0,
            trades_count=0,
        )
        assert response.unrealized_pnl == Decimal("0")
        assert response.realized_pnl == Decimal("0")

    def test_pnl_fields_set(self):
        """Test unrealized_pnl and realized_pnl can be set (PP-002)."""
        now = datetime.now(UTC)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=100,
            cash=Decimal("5000"),
            equity=Decimal("10500"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("25"),
            unrealized_pnl=Decimal("300"),
            realized_pnl=Decimal("525"),
            positions={},
            pending_orders=[],
            completed_orders_count=10,
            trades_count=8,
        )
        assert response.unrealized_pnl == Decimal("300")
        assert response.realized_pnl == Decimal("525")

    def test_pnl_json_serializes_as_float(self):
        """Test PNL fields serialize as float in JSON (PP-002)."""
        now = datetime.now(UTC)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=0,
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0"),
            unrealized_pnl=Decimal("123.45"),
            realized_pnl=Decimal("456.78"),
            positions={},
            pending_orders=[],
            completed_orders_count=0,
            trades_count=0,
        )
        data = response.model_dump(mode="json")
        assert isinstance(data["unrealized_pnl"], float)
        assert isinstance(data["realized_pnl"], float)
        assert data["unrealized_pnl"] == 123.45
        assert data["realized_pnl"] == 456.78


    def test_status_response_with_trades_and_logs(self):
        """Test status response with trades and logs fields."""
        from squant.schemas.backtest import TradeRecordResponse

        now = datetime.now(UTC)
        trades = [
            TradeRecordResponse(
                symbol="BTC/USDT",
                side="buy",
                entry_time=now,
                entry_price=Decimal("50000"),
                exit_time=now,
                exit_price=Decimal("51000"),
                amount=Decimal("0.1"),
                pnl=Decimal("100"),
                pnl_pct=Decimal("2.0"),
                fees=Decimal("0.1"),
            )
        ]
        logs = ["[2024-01-01 12:00:00] Buy signal triggered", "[2024-01-01 12:01:00] Order filled"]

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
            equity=Decimal("10100"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0.1"),
            positions={},
            pending_orders=[],
            completed_orders_count=1,
            trades_count=1,
            trades=trades,
            logs=logs,
        )

        assert len(response.trades) == 1
        assert response.trades[0].symbol == "BTC/USDT"
        assert response.trades[0].pnl == Decimal("100")
        assert len(response.logs) == 2
        assert "Buy signal" in response.logs[0]

    def test_status_response_trades_and_logs_default_empty(self):
        """Test trades and logs default to empty lists when not provided."""
        now = datetime.now(UTC)
        response = PaperTradingStatusResponse(
            run_id=uuid4(),
            symbol="BTC/USDT",
            timeframe="1m",
            is_running=True,
            started_at=now,
            stopped_at=None,
            error_message=None,
            bar_count=0,
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            initial_capital=Decimal("10000"),
            total_fees=Decimal("0"),
            positions={},
            pending_orders=[],
            completed_orders_count=0,
            trades_count=0,
        )

        assert response.trades == []
        assert response.logs == []


class TestPaperTradingListItem:
    """Tests for PaperTradingListItem schema."""

    def test_list_item(self):
        """Test paper trading list item."""
        now = datetime.now(UTC)
        item = PaperTradingListItem(
            id=uuid4(),
            strategy_id=uuid4(),
            symbol="BTC/USDT",
            exchange="okx",
            timeframe="1m",
            status="running",
            is_running=True,
            initial_capital=Decimal("10000"),
            started_at=now,
            created_at=now,
            bar_count=500,
            equity=Decimal("10500"),
            cash=Decimal("5000"),
        )

        assert item.symbol == "BTC/USDT"
        assert item.is_running is True
        assert item.equity == Decimal("10500")
        assert item.initial_capital == Decimal("10000")
        assert item.exchange == "okx"
        assert item.status == "running"

    def test_not_started_item(self):
        """Test list item for session not yet started."""
        now = datetime.now(UTC)
        item = PaperTradingListItem(
            id=uuid4(),
            strategy_id=uuid4(),
            symbol="ETH/USDT",
            exchange="binance",
            timeframe="5m",
            status="pending",
            is_running=False,
            initial_capital=Decimal("10000"),
            started_at=None,
            created_at=now,
            bar_count=0,
            equity=Decimal("10000"),
            cash=Decimal("10000"),
        )

        assert item.started_at is None
        assert item.bar_count == 0
