"""Unit tests for backtest runner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from squant.engine.backtest.runner import (
    BacktestCancelledError,
    BacktestError,
    BacktestRunner,
    StrategyInstantiationError,
    run_backtest,
)
from squant.engine.backtest.types import BacktestResult, Bar


@pytest.fixture
def valid_strategy_code():
    """Create valid strategy code."""
    return '''
class MyStrategy(Strategy):
    """A simple test strategy."""

    def on_init(self):
        self.ctx.log("Strategy initialized")

    def on_bar(self, bar):
        # Simple buy and hold
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        self.ctx.log("Strategy stopped")
'''


@pytest.fixture
def simple_strategy_code():
    """Create simplest valid strategy code."""
    return """
class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""


@pytest.fixture
def invalid_strategy_code():
    """Create invalid strategy code (missing on_bar)."""
    return """
class BadStrategy(Strategy):
    def some_method(self):
        pass
"""


@pytest.fixture
def syntax_error_code():
    """Create code with syntax error."""
    return """
class MyStrategy(Strategy)
    def on_bar(self, bar):
        pass
"""


@pytest.fixture
def sample_bars():
    """Create sample bars for testing."""
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return [
        Bar(
            time=base_time + timedelta(hours=i),
            symbol="BTC/USDT",
            open=Decimal("50000") + Decimal(str(i * 100)),
            high=Decimal("51000") + Decimal(str(i * 100)),
            low=Decimal("49000") + Decimal(str(i * 100)),
            close=Decimal("50500") + Decimal(str(i * 100)),
            volume=Decimal("100"),
        )
        for i in range(10)
    ]


async def async_bar_iterator(bars: list[Bar]) -> AsyncIterator[Bar]:
    """Create async iterator from bars."""
    for bar in bars:
        yield bar


class TestBacktestRunnerInit:
    """Tests for BacktestRunner initialization."""

    def test_initialization(self, simple_strategy_code):
        """Test runner initialization with valid parameters."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test Strategy",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        assert runner.strategy_code == simple_strategy_code
        assert runner.strategy_name == "Test Strategy"
        assert runner.symbol == "BTC/USDT"
        assert runner.timeframe == "1h"
        assert runner.initial_capital == Decimal("10000")
        assert runner.commission_rate == Decimal("0.001")
        assert runner.slippage == Decimal("0")
        assert runner.params == {}

    def test_initialization_with_custom_params(self, simple_strategy_code):
        """Test runner initialization with custom parameters."""
        params = {"lookback": 20, "threshold": 0.5}
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test Strategy",
            symbol="ETH/USDT",
            timeframe="4h",
            initial_capital=Decimal("50000"),
            commission_rate=Decimal("0.002"),
            slippage=Decimal("0.001"),
            params=params,
        )

        assert runner.symbol == "ETH/USDT"
        assert runner.timeframe == "4h"
        assert runner.initial_capital == Decimal("50000")
        assert runner.commission_rate == Decimal("0.002")
        assert runner.slippage == Decimal("0.001")
        assert runner.params == params


class TestBacktestRunnerSetup:
    """Tests for BacktestRunner setup."""

    def test_setup_initializes_context(self, simple_strategy_code):
        """Test setup creates context with correct capital."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner._setup()

        assert runner._context is not None
        assert runner._context.initial_capital == Decimal("10000")
        assert runner._context.cash == Decimal("10000")

    def test_setup_initializes_matching_engine(self, simple_strategy_code):
        """Test setup creates matching engine."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.002"),
            slippage=Decimal("0.001"),
        )
        runner._setup()

        assert runner._matching_engine is not None
        assert runner._matching_engine.commission_rate == Decimal("0.002")
        assert runner._matching_engine.slippage == Decimal("0.001")

    def test_setup_instantiates_strategy(self, simple_strategy_code):
        """Test setup compiles and instantiates strategy."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner._setup()

        assert runner._strategy is not None
        assert runner._strategy.ctx == runner._context


class TestBacktestRunnerRun:
    """Tests for BacktestRunner run method."""

    @pytest.mark.asyncio
    async def test_run_processes_bars(self, simple_strategy_code, sample_bars):
        """Test run processes all bars."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))

        assert result.bar_count == 10
        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1h"

    @pytest.mark.asyncio
    async def test_run_returns_backtest_result(self, simple_strategy_code, sample_bars):
        """Test run returns proper BacktestResult."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test Strategy",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Test Strategy"
        assert result.initial_capital == Decimal("10000")
        assert result.start_time == sample_bars[0].time
        assert result.end_time == sample_bars[-1].time

    @pytest.mark.asyncio
    async def test_run_with_progress_callback(self, simple_strategy_code, sample_bars):
        """Test run calls progress callback."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        progress_calls = []

        def callback(current: int, total: int):
            progress_calls.append((current, total))

        await runner.run(
            async_bar_iterator(sample_bars),
            progress_callback=callback,
            total_bars=10,
        )

        assert len(progress_calls) == 10
        assert progress_calls[-1] == (10, 10)

    @pytest.mark.asyncio
    async def test_run_records_equity_curve(self, simple_strategy_code, sample_bars):
        """Test run records equity snapshots."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))

        assert len(result.equity_curve) == 10
        # First snapshot should have initial capital
        assert result.equity_curve[0].cash == Decimal("10000")

    @pytest.mark.asyncio
    async def test_run_empty_bars(self, simple_strategy_code):
        """Test run with no bars."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator([]))

        assert result.bar_count == 0


class TestStrategyInstantiation:
    """Tests for strategy instantiation."""

    def test_invalid_strategy_raises_error(self, invalid_strategy_code):
        """Test invalid strategy code raises error."""
        runner = BacktestRunner(
            strategy_code=invalid_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        with pytest.raises(StrategyInstantiationError):
            runner._setup()

    def test_syntax_error_raises_error(self, syntax_error_code):
        """Test syntax error raises error."""
        runner = BacktestRunner(
            strategy_code=syntax_error_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        with pytest.raises(StrategyInstantiationError):
            runner._setup()

    def test_no_strategy_class_raises_error(self):
        """Test code without Strategy class raises error."""
        code = """
def some_function():
    pass
"""
        runner = BacktestRunner(
            strategy_code=code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        with pytest.raises(StrategyInstantiationError):
            runner._setup()


class TestProcessBar:
    """Tests for bar processing."""

    def test_process_bar_updates_time_range(self, simple_strategy_code, sample_bars):
        """Test process_bar tracks start and end time."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner._setup()

        runner._process_bar(sample_bars[0])
        assert runner._start_time == sample_bars[0].time
        assert runner._end_time == sample_bars[0].time

        runner._process_bar(sample_bars[5])
        assert runner._start_time == sample_bars[0].time
        assert runner._end_time == sample_bars[5].time

    def test_process_bar_adds_to_history(self, simple_strategy_code, sample_bars):
        """Test process_bar adds bar to history."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner._setup()

        runner._process_bar(sample_bars[0])
        runner._process_bar(sample_bars[1])

        # Check context has bars in history
        closes = runner._context.get_closes(2)
        assert len(closes) == 2

    def test_equity_snapshot_recorded_before_strategy(self, sample_bars):
        """Test equity snapshot is taken before strategy on_bar (P0-1).

        This ensures consistent timing with live and paper engines.
        The snapshot should reflect pre-strategy portfolio state.
        """
        call_order = []

        # Strategy that records call order and modifies cash via buy
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        pass
    def on_bar(self, bar):
        pass
    def on_stop(self):
        pass
"""
        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner._setup()

        # Monkey-patch to track call order
        original_snapshot = runner._context._record_equity_snapshot
        original_on_bar = runner._strategy.on_bar

        def tracked_snapshot(time):
            call_order.append("snapshot")
            return original_snapshot(time)

        def tracked_on_bar(bar):
            call_order.append("on_bar")
            return original_on_bar(bar)

        runner._context._record_equity_snapshot = tracked_snapshot
        runner._strategy.on_bar = tracked_on_bar

        runner._process_bar(sample_bars[0])

        assert call_order == ["snapshot", "on_bar"]


class TestBuildResult:
    """Tests for result building."""

    @pytest.mark.asyncio
    async def test_build_result_includes_metrics(self, simple_strategy_code, sample_bars):
        """Test result includes performance metrics."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))

        assert "total_return" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "sharpe_ratio" in result.metrics

    @pytest.mark.asyncio
    async def test_build_result_includes_logs(self, valid_strategy_code, sample_bars):
        """Test result includes strategy logs."""
        runner = BacktestRunner(
            strategy_code=valid_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))

        # Strategy logs "Strategy initialized" in on_init
        assert any("initialized" in log.lower() for log in result.logs)


class TestRunBacktestFunction:
    """Tests for convenience run_backtest function."""

    @pytest.mark.asyncio
    async def test_run_backtest_function(self, simple_strategy_code, sample_bars):
        """Test run_backtest convenience function."""
        result = await run_backtest(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=async_bar_iterator(sample_bars),
            initial_capital=Decimal("10000"),
        )

        assert isinstance(result, BacktestResult)
        assert result.bar_count == 10

    @pytest.mark.asyncio
    async def test_run_backtest_with_params(self, simple_strategy_code, sample_bars):
        """Test run_backtest with strategy parameters."""
        params = {"test_param": 42}
        result = await run_backtest(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=async_bar_iterator(sample_bars),
            initial_capital=Decimal("10000"),
            params=params,
        )

        assert result is not None


class TestBacktestErrors:
    """Tests for error handling."""

    def test_backtest_error_is_exception(self):
        """Test BacktestError is an Exception."""
        error = BacktestError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_strategy_instantiation_error_is_backtest_error(self):
        """Test StrategyInstantiationError inherits from BacktestError."""
        error = StrategyInstantiationError("Strategy failed")
        assert isinstance(error, BacktestError)
        assert "Strategy failed" in str(error)

    @pytest.mark.asyncio
    async def test_strategy_on_bar_error_caught_and_continues(self, sample_bars):
        """Test that strategy on_bar errors are caught and backtest continues.

        The runner catches exceptions from on_bar(), logs them, and
        continues processing remaining bars — it does NOT wrap them
        in BacktestError or propagate them.
        """
        error_code = """
class ErrorStrategy(Strategy):
    def on_bar(self, bar):
        raise RuntimeError("Test error")
"""
        runner = BacktestRunner(
            strategy_code=error_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        result = await runner.run(async_bar_iterator(sample_bars))
        assert result is not None
        # All bars processed despite errors
        assert result.bar_count == len(sample_bars)
        # Errors logged in context
        assert any("ERROR" in log for log in result.logs)


class TestBacktestCancellation:
    """Tests for backtest cancellation (TRD-008#3)."""

    def test_cancel_sets_flag(self, simple_strategy_code):
        """Test cancel method sets cancelled flag."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        assert runner.is_cancelled is False
        runner.cancel()
        assert runner.is_cancelled is True

    def test_set_run_id(self, simple_strategy_code):
        """Test set_run_id method."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        assert runner._run_id is None
        runner.set_run_id("test-run-id")
        assert runner._run_id == "test-run-id"

    @pytest.mark.asyncio
    async def test_run_cancelled_raises_error(self, simple_strategy_code, sample_bars):
        """Test cancelled run raises BacktestCancelledError."""
        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner.set_run_id("test-run-123")

        # Cancel immediately
        runner.cancel()

        with pytest.raises(BacktestCancelledError) as exc_info:
            await runner.run(async_bar_iterator(sample_bars))

        assert "test-run-123" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_cancelled_mid_execution(self, simple_strategy_code):
        """Test cancellation during bar processing."""
        # Create many bars to ensure we can cancel mid-execution
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        many_bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(100)
        ]

        runner = BacktestRunner(
            strategy_code=simple_strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )
        runner.set_run_id("test-run-456")

        # Create iterator that cancels after 5 bars
        async def cancelling_iterator():
            for i, bar in enumerate(many_bars):
                if i == 5:
                    runner.cancel()
                yield bar

        with pytest.raises(BacktestCancelledError):
            await runner.run(cancelling_iterator())

        # Cancel is set when iterator yields bar at index 5.
        # The cancel check happens before processing each bar.
        # So bars 0-4 are processed (5 bars), and bar 5 triggers the cancel check.
        assert runner._bar_count == 5

    def test_backtest_cancelled_error(self):
        """Test BacktestCancelledError formatting."""
        # With run_id
        error = BacktestCancelledError("run-123")
        assert "run-123" in str(error)
        assert error.run_id == "run-123"
        assert isinstance(error, BacktestError)

        # Without run_id
        error2 = BacktestCancelledError()
        assert "cancelled" in str(error2).lower()
        assert error2.run_id is None


class TestLimitOrderExpiry:
    """Tests for limit order bars_remaining expiry in backtest."""

    @pytest.mark.asyncio
    async def test_limit_order_expires_after_valid_for_bars(self):
        """Test that limit orders with valid_for_bars expire after N bars."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.placed = False

    def on_bar(self, bar):
        if not self.placed:
            # Place a limit buy far below market — should never fill
            self.ctx.buy(bar.symbol, Decimal("0.01"),
                         price=Decimal("10000"), valid_for_bars=3)
            self.placed = True
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(6)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Order should be cancelled (expired), not filled
        assert len(result.trades) == 0
        cancelled = [o for o in result.orders if o.status.value == "cancelled"]
        assert len(cancelled) == 1
        # Verify log mentions expiry
        assert any("订单过期" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_limit_order_without_valid_for_bars_stays_active(self):
        """Test that limit orders without valid_for_bars (GTC) never expire."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.placed = False

    def on_bar(self, bar):
        if not self.placed:
            # GTC limit buy far below market
            self.ctx.buy(bar.symbol, Decimal("0.01"),
                         price=Decimal("10000"))
            self.placed = True
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(10)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # GTC order should still be pending (not cancelled, not filled)
        assert len(result.trades) == 0
        cancelled = [o for o in result.orders if o.status.value == "cancelled"]
        assert len(cancelled) == 0


class TestStopOrderRunner:
    """Tests for stop orders in backtest runner end-to-end."""

    async def test_sell_stop_triggers_and_fills(self):
        """Strategy places a sell stop that triggers on a subsequent bar."""
        strategy_code = '''
class MyStrategy(Strategy):
    def on_init(self):
        self.bought = False
        self.stop_placed = False

    def on_bar(self, bar):
        from decimal import Decimal
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("1"))
            self.bought = True
        elif not self.stop_placed and self.ctx.has_position(bar.symbol):
            # Set stop loss at 40000
            self.ctx.sell(bar.symbol, Decimal("1"), stop_price=Decimal("40000"))
            self.stop_placed = True
'''
        # Bar 0: buy at open
        # Bar 1: place stop at 40000 (price above stop, no trigger)
        # Bar 2: price drops → stop triggers
        bars = [
            Bar(
                time=datetime(2024, 1, 1, 0, i, tzinfo=UTC),
                symbol="BTC/USDT",
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("100"),
            )
            for i, (open_p, high_p, low_p, close_p) in enumerate([
                (Decimal("42000"), Decimal("43000"), Decimal("41000"), Decimal("42500")),
                (Decimal("42500"), Decimal("43000"), Decimal("41500"), Decimal("42000")),
                (Decimal("41000"), Decimal("41500"), Decimal("39500"), Decimal("40000")),
            ])
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="StopTest",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Should have 1 completed trade (buy + sell stop)
        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.exit_price is not None
        # Stop triggered at bar 2: min(stop=40000, open=41000) = 40000
        assert trade.exit_price == Decimal("40000")

    async def test_stop_order_expires_with_bars_remaining(self):
        """Stop order with valid_for_bars expires after N bars."""
        strategy_code = '''
class MyStrategy(Strategy):
    def on_init(self):
        self.bought = False
        self.stop_placed = False

    def on_bar(self, bar):
        from decimal import Decimal
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("1"))
            self.bought = True
        elif not self.stop_placed and self.ctx.has_position(bar.symbol):
            self.ctx.sell(bar.symbol, Decimal("1"), stop_price=Decimal("38000"), valid_for_bars=2)
            self.stop_placed = True
'''
        # Bar 0: buy
        # Bar 1: place stop at 38000 (valid_for_bars=2)
        # Bar 2: no trigger, bars_remaining 2→1
        # Bar 3: no trigger, bars_remaining 1→0 → cancelled
        bars = [
            Bar(
                time=datetime(2024, 1, 1, 0, i, tzinfo=UTC),
                symbol="BTC/USDT",
                open=Decimal("42000"),
                high=Decimal("43000"),
                low=Decimal("41000"),
                close=Decimal("42500"),
                volume=Decimal("100"),
            )
            for i in range(4)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="StopExpiryTest",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Stop should have expired without triggering
        cancelled = [o for o in result.orders if o.status.value == "cancelled"]
        assert len(cancelled) == 1
        assert cancelled[0].stop_price == Decimal("38000")


class TestStrategyCallbacks:
    """Tests for on_fill and on_order_done strategy callbacks."""

    @pytest.mark.asyncio
    async def test_on_fill_called_on_market_order_fill(self):
        """Test on_fill is called when a market order is filled."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.fill_count = 0

    def on_fill(self, fill):
        self.fill_count = self.fill_count + 1
        self.ctx.log(f"on_fill:{fill.symbol}:{fill.side.value}")

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        self.ctx.log(f"fills_received={self.fill_count}")
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Buy on bar 0, fill on bar 1 → 1 fill
        assert any("fills_received=1" in log for log in result.logs)
        assert len(result.fills) == 1

    @pytest.mark.asyncio
    async def test_on_order_done_called_on_filled_order(self):
        """Test on_order_done is called when order reaches FILLED status."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.done_statuses = ""

    def on_order_done(self, order):
        self.done_statuses = self.done_statuses + order.status.value + ","

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        self.ctx.log(f"done_statuses={self.done_statuses}")
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Verify on_order_done was called with FILLED status
        assert any("done_statuses=filled," in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_on_order_done_called_on_expired_limit(self):
        """Test on_order_done is called when a limit order expires."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.placed = False
        self.cancelled_count = 0

    def on_order_done(self, order):
        if order.status == OrderStatus.CANCELLED:
            self.cancelled_count = self.cancelled_count + 1

    def on_bar(self, bar):
        if not self.placed:
            # Limit buy far below market, expires in 2 bars
            self.ctx.buy(bar.symbol, Decimal("0.01"),
                         price=Decimal("10000"), valid_for_bars=2)
            self.placed = True

    def on_stop(self):
        self.ctx.log(f"cancelled_count={self.cancelled_count}")
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Limit order expires → on_order_done with CANCELLED
        assert any("cancelled_count=1" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_on_fill_error_does_not_crash_backtest(self):
        """Test that errors in on_fill are caught and don't crash the backtest."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_fill(self, fill):
        raise RuntimeError("on_fill error")

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Backtest completes despite on_fill error
        assert result.bar_count == 5
        assert any("ERROR in on_fill" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_on_order_done_error_does_not_crash_backtest(self):
        """Test that errors in on_order_done are caught and don't crash the backtest."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_order_done(self, order):
        raise RuntimeError("on_order_done error")

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Backtest completes despite on_order_done error
        assert result.bar_count == 5
        assert any("ERROR in on_order_done" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_on_fill_can_place_orders(self):
        """Test that strategy can place orders from on_fill callback (e.g., stop-loss after buy)."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.stop_placed = False

    def on_fill(self, fill):
        # Place a stop-loss after buy fill
        if fill.side.value == "buy" and not self.stop_placed:
            self.ctx.sell(fill.symbol, fill.amount,
                         stop_price=Decimal("40000"))
            self.stop_placed = True

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        self.ctx.log(f"stop_placed={self.stop_placed}")
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Stop-loss was placed from on_fill
        assert any("stop_placed=True" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_on_fill_called_before_on_bar(self):
        """Test that on_fill is called before on_bar on the same bar."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_init(self):
        self.call_order = ""

    def on_fill(self, fill):
        self.call_order = self.call_order + "on_fill|"

    def on_bar(self, bar):
        self.call_order = self.call_order + "on_bar|"
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        self.ctx.log(f"order={self.call_order}")
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(3)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        # Find the call order log (has timestamp prefix like "[2024-01-01 12:00:00+00:00] order=...")
        order_log = [log for log in result.logs if "order=" in log]
        assert len(order_log) == 1
        # Extract the order part after "order="
        order_str = order_log[0].split("order=")[1]
        calls = order_str.strip("|").split("|")
        # Bar 0: on_bar (buy order placed)
        # Bar 1: on_fill (fill delivered), on_bar
        # Bar 2: on_bar
        assert calls[0] == "on_bar"  # bar 0
        assert calls[1] == "on_fill"  # bar 1, fill first
        assert calls[2] == "on_bar"  # bar 1, then on_bar

    @pytest.mark.asyncio
    async def test_fill_and_orderstatus_types_available_in_sandbox(self):
        """Test that Fill and OrderStatus types are accessible in strategy sandbox."""
        strategy_code = """
class MyStrategy(Strategy):
    def on_fill(self, fill):
        # Verify Fill type is accessible
        assert isinstance(fill, Fill)
        self.ctx.log(f"fill_type_ok={isinstance(fill, Fill)}")

    def on_order_done(self, order):
        # Verify OrderStatus is accessible
        is_filled = order.status == OrderStatus.FILLED
        self.ctx.log(f"status_check_ok={is_filled}")

    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
            )
            for i in range(5)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        result = await runner.run(async_bar_iterator(bars))

        assert any("fill_type_ok=True" in log for log in result.logs)
        assert any("status_check_ok=True" in log for log in result.logs)
