"""Tests for PaperTradingEngine state_update and bar_close event builders.

Covers _build_state_update_event(), _build_bar_close_event(), and
incremental delta tracking after the format unification refactor.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.paper.engine import PaperTradingEngine
from squant.infra.exchange.ws_types import WSCandle

# ---------------------------------------------------------------------------
# Minimal strategies
# ---------------------------------------------------------------------------


class DoNothingStrategy(Strategy):
    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


class BuyOnceStrategy(Strategy):
    """Buys 0.1 BTC on the first bar if no position."""

    def on_init(self) -> None:
        self._bought = False

    def on_bar(self, bar: Bar) -> None:
        if not self._bought and not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.1"))
            self._bought = True

    def on_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATE_KEYS = {
    "cash",
    "equity",
    "unrealized_pnl",
    "realized_pnl",
    "total_fees",
    "fees_by_currency",
    "fees_usdt_equivalent",
    "positions",
    "pending_orders",
    "open_trade",
    "completed_orders_count",
    "trades_count",
    "risk_state",
}


def make_candle(
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    timestamp: datetime | None = None,
    close: Decimal = Decimal("50000"),
    is_closed: bool = True,
    volume: Decimal = Decimal("100"),
) -> WSCandle:
    if timestamp is None:
        timestamp = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
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


def make_engine(strategy=None, on_event=None) -> PaperTradingEngine:
    if strategy is None:
        strategy = DoNothingStrategy()
    if on_event is None:
        on_event = AsyncMock()
    return PaperTradingEngine(
        run_id=uuid4(),
        strategy=strategy,
        symbol="BTC/USDT",
        timeframe="1m",
        initial_capital=Decimal("10000"),
        commission_rate=Decimal("0.001"),
        slippage=Decimal("0"),
        params={},
        on_event=on_event,
    )


# ---------------------------------------------------------------------------
# Tests: _build_state_update_event
# ---------------------------------------------------------------------------


class TestBuildStateUpdateEvent:
    """Unit tests for _build_state_update_event()."""

    async def test_event_type_is_state_update(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert event["event"] == "state_update"

    async def test_trigger_field(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert event["trigger"] == "fill"

    async def test_run_id_present(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert event["run_id"] == str(engine._run_id)

    async def test_state_dict_has_all_keys(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert "state" in event
        for key in STATE_KEYS:
            assert key in event["state"], f"Missing key '{key}' in state"

    async def test_trigger_detail_empty_without_fill(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert event["trigger_detail"] == {}

    async def test_trigger_detail_populated_from_new_fills(self):
        """trigger_detail is extracted from the latest fill in the delta."""
        from squant.engine.backtest.types import Fill, OrderSide

        engine = make_engine()
        await engine.start()

        # Process a fill through context so it appears in _build_state_snapshot delta
        fill = Fill(
            order_id="test-order-id",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            fee=Decimal("5"),
            timestamp=datetime.now(UTC),
            fee_currency="USDT",
        )
        engine._context._process_fill(fill)

        event = engine._build_state_update_event("fill")

        detail = event["trigger_detail"]
        assert detail["order_id"] == "test-order-id"
        assert detail["side"] == "buy"
        assert detail["price"] == "50000"
        assert detail["amount"] == "0.1"
        assert detail["fee"] == "5"

    async def test_incremental_fields_present(self):
        engine = make_engine()
        await engine.start()
        event = engine._build_state_update_event("fill")
        assert "new_fills" in event
        assert "new_trades" in event
        assert "new_logs" in event


# ---------------------------------------------------------------------------
# Tests: _build_bar_close_event
# ---------------------------------------------------------------------------


class TestBuildBarCloseEvent:
    """Unit tests for _build_bar_close_event()."""

    async def test_event_type_is_bar_close(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        assert event["event"] == "bar_close"

    async def test_run_id_present(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        assert event["run_id"] == str(engine._run_id)

    async def test_bar_count_present(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        assert "bar_count" in event

    async def test_bar_ohlcv_present(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle(close=Decimal("50000"))
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        b = event["bar"]
        assert "time" in b
        assert "open" in b
        assert "high" in b
        assert "low" in b
        assert b["close"] == "50000"
        assert "volume" in b

    async def test_equity_point_present(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        ep = event["equity_point"]
        assert "time" in ep
        assert "equity" in ep
        assert "cash" in ep
        assert "position_value" in ep
        assert "unrealized_pnl" in ep

    async def test_state_dict_has_all_keys(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        assert "state" in event
        for key in STATE_KEYS:
            assert key in event["state"], f"Missing key '{key}' in state"

    async def test_incremental_fields_present(self):
        engine = make_engine()
        await engine.start()
        candle = make_candle()
        bar = engine._candle_to_bar(candle)
        event = engine._build_bar_close_event(bar)
        assert "new_fills" in event
        assert "new_trades" in event
        assert "new_logs" in event


# ---------------------------------------------------------------------------
# Tests: delta tracking across fill event then bar_close event
# ---------------------------------------------------------------------------


class TestDeltaTracking:
    """Verify incremental delta tracking: fill event consumes fills, bar_close sees 0."""

    async def test_fill_event_captures_new_fill_bar_close_sees_zero(self):
        """After a fill event consumes a fill, subsequent bar_close has empty new_fills."""
        on_event_mock = AsyncMock()
        strategy = BuyOnceStrategy()
        engine = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            on_event=on_event_mock,
        )
        await engine.start()

        # Candle 1 (closed): strategy places buy order, no fill yet
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)

        # Candle 2 (unclosed): order fills intrabar → state_update with 1 new_fill
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=False)
        await engine.process_candle(candle2)

        fill_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "state_update" and call.args[0].get("trigger") == "fill"
        ]
        assert len(fill_events) == 1
        assert len(fill_events[0]["new_fills"]) == 1

        # Candle 3 (closed, same bar timestamp as candle2): bar_close should see 0 new fills
        # (the fill was already consumed by the state_update event)
        candle3 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=True)
        on_event_mock.reset_mock()
        await engine.process_candle(candle3)

        bar_close_events = [
            call.args[0]
            for call in on_event_mock.call_args_list
            if call.args[0].get("event") == "bar_close"
        ]
        assert len(bar_close_events) == 1
        assert bar_close_events[0]["new_fills"] == []

    async def test_fills_delivered_via_state_update_not_bar_close(self):
        """Fills on a closed candle appear in state_update, not duplicated in bar_close.

        _process_fill_safe emits state_update first (consuming the delta), so
        bar_close sees new_fills == [] — the fill was already delivered.
        The fill is still visible in the bar_close state.positions snapshot.
        """
        on_event_mock = AsyncMock()
        strategy = BuyOnceStrategy()
        engine = PaperTradingEngine(
            run_id=uuid4(),
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
            params={},
            on_event=on_event_mock,
        )
        await engine.start()

        # Candle 1: strategy places order, no fill yet
        t1 = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        candle1 = make_candle(timestamp=t1, close=Decimal("50000"))
        await engine.process_candle(candle1)
        on_event_mock.reset_mock()

        # Candle 2 (closed): order fills first (via _process_fill_safe → state_update),
        # then bar_close is emitted with the delta already consumed.
        t2 = t1 + timedelta(minutes=1)
        candle2 = make_candle(timestamp=t2, close=Decimal("50100"), is_closed=True)
        await engine.process_candle(candle2)

        all_events = [call.args[0] for call in on_event_mock.call_args_list]
        fill_su_events = [
            e for e in all_events if e.get("event") == "state_update" and e.get("trigger") == "fill"
        ]
        bar_close_events = [e for e in all_events if e.get("event") == "bar_close"]

        # Fill delivered via state_update
        assert len(fill_su_events) >= 1
        assert fill_su_events[0]["new_fills"][0]["side"] == "buy"

        # bar_close does not re-deliver the same fill
        assert len(bar_close_events) == 1
        assert bar_close_events[0]["new_fills"] == []

        # But the position is still reflected in bar_close state
        assert "BTC/USDT" in bar_close_events[0]["state"]["positions"]
