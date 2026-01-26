"""Unit tests for paper trading engine."""

from datetime import datetime, timezone
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process multiple candles
        for i in range(5):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
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
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            open=Decimal("45000"),
            high=Decimal("46000"),
            low=Decimal("44000"),
            close=Decimal("45500"),
            volume=Decimal("100"),
            is_closed=True,
        )

        # Process bars below batch size
        for i in range(5):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
            await engine.process_candle(candle)

        assert engine.should_persist_snapshots() is False

        # Process more to exceed batch size (default is 10)
        for i in range(5, 10):
            candle.timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
            await engine.process_candle(candle)

        assert engine.should_persist_snapshots() is True
