"""Unit tests for backtest engine types."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from squant.engine.backtest.types import (
    Bar,
    Fill,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    SimulatedOrder,
    TradeRecord,
)


class TestBar:
    """Tests for Bar dataclass."""

    def test_create_valid_bar(self) -> None:
        """Test creating a valid bar."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        assert bar.symbol == "BTC/USDT"
        assert bar.close == Decimal("42500")

    def test_bar_is_immutable(self) -> None:
        """Test that bar is immutable (frozen dataclass)."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        with pytest.raises(AttributeError):
            bar.close = Decimal("50000")

    def test_bar_validation_high_less_than_low(self) -> None:
        """Test that high cannot be less than low."""
        with pytest.raises(ValueError, match="High cannot be less than low"):
            Bar(
                time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("40000"),  # Invalid: less than low
                low=Decimal("41000"),
                close=Decimal("42500"),
                volume=Decimal("1000"),
            )

    def test_bar_validation_open_outside_range(self) -> None:
        """Test that open must be between low and high."""
        with pytest.raises(ValueError, match="Open must be between"):
            Bar(
                time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                symbol="BTC/USDT",
                open=Decimal("44000"),  # Invalid: greater than high
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal("42500"),
                volume=Decimal("1000"),
            )

    def test_bar_validation_close_outside_range(self) -> None:
        """Test that close must be between low and high."""
        with pytest.raises(ValueError, match="Close must be between"):
            Bar(
                time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal("40000"),  # Invalid: less than low
                volume=Decimal("1000"),
            )


class TestPosition:
    """Tests for Position dataclass."""

    def test_create_position(self) -> None:
        """Test creating a position."""
        pos = Position(
            symbol="BTC/USDT",
            amount=Decimal("1.5"),
            avg_entry_price=Decimal("42000"),
        )
        assert pos.symbol == "BTC/USDT"
        assert pos.amount == Decimal("1.5")
        assert pos.is_open is True

    def test_empty_position(self) -> None:
        """Test empty position."""
        pos = Position(symbol="BTC/USDT")
        assert pos.amount == Decimal("0")
        assert pos.is_open is False

    def test_position_update_buy(self) -> None:
        """Test position update on buy."""
        pos = Position(symbol="BTC/USDT")
        pos.update(Decimal("1"), Decimal("42000"), OrderSide.BUY)

        assert pos.amount == Decimal("1")
        assert pos.avg_entry_price == Decimal("42000")

    def test_position_update_buy_average_price(self) -> None:
        """Test position averaging on additional buy."""
        pos = Position(
            symbol="BTC/USDT",
            amount=Decimal("1"),
            avg_entry_price=Decimal("40000"),
        )
        pos.update(Decimal("1"), Decimal("44000"), OrderSide.BUY)

        assert pos.amount == Decimal("2")
        assert pos.avg_entry_price == Decimal("42000")  # (40000 + 44000) / 2

    def test_position_update_sell(self) -> None:
        """Test position update on sell (reduce)."""
        pos = Position(
            symbol="BTC/USDT",
            amount=Decimal("2"),
            avg_entry_price=Decimal("42000"),
        )
        pos.update(Decimal("1"), Decimal("43000"), OrderSide.SELL)

        assert pos.amount == Decimal("1")
        assert pos.avg_entry_price == Decimal("42000")  # Entry price unchanged

    def test_position_close(self) -> None:
        """Test position close."""
        pos = Position(
            symbol="BTC/USDT",
            amount=Decimal("1"),
            avg_entry_price=Decimal("42000"),
        )
        pos.update(Decimal("1"), Decimal("43000"), OrderSide.SELL)

        assert pos.amount == Decimal("0")
        assert pos.is_open is False


class TestSimulatedOrder:
    """Tests for SimulatedOrder dataclass."""

    def test_create_market_order(self) -> None:
        """Test creating a market order."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.price is None
        assert order.status == OrderStatus.PENDING

    def test_create_limit_order(self) -> None:
        """Test creating a limit order."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("50000"),
        )
        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("50000")

    def test_limit_order_requires_price(self) -> None:
        """Test that limit order requires a price."""
        with pytest.raises(ValueError, match="Limit orders require a price"):
            SimulatedOrder.create(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=Decimal("1"),
            )

    def test_order_remaining(self) -> None:
        """Test remaining amount calculation."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("10"),
        )
        order.filled = Decimal("3")
        assert order.remaining == Decimal("7")

    def test_order_is_complete(self) -> None:
        """Test order completion check."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )
        assert order.is_complete is False

        order.status = OrderStatus.FILLED
        assert order.is_complete is True

        order.status = OrderStatus.CANCELLED
        assert order.is_complete is True


class TestTradeRecord:
    """Tests for TradeRecord dataclass."""

    def test_open_trade(self) -> None:
        """Test open trade record."""
        trade = TradeRecord(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("42000"),
            amount=Decimal("1"),
        )
        assert trade.is_closed is False

    def test_closed_trade(self) -> None:
        """Test closed trade record."""
        trade = TradeRecord(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            entry_price=Decimal("42000"),
            exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            exit_price=Decimal("44000"),
            amount=Decimal("1"),
            pnl=Decimal("2000"),
        )
        assert trade.is_closed is True
        assert trade.pnl == Decimal("2000")
