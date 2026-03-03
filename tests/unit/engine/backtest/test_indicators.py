"""Unit tests for built-in technical indicators."""

from decimal import Decimal

import pytest

from squant.engine.backtest.indicators import (
    atr,
    bollinger_bands,
    crossover,
    crossunder,
    ema,
    highest,
    lowest,
    macd,
    rsi,
    sma,
    stdev,
)


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_basic_sma(self):
        data = [Decimal(str(x)) for x in [10, 20, 30, 40, 50]]
        assert sma(data, 3) == Decimal("40")  # (30+40+50)/3
        assert sma(data, 5) == Decimal("30")  # (10+20+30+40+50)/5

    def test_insufficient_data(self):
        data = [Decimal("10"), Decimal("20")]
        assert sma(data, 3) is None

    def test_period_equals_length(self):
        data = [Decimal(str(x)) for x in [10, 20, 30]]
        assert sma(data, 3) == Decimal("20")

    def test_period_one(self):
        data = [Decimal("42")]
        assert sma(data, 1) == Decimal("42")

    def test_invalid_period(self):
        assert sma([Decimal("1")], 0) is None


class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_basic_ema(self):
        data = [Decimal(str(x)) for x in range(1, 11)]
        result = ema(data, 5)
        assert result is not None
        # EMA should be close to recent values (weighted toward end)
        assert result > Decimal("5")

    def test_insufficient_data(self):
        assert ema([Decimal("10")], 5) is None

    def test_ema_single_value(self):
        data = [Decimal("100")]
        assert ema(data, 1) == Decimal("100")

    def test_ema_trending_up(self):
        data = [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70]]
        result = ema(data, 3)
        assert result is not None
        # EMA tracks trend, should be between simple average and last value
        assert result > Decimal("40") and result < Decimal("70")


class TestRSI:
    """Tests for Relative Strength Index."""

    def test_rsi_overbought(self):
        """Strongly rising prices should give RSI near 100."""
        data = [Decimal(str(x * 100)) for x in range(20)]
        result = rsi(data, 14)
        assert result is not None
        assert result > Decimal("70")

    def test_rsi_oversold(self):
        """Strongly falling prices should give RSI near 0."""
        data = [Decimal(str(2000 - x * 100)) for x in range(20)]
        result = rsi(data, 14)
        assert result is not None
        assert result < Decimal("30")

    def test_rsi_insufficient_data(self):
        data = [Decimal(str(x)) for x in range(10)]
        assert rsi(data, 14) is None

    def test_rsi_all_gains(self):
        """All gains should give RSI = 100."""
        data = [Decimal(str(x)) for x in range(1, 20)]
        result = rsi(data, 14)
        assert result is not None
        assert result == Decimal("100")


class TestMACD:
    """Tests for MACD."""

    def test_macd_returns_tuple(self):
        # Need at least slow + signal - 1 = 26 + 9 - 1 = 34 data points
        data = [Decimal(str(100 + x)) for x in range(40)]
        result = macd(data)
        assert result is not None
        macd_line, signal_line, histogram = result
        assert isinstance(macd_line, Decimal)
        assert isinstance(signal_line, Decimal)
        assert abs(histogram - (macd_line - signal_line)) < Decimal("0.0001")

    def test_macd_insufficient_data(self):
        data = [Decimal(str(x)) for x in range(20)]
        assert macd(data) is None


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bollinger_basic(self):
        data = [Decimal(str(x)) for x in range(1, 25)]
        result = bollinger_bands(data, 20)
        assert result is not None
        upper, middle, lower = result
        assert upper > middle
        assert middle > lower
        # Middle should be SMA
        expected_middle = sma(data, 20)
        assert middle == expected_middle

    def test_bollinger_insufficient_data(self):
        data = [Decimal(str(x)) for x in range(10)]
        assert bollinger_bands(data, 20) is None


class TestATR:
    """Tests for Average True Range."""

    def test_atr_basic(self):
        n = 20
        highs = [Decimal(str(110 + i)) for i in range(n)]
        lows = [Decimal(str(90 + i)) for i in range(n)]
        closes = [Decimal(str(100 + i)) for i in range(n)]
        result = atr(highs, lows, closes, 14)
        assert result is not None
        assert result > Decimal("0")

    def test_atr_insufficient_data(self):
        highs = [Decimal("110")]
        lows = [Decimal("90")]
        closes = [Decimal("100")]
        assert atr(highs, lows, closes, 14) is None

    def test_atr_constant_range(self):
        """Constant high-low range should give ATR close to that range."""
        n = 20
        highs = [Decimal("110")] * n
        lows = [Decimal("90")] * n
        closes = [Decimal("100")] * n
        result = atr(highs, lows, closes, 14)
        assert result is not None
        # True range = 20 for each bar
        assert abs(result - Decimal("20")) < Decimal("1")


class TestStdev:
    """Tests for standard deviation."""

    def test_stdev_basic(self):
        data = [Decimal(str(x)) for x in [10, 20, 30, 40, 50]]
        result = stdev(data, 5)
        assert result is not None
        # Population stdev of [10,20,30,40,50] = sqrt(200) ≈ 14.14
        assert abs(result - Decimal("14.14")) < Decimal("0.1")

    def test_stdev_constant(self):
        data = [Decimal("42")] * 10
        assert stdev(data, 5) == Decimal("0")

    def test_stdev_insufficient_data(self):
        assert stdev([Decimal("1")], 5) is None


class TestHighestLowest:
    """Tests for highest/lowest."""

    def test_highest(self):
        data = [Decimal(str(x)) for x in [10, 50, 30, 20, 40]]
        assert highest(data, 3) == Decimal("40")  # last 3: [30, 20, 40]
        assert highest(data, 5) == Decimal("50")

    def test_lowest(self):
        data = [Decimal(str(x)) for x in [10, 50, 30, 20, 40]]
        assert lowest(data, 3) == Decimal("20")  # last 3: [30, 20, 40]
        assert lowest(data, 5) == Decimal("10")

    def test_insufficient_data(self):
        assert highest([Decimal("1")], 5) is None
        assert lowest([Decimal("1")], 5) is None


class TestCrossover:
    """Tests for crossover/crossunder."""

    def test_crossover_true(self):
        fast = [Decimal("10"), Decimal("21")]
        slow = [Decimal("20"), Decimal("20")]
        assert crossover(fast, slow) is True

    def test_crossover_false(self):
        fast = [Decimal("21"), Decimal("22")]
        slow = [Decimal("20"), Decimal("20")]
        assert crossover(fast, slow) is False

    def test_crossunder_true(self):
        fast = [Decimal("21"), Decimal("19")]
        slow = [Decimal("20"), Decimal("20")]
        assert crossunder(fast, slow) is True

    def test_crossunder_false(self):
        fast = [Decimal("19"), Decimal("18")]
        slow = [Decimal("20"), Decimal("20")]
        assert crossunder(fast, slow) is False

    def test_insufficient_data(self):
        assert crossover([Decimal("1")], [Decimal("2")]) is False
        assert crossunder([Decimal("1")], [Decimal("2")]) is False


class TestSandboxIntegration:
    """Test that indicators are accessible from strategy sandbox."""

    @pytest.mark.asyncio
    async def test_ta_module_in_sandbox(self):
        """Verify ta module is injected and usable in strategy code."""
        from collections.abc import AsyncIterator
        from datetime import UTC, datetime, timedelta

        from squant.engine.backtest.runner import BacktestRunner
        from squant.engine.backtest.types import Bar

        strategy_code = """
class MyStrategy(Strategy):
    def on_bar(self, bar):
        closes = self.ctx.get_closes(20)
        if len(closes) >= 20:
            sma_val = ta.sma(closes, 20)
            ema_val = ta.ema(closes, 10)
            rsi_val = ta.rsi(closes, 14)
            if sma_val is not None:
                self.ctx.log(f"sma={sma_val}")
            if rsi_val is not None:
                self.ctx.log(f"rsi={rsi_val}")
"""
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                time=base_time + timedelta(hours=i),
                symbol="BTC/USDT",
                open=Decimal(str(50000 + i * 100)),
                high=Decimal(str(51000 + i * 100)),
                low=Decimal(str(49000 + i * 100)),
                close=Decimal(str(50500 + i * 100)),
                volume=Decimal("100"),
            )
            for i in range(25)
        ]

        runner = BacktestRunner(
            strategy_code=strategy_code,
            strategy_name="Test",
            symbol="BTC/USDT",
            timeframe="1h",
            initial_capital=Decimal("100000"),
        )

        async def bar_iter() -> AsyncIterator[Bar]:
            for b in bars:
                yield b

        result = await runner.run(bar_iter())
        assert result.bar_count == 25
        assert any("sma=" in log for log in result.logs)
        assert any("rsi=" in log for log in result.logs)
