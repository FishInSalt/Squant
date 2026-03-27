"""Unit tests for paper trading engine WebSocket event emission."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.paper.engine import PaperTradingEngine
from squant.infra.exchange.ws_types import WSCandle


class SimpleStrategy(Strategy):
    """Simple test strategy that buys when price is below threshold."""

    def on_init(self) -> None:
        self.threshold = self.ctx.params.get("threshold", Decimal("50000"))

    def on_bar(self, bar: Bar) -> None:
        if bar.close < self.threshold and not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self) -> None:
        pass


class DoNothingStrategy(Strategy):
    """Strategy that does nothing."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


@pytest.fixture
def run_id():
    return uuid4()


@pytest.fixture
def on_event_mock():
    return AsyncMock()


@pytest.fixture
def engine(run_id, on_event_mock):
    """Create a paper trading engine with on_event callback."""
    strategy = DoNothingStrategy()
    return PaperTradingEngine(
        run_id=run_id,
        strategy=strategy,
        symbol="BTC/USDT",
        timeframe="1m",
        initial_capital=Decimal("10000"),
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
        params={},
        on_event=on_event_mock,
    )


def make_candle(
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    timestamp: datetime | None = None,
    close: Decimal = Decimal("50000"),
    is_closed: bool = True,
    volume: Decimal = Decimal("100"),
) -> WSCandle:
    """Helper to create a WSCandle."""
    if timestamp is None:
        timestamp = datetime.now(UTC)
    return WSCandle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=close - Decimal("10"),
        high=close + Decimal("10"),
        low=close - Decimal("20"),
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


class TestBarCloseEvent:
    """Tests for bar_close event emission."""

    async def test_bar_close_emitted_on_closed_candle(self, engine, on_event_mock, run_id):
        """Test that on_event is called after processing a closed candle."""
        await engine.start()

        candle = make_candle()
        await engine.process_candle(candle)

        # on_event is called via create_task, so check the mock was called
        assert on_event_mock.call_count == 1
        event = on_event_mock.call_args[0][0]
        assert event["event"] == "bar_close"
        assert event["run_id"] == str(run_id)
        assert event["bar_count"] == 1

    async def test_bar_close_not_emitted_on_unclosed_candle(self, engine, on_event_mock):
        """Test that on_event is NOT called for unclosed candles."""
        await engine.start()

        candle = make_candle(is_closed=False)
        await engine.process_candle(candle)

        on_event_mock.assert_not_called()

    async def test_bar_close_contains_correct_fields(self, engine, on_event_mock):
        """Test that bar_close event contains all required fields."""
        await engine.start()

        candle = make_candle(close=Decimal("50000"))
        await engine.process_candle(candle)

        event = on_event_mock.call_args[0][0]
        assert event["event"] == "bar_close"
        assert "bar" in event
        assert "equity_point" in event
        assert "state" in event
        state = event["state"]
        assert "cash" in state
        assert "equity" in state
        assert "unrealized_pnl" in state
        assert "realized_pnl" in state
        assert "total_fees" in state
        assert "completed_orders_count" in state
        assert "trades_count" in state
        assert "positions" in state
        assert "pending_orders" in state
        assert "new_fills" in event
        assert "new_trades" in event
        assert "new_logs" in event
        assert "risk_state" in state

    async def test_incremental_tracking(self, engine, on_event_mock):
        """Test that incremental fields only contain new items."""
        await engine.start()

        # First candle
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1)
        await engine.process_candle(candle1)

        event1 = on_event_mock.call_args[0][0]
        # No trades, fills, or logs expected from DoNothingStrategy
        assert event1["new_fills"] == []
        assert event1["new_trades"] == []
        assert event1["new_logs"] == []

        # Second candle
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2)
        await engine.process_candle(candle2)

        event2 = on_event_mock.call_args[0][0]
        assert event2["bar_count"] == 2
        # Still no new items (incremental)
        assert event2["new_fills"] == []
        assert event2["new_trades"] == []
        assert event2["new_logs"] == []

    async def test_incremental_with_trading(self, run_id, on_event_mock):
        """Test that incremental tracking captures new fills/trades from trading.

        When a fill occurs on a closed candle, _process_fill_safe emits a
        state_update event that consumes the fill delta first. The subsequent
        bar_close event therefore sees new_fills == [] (already delivered).
        The fill still appears in the state_update event for that candle.
        """
        strategy = SimpleStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("60000")},
            on_event=on_event_mock,
        )
        await engine.start()

        # First candle - strategy places a buy order in on_bar()
        # But orders are filled on the NEXT candle (steps 1-2), so no fills yet
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)

        bar_close_event1 = on_event_mock.call_args[0][0]
        # No fills yet - order was placed but not filled until next candle
        assert bar_close_event1["new_fills"] == []

        # Second candle - the pending buy order gets filled at steps 1-2
        # fill → state_update event (consumes delta), then bar_close event (empty delta)
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"))
        on_event_mock.reset_mock()
        await engine.process_candle(candle2)

        # The fill appears in the state_update event, not bar_close
        all_events2 = [call.args[0] for call in on_event_mock.call_args_list]
        fill_state_updates = [
            e for e in all_events2
            if e.get("event") == "state_update" and e.get("trigger") == "fill"
        ]
        assert len(fill_state_updates) >= 1
        assert fill_state_updates[0]["new_fills"][0]["side"] == "buy"

        # The bar_close event for candle2 should NOT re-emit the same fill
        bar_close_events2 = [e for e in all_events2 if e.get("event") == "bar_close"]
        assert len(bar_close_events2) == 1
        assert bar_close_events2[0]["new_fills"] == []

        # Third candle - no new buy (already has position), no new fills anywhere
        t3 = t2 + timedelta(minutes=1)
        candle3 = make_candle(timestamp=t3, close=Decimal("50200"))
        on_event_mock.reset_mock()
        await engine.process_candle(candle3)

        bar_close_event3 = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "bar_close"
        ][0]
        # No new fills this time (incremental)
        assert bar_close_event3["new_fills"] == []


class TestEngineStoppedEvent:
    """Tests for engine_stopped event emission."""

    async def test_engine_stopped_emitted_on_stop(self, engine, on_event_mock, run_id):
        """Test that engine_stopped event is emitted when engine stops."""
        await engine.start()
        await engine.stop()

        # Find the engine_stopped call (it's the one where event is "engine_stopped")
        stopped_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "engine_stopped"
        ]
        assert len(stopped_events) == 1
        event = stopped_events[0]
        assert event["run_id"] == str(run_id)
        assert event["stopped_at"] is not None

    async def test_engine_stopped_with_error(self, engine, on_event_mock, run_id):
        """Test that engine_stopped event includes error message."""
        await engine.start()
        await engine.stop(error="Test error")

        stopped_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "engine_stopped"
        ]
        assert len(stopped_events) == 1
        assert stopped_events[0]["error_message"] == "Test error"


class TestFillEvent:
    """Tests for real-time state_update fill event emission."""

    async def test_fill_event_emitted_on_intrabar_fill(self, run_id, on_event_mock):
        """Test that state_update event is emitted when an order fills on an unclosed candle."""
        strategy = SimpleStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("60000")},
            on_event=on_event_mock,
        )
        await engine.start()

        # First closed candle — strategy places a buy order
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)

        # bar_close emitted, reset mock to isolate fill events
        on_event_mock.reset_mock()

        # Second candle, UNCLOSED — pending buy order gets filled intrabar
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=False)
        await engine.process_candle(candle2)

        # A state_update event should have been emitted (not bar_close, since candle is unclosed)
        assert on_event_mock.call_count >= 1
        fill_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "state_update"
            and call.args[0].get("trigger") == "fill"
        ]
        assert len(fill_events) == 1
        event = fill_events[0]
        assert event["run_id"] == str(run_id)
        assert event["trigger_detail"]["side"] == "buy"
        state = event["state"]
        assert "cash" in state
        assert "equity" in state
        assert "unrealized_pnl" in state
        assert "positions" in state
        assert "pending_orders" in state
        assert "open_trade" in state

    async def test_fill_event_contains_correct_scalar_state(self, run_id, on_event_mock):
        """Test that state_update fill event scalar state reflects post-fill values."""
        strategy = SimpleStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("60000")},
            on_event=on_event_mock,
        )
        await engine.start()

        # Place order via closed candle
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)
        on_event_mock.reset_mock()

        # Fill via unclosed candle
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=False)
        await engine.process_candle(candle2)

        fill_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "state_update"
            and call.args[0].get("trigger") == "fill"
        ]
        assert len(fill_events) == 1
        event = fill_events[0]
        state = event["state"]

        # Cash should have decreased (bought 0.1 BTC)
        cash = Decimal(state["cash"])
        assert cash < Decimal("10000")

        # Should have a position
        assert "BTC/USDT" in state["positions"]
        assert Decimal(state["positions"]["BTC/USDT"]["amount"]) == Decimal("0.1")

    async def test_fill_event_not_emitted_during_warmup(self, run_id, on_event_mock):
        """Test that fill events are suppressed during warmup phase."""
        strategy = SimpleStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("60000")},
            on_event=on_event_mock,
        )
        await engine.start()

        # Set warmup flag
        engine._warming_up = True

        # Process candle - no events at all (process_candle returns early during warmup)
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)

        on_event_mock.assert_not_called()

    async def test_fill_event_callback_error_does_not_break_engine(self, run_id):
        """Test that an error in the on_event callback doesn't crash the engine."""
        error_callback = AsyncMock(side_effect=Exception("callback failed"))

        strategy = SimpleStrategy()
        engine = PaperTradingEngine(
            run_id=run_id,
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={"threshold": Decimal("60000")},
            on_event=error_callback,
        )
        await engine.start()

        # Place order via closed candle
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)

        # Fill via unclosed candle — callback will raise, but engine should survive
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=False)
        await engine.process_candle(candle2)

        # Engine should still be running
        assert engine.is_running is True


class TestNoEventCallback:
    """Tests to ensure engine works without on_event callback."""

    async def test_no_callback_no_error(self):
        """Test engine works correctly without on_event callback."""
        strategy = DoNothingStrategy()
        engine = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
        )
        await engine.start()

        candle = make_candle()
        await engine.process_candle(candle)

        assert engine.bar_count == 1

        await engine.stop()
        assert engine.is_running is False
