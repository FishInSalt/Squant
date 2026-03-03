"""Unit tests for backtest context."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.types import (
    Bar,
    Fill,
    OrderSide,
    OrderType,
)


@pytest.fixture
def context() -> BacktestContext:
    """Create a backtest context with default settings."""
    return BacktestContext(
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
        params={"fast": 5, "slow": 20},
    )


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar."""
    return Bar(
        time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        symbol="BTC/USDT",
        open=Decimal("42000"),
        high=Decimal("43000"),
        low=Decimal("41000"),
        close=Decimal("42500"),
        volume=Decimal("1000"),
    )


class TestContextInitialization:
    """Tests for context initialization."""

    def test_initial_cash(self, context: BacktestContext) -> None:
        """Test that initial cash is set correctly."""
        assert context.cash == Decimal("100000")

    def test_initial_equity(self, context: BacktestContext) -> None:
        """Test that initial equity equals initial capital."""
        assert context.equity == Decimal("100000")

    def test_params_accessible(self, context: BacktestContext) -> None:
        """Test that params are accessible."""
        assert context.params["fast"] == 5
        assert context.params["slow"] == 20

    def test_no_positions_initially(self, context: BacktestContext) -> None:
        """Test that there are no positions initially."""
        assert len(context.positions) == 0

    def test_no_pending_orders_initially(self, context: BacktestContext) -> None:
        """Test that there are no pending orders initially."""
        assert len(context.pending_orders) == 0


class TestOrderPlacement:
    """Tests for order placement."""

    def test_buy_order_creates_pending_order(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that buy creates a pending order."""
        context._set_current_bar(sample_bar)

        order_id = context.buy("BTC/USDT", Decimal("1"))

        assert len(context.pending_orders) == 1
        order = context.pending_orders[0]
        assert order.id == order_id
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.amount == Decimal("1")

    def test_sell_order_creates_pending_order(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that sell creates a pending order when position exists."""
        context._set_current_bar(sample_bar)

        # First establish a position (spot trading requires owning before selling)
        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position("BTC/USDT", Decimal("1"), Decimal("40000"))

        order_id = context.sell("BTC/USDT", Decimal("0.5"))

        assert len(context.pending_orders) == 1
        order = context.pending_orders[0]
        assert order.id == order_id
        assert order.side == OrderSide.SELL
        assert order.amount == Decimal("0.5")

    def test_sell_without_position_raises(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that sell without position raises error (spot trading - no short selling)."""
        context._set_current_bar(sample_bar)

        with pytest.raises(ValueError, match="Insufficient position"):
            context.sell("BTC/USDT", Decimal("0.5"))

    def test_sell_more_than_position_raises(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that selling more than position raises error (spot trading - no short selling)."""
        context._set_current_bar(sample_bar)

        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position("BTC/USDT", Decimal("1"), Decimal("40000"))

        with pytest.raises(ValueError, match="Insufficient position"):
            context.sell("BTC/USDT", Decimal("1.5"))

    def test_sell_considers_pending_orders(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that sell considers pending sell orders when validating position."""
        context._set_current_bar(sample_bar)

        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position("BTC/USDT", Decimal("1"), Decimal("40000"))

        # First sell order for 0.7
        context.sell("BTC/USDT", Decimal("0.7"))

        # Second sell order should fail because only 0.3 available
        with pytest.raises(ValueError, match="Insufficient position"):
            context.sell("BTC/USDT", Decimal("0.5"))

    def test_limit_buy_order(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test limit buy order placement."""
        context._set_current_bar(sample_bar)

        context.buy("BTC/USDT", Decimal("1"), price=Decimal("41000"))

        order = context.pending_orders[0]
        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("41000")

    def test_negative_amount_raises(self, context: BacktestContext) -> None:
        """Test that negative amount raises error."""
        with pytest.raises(ValueError, match="Amount must be positive"):
            context.buy("BTC/USDT", Decimal("-1"))

    def test_zero_amount_raises(self, context: BacktestContext) -> None:
        """Test that zero amount raises error."""
        with pytest.raises(ValueError, match="Amount must be positive"):
            context.sell("BTC/USDT", Decimal("0"))


class TestOrderCancellation:
    """Tests for order cancellation."""

    def test_cancel_pending_order(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test cancelling a pending order."""
        context._set_current_bar(sample_bar)
        order_id = context.buy("BTC/USDT", Decimal("1"))

        result = context.cancel_order(order_id)

        assert result is True
        assert len(context.pending_orders) == 0
        assert len(context.completed_orders) == 1

    def test_cancel_nonexistent_order(self, context: BacktestContext) -> None:
        """Test cancelling non-existent order returns False."""
        result = context.cancel_order("nonexistent-id")
        assert result is False


class TestFillProcessing:
    """Tests for fill processing."""

    def test_buy_fill_updates_cash(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that buy fill decreases cash."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)
        order_id = context.buy("BTC/USDT", Decimal("1"))

        fill = Fill(
            order_id=order_id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill)

        # Cash should decrease by cost + fee
        # 100000 - (42000 * 1 + 42) = 100000 - 42042 = 57958
        expected_cash = Decimal("100000") - Decimal("42000") - Decimal("42")
        assert context.cash == expected_cash

    def test_sell_fill_updates_cash(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that sell fill increases cash."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # First buy to have a position
        context._positions["BTC/USDT"] = context._positions.get("BTC/USDT", None)
        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position("BTC/USDT", Decimal("1"), Decimal("40000"))

        fill = Fill(
            order_id="test-order",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill)

        # Cash should increase by proceeds - fee
        # 100000 + (42000 * 1 - 42) = 100000 + 41958 = 141958
        assert context.cash == Decimal("141958")

    def test_buy_fill_creates_position(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that buy fill creates/updates position."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)
        order_id = context.buy("BTC/USDT", Decimal("1"))

        fill = Fill(
            order_id=order_id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill)

        pos = context.get_position("BTC/USDT")
        assert pos is not None
        assert pos.amount == Decimal("1")
        assert pos.avg_entry_price == Decimal("42000")

    def test_buy_fill_insufficient_cash_raises(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that buy fill with insufficient cash raises error."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Try to fill an order that costs more than available cash
        fill = Fill(
            order_id="test-order",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("100000"),  # Price that exceeds cash
            amount=Decimal("2"),  # 200,000 total cost > 100,000 cash
            fee=Decimal("200"),
            timestamp=sample_bar.time,
        )

        with pytest.raises(ValueError, match="Insufficient cash"):
            context._process_fill(fill)

    def test_sell_fill_insufficient_position_raises(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that sell fill with insufficient position raises error (spot - no short)."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Create a small position
        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position("BTC/USDT", Decimal("0.5"), Decimal("40000"))

        # Try to fill a sell order for more than position
        fill = Fill(
            order_id="test-order",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("42000"),
            amount=Decimal("1"),  # More than 0.5 position
            fee=Decimal("42"),
            timestamp=sample_bar.time,
        )

        with pytest.raises(ValueError, match="Insufficient position"):
            context._process_fill(fill)


class TestMarketDataAccess:
    """Tests for market data access."""

    def test_get_closes(self, context: BacktestContext) -> None:
        """Test getting close prices."""
        bars = [
            Bar(
                time=datetime(2024, 1, 1, i, tzinfo=UTC),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal(str(42000 + i * 100)),
                volume=Decimal("1000"),
            )
            for i in range(5)
        ]
        for bar in bars:
            context._add_bar_to_history(bar)

        closes = context.get_closes(3)

        assert len(closes) == 3
        assert closes[-1] == Decimal("42400")  # Last bar close

    def test_get_bars(self, context: BacktestContext) -> None:
        """Test getting bar objects."""
        bars = [
            Bar(
                time=datetime(2024, 1, 1, i, tzinfo=UTC),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal("42500"),
                volume=Decimal("1000"),
            )
            for i in range(5)
        ]
        for bar in bars:
            context._add_bar_to_history(bar)

        retrieved = context.get_bars(2)

        assert len(retrieved) == 2
        assert retrieved[0].time < retrieved[1].time  # Oldest first

    def test_get_closes_fewer_bars_than_requested(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test getting closes when fewer bars available than requested."""
        context._add_bar_to_history(sample_bar)

        closes = context.get_closes(10)  # Request 10, only 1 available

        assert len(closes) == 1


class TestLogging:
    """Tests for logging functionality."""

    def test_log_message(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test logging a message."""
        context._set_current_bar(sample_bar)

        context.log("Test message")

        assert len(context.logs) == 1
        assert "Test message" in context.logs[0]

    def test_log_includes_timestamp(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test that log includes timestamp."""
        context._set_current_bar(sample_bar)

        context.log("Test message")

        assert "2024-01-01" in context.logs[0]


class TestEquitySnapshot:
    """Tests for equity snapshot recording."""

    def test_record_equity_snapshot(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test recording equity snapshot."""
        context._set_current_bar(sample_bar)

        context._record_equity_snapshot(sample_bar.time)

        assert len(context.equity_curve) == 1
        snapshot = context.equity_curve[0]
        assert snapshot.equity == context.equity
        assert snapshot.time == sample_bar.time


class TestInsufficientBalance:
    """Tests for insufficient balance scenarios (TRD-025#3)."""

    @pytest.fixture
    def low_cash_context(self) -> BacktestContext:
        """Create a backtest context with low cash balance."""
        return BacktestContext(
            initial_capital=Decimal("100"),  # Only $100
            commission_rate=Decimal("0.001"),  # 0.1% commission
            slippage=Decimal("0"),
        )

    @pytest.fixture
    def low_cash_bar(self) -> Bar:
        """Create a bar with price suitable for low cash tests."""
        return Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )

    def test_buy_exceeds_balance_rejected(
        self, low_cash_context: BacktestContext, low_cash_bar: Bar
    ) -> None:
        """Test buy order exceeding balance is rejected."""
        low_cash_context._set_current_bar(low_cash_bar)

        # Try to buy 0.01 BTC at $50000 = $500 + commission > $100 balance
        with pytest.raises(ValueError) as exc_info:
            low_cash_context.buy("BTC/USDT", Decimal("0.01"))

        assert "Insufficient cash" in str(exc_info.value)
        assert "100" in str(exc_info.value)  # Shows available cash

    def test_exact_balance_with_commission_rejected(
        self, low_cash_context: BacktestContext, low_cash_bar: Bar
    ) -> None:
        """Test order affordable but not with commission is rejected."""
        # Set up context with exactly $100 and bar at $100
        low_cash_context._cash = Decimal("100")
        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="TEST/USDT",
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),  # $100 price
            volume=Decimal("10"),
        )
        low_cash_context._set_current_bar(bar)

        # Buy 1 unit at $100 = $100, but with 0.1% commission = $100.10 > $100
        with pytest.raises(ValueError) as exc_info:
            low_cash_context.buy("TEST/USDT", Decimal("1.0"))

        assert "Insufficient cash" in str(exc_info.value)

    def test_exact_balance_including_commission_passes(self) -> None:
        """Test order passes when balance covers cost + commission."""
        # Set up context with enough for cost + commission
        context = BacktestContext(
            initial_capital=Decimal("100.10"),  # Exactly enough for $100 + 0.1% fee
            commission_rate=Decimal("0.001"),
        )

        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="TEST/USDT",
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("10"),
        )
        context._set_current_bar(bar)

        # Should not raise - exactly enough for $100 * 1.001 = $100.10
        order_id = context.buy("TEST/USDT", Decimal("1.0"))

        assert order_id is not None
        assert len(context.pending_orders) == 1

    def test_zero_balance_rejected(
        self, low_cash_context: BacktestContext, low_cash_bar: Bar
    ) -> None:
        """Test buy with zero balance is rejected."""
        low_cash_context._cash = Decimal("0")
        low_cash_context._set_current_bar(low_cash_bar)

        with pytest.raises(ValueError) as exc_info:
            low_cash_context.buy("BTC/USDT", Decimal("0.001"))

        assert "Insufficient cash" in str(exc_info.value)

    def test_error_message_contains_useful_info(
        self, low_cash_context: BacktestContext, low_cash_bar: Bar
    ) -> None:
        """Test error message contains available and required amounts."""
        low_cash_context._set_current_bar(low_cash_bar)

        with pytest.raises(ValueError) as exc_info:
            low_cash_context.buy("BTC/USDT", Decimal("0.01"))

        error_msg = str(exc_info.value)
        # Should contain available cash
        assert "available=" in error_msg
        # Should contain estimated cost
        assert "estimated_cost=" in error_msg

    def test_limit_order_uses_limit_price_for_validation(self) -> None:
        """Test that limit order uses limit price for balance validation."""
        context = BacktestContext(
            initial_capital=Decimal("500"),
            commission_rate=Decimal("0.001"),
        )

        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("50000"),
            low=Decimal("50000"),
            close=Decimal("50000"),
            volume=Decimal("10"),
        )
        context._set_current_bar(bar)

        # Market order at $50000 * 0.01 = $500 + fee would fail
        # But limit order at $40000 * 0.01 = $400 + fee should pass
        order_id = context.buy("BTC/USDT", Decimal("0.01"), price=Decimal("40000"))

        assert order_id is not None
        assert len(context.pending_orders) == 1
        assert context.pending_orders[0].price == Decimal("40000")

    def test_multiple_orders_reserve_cash(self) -> None:
        """Test that pending buy orders reserve cash, preventing over-allocation.

        With $600 capital, a $500.50 buy (5 units @ 100 + 0.1% fee) leaves only
        ~$99.50 available. A second buy of $200.20 should be rejected.
        """
        context = BacktestContext(
            initial_capital=Decimal("600"),
            commission_rate=Decimal("0.001"),
        )

        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="TEST/USDT",
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("10"),
        )
        context._set_current_bar(bar)

        # First order: 5 * 100 * 1.001 = $500.50 → accepted
        order1 = context.buy("TEST/USDT", Decimal("5"), price=Decimal("100"))
        assert order1 is not None
        assert len(context.pending_orders) == 1

        # Second order: 2 * 100 * 1.001 = $200.20 → rejected (only ~$99.50 available)
        with pytest.raises(ValueError, match="Insufficient cash"):
            context.buy("TEST/USDT", Decimal("2"), price=Decimal("100"))

        # Only one order should exist
        assert len(context.pending_orders) == 1

    def test_multiple_small_orders_within_budget(self) -> None:
        """Test that multiple buy orders within total budget are all accepted."""
        context = BacktestContext(
            initial_capital=Decimal("1000"),
            commission_rate=Decimal("0.001"),
        )

        bar = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="TEST/USDT",
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("10"),
        )
        context._set_current_bar(bar)

        # Order 1: 3 * 100 * 1.001 = $300.30
        context.buy("TEST/USDT", Decimal("3"), price=Decimal("100"))
        # Order 2: 3 * 100 * 1.001 = $300.30 (total $600.60, still within $1000)
        context.buy("TEST/USDT", Decimal("3"), price=Decimal("100"))
        # Order 3: 3 * 100 * 1.001 = $300.30 (total $900.90, still within $1000)
        context.buy("TEST/USDT", Decimal("3"), price=Decimal("100"))

        assert len(context.pending_orders) == 3

        # Order 4: would bring total to $1201.20 → rejected
        with pytest.raises(ValueError, match="Insufficient cash"):
            context.buy("TEST/USDT", Decimal("3"), price=Decimal("100"))


class TestTradeTracking:
    """Tests for trade tracking (TradeRecord) with position averaging and PnL."""

    def test_single_buy_sell_trade_pnl(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test PnL calculation for a simple buy-then-sell trade."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC at $42000
        order_id = context.buy("BTC/USDT", Decimal("1"))
        fill_buy = Fill(
            order_id=order_id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill_buy)
        context._move_completed_orders()

        assert context._open_trade is not None
        assert context._open_trade.entry_price == Decimal("42000")
        assert context._open_trade.amount == Decimal("1")

        # Sell 1 BTC at $43000
        sell_bar = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("43000"),
            high=Decimal("44000"),
            low=Decimal("42500"),
            close=Decimal("43000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(sell_bar)
        context._add_bar_to_history(sell_bar)

        sell_id = context.sell("BTC/USDT", Decimal("1"))
        fill_sell = Fill(
            order_id=sell_id,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("43000"),
            amount=Decimal("1"),
            fee=Decimal("43"),
            timestamp=sell_bar.time,
        )
        context._process_fill(fill_sell)

        # Trade should be closed
        assert context._open_trade is None
        assert len(context.trades) == 1
        trade = context.trades[0]
        assert trade.entry_price == Decimal("42000")
        assert trade.exit_price == Decimal("43000")
        # PnL = (43000 - 42000) * 1 - (42 + 43) = 1000 - 85 = 915
        assert trade.pnl == Decimal("915")

    def test_averaging_into_position_updates_entry_price(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that adding to a position calculates weighted average entry price."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC at $40000
        order1 = context.buy("BTC/USDT", Decimal("1"))
        fill1 = Fill(
            order_id=order1,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            amount=Decimal("1"),
            fee=Decimal("40"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill1)
        context._move_completed_orders()

        assert context._open_trade is not None
        assert context._open_trade.entry_price == Decimal("40000")
        assert context._open_trade.amount == Decimal("1")

        # Buy 1 more BTC at $44000 (averaging in)
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("44000"),
            high=Decimal("45000"),
            low=Decimal("43000"),
            close=Decimal("44000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)

        order2 = context.buy("BTC/USDT", Decimal("1"))
        fill2 = Fill(
            order_id=order2,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("44000"),
            amount=Decimal("1"),
            fee=Decimal("44"),
            timestamp=bar2.time,
        )
        context._process_fill(fill2)

        # Entry price should be weighted average: (40000*1 + 44000*1) / 2 = 42000
        assert context._open_trade.entry_price == Decimal("42000")
        assert context._open_trade.amount == Decimal("2")
        assert context._open_trade.fees == Decimal("84")  # 40 + 44

    def test_averaging_into_position_then_close_pnl(self, context: BacktestContext) -> None:
        """Test PnL after averaging into position then closing."""
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)

        # Buy 1 BTC at $40000
        order1 = context.buy("BTC/USDT", Decimal("1"))
        fill1 = Fill(
            order_id=order1,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            amount=Decimal("1"),
            fee=Decimal("40"),
            timestamp=bar1.time,
        )
        context._process_fill(fill1)
        context._move_completed_orders()

        # Buy 1 more BTC at $44000
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("44000"),
            high=Decimal("45000"),
            low=Decimal("43000"),
            close=Decimal("44000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)

        order2 = context.buy("BTC/USDT", Decimal("1"))
        fill2 = Fill(
            order_id=order2,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("44000"),
            amount=Decimal("1"),
            fee=Decimal("44"),
            timestamp=bar2.time,
        )
        context._process_fill(fill2)
        context._move_completed_orders()

        # Sell 2 BTC at $43000
        bar3 = Bar(
            time=datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("43000"),
            high=Decimal("44000"),
            low=Decimal("42000"),
            close=Decimal("43000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar3)
        context._add_bar_to_history(bar3)

        sell_id = context.sell("BTC/USDT", Decimal("2"))
        fill_sell = Fill(
            order_id=sell_id,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("43000"),
            amount=Decimal("2"),
            fee=Decimal("86"),
            timestamp=bar3.time,
        )
        context._process_fill(fill_sell)

        # Trade closed
        assert context._open_trade is None
        assert len(context.trades) == 1
        trade = context.trades[0]
        # Avg entry = (40000*1 + 44000*1) / 2 = 42000
        assert trade.entry_price == Decimal("42000")
        assert trade.exit_price == Decimal("43000")
        assert trade.amount == Decimal("2")
        # PnL = (43000 - 42000) * 2 - (40 + 44 + 86) = 2000 - 170 = 1830
        assert trade.pnl == Decimal("1830")
        # PnL% = 1830 / (42000 * 2) * 100 ≈ 2.178...
        expected_pnl_pct = Decimal("1830") / Decimal("84000") * 100
        assert trade.pnl_pct == expected_pnl_pct

    def test_averaging_with_unequal_amounts(self, context: BacktestContext) -> None:
        """Test weighted average with different buy amounts."""
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="ETH/USDT",
            open=Decimal("3000"),
            high=Decimal("3100"),
            low=Decimal("2900"),
            close=Decimal("3000"),
            volume=Decimal("5000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)

        # Buy 2 ETH at $3000
        order1 = context.buy("ETH/USDT", Decimal("2"))
        fill1 = Fill(
            order_id=order1,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            price=Decimal("3000"),
            amount=Decimal("2"),
            fee=Decimal("6"),
            timestamp=bar1.time,
        )
        context._process_fill(fill1)
        context._move_completed_orders()

        assert context._open_trade.entry_price == Decimal("3000")
        assert context._open_trade.amount == Decimal("2")

        # Buy 1 more ETH at $3600
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="ETH/USDT",
            open=Decimal("3600"),
            high=Decimal("3700"),
            low=Decimal("3500"),
            close=Decimal("3600"),
            volume=Decimal("5000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)

        order2 = context.buy("ETH/USDT", Decimal("1"))
        fill2 = Fill(
            order_id=order2,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            price=Decimal("3600"),
            amount=Decimal("1"),
            fee=Decimal("3.6"),
            timestamp=bar2.time,
        )
        context._process_fill(fill2)

        # Weighted avg: (3000*2 + 3600*1) / 3 = 9600 / 3 = 3200
        assert context._open_trade.entry_price == Decimal("3200")
        assert context._open_trade.amount == Decimal("3")

    def test_partial_close_does_not_reset_entry_price(self, context: BacktestContext) -> None:
        """Test that partial close keeps the trade open with correct entry price."""
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)

        # Buy 2 BTC at $40000
        order1 = context.buy("BTC/USDT", Decimal("2"))
        fill1 = Fill(
            order_id=order1,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            amount=Decimal("2"),
            fee=Decimal("80"),
            timestamp=bar1.time,
        )
        context._process_fill(fill1)
        context._move_completed_orders()

        # Sell 1 BTC (partial close)
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)

        sell_id = context.sell("BTC/USDT", Decimal("1"))
        fill_sell = Fill(
            order_id=sell_id,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=bar2.time,
        )
        context._process_fill(fill_sell)

        # Trade still open (1 BTC remaining)
        assert context._open_trade is not None
        assert context._open_trade.entry_price == Decimal("40000")
        # Trade should not be in completed trades yet
        assert len(context.trades) == 0

    def test_partial_close_pnl_uses_each_fill_price(self, context: BacktestContext) -> None:
        """Test that PnL accounts for each partial exit price, not just the last one.

        Regression test for ISSUE-007: Buy 2 BTC @ $40K, Sell 1 @ $42K, Sell 1 @ $44K.
        Correct PnL = ($42K-$40K)*1 + ($44K-$40K)*1 - fees = $6,000 - fees
        Bug was: PnL = ($44K-$40K)*2 - fees = $8,000 - fees (used last price × total amount)
        """
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)

        # Buy 2 BTC at $40,000
        order1 = context.buy("BTC/USDT", Decimal("2"))
        fill_buy = Fill(
            order_id=order1,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            amount=Decimal("2"),
            fee=Decimal("80"),  # 0.1%
            timestamp=bar1.time,
        )
        context._process_fill(fill_buy)
        context._move_completed_orders()

        assert context._open_trade is not None
        assert context._open_trade.amount == Decimal("2")

        # Sell 1 BTC at $42,000 (partial close)
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)

        sell_id1 = context.sell("BTC/USDT", Decimal("1"))
        fill_sell1 = Fill(
            order_id=sell_id1,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=bar2.time,
        )
        context._process_fill(fill_sell1)
        context._move_completed_orders()

        # Trade still open
        assert context._open_trade is not None
        assert len(context.trades) == 0

        # Sell remaining 1 BTC at $44,000 (full close)
        bar3 = Bar(
            time=datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("44000"),
            high=Decimal("45000"),
            low=Decimal("43000"),
            close=Decimal("44000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar3)
        context._add_bar_to_history(bar3)

        sell_id2 = context.sell("BTC/USDT", Decimal("1"))
        fill_sell2 = Fill(
            order_id=sell_id2,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("44000"),
            amount=Decimal("1"),
            fee=Decimal("44"),
            timestamp=bar3.time,
        )
        context._process_fill(fill_sell2)

        # Trade should be closed
        assert context._open_trade is None
        assert len(context.trades) == 1
        trade = context.trades[0]

        # PnL = (42000-40000)*1 + (44000-40000)*1 - (80+42+44) = 2000+4000-166 = 5834
        assert trade.pnl == Decimal("5834")
        # Weighted average exit: (42000*1 + 44000*1) / 2 = 43000
        assert trade.exit_price == Decimal("43000")
        assert trade.entry_price == Decimal("40000")
        # pnl_pct = 5834 / (40000*2) * 100
        expected_pnl_pct = Decimal("5834") / Decimal("80000") * 100
        assert trade.pnl_pct == expected_pnl_pct

    def test_partial_close_three_exits_pnl(self) -> None:
        """Test PnL with three separate partial exits."""
        context = BacktestContext(
            initial_capital=Decimal("200000"),
            commission_rate=Decimal("0.001"),
        )
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)

        # Buy 3 BTC at $40,000
        order1 = context.buy("BTC/USDT", Decimal("3"))
        fill_buy = Fill(
            order_id=order1,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            amount=Decimal("3"),
            fee=Decimal("0"),  # zero fee for simpler math
            timestamp=bar1.time,
        )
        context._process_fill(fill_buy)
        context._move_completed_orders()

        # Sell 1 @ $41,000
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("41000"),
            high=Decimal("42000"),
            low=Decimal("40500"),
            close=Decimal("41000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)
        sid1 = context.sell("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=sid1,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("41000"),
                amount=Decimal("1"),
                fee=Decimal("0"),
                timestamp=bar2.time,
            )
        )
        context._move_completed_orders()

        # Sell 1 @ $43,000
        bar3 = Bar(
            time=datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("43000"),
            high=Decimal("44000"),
            low=Decimal("42000"),
            close=Decimal("43000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar3)
        context._add_bar_to_history(bar3)
        sid2 = context.sell("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=sid2,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("43000"),
                amount=Decimal("1"),
                fee=Decimal("0"),
                timestamp=bar3.time,
            )
        )
        context._move_completed_orders()

        # Sell 1 @ $39,000 (losing exit)
        bar4 = Bar(
            time=datetime(2024, 1, 4, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("39000"),
            high=Decimal("40000"),
            low=Decimal("38000"),
            close=Decimal("39000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar4)
        context._add_bar_to_history(bar4)
        sid3 = context.sell("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=sid3,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("39000"),
                amount=Decimal("1"),
                fee=Decimal("0"),
                timestamp=bar4.time,
            )
        )

        assert context._open_trade is None
        assert len(context.trades) == 1
        trade = context.trades[0]
        # PnL = (41K-40K)*1 + (43K-40K)*1 + (39K-40K)*1 = 1000+3000+(-1000) = 3000
        assert trade.pnl == Decimal("3000")

    def test_multiple_buys_then_partial_exits_pnl(self) -> None:
        """Test PnL when averaging into position at different prices, then exiting in batches.

        This combines weighted average entry price calculation with partial exit PnL.
        Buy 1 BTC @ $40K, Buy 2 BTC @ $46K → avg entry = $44K (weighted).
        Sell 1 BTC @ $48K → PnL₁ = (48K-44K)*1 = $4K
        Sell 2 BTC @ $42K → PnL₂ = (42K-44K)*2 = -$4K
        Total PnL = 4000 + (-4000) - fees(40+92+48+84) = -264
        """
        context = BacktestContext(
            initial_capital=Decimal("200000"),
            commission_rate=Decimal("0.001"),
        )

        # --- Buy 1 BTC @ $40,000 ---
        bar1 = Bar(
            time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar1)
        context._add_bar_to_history(bar1)
        oid1 = context.buy("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=oid1,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("40000"),
                amount=Decimal("1"),
                fee=Decimal("40"),
                timestamp=bar1.time,
            )
        )
        context._move_completed_orders()

        # Verify: 1 BTC, entry price = $40,000
        assert context._open_trade is not None
        assert context._open_trade.amount == Decimal("1")
        assert context._open_trade.entry_price == Decimal("40000")

        # --- Buy 2 more BTC @ $46,000 ---
        bar2 = Bar(
            time=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("46000"),
            high=Decimal("47000"),
            low=Decimal("45000"),
            close=Decimal("46000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar2)
        context._add_bar_to_history(bar2)
        oid2 = context.buy("BTC/USDT", Decimal("2"))
        context._process_fill(
            Fill(
                order_id=oid2,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("46000"),
                amount=Decimal("2"),
                fee=Decimal("92"),
                timestamp=bar2.time,
            )
        )
        context._move_completed_orders()

        # Verify: 3 BTC, weighted avg entry = (40000*1 + 46000*2) / 3 = 44000
        assert context._open_trade.amount == Decimal("3")
        assert context._open_trade.entry_price == Decimal("44000")

        # --- Sell 1 BTC @ $48,000 (partial profitable exit) ---
        bar3 = Bar(
            time=datetime(2024, 1, 3, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("48000"),
            high=Decimal("49000"),
            low=Decimal("47000"),
            close=Decimal("48000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar3)
        context._add_bar_to_history(bar3)
        sid1 = context.sell("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=sid1,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("48000"),
                amount=Decimal("1"),
                fee=Decimal("48"),
                timestamp=bar3.time,
            )
        )
        context._move_completed_orders()

        # Trade still open; amount stays at peak (3 BTC), entry price unchanged
        assert context._open_trade is not None
        assert context._open_trade.amount == Decimal("3")
        assert context._open_trade.entry_price == Decimal("44000")

        # --- Sell 2 BTC @ $42,000 (full close at a loss) ---
        bar4 = Bar(
            time=datetime(2024, 1, 4, 12, 0, 0, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42000"),
            volume=Decimal("1000"),
        )
        context._set_current_bar(bar4)
        context._add_bar_to_history(bar4)
        sid2 = context.sell("BTC/USDT", Decimal("2"))
        context._process_fill(
            Fill(
                order_id=sid2,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("42000"),
                amount=Decimal("2"),
                fee=Decimal("84"),
                timestamp=bar4.time,
            )
        )

        # Trade closed
        assert context._open_trade is None
        assert len(context.trades) == 1
        trade = context.trades[0]

        # PnL = (48K-44K)*1 + (42K-44K)*2 - fees = 4000 + (-4000) - (40+92+48+84) = -264
        assert trade.pnl == Decimal("-264")
        assert trade.entry_price == Decimal("44000")
        # pnl_pct = -264 / (44000 * 3) * 100
        expected_pnl_pct = Decimal("-264") / Decimal("132000") * 100
        assert trade.pnl_pct == expected_pnl_pct


class TestRestoreState:
    """Tests for restore_state() — session resume support."""

    def test_restore_cash(self, context: BacktestContext) -> None:
        """Test that cash is restored from state."""
        context.restore_state({"cash": "5000.50"})
        assert context.cash == Decimal("5000.50")

    def test_restore_total_fees(self, context: BacktestContext) -> None:
        """Test that total_fees is restored from state."""
        context.restore_state({"total_fees": "123.45"})
        assert context._total_fees == Decimal("123.45")

    def test_restore_positions(self, context: BacktestContext) -> None:
        """Test that positions are restored from state."""
        state = {
            "positions": {
                "BTC/USDT": {
                    "amount": "0.5",
                    "avg_entry_price": "45000",
                    "current_price": "46000",
                },
            }
        }
        context.restore_state(state)

        assert "BTC/USDT" in context._positions
        pos = context._positions["BTC/USDT"]
        assert pos.amount == Decimal("0.5")
        assert pos.avg_entry_price == Decimal("45000")
        assert context._last_prices["BTC/USDT"] == Decimal("46000")

    def test_restore_positions_clears_previous(self, context: BacktestContext) -> None:
        """Test that restore_state clears pre-existing positions."""
        from squant.engine.backtest.types import Position

        context._positions["ETH/USDT"] = Position(
            symbol="ETH/USDT", amount=Decimal("1"), avg_entry_price=Decimal("3000")
        )

        context.restore_state(
            {
                "positions": {
                    "BTC/USDT": {"amount": "1", "avg_entry_price": "50000"},
                }
            }
        )

        assert "ETH/USDT" not in context._positions
        assert "BTC/USDT" in context._positions

    def test_restore_trades(self, context: BacktestContext) -> None:
        """Test that closed trades are restored from state."""
        state = {
            "trades": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "entry_time": "2024-06-01T12:00:00+00:00",
                    "entry_price": "50000",
                    "exit_time": "2024-06-01T13:00:00+00:00",
                    "exit_price": "51000",
                    "amount": "0.1",
                    "pnl": "100",
                    "pnl_pct": "2.0",
                    "fees": "10.2",
                },
            ]
        }
        context.restore_state(state)

        assert len(context.trades) == 1
        trade = context.trades[0]
        assert trade.symbol == "BTC/USDT"
        assert trade.entry_price == Decimal("50000")
        assert trade.exit_price == Decimal("51000")
        assert trade.pnl == Decimal("100")
        assert trade.fees == Decimal("10.2")

    def test_restore_open_position_creates_open_trade(self, context: BacktestContext) -> None:
        """Test that an open position causes _open_trade to be set."""
        state = {
            "positions": {
                "BTC/USDT": {
                    "amount": "0.5",
                    "avg_entry_price": "45000",
                },
            }
        }
        context.restore_state(state)

        assert context._open_trade is not None
        assert context._open_trade.symbol == "BTC/USDT"
        assert context._open_trade.entry_price == Decimal("45000")
        assert context._open_trade.amount == Decimal("0.5")

    def test_restore_open_trade_preserves_entry_time(self, context: BacktestContext) -> None:
        """Test that open_trade field preserves entry_time and partial_exit_pnl."""
        state = {
            "positions": {
                "BTC/USDT": {
                    "amount": "0.5",
                    "avg_entry_price": "45000",
                },
            },
            "open_trade": {
                "symbol": "BTC/USDT",
                "side": "buy",
                "entry_time": "2024-06-01T14:30:00+00:00",
                "entry_price": "45000",
                "amount": "0.5",
                "fees": "4.5",
                "partial_exit_pnl": "75.25",
            },
        }
        context.restore_state(state)

        assert context._open_trade is not None
        assert context._open_trade.symbol == "BTC/USDT"
        assert context._open_trade.entry_time == datetime(2024, 6, 1, 14, 30, tzinfo=UTC)
        assert context._open_trade.entry_price == Decimal("45000")
        assert context._open_trade.fees == Decimal("4.5")
        assert context._partial_exit_pnl == Decimal("75.25")

    def test_restore_short_position_creates_sell_open_trade(self, context: BacktestContext) -> None:
        """Test that a short (negative amount) position creates a SELL open trade."""
        state = {
            "positions": {
                "BTC/USDT": {
                    "amount": "-0.5",
                    "avg_entry_price": "45000",
                },
            }
        }
        context.restore_state(state)

        assert context._open_trade is not None
        assert context._open_trade.side == OrderSide.SELL
        assert context._open_trade.amount == Decimal("0.5")

    def test_restore_no_positions_clears_open_trade(self, context: BacktestContext) -> None:
        """Test that empty positions dict clears _open_trade."""
        context.restore_state({"positions": {}})

        assert context._open_trade is None
        assert context._partial_exit_pnl == Decimal("0")

    def test_restore_partial_state(self, context: BacktestContext) -> None:
        """Test that only provided fields are restored."""
        original_cash = context.cash
        context.restore_state({"total_fees": "50"})

        # Cash unchanged, fees restored
        assert context.cash == original_cash
        assert context._total_fees == Decimal("50")

    def test_restore_empty_state(self, context: BacktestContext) -> None:
        """Test that empty state dict is a no-op."""
        original_cash = context.cash
        context.restore_state({})
        assert context.cash == original_cash

    def test_restore_full_state(self, context: BacktestContext) -> None:
        """Test complete state restoration combining all fields."""
        state = {
            "cash": "8000",
            "total_fees": "200",
            "positions": {
                "BTC/USDT": {
                    "amount": "0.1",
                    "avg_entry_price": "40000",
                    "current_price": "42000",
                },
            },
            "trades": [
                {
                    "symbol": "ETH/USDT",
                    "side": "buy",
                    "entry_time": "2024-01-01T10:00:00+00:00",
                    "entry_price": "2000",
                    "exit_time": "2024-01-01T11:00:00+00:00",
                    "exit_price": "2100",
                    "amount": "1.0",
                    "pnl": "100",
                    "pnl_pct": "5.0",
                    "fees": "4.1",
                },
            ],
        }
        context.restore_state(state)

        assert context.cash == Decimal("8000")
        assert context._total_fees == Decimal("200")
        assert "BTC/USDT" in context._positions
        assert len(context.trades) == 1
        assert context._open_trade is not None
        assert context._partial_exit_pnl == Decimal("0")


class TestBuildResultSnapshot:
    """Tests for build_result_snapshot() — result persistence support."""

    def test_empty_context(self, context: BacktestContext) -> None:
        """Test snapshot of fresh context."""
        result = context.build_result_snapshot()

        assert result["cash"] == str(context.cash)
        assert result["total_fees"] == "0"
        assert result["unrealized_pnl"] == "0"
        assert result["realized_pnl"] == "0"
        assert result["positions"] == {}
        assert result["trades"] == []
        assert result["open_trade"] is None
        assert result["trades_count"] == 0
        assert result["logs"] == []

    def test_with_position(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Test snapshot includes open positions with unrealized PnL."""
        from squant.engine.backtest.types import Position

        context._positions["BTC/USDT"] = Position(
            symbol="BTC/USDT",
            amount=Decimal("0.5"),
            avg_entry_price=Decimal("40000"),
        )
        context._last_prices["BTC/USDT"] = Decimal("42000")

        result = context.build_result_snapshot()

        assert "BTC/USDT" in result["positions"]
        pos = result["positions"]["BTC/USDT"]
        assert pos["amount"] == "0.5"
        assert pos["avg_entry_price"] == "40000"
        assert pos["current_price"] == "42000"
        # unrealized = (42000 - 40000) * 0.5 = 1000
        assert Decimal(pos["unrealized_pnl"]) == Decimal("1000")
        # Top-level total matches
        assert Decimal(result["unrealized_pnl"]) == Decimal("1000")

    def test_with_trades(self, context: BacktestContext) -> None:
        """Test snapshot includes closed trades."""
        from squant.engine.backtest.types import TradeRecord

        context._trades.append(
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
                entry_price=Decimal("40000"),
                exit_time=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
                exit_price=Decimal("41000"),
                amount=Decimal("0.1"),
                pnl=Decimal("100"),
                pnl_pct=Decimal("2.5"),
                fees=Decimal("8"),
            )
        )

        result = context.build_result_snapshot()

        assert result["trades_count"] == 1
        assert len(result["trades"]) == 1
        trade = result["trades"][0]
        assert trade["symbol"] == "BTC/USDT"
        assert trade["entry_price"] == "40000"
        assert trade["exit_price"] == "41000"
        assert trade["pnl"] == "100"
        # Top-level realized PnL
        assert Decimal(result["realized_pnl"]) == Decimal("100")

    def test_roundtrip_with_restore(self, context: BacktestContext) -> None:
        """Test that build_result_snapshot output can be fed to restore_state."""
        from squant.engine.backtest.types import Position, TradeRecord

        # Set up state
        context._cash = Decimal("8000")
        context._total_fees = Decimal("50")
        context._positions["BTC/USDT"] = Position(
            symbol="BTC/USDT",
            amount=Decimal("0.2"),
            avg_entry_price=Decimal("45000"),
        )
        context._last_prices["BTC/USDT"] = Decimal("46000")
        context._open_trade = TradeRecord(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            entry_time=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
            entry_price=Decimal("45000"),
            amount=Decimal("0.2"),
            fees=Decimal("9.0"),
        )
        context._partial_exit_pnl = Decimal("150.5")  # from a prior partial exit
        context._trades.append(
            TradeRecord(
                symbol="ETH/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                entry_price=Decimal("3000"),
                exit_time=datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC),
                exit_price=Decimal("3100"),
                amount=Decimal("1"),
                pnl=Decimal("100"),
                pnl_pct=Decimal("3.33"),
                fees=Decimal("6.2"),
            )
        )
        context.log("Test trade executed")
        context.log("Position opened")

        # Snapshot → restore into a fresh context
        snapshot = context.build_result_snapshot()

        # Verify top-level aggregates in snapshot
        assert Decimal(snapshot["realized_pnl"]) == Decimal("100")
        assert Decimal(snapshot["unrealized_pnl"]) == Decimal("200")  # (46000-45000)*0.2
        assert len(snapshot["logs"]) == 2

        new_ctx = BacktestContext(
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
        )
        new_ctx.restore_state(snapshot)

        assert new_ctx.cash == Decimal("8000")
        assert new_ctx._total_fees == Decimal("50")
        assert "BTC/USDT" in new_ctx._positions
        assert new_ctx._positions["BTC/USDT"].amount == Decimal("0.2")
        assert new_ctx._last_prices["BTC/USDT"] == Decimal("46000")
        assert len(new_ctx.trades) == 1
        assert new_ctx.trades[0].pnl == Decimal("100")
        # Open trade restored with original entry_time and partial exit PnL
        assert new_ctx._open_trade is not None
        assert new_ctx._open_trade.entry_time == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
        assert new_ctx._open_trade.fees == Decimal("9.0")
        assert new_ctx._partial_exit_pnl == Decimal("150.5")
        # Logs restored
        assert len(new_ctx.logs) == 2
        assert "Test trade executed" in new_ctx.logs[0]


class TestWeightedExitPrice:
    """P1-2: exit_price should be weighted average across partial exits."""

    def test_single_exit_uses_fill_price(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Single exit sets exit_price to the fill price directly."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC at $50,000
        order_id = context.buy("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("1"),
                fee=Decimal("50"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell 1 BTC at $52,000
        sell_id = context.sell("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=sell_id,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("52000"),
                amount=Decimal("1"),
                fee=Decimal("52"),
                timestamp=sample_bar.time,
            )
        )

        trade = context.trades[-1]
        assert trade.exit_price == Decimal("52000")

    def test_two_partial_exits_weighted_average(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Two partial exits produce a weighted average exit_price."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC at $50,000
        order_id = context.buy("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("1"),
                fee=Decimal("50"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell 0.6 BTC at $52,000
        sell1_id = context.sell("BTC/USDT", Decimal("0.6"))
        context._process_fill(
            Fill(
                order_id=sell1_id,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("52000"),
                amount=Decimal("0.6"),
                fee=Decimal("31.2"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell remaining 0.4 BTC at $51,000
        sell2_id = context.sell("BTC/USDT", Decimal("0.4"))
        context._process_fill(
            Fill(
                order_id=sell2_id,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("51000"),
                amount=Decimal("0.4"),
                fee=Decimal("20.4"),
                timestamp=sample_bar.time,
            )
        )

        trade = context.trades[-1]
        # Weighted avg: (52000 * 0.6 + 51000 * 0.4) / 1.0 = (31200 + 20400) / 1.0 = 51600
        assert trade.exit_price == Decimal("51600")

    def test_three_partial_exits_weighted_average(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Three partial exits produce correct weighted average exit_price."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC at $50,000
        order_id = context.buy("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("1"),
                fee=Decimal("50"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell 0.3 at $53,000
        s1 = context.sell("BTC/USDT", Decimal("0.3"))
        context._process_fill(
            Fill(
                order_id=s1,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("53000"),
                amount=Decimal("0.3"),
                fee=Decimal("15.9"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell 0.3 at $52,000
        s2 = context.sell("BTC/USDT", Decimal("0.3"))
        context._process_fill(
            Fill(
                order_id=s2,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("52000"),
                amount=Decimal("0.3"),
                fee=Decimal("15.6"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Sell final 0.4 at $51,000
        s3 = context.sell("BTC/USDT", Decimal("0.4"))
        context._process_fill(
            Fill(
                order_id=s3,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("51000"),
                amount=Decimal("0.4"),
                fee=Decimal("20.4"),
                timestamp=sample_bar.time,
            )
        )

        trade = context.trades[-1]
        # (53000*0.3 + 52000*0.3 + 51000*0.4) / 1.0 = (15900 + 15600 + 20400) / 1.0 = 51900
        assert trade.exit_price == Decimal("51900")


class TestFillsPersistRestore:
    """P2-2: Fills should be persisted and restored across session restarts."""

    def test_fills_included_in_snapshot(self, context: BacktestContext, sample_bar: Bar) -> None:
        """build_result_snapshot includes fills data."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        order_id = context.buy("BTC/USDT", Decimal("0.1"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("0.1"),
                fee=Decimal("5"),
                timestamp=sample_bar.time,
            )
        )

        snapshot = context.build_result_snapshot()
        assert "fills" in snapshot
        assert len(snapshot["fills"]) == 1
        assert snapshot["fills"][0]["symbol"] == "BTC/USDT"
        assert snapshot["fills"][0]["price"] == "50000"

    def test_fills_restored_from_state(self) -> None:
        """restore_state restores fills from saved state."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))
        state = {
            "fills": [
                {
                    "order_id": "abc-123",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "price": "50000",
                    "amount": "0.1",
                    "fee": "5",
                    "timestamp": "2024-01-01T12:00:00+00:00",
                },
                {
                    "order_id": "def-456",
                    "symbol": "BTC/USDT",
                    "side": "sell",
                    "price": "52000",
                    "amount": "0.1",
                    "fee": "5.2",
                    "timestamp": "2024-01-01T13:00:00+00:00",
                },
            ]
        }
        ctx.restore_state(state)

        assert len(ctx.fills) == 2
        assert ctx.fills[0].order_id == "abc-123"
        assert ctx.fills[0].price == Decimal("50000")
        assert ctx.fills[1].side == OrderSide.SELL
        assert ctx.fills[1].amount == Decimal("0.1")

    def test_fills_roundtrip(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Fills survive a snapshot → restore roundtrip."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        order_id = context.buy("BTC/USDT", Decimal("0.5"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("45000"),
                amount=Decimal("0.5"),
                fee=Decimal("22.5"),
                timestamp=sample_bar.time,
            )
        )

        snapshot = context.build_result_snapshot()

        new_ctx = BacktestContext(initial_capital=Decimal("100000"))
        new_ctx.restore_state(snapshot)

        assert len(new_ctx.fills) == 1
        assert new_ctx.fills[0].price == Decimal("45000")
        assert new_ctx.fills[0].amount == Decimal("0.5")


class TestExitFillTrackingRestore:
    """exit_fill_notional/amount should be persisted and restored."""

    def test_exit_fill_tracking_roundtrip(self, context: BacktestContext, sample_bar: Bar) -> None:
        """Partial exit tracking survives snapshot → restore."""
        context._set_current_bar(sample_bar)
        context._add_bar_to_history(sample_bar)

        # Buy 1 BTC
        order_id = context.buy("BTC/USDT", Decimal("1"))
        context._process_fill(
            Fill(
                order_id=order_id,
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("50000"),
                amount=Decimal("1"),
                fee=Decimal("50"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Partial sell 0.5 BTC at $52,000
        sell_id = context.sell("BTC/USDT", Decimal("0.5"))
        context._process_fill(
            Fill(
                order_id=sell_id,
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                price=Decimal("52000"),
                amount=Decimal("0.5"),
                fee=Decimal("26"),
                timestamp=sample_bar.time,
            )
        )
        context._move_completed_orders()

        # Snapshot while position is open with partial exits
        snapshot = context.build_result_snapshot()
        assert snapshot["open_trade"]["exit_fill_notional"] == str(
            Decimal("52000") * Decimal("0.5")
        )
        assert snapshot["open_trade"]["exit_fill_amount"] == "0.5"

        # Restore and verify
        new_ctx = BacktestContext(initial_capital=Decimal("100000"))
        new_ctx.restore_state(snapshot)
        assert new_ctx._exit_fill_notional == Decimal("52000") * Decimal("0.5")
        assert new_ctx._exit_fill_amount == Decimal("0.5")


class TestStopOrderContextAPI:
    """Tests for stop/stop-limit order placement via context API."""

    def test_buy_stop_order_creates_correct_type(self, context: BacktestContext) -> None:
        """buy() with stop_price creates a STOP order."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        order_id = context.buy("BTC/USDT", Decimal("0.1"), stop_price=Decimal("43000"))

        orders = context.pending_orders
        assert len(orders) == 1
        order = orders[0]
        assert order.id == order_id
        assert order.type == OrderType.STOP
        assert order.stop_price == Decimal("43000")
        assert order.price is None
        assert order.triggered is False

    def test_buy_stop_limit_order_creates_correct_type(self, context: BacktestContext) -> None:
        """buy() with stop_price and price creates a STOP_LIMIT order."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        order_id = context.buy(
            "BTC/USDT", Decimal("0.1"),
            price=Decimal("43500"), stop_price=Decimal("43000"),
        )

        orders = context.pending_orders
        assert len(orders) == 1
        order = orders[0]
        assert order.id == order_id
        assert order.type == OrderType.STOP_LIMIT
        assert order.stop_price == Decimal("43000")
        assert order.price == Decimal("43500")

    def test_sell_stop_order_creates_correct_type(self, context: BacktestContext) -> None:
        """sell() with stop_price creates a STOP order."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        # Give a position first
        from squant.engine.backtest.types import Fill, OrderSide as Side

        context._process_fill(Fill(
            order_id="fake",
            symbol="BTC/USDT",
            side=Side.BUY,
            price=Decimal("42000"),
            amount=Decimal("1"),
            fee=Decimal("42"),
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ))

        order_id = context.sell("BTC/USDT", Decimal("0.5"), stop_price=Decimal("41000"))

        orders = context.pending_orders
        assert len(orders) == 1
        order = orders[0]
        assert order.id == order_id
        assert order.type == OrderType.STOP
        assert order.stop_price == Decimal("41000")

    def test_stop_buy_cash_reservation(self, context: BacktestContext) -> None:
        """STOP buy reserves cash based on stop_price + slippage."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        # Place a stop buy that would use most of the capital
        # Capital = 100000, stop_price = 43000, amount = 2
        # Cost ≈ 43000 * 2 * 1.001 (commission) = 86086
        context.buy("BTC/USDT", Decimal("2"), stop_price=Decimal("43000"))

        # Second stop buy should fail due to insufficient available cash
        with pytest.raises(ValueError, match="Insufficient cash"):
            context.buy("BTC/USDT", Decimal("1"), stop_price=Decimal("43000"))

    def test_stop_order_gets_bars_remaining(self, context: BacktestContext) -> None:
        """STOP orders support valid_for_bars expiry."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("42000"),
            high=Decimal("43000"),
            low=Decimal("41000"),
            close=Decimal("42500"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        context.buy("BTC/USDT", Decimal("0.1"), stop_price=Decimal("43000"), valid_for_bars=5)

        orders = context.pending_orders
        assert orders[0].bars_remaining == 5


class TestConvenienceTradingMethods:
    """Tests for close_position, target_position, target_percent."""

    def _setup_position(self, context: BacktestContext, symbol: str, amount: Decimal) -> None:
        """Helper: simulate owning a position by processing a fill."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol=symbol,
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)
        context._add_bar_to_history(bar)

        fill = Fill(
            order_id="setup-fill",
            symbol=symbol,
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=amount,
            fee=amount * Decimal("50000") * Decimal("0.001"),
            timestamp=bar.time,
        )
        context._process_fill(fill)

    # --- close_position ---

    def test_close_position_sells_entire_position(self, context: BacktestContext) -> None:
        """close_position places a market sell for the full position amount."""
        self._setup_position(context, "BTC/USDT", Decimal("0.5"))
        order_id = context.close_position("BTC/USDT")

        assert order_id is not None
        assert len(context.pending_orders) == 1
        order = context.pending_orders[0]
        assert order.side == OrderSide.SELL
        assert order.amount == Decimal("0.5")
        assert order.type == OrderType.MARKET

    def test_close_position_no_position_returns_none(self, context: BacktestContext) -> None:
        """close_position returns None when there is no position."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)
        result = context.close_position("BTC/USDT")
        assert result is None

    def test_close_position_cancels_pending_sells(self, context: BacktestContext) -> None:
        """close_position cancels existing pending sell orders before placing new sell."""
        self._setup_position(context, "BTC/USDT", Decimal("1.0"))
        # Place partial sell order first
        context.sell("BTC/USDT", Decimal("0.3"), price=Decimal("55000"))
        assert len(context.pending_orders) == 1

        # close_position should cancel the pending sell and sell everything
        order_id = context.close_position("BTC/USDT")
        assert order_id is not None
        # Only the new market sell should be pending
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].amount == Decimal("1.0")
        assert pending[0].type == OrderType.MARKET

    # --- target_position ---

    def test_target_position_buy_to_increase(self, context: BacktestContext) -> None:
        """target_position buys the difference when target > current."""
        self._setup_position(context, "BTC/USDT", Decimal("0.3"))
        order_id = context.target_position("BTC/USDT", Decimal("0.5"))

        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.BUY
        assert pending[0].amount == Decimal("0.2")

    def test_target_position_sell_to_decrease(self, context: BacktestContext) -> None:
        """target_position sells the difference when target < current."""
        self._setup_position(context, "BTC/USDT", Decimal("0.5"))
        order_id = context.target_position("BTC/USDT", Decimal("0.2"))

        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.SELL
        assert pending[0].amount == Decimal("0.3")

    def test_target_position_no_change_returns_none(self, context: BacktestContext) -> None:
        """target_position returns None when already at target."""
        self._setup_position(context, "BTC/USDT", Decimal("0.5"))
        result = context.target_position("BTC/USDT", Decimal("0.5"))
        assert result is None
        assert len(context.pending_orders) == 0

    def test_target_position_zero_closes(self, context: BacktestContext) -> None:
        """target_position(symbol, 0) sells the entire position."""
        self._setup_position(context, "BTC/USDT", Decimal("0.5"))
        order_id = context.target_position("BTC/USDT", Decimal("0"))

        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.SELL
        assert pending[0].amount == Decimal("0.5")

    def test_target_position_negative_raises(self, context: BacktestContext) -> None:
        """target_position raises ValueError for negative target."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)
        with pytest.raises(ValueError, match="target_amount must be >= 0"):
            context.target_position("BTC/USDT", Decimal("-0.1"))

    def test_target_position_from_zero_buys(self, context: BacktestContext) -> None:
        """target_position opens a new position when none exists."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)
        order_id = context.target_position("BTC/USDT", Decimal("0.5"))

        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.BUY
        assert pending[0].amount == Decimal("0.5")

    def test_target_position_cancels_conflicting_orders(self, context: BacktestContext) -> None:
        """target_position cancels pending orders on the same side before adjusting."""
        self._setup_position(context, "BTC/USDT", Decimal("1.0"))
        # Place a pending sell
        context.sell("BTC/USDT", Decimal("0.3"), price=Decimal("55000"))
        assert len(context.pending_orders) == 1

        # target_position to sell more should cancel the pending sell first
        order_id = context.target_position("BTC/USDT", Decimal("0.5"))
        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].amount == Decimal("0.5")
        assert pending[0].side == OrderSide.SELL

    # --- target_percent ---

    def test_target_percent_buys_correct_amount(self, context: BacktestContext) -> None:
        """target_percent calculates and buys to reach 50% equity allocation."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)
        context._add_bar_to_history(bar)

        # equity=100000, 50% target = 50000 worth = 1.0 BTC at 50000
        order_id = context.target_percent("BTC/USDT", Decimal("0.5"))
        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.BUY
        assert pending[0].amount == Decimal("1")

    def test_target_percent_sells_excess(self, context: BacktestContext) -> None:
        """target_percent sells when current position exceeds target allocation."""
        self._setup_position(context, "BTC/USDT", Decimal("1.0"))
        # Position value = 1.0 * 50000 = 50000, equity ≈ 99950 + 50000 = ~99950 cash + 50000 pos
        # target 10% of equity → need to sell down
        order_id = context.target_percent("BTC/USDT", Decimal("0.1"))
        assert order_id is not None
        pending = context.pending_orders
        assert len(pending) == 1
        assert pending[0].side == OrderSide.SELL

    def test_target_percent_out_of_range_raises(self, context: BacktestContext) -> None:
        """target_percent raises for percent outside [0, 1]."""
        bar = Bar(
            time=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTC/USDT",
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(bar)

        with pytest.raises(ValueError, match="percent must be between 0 and 1"):
            context.target_percent("BTC/USDT", Decimal("1.5"))

        with pytest.raises(ValueError, match="percent must be between 0 and 1"):
            context.target_percent("BTC/USDT", Decimal("-0.1"))

    def test_target_percent_no_bar_raises(self, context: BacktestContext) -> None:
        """target_percent raises when no current bar is set."""
        with pytest.raises(ValueError, match="No current bar"):
            context.target_percent("BTC/USDT", Decimal("0.5"))


class TestAccountMetrics:
    """Tests for public account metrics properties (P1-4)."""

    def test_unrealized_pnl_no_position(self, context: BacktestContext) -> None:
        """unrealized_pnl returns 0 with no position."""
        assert context.unrealized_pnl == Decimal("0")

    def test_unrealized_pnl_with_profit(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """unrealized_pnl reflects paper profit."""
        context._set_current_bar(sample_bar)
        # Simulate a buy fill
        fill = Fill(
            order_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("1"),
            fee=Decimal("50"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill)
        # Set a higher price
        higher_bar = Bar(
            time=sample_bar.time,
            symbol="BTC/USDT",
            open=Decimal("51000"),
            high=Decimal("52000"),
            low=Decimal("50500"),
            close=Decimal("51000"),
            volume=Decimal("100"),
        )
        context._set_current_bar(higher_bar)
        # Position bought at 50000, now at 51000 → +1000
        assert context.unrealized_pnl == Decimal("1000")

    def test_realized_pnl_no_trades(self, context: BacktestContext) -> None:
        """realized_pnl returns 0 with no completed trades."""
        assert context.realized_pnl == Decimal("0")

    def test_realized_pnl_after_round_trip(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """realized_pnl reflects closed trade PnL."""
        context._set_current_bar(sample_bar)
        # Buy fill
        buy_fill = Fill(
            order_id="buy1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("1"),
            fee=Decimal("50"),
            timestamp=sample_bar.time,
        )
        context._process_fill(buy_fill)
        # Sell fill at higher price
        sell_fill = Fill(
            order_id="sell1",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            price=Decimal("51000"),
            amount=Decimal("1"),
            fee=Decimal("51"),
            timestamp=sample_bar.time,
        )
        context._process_fill(sell_fill)
        # 1 completed trade with PnL
        assert len(context.trades) == 1
        assert context.realized_pnl == context.trades[0].pnl

    def test_return_pct_initial(self, context: BacktestContext) -> None:
        """return_pct is 0 at start."""
        assert context.return_pct == Decimal("0")

    def test_return_pct_after_profit(
        self, context: BacktestContext, sample_bar: Bar
    ) -> None:
        """return_pct reflects equity change."""
        context._set_current_bar(sample_bar)
        # Buy 1 BTC at 50000
        fill = Fill(
            order_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("1"),
            fee=Decimal("50"),
            timestamp=sample_bar.time,
        )
        context._process_fill(fill)
        # Initial capital is 100000, after buy: cash=49950, position=50000, equity=99950
        # return = (99950-100000)/100000 = -0.0005
        expected = (context.equity - Decimal("100000")) / Decimal("100000")
        assert context.return_pct == expected

    def test_max_drawdown_no_snapshots(self, context: BacktestContext) -> None:
        """max_drawdown returns 0 with no equity curve."""
        assert context.max_drawdown == Decimal("0")

    def test_max_drawdown_with_decline(self, context: BacktestContext) -> None:
        """max_drawdown reflects peak-to-trough decline."""
        from squant.engine.backtest.types import EquitySnapshot

        # Simulate equity curve: 100 → 110 → 90 → 100
        for i, eq in enumerate([100, 110, 90, 100]):
            context._equity_curve.append(
                EquitySnapshot(
                    time=datetime(2024, 1, 1, i, tzinfo=UTC),
                    equity=Decimal(str(eq)),
                    cash=Decimal(str(eq)),
                    position_value=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                )
            )
        # Peak=110, trough=90, drawdown = (110-90)/110 = 20/110
        expected = Decimal("20") / Decimal("110")
        assert abs(context.max_drawdown - expected) < Decimal("0.0001")
