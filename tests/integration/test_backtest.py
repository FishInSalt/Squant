"""Integration tests for backtest engine."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.engine.backtest.runner import BacktestRunner, run_backtest
from squant.engine.backtest.types import Bar


async def create_sample_bars(
    symbol: str = "BTC/USDT",
    start_price: Decimal = Decimal("42000"),
    num_bars: int = 100,
    trend: str = "up",
) -> AsyncIterator[Bar]:
    """Generate sample bar data for testing."""
    price = start_price
    for i in range(num_bars):
        # Simple price movement
        if trend == "up":
            change = Decimal("100")
        elif trend == "down":
            change = Decimal("-100")
        else:  # sideways
            change = Decimal("0")

        # Add some noise
        noise = Decimal(str(i % 50 - 25))
        open_price = price
        close_price = price + change + noise
        high = max(open_price, close_price) + Decimal("50")
        low = min(open_price, close_price) - Decimal("50")

        yield Bar(
            time=datetime(2024, 1, 1, i % 24, tzinfo=UTC),
            symbol=symbol,
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=Decimal("1000"),
        )

        price = close_price


class TestBacktestRunner:
    """Integration tests for BacktestRunner."""

    @pytest.mark.asyncio
    async def test_simple_strategy_execution(self) -> None:
        """Test running a simple strategy."""
        strategy_code = """
class TestStrategy(Strategy):
    def on_init(self):
        self.bought = False

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("0.1"))
            self.bought = True
"""

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="TestStrategy",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
        )

        bars = create_sample_bars(num_bars=10)
        result = await runner.run(bars)

        # Check result structure
        assert result.strategy_name == "TestStrategy"
        assert result.symbol == "BTC/USDT"
        assert result.bar_count == 10
        assert result.initial_capital == Decimal("100000")
        assert len(result.equity_curve) == 10

    @pytest.mark.asyncio
    async def test_dual_ma_strategy(self) -> None:
        """Test a dual moving average strategy."""
        strategy_code = """
class DualMA(Strategy):
    def on_init(self):
        self.fast_period = self.ctx.params.get("fast", 5)
        self.slow_period = self.ctx.params.get("slow", 10)

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.slow_period)
        if len(closes) < self.slow_period:
            return

        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes) / self.slow_period

        pos = self.ctx.get_position(bar.symbol)

        if fast_ma > slow_ma and not pos:
            self.ctx.buy(bar.symbol, Decimal("0.1"))
        elif fast_ma < slow_ma and pos:
            self.ctx.sell(bar.symbol, pos.amount)
"""

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="DualMA",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"fast": 3, "slow": 5},
        )

        bars = create_sample_bars(num_bars=50, trend="up")
        result = await runner.run(bars)

        # Should have made some trades
        assert result.bar_count == 50
        assert len(result.orders) > 0

    @pytest.mark.asyncio
    async def test_strategy_with_logging(self) -> None:
        """Test strategy logging functionality."""
        strategy_code = """
class LoggingStrategy(Strategy):
    def on_init(self):
        self.ctx.log("Strategy initialized")

    def on_bar(self, bar):
        self.ctx.log(f"Processing bar at {bar.close}")

    def on_stop(self):
        self.ctx.log("Strategy stopped")
"""

        result = await run_backtest(
            strategy_code=strategy_code,
            strategy_name="LoggingStrategy",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=create_sample_bars(num_bars=5),
            initial_capital=Decimal("10000"),
        )

        assert len(result.logs) >= 7  # init + 5 bars + stop
        assert any("initialized" in log for log in result.logs)
        assert any("stopped" in log for log in result.logs)

    @pytest.mark.asyncio
    async def test_metrics_calculated(self) -> None:
        """Test that metrics are calculated."""
        strategy_code = """
class BuyAndHold(Strategy):
    def on_init(self):
        self.bought = False

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("1"))
            self.bought = True
"""

        result = await run_backtest(
            strategy_code=strategy_code,
            strategy_name="BuyAndHold",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=create_sample_bars(num_bars=100, trend="up"),
            initial_capital=Decimal("100000"),
        )

        # Check metrics are present
        assert "total_return" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "total_trades" in result.metrics

    @pytest.mark.asyncio
    async def test_commission_deducted(self) -> None:
        """Test that commission is deducted from trades."""
        strategy_code = """
class SingleTrade(Strategy):
    def on_init(self):
        self.traded = False

    def on_bar(self, bar):
        if not self.traded:
            self.ctx.buy(bar.symbol, Decimal("1"))
            self.traded = True
"""

        result = await run_backtest(
            strategy_code=strategy_code,
            strategy_name="SingleTrade",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=create_sample_bars(num_bars=10),
            initial_capital=Decimal("100000"),
            commission_rate=Decimal("0.001"),  # 0.1%
        )

        # There should be fills with fees
        fills = [o for o in result.orders if o.filled > 0]
        assert len(fills) > 0


class TestRunBacktestFunction:
    """Tests for the run_backtest convenience function."""

    @pytest.mark.asyncio
    async def test_run_backtest_convenience(self) -> None:
        """Test the convenience function."""
        strategy_code = """
class Simple(Strategy):
    def on_bar(self, bar):
        pass
"""

        result = await run_backtest(
            strategy_code=strategy_code,
            strategy_name="Simple",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=create_sample_bars(num_bars=10),
            initial_capital=Decimal("10000"),
        )

        assert result.bar_count == 10
        assert result.final_equity == Decimal("10000")  # No trades


class TestErrorHandling:
    """Tests for error handling in backtest."""

    @pytest.mark.asyncio
    async def test_invalid_strategy_code_raises(self) -> None:
        """Test that invalid strategy code raises error."""
        strategy_code = """
class NotAStrategy:
    def on_bar(self, bar):
        pass
"""

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Invalid",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("10000"),
        )

        with pytest.raises(Exception):  # Should raise some error
            await runner.run(create_sample_bars(num_bars=1))

    @pytest.mark.asyncio
    async def test_strategy_error_logged(self) -> None:
        """Test that strategy errors are logged but don't crash backtest."""
        strategy_code = """
class ErrorStrategy(Strategy):
    def on_bar(self, bar):
        if self.ctx.get_closes(5):  # Will work after 5 bars
            raise ValueError("Intentional error for testing")
"""

        result = await run_backtest(
            strategy_code=strategy_code,
            strategy_name="ErrorStrategy",
            symbol="BTC/USDT",
            timeframe="1h",
            bars=create_sample_bars(num_bars=10),
            initial_capital=Decimal("10000"),
        )

        # Backtest should complete despite errors
        assert result.bar_count == 10
        # Errors should be logged
        assert any("ERROR" in log for log in result.logs)
