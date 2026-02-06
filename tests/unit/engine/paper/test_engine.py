"""Unit tests for paper trading engine."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.paper.engine import PaperTradingEngine
from squant.infra.exchange.okx.ws_types import WSCandle


class SimpleStrategy(Strategy):
    """Simple test strategy that buys when price is below threshold."""

    def on_init(self) -> None:
        self.threshold = self.ctx.params.get("threshold", Decimal("50000"))
        self.buy_executed = False

    def on_bar(self, bar: Bar) -> None:
        if bar.close < self.threshold and not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
            self.buy_executed = True

    def on_stop(self) -> None:
        pass


@pytest.fixture
def run_id():
    """Generate a unique run ID."""
    return uuid4()


@pytest.fixture
def strategy():
    """Create a simple test strategy."""
    return SimpleStrategy()


@pytest.fixture
def engine(run_id, strategy):
    """Create a paper trading engine for testing."""
    return PaperTradingEngine(
        run_id=run_id,
        strategy=strategy,
        symbol="BTC/USDT",
        timeframe="1m",
        initial_capital=Decimal("10000"),
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
        params={"threshold": Decimal("50000")},
    )


class TestPaperTradingEngineInit:
    """Tests for engine initialization."""

    def test_engine_creation(self, engine, run_id):
        """Test engine is created with correct attributes."""
        assert engine.run_id == run_id
        assert engine.symbol == "BTC/USDT"
        assert engine.timeframe == "1m"
        assert engine.is_running is False
        assert engine.bar_count == 0

    def test_context_initialized(self, engine):
        """Test that context is properly initialized."""
        assert engine.context.cash == Decimal("10000")
        assert engine.context.initial_capital == Decimal("10000")
        assert engine.context.params.get("threshold") == Decimal("50000")

    def test_strategy_has_context(self, engine, strategy):
        """Test that strategy has context injected."""
        assert strategy.ctx is engine.context


class TestPaperTradingEngineLifecycle:
    """Tests for engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_engine(self, engine, strategy):
        """Test starting the engine."""
        await engine.start()

        assert engine.is_running is True
        assert engine.started_at is not None
        # Strategy on_init was called
        assert hasattr(strategy, "threshold")

    @pytest.mark.asyncio
    async def test_stop_engine(self, engine):
        """Test stopping the engine."""
        await engine.start()
        await engine.stop()

        assert engine.is_running is False
        assert engine.stopped_at is not None

    @pytest.mark.asyncio
    async def test_stop_with_error(self, engine):
        """Test stopping the engine with an error message."""
        await engine.start()
        await engine.stop(error="Test error")

        assert engine.is_running is False
        assert engine.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_double_start_warns(self, engine):
        """Test that starting twice doesn't cause issues."""
        await engine.start()
        await engine.start()  # Should log warning but not fail

        assert engine.is_running is True


class TestCandleProcessing:
    """Tests for candle processing."""

    @pytest.fixture
    def closed_candle(self):
        """Create a closed candle for testing."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.fixture
    def unclosed_candle(self):
        """Create an unclosed candle for testing."""
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=False,
        )

    @pytest.mark.asyncio
    async def test_process_closed_candle(self, engine, strategy, closed_candle):
        """Test that closed candles are processed."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 1
        assert engine.context.current_bar is not None
        assert engine.context.current_bar.close == Decimal("45500")
        # Strategy should have executed buy (price 45500 < threshold 50000)
        assert strategy.buy_executed is True

    @pytest.mark.asyncio
    async def test_skip_unclosed_candle(self, engine, unclosed_candle):
        """Test that unclosed candles are skipped."""
        await engine.start()
        await engine.process_candle(unclosed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_skip_when_not_running(self, engine, closed_candle):
        """Test that candles are skipped when engine is not running."""
        # Don't start the engine
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_skip_wrong_symbol(self, engine, closed_candle):
        """Test that candles for wrong symbol are skipped."""
        await engine.start()
        closed_candle.symbol = "ETH/USDT"
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 0

    @pytest.mark.asyncio
    async def test_equity_recorded(self, engine, closed_candle):
        """Test that equity snapshots are recorded."""
        await engine.start()
        await engine.process_candle(closed_candle)

        assert len(engine.context.equity_curve) == 1
        snapshot = engine.context.equity_curve[0]
        assert snapshot.time == closed_candle.timestamp


class TestOrderMatching:
    """Tests for order matching during candle processing."""

    @pytest.mark.asyncio
    async def test_market_order_filled_on_next_bar(self, engine, strategy):
        """Test that market orders are filled on the next bar."""
        await engine.start()

        # First bar: strategy places order (price < threshold)
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle1)

        # Should have pending orders
        assert len(engine.context.pending_orders) == 1

        # Second bar: order gets filled at open
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("46000"),
            high=Decimal("47000"),
            low=Decimal("45000"),
            close=Decimal("46500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle2)

        # Order should be filled now
        assert len(engine.context.pending_orders) == 0
        assert len(engine.context.completed_orders) == 1
        assert engine.context.has_position("BTC/USDT")


class TestStateSnapshot:
    """Tests for state snapshot functionality."""

    @pytest.mark.asyncio
    async def test_state_snapshot(self, engine):
        """Test that state snapshot contains correct data."""
        await engine.start()

        snapshot = engine.get_state_snapshot()

        assert snapshot["run_id"] == str(engine.run_id)
        assert snapshot["symbol"] == "BTC/USDT"
        assert snapshot["timeframe"] == "1m"
        assert snapshot["is_running"] is True
        assert snapshot["bar_count"] == 0
        assert Decimal(snapshot["cash"]) == Decimal("10000")
        assert Decimal(snapshot["equity"]) == Decimal("10000")
        assert snapshot["positions"] == {}
        assert snapshot["pending_orders"] == []

    @pytest.mark.asyncio
    async def test_state_snapshot_with_position(self, engine, strategy):
        """Test snapshot includes position data after trading."""
        await engine.start()

        # Process two candles to get a filled position
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle1)

        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("46000"),
            high=Decimal("47000"),
            low=Decimal("45000"),
            close=Decimal("46500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle2)

        snapshot = engine.get_state_snapshot()

        assert "BTC/USDT" in snapshot["positions"]
        assert Decimal(snapshot["positions"]["BTC/USDT"]["amount"]) == Decimal("0.1")


class TestPendingSnapshots:
    """Tests for pending snapshot management."""

    @pytest.mark.asyncio
    async def test_pending_snapshots_collected(self, engine):
        """Test that pending snapshots are collected."""
        await engine.start()

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process multiple candles
        for i in range(5):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(candle)

        snapshots = engine.get_pending_snapshots()
        assert len(snapshots) == 5

        # After getting, should be cleared
        assert len(engine.get_pending_snapshots()) == 0

    @pytest.mark.asyncio
    async def test_should_persist_snapshots(self, engine):
        """Test persistence threshold check."""
        await engine.start()

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process bars below batch size
        for i in range(5):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(candle)

        assert engine.should_persist_snapshots() is False

        # Process more to exceed batch size (default is 10)
        for i in range(5, 10):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC)
            await engine.process_candle(candle)

        assert engine.should_persist_snapshots() is True


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_last_active_at_set_on_start(self, engine):
        """Test that last_active_at is set when engine starts."""
        assert engine.last_active_at is None

        await engine.start()

        assert engine.last_active_at is not None

    @pytest.mark.asyncio
    async def test_last_active_at_updated_on_candle(self, engine):
        """Test that last_active_at is updated when processing candles."""
        await engine.start()
        initial_time = engine.last_active_at

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle)

        assert engine.last_active_at >= initial_time

    @pytest.mark.asyncio
    async def test_is_healthy_returns_true_when_active(self, engine):
        """Test is_healthy returns True when recently active."""
        await engine.start()

        assert engine.is_healthy(timeout_seconds=300) is True

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_not_running(self, engine):
        """Test is_healthy returns False when not running."""
        # Engine not started
        assert engine.is_healthy(timeout_seconds=300) is False


class TestProcessingLock:
    """Tests for processing lock (PP-C05)."""

    @pytest.mark.asyncio
    async def test_stop_waits_for_processing_candle(self, engine, strategy):
        """Test that stop() waits for in-progress candle processing to complete."""
        import asyncio

        await engine.start()

        # Acquire the processing lock to simulate in-progress candle
        async with engine._processing_lock:
            # Start stop() in background — it should block on the lock
            stop_task = asyncio.create_task(engine.stop())

            # Give the event loop a chance to process
            await asyncio.sleep(0.05)

            # Engine should still be running because stop is waiting for lock
            assert engine.is_running is True

        # Now the lock is released, stop should complete
        await stop_task
        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_stopped(self, engine):
        """Test is_healthy returns False after stop."""
        await engine.start()
        await engine.stop()

        assert engine.is_healthy(timeout_seconds=300) is False

    @pytest.mark.asyncio
    async def test_is_healthy_with_zero_timeout(self, engine):
        """Test is_healthy with very short timeout."""
        await engine.start()

        # With 0 second timeout, should be considered unhealthy
        # since any elapsed time > 0
        import asyncio

        await asyncio.sleep(0.01)
        assert engine.is_healthy(timeout_seconds=0) is False


class FailingOnInitStrategy(Strategy):
    """Strategy that raises in on_init."""

    def on_init(self) -> None:
        raise ValueError("Strategy init failed")

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


class FailingOnBarStrategy(Strategy):
    """Strategy that raises in on_bar."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        raise RuntimeError("Strategy on_bar crashed")

    def on_stop(self) -> None:
        pass


class FailingOnStopStrategy(Strategy):
    """Strategy that raises in on_stop."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        raise RuntimeError("Strategy on_stop crashed")


class TestStrategyExceptionHandling:
    """Tests for strategy exception handling during lifecycle."""

    @pytest.fixture
    def closed_candle(self):
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_start_strategy_on_init_throws(self, run_id):
        """Strategy on_init() raising should stop engine and propagate."""
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=FailingOnInitStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )
        with pytest.raises(ValueError, match="Strategy init failed"):
            await engine.start()

        assert engine.is_running is False
        assert "Strategy initialization failed" in engine.error_message

    @pytest.mark.asyncio
    async def test_process_candle_strategy_on_bar_throws(self, run_id, closed_candle):
        """Strategy on_bar() raising should log error but engine continues.

        Consistent with backtest runner behavior — strategy exceptions
        are logged and the engine keeps processing bars (TRD-025#3).
        """
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=FailingOnBarStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )
        await engine.start()
        assert engine.is_running is True

        # Strategy on_bar exception should be caught and logged, not crash
        await engine.process_candle(closed_candle)

        assert engine.is_running is True
        assert engine.bar_count == 1
        # Error logged in context
        assert any("error" in log.lower() for log in engine.context.logs)

    @pytest.mark.asyncio
    async def test_stop_strategy_on_stop_throws(self, run_id):
        """Strategy on_stop() raising should still mark engine as stopped."""
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=FailingOnStopStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )
        await engine.start()
        await engine.stop()

        assert engine.is_running is False
        assert engine.stopped_at is not None
        assert "Strategy stop failed" in engine.error_message

    @pytest.mark.asyncio
    async def test_stop_with_prior_error_preserves_original_error(self, run_id):
        """Stopping with error and failing on_stop preserves original error."""
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=FailingOnStopStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
        )
        await engine.start()
        await engine.stop(error="Original error")

        # The original error should be preserved, not overwritten by on_stop failure
        assert engine.error_message == "Original error"


class TestResourceLimitExceeded:
    """Tests for resource limit enforcement during strategy execution."""

    @pytest.fixture
    def closed_candle(self):
        return WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

    @pytest.mark.asyncio
    async def test_resource_limit_exceeded_stops_engine(self, run_id, strategy, closed_candle):
        """ResourceLimitExceededError during on_bar should stop engine."""
        from unittest.mock import patch

        from squant.engine.resource_limits import ResourceLimitExceededError

        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            params={"threshold": Decimal("50000")},
        )
        await engine.start()

        # Mock the resource_limiter to raise ResourceLimitExceededError
        with patch("squant.engine.paper.engine.resource_limiter") as mock_limiter:
            mock_ctx = mock_limiter.return_value.__enter__
            mock_ctx.side_effect = ResourceLimitExceededError("CPU time exceeded")

            with pytest.raises(ResourceLimitExceededError):
                await engine.process_candle(closed_candle)

        assert engine.is_running is False
        assert "resource limit exceeded" in engine.error_message.lower()


class TestEdgeCaseCandles:
    """Tests for edge case candle data."""

    @pytest.mark.asyncio
    async def test_process_candle_with_zero_volume(self, engine):
        """Engine should handle zero volume candles."""
        await engine.start()

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("0"),
            is_closed=True,
        )
        await engine.process_candle(candle)

        assert engine.bar_count == 1

    @pytest.mark.asyncio
    async def test_candle_to_bar_conversion(self, engine):
        """Verify WSCandle to Bar field mapping."""
        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000.12"),
            high=Decimal("46000.34"),
            low=Decimal("44000.56"),
            close=Decimal("45500.78"),
            volume=Decimal("100.99"),
            is_closed=True,
        )
        bar = engine._candle_to_bar(candle)

        assert bar.time == candle.timestamp
        assert bar.symbol == candle.symbol
        assert bar.open == Decimal("45000.12")
        assert bar.high == Decimal("46000.34")
        assert bar.low == Decimal("44000.56")
        assert bar.close == Decimal("45500.78")
        assert bar.volume == Decimal("100.99")


class TestInsufficientCashHandling:
    """Tests for TRD-025#3: insufficient cash should log, not crash engine."""

    @pytest.mark.asyncio
    async def test_insufficient_cash_does_not_stop_engine(self):
        """Engine should continue running when a fill is rejected due to insufficient cash."""

        class AggressiveBuyStrategy(Strategy):
            """Strategy that tries to buy more than available cash."""

            def on_init(self) -> None:
                self.bar_count = 0

            def on_bar(self, bar: Bar) -> None:
                self.bar_count += 1
                # Always try to buy a huge amount on every bar
                if self.bar_count == 1:
                    self.ctx.buy(bar.symbol, Decimal("1000"))  # Way more than cash allows

            def on_stop(self) -> None:
                pass

        run_id = uuid4()
        strategy = AggressiveBuyStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("100"),  # Very small capital
        )
        await engine.start()

        # Bar 1: strategy places huge buy order
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle1)
        assert engine.is_running is True
        assert engine.bar_count == 1

        # Bar 2: order would be matched but fill should be rejected (insufficient cash)
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("50200"),
            high=Decimal("51200"),
            low=Decimal("49200"),
            close=Decimal("50700"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle2)

        # Engine should still be running (not crashed)
        assert engine.is_running is True
        assert engine.bar_count == 2
        assert engine.error_message is None

        # Logs should contain the error from insufficient cash
        logs = engine.context.logs
        assert any("insufficient cash" in log.lower() for log in logs)

    @pytest.mark.asyncio
    async def test_resource_limit_records_equity_snapshot(self):
        """ResourceLimitExceededError should record equity snapshot before stopping."""
        from unittest.mock import patch

        from squant.engine.resource_limits import ResourceLimitExceededError

        strategy = SimpleStrategy()
        run_id = uuid4()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            params={"threshold": Decimal("50000")},
        )
        await engine.start()

        candle = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        with patch("squant.engine.paper.engine.resource_limiter") as mock_limiter:
            mock_ctx = mock_limiter.return_value.__enter__
            mock_ctx.side_effect = ResourceLimitExceededError("CPU time exceeded")

            with pytest.raises(ResourceLimitExceededError):
                await engine.process_candle(candle)

        # Engine should have recorded equity snapshot before stopping
        assert len(engine.context.equity_curve) >= 1
