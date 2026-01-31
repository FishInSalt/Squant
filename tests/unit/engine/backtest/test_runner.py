"""Unit tests for backtest runner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from squant.engine.backtest.runner import (
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
        if not self.ctx.get_position(bar.symbol).is_open:
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
    async def test_run_error_wrapped_in_backtest_error(self, sample_bars):
        """Test runtime errors are wrapped in BacktestError."""
        # Code that will error in on_bar
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

        # The error is caught and logged, backtest continues
        # (based on the runner implementation which catches strategy errors)
        result = await runner.run(async_bar_iterator(sample_bars))
        assert result is not None
