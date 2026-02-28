"""Unit tests for paper trading engine."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
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
    async def test_unclosed_candle_matches_orders_but_no_on_bar(self, engine, strategy):
        """Test that unclosed candles trigger order matching but don't call on_bar."""
        await engine.start()

        # First closed candle: strategy places buy order
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
        assert engine.bar_count == 1
        assert strategy.buy_executed is True
        assert len(engine.context.pending_orders) == 1

        # Unclosed candle update: should fill the market order but NOT call on_bar
        unclosed = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("45500"),
            high=Decimal("46000"),
            low=Decimal("45000"),
            close=Decimal("45700"),
            volume=Decimal("50"),
            is_closed=False,
        )
        await engine.process_candle(unclosed)

        # Order should be filled (tick-level matching)
        assert len(engine.context.pending_orders) == 0
        assert engine.context.has_position("BTC/USDT")
        # But bar_count should NOT increase (on_bar not called)
        assert engine.bar_count == 1

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
    async def test_market_order_filled_immediately(self, engine, strategy):
        """Test that market orders are filled on the next candle update (tick-level).

        With tick-level matching, a market order placed in on_bar() of bar N
        gets filled on the very next candle update (even an unclosed one),
        not at bar N+1's open.
        """
        await engine.start()

        # First closed bar: strategy places buy order in on_bar
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

        # Strategy placed order, but it's pending until next candle update
        assert len(engine.context.pending_orders) == 1

        # Next candle update (even unclosed): market order fills immediately
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("46000"),
            high=Decimal("47000"),
            low=Decimal("45000"),
            close=Decimal("46500"),
            volume=Decimal("100"),
            is_closed=False,
        )
        await engine.process_candle(candle2)

        # Order should be filled now (on the unclosed candle update)
        assert len(engine.context.pending_orders) == 0
        assert len(engine.context.completed_orders) == 1
        assert engine.context.has_position("BTC/USDT")

    @pytest.mark.asyncio
    async def test_limit_order_fills_on_interim_update(self, run_id):
        """Test that limit orders trigger on unclosed candle price updates."""

        class LimitBuyStrategy(Strategy):
            def on_init(self):
                self.bar_num = 0

            def on_bar(self, bar):
                self.bar_num += 1
                if self.bar_num == 1:
                    # Place a limit buy below current price
                    self.ctx.buy(bar.symbol, Decimal("0.1"), price=Decimal("44000"))

            def on_stop(self):
                pass

        strategy = LimitBuyStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
        )
        await engine.start()

        # Bar 1: strategy places limit buy at 44000
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44500"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle1)
        assert len(engine.context.pending_orders) == 1

        # Unclosed candle: price drops to 43500, should trigger limit buy
        interim = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("45500"),
            high=Decimal("45500"),
            low=Decimal("43000"),
            close=Decimal("43500"),
            volume=Decimal("50"),
            is_closed=False,
        )
        await engine.process_candle(interim)

        # Limit order should be filled at limit price (44000), not current price
        assert len(engine.context.pending_orders) == 0
        assert engine.context.has_position("BTC/USDT")
        # Fill price should be the limit price
        assert len(engine.context.fills) == 1
        assert engine.context.fills[0].price == Decimal("44000")

    @pytest.mark.asyncio
    async def test_on_bar_only_called_on_closed(self, run_id):
        """Verify on_bar() is only called when is_closed=True."""

        class CountingStrategy(Strategy):
            def on_init(self):
                self.on_bar_count = 0

            def on_bar(self, bar):
                self.on_bar_count += 1

            def on_stop(self):
                pass

        strategy = CountingStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            slippage=Decimal("0"),
        )
        await engine.start()

        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Send 3 unclosed updates
        for i in range(3):
            candle = WSCandle(
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=ts,
                open=Decimal("45000"),
                high=Decimal("46000"),
                low=Decimal("44000"),
                close=Decimal("45500"),
                volume=Decimal("50"),
                is_closed=False,
            )
            await engine.process_candle(candle)

        assert strategy.on_bar_count == 0

        # Send 1 closed candle
        closed = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=ts,
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(closed)

        assert strategy.on_bar_count == 1


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
        """Test snapshot includes position data after trading.

        With tick-level matching, the buy order placed in bar 1's on_bar
        fills on the next candle update (bar 2).
        """
        await engine.start()

        # Bar 1: strategy places buy order
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

        # Bar 2: market order fills immediately at candle.close
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

        # Closed trades list should be empty (position still open)
        assert len(snapshot["trades"]) == 0
        # Open trade exposed as separate field for chart buy marker
        assert snapshot["open_trade"] is not None
        assert snapshot["open_trade"]["entry_time"] is not None
        assert snapshot["open_trade"]["entry_price"] is not None
        assert snapshot["open_trade"]["symbol"] == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_state_snapshot_includes_trades_and_logs(self, engine, strategy):
        """Test snapshot includes trades and logs fields."""
        await engine.start()

        snapshot = engine.get_state_snapshot()

        assert "trades" in snapshot
        assert "logs" in snapshot
        assert isinstance(snapshot["trades"], list)
        assert isinstance(snapshot["logs"], list)
        assert snapshot["trades"] == []
        assert snapshot["logs"] == []

    @pytest.mark.asyncio
    async def test_state_snapshot_with_completed_trade(self, run_id):
        """Test snapshot includes trade records after a buy-sell cycle.

        With tick-level matching:
        - Bar 1: strategy buys → order pending
        - Bar 2: buy fills at close, strategy sees position, sells on bar 2
        - Bar 3: sell fills at close, trade completed
        """

        class BuySellStrategy(Strategy):
            """Strategy that buys on first bar, sells on second."""

            def on_init(self):
                self.bar_num = 0

            def on_bar(self, bar):
                self.bar_num += 1
                if self.bar_num == 1:
                    self.ctx.buy(bar.symbol, Decimal("0.1"))
                elif self.bar_num == 2 and self.ctx.has_position(bar.symbol):
                    self.ctx.sell(bar.symbol, Decimal("0.1"))

            def on_stop(self):
                pass

        strategy = BuySellStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
        )
        await engine.start()

        # Bar 1: strategy places buy order
        candle1 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            open=Decimal("40000"),
            high=Decimal("41000"),
            low=Decimal("39000"),
            close=Decimal("40500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle1)

        # Bar 2: buy fills at close, then on_bar places sell
        candle2 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=UTC),
            open=Decimal("40500"),
            high=Decimal("41500"),
            low=Decimal("40000"),
            close=Decimal("41000"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle2)

        # Bar 3: sell fills at close, completing the trade
        candle3 = WSCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime(2024, 1, 1, 12, 2, 0, tzinfo=UTC),
            open=Decimal("41000"),
            high=Decimal("42000"),
            low=Decimal("40500"),
            close=Decimal("41500"),
            volume=Decimal("100"),
            is_closed=True,
        )
        await engine.process_candle(candle3)

        snapshot = engine.get_state_snapshot()

        assert len(snapshot["trades"]) >= 1
        trade = snapshot["trades"][0]
        assert trade["symbol"] == "BTC/USDT"
        assert trade["side"] in ("buy", "sell")
        assert "entry_time" in trade
        assert "entry_price" in trade
        assert "amount" in trade
        assert "pnl" in trade
        assert "pnl_pct" in trade
        assert "fees" in trade

    @pytest.mark.asyncio
    async def test_state_snapshot_logs_on_error(self, engine, strategy):
        """Test snapshot logs field is populated when strategy logs messages."""
        await engine.start()

        # Manually add a log via context
        engine.context.log("Test log message")

        snapshot = engine.get_state_snapshot()

        assert len(snapshot["logs"]) == 1
        assert "Test log message" in snapshot["logs"][0]


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
    async def test_is_healthy_adapts_to_timeframe(self, engine):
        """Test is_healthy uses adaptive timeout based on timeframe.

        For 1m timeframe, effective timeout = max(timeout_seconds, 60*3=180).
        So even with timeout_seconds=0, a just-started engine is healthy.
        """
        await engine.start()
        # Effective timeout = max(0, 180) = 180s, just started so healthy
        assert engine.is_healthy(timeout_seconds=0) is True

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_expired(self, engine):
        """Test is_healthy returns False when activity exceeds adaptive timeout."""
        await engine.start()
        # Set last_active_at far in the past (beyond adaptive timeout of 180s for 1m)
        engine._last_active_at = datetime.now(UTC) - timedelta(seconds=600)
        assert engine.is_healthy(timeout_seconds=300) is False


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
            slippage=Decimal("0"),
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
            slippage=Decimal("0"),
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
            slippage=Decimal("0"),
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
            slippage=Decimal("0"),
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
            slippage=Decimal("0"),
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
        """Engine should continue running when a fill is rejected due to insufficient cash.

        With tick-level matching, the order fills on the next candle update.
        """

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
            slippage=Decimal("0"),
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

        # Bar 2: order fills immediately at close, but should be rejected (insufficient cash)
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
            slippage=Decimal("0"),
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


class TestDeadlockFix:
    """Tests for ISSUE-300 fix: process_candle outer except must not deadlock
    by calling stop() while holding _processing_lock."""

    @pytest.fixture
    def engine(self):
        strategy = SimpleStrategy()
        with patch("squant.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.paper_max_equity_curve_size = 10000
            settings.paper_max_completed_orders = 1000
            settings.paper_max_fills = 1000
            settings.paper_max_trades = 1000
            settings.paper_max_logs = 1000
            settings.strategy.cpu_limit_seconds = 5
            settings.strategy.memory_limit_mb = 256
            mock_settings.return_value = settings

            return PaperTradingEngine(
                run_id=uuid4(),
                strategy=strategy,
                symbol="BTC/USDT",
                timeframe="1m",
                initial_capital=Decimal("10000"),
                slippage=Decimal("0"),
                params={"threshold": Decimal("50000")},
            )

    @pytest.mark.asyncio
    async def test_unexpected_error_stops_engine_without_deadlock(self, engine):
        """Test that an unexpected error in process_candle stops the engine
        cleanly without deadlocking on _processing_lock (ISSUE-300)."""
        await engine.start()
        assert engine.is_running is True

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

        # Inject an error in _candle_to_bar to trigger the outer except
        with patch.object(engine, "_candle_to_bar", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                await engine.process_candle(candle)

        # Engine should be stopped (not deadlocked)
        assert engine.is_running is False
        assert engine.stopped_at is not None
        assert "Error processing candle" in engine.error_message

        # Lock should be released — another stop() should be a no-op, not deadlock
        await engine.stop()
        assert engine.is_running is False


class TestSnapshotCallback:
    """Tests for on_snapshot callback (Phase 1: synchronous equity persistence)."""

    @pytest.fixture
    def callback(self):
        """Create a mock snapshot persist callback."""
        from unittest.mock import AsyncMock

        return AsyncMock()

    @pytest.fixture
    def engine_with_callback(self, run_id, strategy, callback):
        """Create engine with snapshot callback."""
        return PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("50000")},
            on_snapshot=callback,
        )

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

    @pytest.mark.asyncio
    async def test_callback_called_on_candle(self, engine_with_callback, callback, closed_candle):
        """Test that on_snapshot callback is called after processing a candle."""
        await engine_with_callback.start()
        await engine_with_callback.process_candle(closed_candle)

        callback.assert_called_once()
        call_args = callback.call_args
        assert call_args[0][0] == str(engine_with_callback.run_id)  # run_id

    @pytest.mark.asyncio
    async def test_callback_success_skips_pending(
        self, engine_with_callback, callback, closed_candle
    ):
        """Test that successful callback means snapshot is NOT added to pending."""
        await engine_with_callback.start()
        await engine_with_callback.process_candle(closed_candle)

        callback.assert_called_once()
        # Should not be in pending since callback succeeded
        assert len(engine_with_callback.get_pending_snapshots()) == 0

    @pytest.mark.asyncio
    async def test_callback_failure_adds_to_pending(
        self, engine_with_callback, callback, closed_candle
    ):
        """Test that failed callback adds snapshot to pending as fallback."""
        callback.side_effect = Exception("DB connection error")

        await engine_with_callback.start()
        await engine_with_callback.process_candle(closed_candle)

        # Callback was attempted
        callback.assert_called_once()
        # Should be in pending since callback failed
        assert len(engine_with_callback.get_pending_snapshots()) == 1

    @pytest.mark.asyncio
    async def test_no_callback_adds_to_pending(self, engine, closed_candle):
        """Test that without callback, snapshots go to pending (default behavior)."""
        await engine.start()
        await engine.process_candle(closed_candle)

        # Default engine has no callback, so snapshot goes to pending
        assert len(engine.get_pending_snapshots()) >= 1

    def test_engine_init_with_callback(self, engine_with_callback, callback):
        """Test that engine stores the callback."""
        assert engine_with_callback._on_snapshot is callback

    def test_engine_init_without_callback(self, engine):
        """Test that engine defaults to no callback."""
        assert engine._on_snapshot is None


class TestResultCallback:
    """Tests for on_result callback (synchronous result state persistence)."""

    @pytest.fixture
    def result_callback(self):
        """Create a mock result persist callback."""
        from unittest.mock import AsyncMock

        return AsyncMock()

    @pytest.fixture
    def engine_with_result_callback(self, run_id, strategy, result_callback):
        """Create engine with result callback."""
        return PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("50000")},
            on_result=result_callback,
        )

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

    @pytest.mark.asyncio
    async def test_result_callback_called_on_candle(
        self, engine_with_result_callback, result_callback, closed_candle
    ):
        """Test that on_result callback is called after processing a candle."""
        await engine_with_result_callback.start()
        await engine_with_result_callback.process_candle(closed_candle)

        result_callback.assert_called_once()
        call_args = result_callback.call_args
        assert call_args[0][0] == str(engine_with_result_callback.run_id)
        # Second arg should be a dict with result data
        result_data = call_args[0][1]
        assert "cash" in result_data
        assert "equity" in result_data
        assert "positions" in result_data
        assert "trades" in result_data
        assert "unrealized_pnl" in result_data
        assert "realized_pnl" in result_data
        assert "logs" in result_data
        assert "bar_count" in result_data

    @pytest.mark.asyncio
    async def test_result_callback_failure_does_not_crash(
        self, engine_with_result_callback, result_callback, closed_candle
    ):
        """Test that failed result callback does not crash the engine."""
        result_callback.side_effect = Exception("DB write failed")

        await engine_with_result_callback.start()
        await engine_with_result_callback.process_candle(closed_candle)

        # Engine should still be running despite callback failure
        assert engine_with_result_callback.is_running is True
        assert engine_with_result_callback.bar_count == 1

    @pytest.mark.asyncio
    async def test_no_result_callback_by_default(self, engine, closed_candle):
        """Test that engine without result callback still processes candles."""
        assert engine._on_result is None

        await engine.start()
        await engine.process_candle(closed_candle)

        assert engine.bar_count == 1

    def test_engine_stores_result_callback(self, engine_with_result_callback, result_callback):
        """Test that engine stores the result callback."""
        assert engine_with_result_callback._on_result is result_callback

    @pytest.mark.asyncio
    async def test_result_callback_called_on_each_candle(
        self, engine_with_result_callback, result_callback
    ):
        """Test that on_result is called once per candle."""
        await engine_with_result_callback.start()

        for i in range(3):
            candle = WSCandle(
                symbol="BTC/USDT",
                timeframe="1m",
                timestamp=datetime(2024, 1, 1, 12, i, 0, tzinfo=UTC),
                open=Decimal("45000"),
                high=Decimal("46000"),
                low=Decimal("44000"),
                close=Decimal("45500"),
                volume=Decimal("100"),
                is_closed=True,
            )
            await engine_with_result_callback.process_candle(candle)

        assert result_callback.call_count == 3
