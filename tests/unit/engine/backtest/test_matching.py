"""Unit tests for backtest matching engine."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.matching import MatchingEngine
from squant.engine.backtest.types import (
    Bar,
    OrderSide,
    OrderStatus,
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

    def test_slippage_clamped_to_bar_high(self) -> None:
        """Test that buy slippage is clamped to bar's high price."""
        # Create a bar with tight range
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("42010"),  # Very tight high
            low=Decimal("41990"),
            close=Decimal("42005"),
            volume=Decimal("1000"),
        )
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.01"),  # 1% slippage would exceed high
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(bar, [order])

        # Slippage would be 42000 * 1.01 = 42420, but clamped to high
        assert fills[0].price == Decimal("42010")

    def test_slippage_clamped_to_bar_low(self) -> None:
        """Test that sell slippage is clamped to bar's low price."""
        # Create a bar with tight range
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("42010"),
            low=Decimal("41990"),  # Very tight low
            close=Decimal("42005"),
            volume=Decimal("1000"),
        )
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.01"),  # 1% slippage would go below low
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(bar, [order])

        # Slippage would be 42000 * 0.99 = 41580, but clamped to low
        assert fills[0].price == Decimal("41990")


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

    def test_sell_limit_better_fill_on_gap_up(self, engine: MatchingEngine) -> None:
        """Test that sell limit gets better price on gap up."""
        # Bar opens above limit price
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("45000"),  # Gap up above limit
            high=Decimal("46000"),
            low=Decimal("44500"),
            close=Decimal("45500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("44000"),  # Limit below open
        )

        fills = engine.process_bar(bar, [order])

        # Should fill at open (better than limit)
        assert len(fills) == 1
        assert fills[0].price == Decimal("45000")


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


class TestFilledOrdersSkipped:
    """Tests for skipping already processed orders."""

    def test_filled_order_not_processed(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that filled orders are skipped."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )
        order.status = OrderStatus.FILLED

        fills = engine.process_bar(sample_bar, [order])

        assert len(fills) == 0

    def test_cancelled_order_not_processed(self, engine: MatchingEngine, sample_bar: Bar) -> None:
        """Test that cancelled orders are skipped."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )
        order.status = OrderStatus.CANCELLED

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

    def test_validate_zero_amount(self, engine: MatchingEngine) -> None:
        """Test validation fails for zero amount order."""
        order = SimulatedOrder(
            id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0"),
        )

        is_valid, error = engine.validate_order(order, Decimal("100000"))
        assert is_valid is False
        assert "positive" in error.lower()

    def test_validate_negative_amount(self, engine: MatchingEngine) -> None:
        """Test validation fails for negative amount order."""
        order = SimulatedOrder(
            id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("-1"),
        )

        is_valid, error = engine.validate_order(order, Decimal("100000"))
        assert is_valid is False
        assert "positive" in error.lower()

    def test_validate_sell_order_passes(self, engine: MatchingEngine) -> None:
        """Test that sell orders pass validation without cash check."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        is_valid, error = engine.validate_order(order, Decimal("0"))  # No cash
        assert is_valid is True
        assert error == ""


class TestLookAheadBiasPrevention:
    """Tests explicitly verifying no look-ahead bias in order execution."""

    def test_market_order_fills_at_open_not_close(self, engine: MatchingEngine) -> None:
        """Market orders must fill at open price, never at close (prevents look-ahead bias)."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("48000"),
            low=Decimal("41000"),
            close=Decimal("47000"),  # Significantly different from open
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("42000")  # Must be open
        assert fills[0].price != Decimal("47000")  # Must NOT be close

    def test_market_sell_fills_at_open_not_close(self, engine: MatchingEngine) -> None:
        """Market sell orders must also fill at open, not close."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("48000"),
            low=Decimal("41000"),
            close=Decimal("41500"),  # Large drop from open, within valid range
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=Decimal("1"),
        )

        fills = engine.process_bar(bar, [order])

        assert fills[0].price == Decimal("42000")  # Must be open, not close


class TestLimitOrderBoundaries:
    """Tests for exact boundary conditions in limit order matching."""

    def test_buy_limit_exact_low_match(self, engine: MatchingEngine) -> None:
        """Buy limit fills when bar.low exactly equals limit price."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("41000"),  # Exactly bar.low
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("41000")

    def test_sell_limit_exact_high_match(self, engine: MatchingEngine) -> None:
        """Sell limit fills when bar.high exactly equals limit price."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("43000"),  # Exactly bar.high
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 1
        assert fills[0].price == Decimal("43000")

    def test_buy_limit_one_tick_below_low_no_fill(self, engine: MatchingEngine) -> None:
        """Buy limit does NOT fill when price is just below bar.low."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("40999.99"),  # Just below bar.low
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 0

    def test_sell_limit_one_tick_above_high_no_fill(self, engine: MatchingEngine) -> None:
        """Sell limit does NOT fill when price is just above bar.high."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("43000.01"),  # Just above bar.high
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 0

    def test_buy_limit_at_open_price(self, engine: MatchingEngine) -> None:
        """Buy limit at open price gets filled at open."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("42000"),  # Exactly open
        )

        fills = engine.process_bar(bar, [order])

        assert len(fills) == 1
        # min(42000, 42000) = 42000
        assert fills[0].price == Decimal("42000")


class TestMultiBarLimitOrder:
    """Tests for limit orders that wait multiple bars before filling (BT-5)."""

    def test_buy_limit_fills_after_multiple_bars(self, engine: MatchingEngine) -> None:
        """Test buy limit order that waits 2 bars then fills on 3rd bar."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("40000"),  # Below all bars initially
        )

        # Bar 1: price range 42000-43000, limit at 40000 not triggered
        bar1 = Bar(
            time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42500"),
            high=Decimal("43000"),
            low=Decimal("42000"),
            close=Decimal("42800"),
            volume=Decimal("1000"),
        )
        fills1 = engine.process_bar(bar1, [order])
        assert len(fills1) == 0

        # Bar 2: price range 41500-42500, still above 40000
        bar2 = Bar(
            time=datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("42500"),
            low=Decimal("41500"),
            close=Decimal("41800"),
            volume=Decimal("1000"),
        )
        fills2 = engine.process_bar(bar2, [order])
        assert len(fills2) == 0

        # Bar 3: price drops to 39500, limit at 40000 is triggered
        bar3 = Bar(
            time=datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("41000"),
            high=Decimal("41500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
        )
        fills3 = engine.process_bar(bar3, [order])
        assert len(fills3) == 1
        assert fills3[0].price == Decimal("40000")
        assert fills3[0].side == OrderSide.BUY

    def test_sell_limit_fills_after_multiple_bars(self, engine: MatchingEngine) -> None:
        """Test sell limit order that waits 2 bars then fills on 3rd bar."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=Decimal("1"),
            price=Decimal("46000"),  # Above all bars initially
        )

        # Bar 1: price range 42000-43000, limit at 46000 not triggered
        bar1 = Bar(
            time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42500"),
            high=Decimal("43000"),
            low=Decimal("42000"),
            close=Decimal("42800"),
            volume=Decimal("1000"),
        )
        fills1 = engine.process_bar(bar1, [order])
        assert len(fills1) == 0

        # Bar 2: price range 43000-44500, still below 46000
        bar2 = Bar(
            time=datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("43000"),
            high=Decimal("44500"),
            low=Decimal("42800"),
            close=Decimal("44000"),
            volume=Decimal("1000"),
        )
        fills2 = engine.process_bar(bar2, [order])
        assert len(fills2) == 0

        # Bar 3: price rises to 46500, limit at 46000 is triggered
        bar3 = Bar(
            time=datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("44500"),
            high=Decimal("46500"),
            low=Decimal("44000"),
            close=Decimal("46000"),
            volume=Decimal("1000"),
        )
        fills3 = engine.process_bar(bar3, [order])
        assert len(fills3) == 1
        assert fills3[0].price == Decimal("46000")
        assert fills3[0].side == OrderSide.SELL


class TestStopOrders:
    """Tests for stop (market) order matching."""

    def test_buy_stop_triggers_when_high_reaches_stop_price(
        self, engine: MatchingEngine
    ) -> None:
        """Buy STOP triggers when bar.high >= stop_price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43500"),
            low=Decimal("41500"),
            close=Decimal("43000"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # Base price = max(stop_price, open) = max(43000, 42000) = 43000
        assert fills[0].price == Decimal("43000")
        assert fills[0].side == OrderSide.BUY

    def test_buy_stop_does_not_trigger_when_high_below_stop_price(
        self, engine: MatchingEngine
    ) -> None:
        """Buy STOP does not trigger when bar.high < stop_price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("45000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43000"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 0

    def test_sell_stop_triggers_when_low_reaches_stop_price(
        self, engine: MatchingEngine
    ) -> None:
        """Sell STOP triggers when bar.low <= stop_price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("41500"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("41500"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # Base price = min(stop_price, open) = min(41500, 42000) = 41500
        assert fills[0].price == Decimal("41500")
        assert fills[0].side == OrderSide.SELL

    def test_sell_stop_does_not_trigger_when_low_above_stop_price(
        self, engine: MatchingEngine
    ) -> None:
        """Sell STOP does not trigger when bar.low > stop_price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("40000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 0

    def test_buy_stop_gap_open_above_stop_price(self, engine: MatchingEngine) -> None:
        """When bar opens above stop_price (gap up), fill at open price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("44000"),  # Opens above stop_price
            high=Decimal("45000"),
            low=Decimal("43500"),
            close=Decimal("44500"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # Base price = max(43000, 44000) = 44000 (fill at open)
        assert fills[0].price == Decimal("44000")

    def test_sell_stop_gap_open_below_stop_price(self, engine: MatchingEngine) -> None:
        """When bar opens below stop_price (gap down), fill at open price."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("42000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("41000"),  # Opens below stop_price
            high=Decimal("41500"),
            low=Decimal("40500"),
            close=Decimal("41200"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # Base price = min(42000, 41000) = 41000 (fill at open)
        assert fills[0].price == Decimal("41000")

    def test_stop_order_with_slippage(self) -> None:
        """Stop order applies slippage after trigger."""
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.001"),  # 0.1% slippage
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43500"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # Base = 43000, slippage = 43000 * 1.001 = 43043
        expected = Decimal("43000") * (1 + Decimal("0.001"))
        assert fills[0].price == expected

    def test_stop_order_slippage_clamped_to_bar_range(self) -> None:
        """Stop order fill price is clamped to [bar.low, bar.high]."""
        engine = MatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.05"),  # 5% slippage (large)
        )
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43500"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        # 43000 * 1.05 = 45150, but clamped to high=44000
        assert fills[0].price == Decimal("44000")


class TestStopLimitOrders:
    """Tests for stop-limit order matching."""

    def test_stop_limit_triggers_and_fills_on_same_bar(
        self, engine: MatchingEngine
    ) -> None:
        """STOP_LIMIT triggers and limit is reachable → fills on same bar."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
            price=Decimal("43500"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43200"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        assert order.triggered is True
        # Limit buy: fill at min(limit_price, open) = min(43500, 42000) = 42000
        assert fills[0].price == Decimal("42000")

    def test_stop_limit_triggers_but_limit_not_reachable(
        self, engine: MatchingEngine
    ) -> None:
        """STOP_LIMIT triggers but limit is not reachable → no fill, triggered=True."""
        # Sell stop-limit: stop at 41500, limit at 41000
        # Bar low reaches 41500 (triggers) but not 41000 (limit not reachable for sell)
        # Actually for sell limit, need high >= limit. Let's use a buy scenario:
        # Buy stop-limit: stop at 43000 (high >= 43000 triggers), limit at 40000 (buy limit)
        # For buy limit to fill, low must reach limit price (40000), but low is 41000
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
            price=Decimal("40000"),  # limit below bar range
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43200"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 0
        assert order.triggered is True  # Trigger condition met

    def test_stop_limit_triggered_fills_on_next_bar(
        self, engine: MatchingEngine
    ) -> None:
        """After triggering, STOP_LIMIT fills as limit order on subsequent bar."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
            price=Decimal("40000"),
        )

        # Bar 1: triggers but limit not reachable
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43200"),
            volume=Decimal("1000"),
        )
        fills1 = engine.process_bar(bar1, [order])
        assert len(fills1) == 0
        assert order.triggered is True

        # Bar 2: price drops, limit price reachable
        bar2 = Bar(
            time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40500"),
            high=Decimal("41000"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
        )
        fills2 = engine.process_bar(bar2, [order])
        assert len(fills2) == 1
        # Buy limit: fill at min(limit_price=40000, open=40500) = 40000
        assert fills2[0].price == Decimal("40000")

    def test_stop_limit_does_not_trigger(self, engine: MatchingEngine) -> None:
        """STOP_LIMIT does not trigger when condition not met → no fill."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("45000"),
            price=Decimal("45500"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("44000"),
            low=Decimal("41000"),
            close=Decimal("43200"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 0
        assert order.triggered is False

    def test_sell_stop_limit_triggers_and_fills(self, engine: MatchingEngine) -> None:
        """Sell STOP_LIMIT triggers and fills correctly."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("41000"),
            price=Decimal("40500"),
        )
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("40000"),
            close=Decimal("40800"),
            volume=Decimal("1000"),
        )
        fills = engine.process_bar(bar, [order])
        assert len(fills) == 1
        assert order.triggered is True
        # Sell limit: fill at max(limit_price=40500, open=42000) = 42000
        assert fills[0].price == Decimal("42000")


class TestSimulatedOrderCreateValidation:
    """Tests for SimulatedOrder.create() validation with new order types."""

    def test_stop_order_requires_stop_price(self) -> None:
        """STOP order without stop_price raises ValueError."""
        with pytest.raises(ValueError, match="stop_price"):
            SimulatedOrder.create(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP,
                amount=Decimal("1"),
            )

    def test_stop_order_must_not_have_limit_price(self) -> None:
        """STOP order with price raises ValueError."""
        with pytest.raises(ValueError, match="limit price"):
            SimulatedOrder.create(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP,
                amount=Decimal("1"),
                stop_price=Decimal("43000"),
                price=Decimal("43500"),
            )

    def test_stop_limit_requires_stop_price(self) -> None:
        """STOP_LIMIT order without stop_price raises ValueError."""
        with pytest.raises(ValueError, match="stop_price"):
            SimulatedOrder.create(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP_LIMIT,
                amount=Decimal("1"),
                price=Decimal("43500"),
            )

    def test_stop_limit_requires_limit_price(self) -> None:
        """STOP_LIMIT order without price raises ValueError."""
        with pytest.raises(ValueError, match="limit price"):
            SimulatedOrder.create(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.STOP_LIMIT,
                amount=Decimal("1"),
                stop_price=Decimal("43000"),
            )

    def test_stop_order_creates_successfully(self) -> None:
        """Valid STOP order is created."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
        )
        assert order.type == OrderType.STOP
        assert order.stop_price == Decimal("43000")
        assert order.price is None
        assert order.triggered is False

    def test_stop_limit_order_creates_successfully(self) -> None:
        """Valid STOP_LIMIT order is created."""
        order = SimulatedOrder.create(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("1"),
            stop_price=Decimal("43000"),
            price=Decimal("43500"),
        )
        assert order.type == OrderType.STOP_LIMIT
        assert order.stop_price == Decimal("43000")
        assert order.price == Decimal("43500")
        assert order.triggered is False
