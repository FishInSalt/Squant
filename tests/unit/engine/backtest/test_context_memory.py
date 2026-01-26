"""Unit tests for BacktestContext memory management with deque."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.types import (
    Bar,
    EquitySnapshot,
    Fill,
    OrderSide,
)


@pytest.fixture
def small_limits_context() -> BacktestContext:
    """Create a backtest context with small limits for testing."""
    return BacktestContext(
        initial_capital=Decimal("100000"),
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
        max_bar_history=5,
        max_equity_curve=3,
        max_completed_orders=3,
        max_fills=3,
        max_trades=3,
        max_logs=3,
    )


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar."""
    return Bar(
        time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        symbol="BTC/USDT",
        open=Decimal("42000"),
        high=Decimal("43000"),
        low=Decimal("41000"),
        close=Decimal("42500"),
        volume=Decimal("1000"),
    )


class TestEquityCurveMemoryLimit:
    """Tests for equity curve deque memory limit."""

    def test_equity_curve_respects_max_length(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that equity curve respects max length."""
        small_limits_context._set_current_bar(sample_bar)

        # Record more snapshots than the limit
        for i in range(10):
            snapshot_time = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
            small_limits_context._record_equity_snapshot(snapshot_time)

        # Should only keep the last 3 (max_equity_curve=3)
        assert len(small_limits_context.equity_curve) == 3

    def test_equity_curve_keeps_latest(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that equity curve keeps the latest snapshots."""
        small_limits_context._set_current_bar(sample_bar)

        # Record 5 snapshots, expecting to keep last 3
        for i in range(5):
            snapshot_time = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
            small_limits_context._record_equity_snapshot(snapshot_time)

        equity_curve = small_limits_context.equity_curve
        # Last 3 snapshots should be at minutes 2, 3, 4
        assert equity_curve[0].time.minute == 2
        assert equity_curve[1].time.minute == 3
        assert equity_curve[2].time.minute == 4


class TestCompletedOrdersMemoryLimit:
    """Tests for completed orders deque memory limit."""

    def test_completed_orders_respects_max_length(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that completed orders respects max length."""
        small_limits_context._set_current_bar(sample_bar)

        # Create and cancel orders to move them to completed
        for i in range(10):
            order_id = small_limits_context.buy("BTC/USDT", Decimal("0.1"))
            small_limits_context.cancel_order(order_id)

        # Should only keep the last 3 (max_completed_orders=3)
        assert len(small_limits_context.completed_orders) == 3


class TestFillsMemoryLimit:
    """Tests for fills deque memory limit."""

    def test_fills_respects_max_length(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that fills respects max length."""
        small_limits_context._set_current_bar(sample_bar)

        # Process more fills than the limit
        for i in range(10):
            fill = Fill(
                order_id=f"order-{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                price=Decimal("42000"),
                amount=Decimal("0.01"),
                fee=Decimal("0.42"),
                timestamp=datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc),
            )
            small_limits_context._process_fill(fill)

        # Should only keep the last 3 (max_fills=3)
        assert len(small_limits_context.fills) == 3


class TestLogsMemoryLimit:
    """Tests for logs deque memory limit."""

    def test_logs_respects_max_length(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that logs respects max length."""
        small_limits_context._set_current_bar(sample_bar)

        # Log more messages than the limit
        for i in range(10):
            small_limits_context.log(f"Message {i}")

        # Should only keep the last 3 (max_logs=3)
        assert len(small_limits_context.logs) == 3

    def test_logs_keeps_latest(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that logs keeps the latest messages."""
        small_limits_context._set_current_bar(sample_bar)

        for i in range(5):
            small_limits_context.log(f"Message {i}")

        logs = small_limits_context.logs
        # Last 3 messages should be 2, 3, 4
        assert "Message 2" in logs[0]
        assert "Message 3" in logs[1]
        assert "Message 4" in logs[2]


class TestBarHistoryMemoryLimit:
    """Tests for bar history deque memory limit (existing functionality)."""

    def test_bar_history_respects_max_length(
        self, small_limits_context: BacktestContext
    ) -> None:
        """Test that bar history respects max length."""
        # Add more bars than the limit
        for i in range(10):
            bar = Bar(
                time=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal("42500"),
                volume=Decimal("1000"),
            )
            small_limits_context._add_bar_to_history(bar)

        # Should only keep the last 5 (max_bar_history=5)
        bars = small_limits_context.get_bars(100)
        assert len(bars) == 5

    def test_bar_history_keeps_latest(
        self, small_limits_context: BacktestContext
    ) -> None:
        """Test that bar history keeps the latest bars."""
        for i in range(10):
            bar = Bar(
                time=datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal(str(42000 + i)),
                volume=Decimal("1000"),
            )
            small_limits_context._add_bar_to_history(bar)

        bars = small_limits_context.get_bars(5)
        # Last 5 bars should have hours 5, 6, 7, 8, 9
        assert bars[0].time.hour == 5
        assert bars[4].time.hour == 9


class TestDefaultMemoryLimits:
    """Tests for default memory limits."""

    def test_default_limits_applied(self) -> None:
        """Test that default limits are applied."""
        context = BacktestContext(initial_capital=Decimal("100000"))

        # Access internal deques to check maxlen
        assert context._equity_curve.maxlen == 10000
        assert context._completed_orders.maxlen == 1000
        assert context._fills.maxlen == 5000
        assert context._trades.maxlen == 1000
        assert context._logs.maxlen == 1000


class TestPropertiesReturnLists:
    """Tests that properties return proper list copies."""

    def test_equity_curve_returns_list(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that equity_curve property returns a list."""
        small_limits_context._set_current_bar(sample_bar)
        small_limits_context._record_equity_snapshot(sample_bar.time)

        result = small_limits_context.equity_curve
        assert isinstance(result, list)

    def test_completed_orders_returns_list(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that completed_orders property returns a list."""
        small_limits_context._set_current_bar(sample_bar)
        order_id = small_limits_context.buy("BTC/USDT", Decimal("0.1"))
        small_limits_context.cancel_order(order_id)

        result = small_limits_context.completed_orders
        assert isinstance(result, list)

    def test_fills_returns_list(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that fills property returns a list."""
        small_limits_context._set_current_bar(sample_bar)
        fill = Fill(
            order_id="test",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("0.01"),
            fee=Decimal("0.42"),
            timestamp=sample_bar.time,
        )
        small_limits_context._process_fill(fill)

        result = small_limits_context.fills
        assert isinstance(result, list)

    def test_logs_returns_list(
        self, small_limits_context: BacktestContext, sample_bar: Bar
    ) -> None:
        """Test that logs property returns a list."""
        small_limits_context._set_current_bar(sample_bar)
        small_limits_context.log("Test")

        result = small_limits_context.logs
        assert isinstance(result, list)
