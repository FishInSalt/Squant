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
