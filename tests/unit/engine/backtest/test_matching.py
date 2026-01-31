"""Unit tests for backtest matching engine."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.matching import MatchingEngine
from squant.engine.backtest.types import (
    Bar,
    OrderSide,
    OrderType,
    SimulatedOrder,
)


@pytest.fixture
def engine() -> MatchingEngine:
    """Create a matching engine with default settings."""
    return MatchingEngine(
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
    )


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar for testing."""
    return Bar(
        time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        symbol="BTC/USDT",
        open=Decimal("42000"),
        high=Decimal("43000"),
        low=Decimal("41000"),
        close=Decimal("42500"),
        volume=Decimal("1000"),
    )


class TestMarketOrders:
    """Tests for market order matching."""

    def test_market_buy_fills_at_open(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that market buy fills at bar's open price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 1
        fill = fills[0]
        assert fill.price == Decimal("42000")  # Open price
        assert fill.amount == Decimal("1")
        assert fill.side == OrderSide.BUY

    def test_market_sell_fills_at_open(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that market sell fills at bar's open price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("0.5"),
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("42000")

    def test_market_order_commission(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that commission is calculated correctly."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(sample_bar, [order])

        # Commission = 42000 * 1 * 0.001 = 42
        assert fills[0].fee == Decimal("42")


class TestSlippage:
    """Tests for slippage handling."""

    def test_buy_slippage_increases_price(self, sample_bar: Bar) -> None:
        """Test that slippage increases buy price."""
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.001"),  # 0.1% slippage
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(sample_bar, [order])

        # Expected: 42000 * 1.001 = 42042
        assert fills[0].price == Decimal("42042")

    def test_sell_slippage_decreases_price(self, sample_bar: Bar) -> None:
        """Test that slippage decreases sell price."""
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.001"),  # 0.1% slippage
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(sample_bar, [order])

        # Expected: 42000 * 0.999 = 41958
        assert fills[0].price == Decimal("41958")


class TestLimitOrders:
    """Tests for limit order matching."""

    def test_buy_limit_fills_when_price_touches(
        self, engine: MatchingEngine, sample_bar: Bar
    ) -> None:
        """Test that buy limit fills when low reaches limit."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("41500"),  # Below open, within bar's range
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("41500")

    def test_buy_limit_no_fill_when_price_not_reached(
        self, engine: MatchingEngine, sample_bar: Bar
    ) -> None:
        """Test that buy limit doesn't fill if price doesn't reach limit."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("40000"),  # Below bar's low
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 0

    def test_sell_limit_fills_when_price_touches(
        self, engine: MatchingEngine, sample_bar: Bar
    ) -> None:
        """Test that sell limit fills when high reaches limit."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("42500"),  # Above open, within bar's range
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("42500")

    def test_sell_limit_no_fill_when_price_not_reached(
        self, engine: MatchingEngine, sample_bar: Bar
    ) -> None:
        """Test that sell limit doesn't fill if price doesn't reach limit."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("44000"),  # Above bar's high
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 0

    def test_buy_limit_better_fill_on_gap_down(self, engine: MatchingEngine) -> None:
        """Test that buy limit gets better price on gap down."""
        # Bar opens below limit price
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),  # Gap down below limit
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("41500"),  # Limit above open
        )

        fills = engine.process_bar(bar, [order])

        # Should fill at open (better than limit)
        assert len(fills) == 1
        assert fills[0].price == Decimal("40000")


class TestMultipleOrders:
    """Tests for multiple order processing."""

    def test_multiple_orders_processed(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that multiple orders are processed in one bar."""
        order1 = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )
        order2 = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("0.5"),
        )

        fills = engine.process_bar(sample_bar, [order1, order2])

        assert len(fills) == 2

    def test_different_symbol_order_not_filled(
        self, engine: MatchingEngine, sample_bar: Bar
    ) -> None:
        """Test that orders for different symbols are not filled."""
        order = SimulatedOrder.create(
            symbol="ETH/USDT",  # Different symbol
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 0


class TestOrderValidation:
    """Tests for order validation."""

    def test_validate_valid_order(self, engine: MatchingEngine) -> None:
        """Test validation of a valid order."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("42000"),
        )

        is_valid, error = engine.validate_order(order, Decimal("100000"))
        assert is_valid is True
        assert error == ""

    def test_validate_insufficient_cash(self, engine: MatchingEngine) -> None:
        """Test validation fails with insufficient cash for limit order."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("42000"),
        )

        is_valid, error = engine.validate_order(order, Decimal("1000"))  # Not enough
        assert is_valid is False
        assert "Insufficient cash" in error
