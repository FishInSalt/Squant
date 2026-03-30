"""Tests for the unified event loop in LiveTradingEngine (Task 2).

Covers:
- Event processing for WS_FILL, WS_ORDER, BAR_CLOSE event types
- Emergency close skipping of WS events
- Graceful loop exit on _is_running = False
- Deadlock avoidance when stop() is called from within _handle_bar_close()
- Crash detection via _on_event_loop_done callback
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.live.engine import EngineEvent, EngineEventType, LiveTradingEngine
from squant.engine.risk import RiskConfig
from squant.infra.exchange.types import AccountBalance, Balance, OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType

# ---------------------------------------------------------------------------
# Minimal strategy
# ---------------------------------------------------------------------------


class NoOpStrategy(Strategy):
    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def run_id():
    return uuid4()


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_position_size=Decimal("0.5"),
        max_order_size=Decimal("0.1"),
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.1"),
        max_price_deviation=Decimal("0.05"),
        circuit_breaker_enabled=False,
        circuit_breaker_loss_count=5,
        circuit_breaker_cooldown_minutes=30,
    )


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.connect = AsyncMock()
    adapter.close = AsyncMock()
    adapter.get_balance = AsyncMock(
        return_value=AccountBalance(
            exchange="okx",
            balances=[
                Balance(
                    currency="USDT",
                    available=Decimal("10000"),
                    frozen=Decimal("0"),
                ),
            ],
        )
    )
    adapter.place_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-123",
            client_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.01"),
            filled=Decimal("0"),
        )
    )
    return adapter


@pytest.fixture
def engine(run_id, risk_config, mock_adapter):
    """Create a LiveTradingEngine with minimal configuration."""
    with patch("squant.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.paper_max_equity_curve_size = 10000
        settings.paper_max_completed_orders = 1000
        settings.paper_max_fills = 1000
        settings.paper_max_trades = 1000
        settings.paper_max_logs = 1000
        settings.strategy.max_bar_history = 1000
        mock_settings.return_value = settings

        return LiveTradingEngine(
            run_id=run_id,
            strategy=NoOpStrategy(),
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=mock_adapter,
            risk_config=risk_config,
            initial_equity=Decimal("10000"),
            params={},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _start_event_loop(engine: LiveTradingEngine) -> asyncio.Task:
    """Manually activate the event loop without calling full start()."""
    engine._is_running = True
    engine._event_loop_task = asyncio.create_task(engine._event_loop())
    engine._event_loop_task.add_done_callback(engine._on_event_loop_done)
    return engine._event_loop_task


async def _stop_event_loop(engine: LiveTradingEngine) -> None:
    """Cleanly shut down the event loop."""
    engine._is_running = False
    if engine._event_loop_task and not engine._event_loop_task.done():
        try:
            await asyncio.wait_for(engine._event_loop_task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            engine._event_loop_task.cancel()


def _make_event(event_type: EngineEventType, data: dict | None = None) -> EngineEvent:
    return EngineEvent(
        type=event_type,
        data=data or {},
        received_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventLoopProcessing:
    async def test_event_loop_processes_ws_fill(self, engine):
        """WS_FILL event should call _process_trade_execution and _flush_order_events."""
        engine._process_trade_execution = MagicMock()
        engine._flush_order_events = AsyncMock()
        engine._build_state_update_event = MagicMock(return_value=None)

        await _start_event_loop(engine)
        try:
            fill_data = {"trade_id": "t1", "symbol": "BTC/USDT"}
            await engine._event_queue.put(_make_event(EngineEventType.WS_FILL, fill_data))
            # Give event loop time to process
            await asyncio.sleep(0.1)

            engine._process_trade_execution.assert_called_once_with(fill_data)
            engine._flush_order_events.assert_called_once()
        finally:
            await _stop_event_loop(engine)

    async def test_event_loop_processes_ws_order(self, engine):
        """WS_ORDER event should call _process_single_ws_update and _flush_order_events."""
        engine._process_single_ws_update = MagicMock()
        engine._flush_order_events = AsyncMock()
        engine._build_state_update_event = MagicMock(return_value=None)

        await _start_event_loop(engine)
        try:
            order_data = {"order_id": "o1", "status": "filled"}
            await engine._event_queue.put(_make_event(EngineEventType.WS_ORDER, order_data))
            await asyncio.sleep(0.1)

            engine._process_single_ws_update.assert_called_once_with(order_data)
            engine._flush_order_events.assert_called_once()
        finally:
            await _stop_event_loop(engine)

    async def test_event_loop_processes_bar_close(self, engine):
        """BAR_CLOSE event should call _handle_bar_close."""
        engine._handle_bar_close = AsyncMock()

        await _start_event_loop(engine)
        try:
            candle_data = {"symbol": "BTC/USDT", "close": "50000"}
            await engine._event_queue.put(_make_event(EngineEventType.BAR_CLOSE, candle_data))
            await asyncio.sleep(0.1)

            engine._handle_bar_close.assert_called_once_with(candle_data)
        finally:
            await _stop_event_loop(engine)

    async def test_event_loop_pushes_event_via_on_event(self, engine):
        """WS_FILL should produce a push_event and call _on_event outside the lock."""
        engine._process_trade_execution = MagicMock()
        engine._flush_order_events = AsyncMock()

        on_event_mock = AsyncMock()
        engine._on_event = on_event_mock

        await _start_event_loop(engine)
        try:
            await engine._event_queue.put(_make_event(EngineEventType.WS_FILL, {"trade_id": "t1"}))
            await asyncio.sleep(0.2)

            on_event_mock.assert_called_once()
            push_arg = on_event_mock.call_args[0][0]
            assert push_arg["event"] == "state_update"
            assert push_arg["trigger"] == "fill"
            assert str(engine._run_id) == push_arg["run_id"]
        finally:
            await _stop_event_loop(engine)


class TestEventLoopEmergencyClose:
    async def test_event_loop_skips_ws_during_emergency_close(self, engine):
        """WS_FILL and WS_ORDER should be skipped when emergency close is in progress."""
        engine._process_trade_execution = MagicMock()
        engine._process_single_ws_update = MagicMock()
        engine._flush_order_events = AsyncMock()
        engine._emergency_close_in_progress = True

        await _start_event_loop(engine)
        try:
            await engine._event_queue.put(_make_event(EngineEventType.WS_FILL, {"trade_id": "t1"}))
            await engine._event_queue.put(_make_event(EngineEventType.WS_ORDER, {"order_id": "o1"}))
            await asyncio.sleep(0.2)

            engine._process_trade_execution.assert_not_called()
            engine._process_single_ws_update.assert_not_called()
        finally:
            await _stop_event_loop(engine)

    async def test_bar_close_not_skipped_during_emergency_close(self, engine):
        """BAR_CLOSE should still be processed during emergency close."""
        engine._handle_bar_close = AsyncMock()
        engine._emergency_close_in_progress = True

        await _start_event_loop(engine)
        try:
            await engine._event_queue.put(
                _make_event(EngineEventType.BAR_CLOSE, {"candle": "data"})
            )
            await asyncio.sleep(0.1)

            engine._handle_bar_close.assert_called_once()
        finally:
            await _stop_event_loop(engine)


class TestEventLoopLifecycle:
    async def test_event_loop_exits_on_is_running_false(self, engine):
        """Event loop should exit cleanly when _is_running is set to False."""
        task = await _start_event_loop(engine)

        # Set _is_running = False; the loop should exit on next timeout cycle
        engine._is_running = False
        await asyncio.wait_for(task, timeout=3.0)

        assert task.done()
        assert task.exception() is None

    async def test_event_loop_exits_when_is_running_false_inside_lock(self, engine):
        """If _is_running becomes False while waiting for the lock, loop should break."""
        engine._process_trade_execution = MagicMock()
        engine._flush_order_events = AsyncMock()

        task = await _start_event_loop(engine)
        try:
            # Acquire the lock externally to simulate contention
            async with engine._processing_lock:
                # Put an event while lock is held
                await engine._event_queue.put(
                    _make_event(EngineEventType.WS_FILL, {"trade_id": "t1"})
                )
                await asyncio.sleep(0.05)
                # Set running to False while event is waiting for lock
                engine._is_running = False

            # Release the lock; event loop should now see _is_running=False and break
            await asyncio.wait_for(task, timeout=3.0)
            assert task.done()
            # The fill should NOT have been processed
            engine._process_trade_execution.assert_not_called()
        except TimeoutError:
            engine._is_running = False
            task.cancel()
            pytest.fail("Event loop did not exit when _is_running was set to False")

    async def test_stop_from_handle_bar_close_no_deadlock(self, engine):
        """stop() called from _handle_bar_close should not deadlock.

        The event loop runs _handle_bar_close inside the processing lock.
        If _handle_bar_close calls stop(), stop() must not await the event loop
        task (which would deadlock since we ARE the event loop task).
        """
        call_count = 0

        async def bar_close_calls_stop(candle):
            nonlocal call_count
            call_count += 1
            # Simulate stop called from bar processing error path
            await engine.stop(error="test error from bar close")

        engine._handle_bar_close = bar_close_calls_stop
        # Patch out methods called by stop() that need real infrastructure
        engine._stop_private_ws = AsyncMock()
        engine._deactivate_dead_man_switch = AsyncMock()
        engine._cancel_all_orders = AsyncMock(return_value=[])

        task = await _start_event_loop(engine)

        await engine._event_queue.put(_make_event(EngineEventType.BAR_CLOSE, {"candle": "data"}))

        # Should complete without deadlock within the timeout
        await asyncio.wait_for(task, timeout=5.0)

        assert call_count == 1
        assert not engine._is_running

    async def test_bar_close_error_calls_stop(self, engine):
        """Exception in BAR_CLOSE handler should call stop() with error message."""
        engine._handle_bar_close = AsyncMock(side_effect=RuntimeError("bar processing failed"))
        engine._stop_private_ws = AsyncMock()
        engine._deactivate_dead_man_switch = AsyncMock()
        engine._cancel_all_orders = AsyncMock(return_value=[])

        task = await _start_event_loop(engine)

        await engine._event_queue.put(_make_event(EngineEventType.BAR_CLOSE, {"candle": "data"}))

        await asyncio.wait_for(task, timeout=5.0)

        assert not engine._is_running
        assert "Bar processing error" in (engine._error_message or "")

    async def test_ws_fill_error_does_not_stop_engine(self, engine):
        """Exception in WS_FILL handler should log but not stop the engine."""
        engine._process_trade_execution = MagicMock(
            side_effect=RuntimeError("fill processing failed")
        )
        engine._flush_order_events = AsyncMock()
        engine._build_state_update_event = MagicMock(return_value=None)

        await _start_event_loop(engine)
        try:
            await engine._event_queue.put(_make_event(EngineEventType.WS_FILL, {"trade_id": "t1"}))
            await asyncio.sleep(0.2)

            # Engine should still be running (WS errors are non-fatal)
            assert engine._is_running
            engine._process_trade_execution.assert_called_once()
        finally:
            await _stop_event_loop(engine)


class TestOnEventLoopDone:
    async def test_on_event_loop_done_triggers_stop(self, engine):
        """_on_event_loop_done should trigger stop() when task crashes."""
        engine._is_running = True
        engine._stop_private_ws = AsyncMock()
        engine._deactivate_dead_man_switch = AsyncMock()
        engine._cancel_all_orders = AsyncMock(return_value=[])

        # Create a task that raises an exception
        async def crashing_coro():
            raise RuntimeError("unexpected crash")

        crashing_task = asyncio.create_task(crashing_coro())

        # Wait for the task to complete with the exception
        with pytest.raises(RuntimeError):
            await crashing_task

        # Now call the done callback
        engine._on_event_loop_done(crashing_task)

        # Give the fire-and-forget stop() task time to execute
        await asyncio.sleep(0.2)

        assert not engine._is_running

    async def test_on_event_loop_done_no_op_when_not_running(self, engine):
        """_on_event_loop_done should not call stop() if engine already stopped."""
        engine._is_running = False
        original_stop = engine.stop

        stop_called = False

        async def tracking_stop(**kwargs):
            nonlocal stop_called
            stop_called = True
            await original_stop(**kwargs)

        engine.stop = tracking_stop

        async def crashing_coro():
            raise RuntimeError("crash")

        crashing_task = asyncio.create_task(crashing_coro())
        with pytest.raises(RuntimeError):
            await crashing_task

        engine._on_event_loop_done(crashing_task)
        await asyncio.sleep(0.1)

        assert not stop_called

    async def test_on_event_loop_done_no_op_on_cancel(self, engine):
        """_on_event_loop_done should not trigger stop() on cancellation."""
        engine._is_running = True

        async def sleeping_coro():
            await asyncio.sleep(100)

        task = asyncio.create_task(sleeping_coro())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Patch stop to detect calls
        engine.stop = AsyncMock()
        engine._on_event_loop_done(task)
        await asyncio.sleep(0.1)

        engine.stop.assert_not_called()


class TestQueueOverflow:
    async def test_queue_overflow_ws_event_dropped(self, engine):
        """WS_FILL event is silently dropped when the event queue is full.

        Verifies that put_nowait raises QueueFull internally but does not
        propagate to the caller, and that the event is not added to the queue.
        """
        # Replace engine's event queue with a tiny maxsize=2 queue
        engine._event_queue = asyncio.Queue(maxsize=2)

        # Fill the queue to capacity
        dummy_event = _make_event(EngineEventType.WS_FILL, {"trade_id": "dummy"})
        engine._event_queue.put_nowait(dummy_event)
        engine._event_queue.put_nowait(dummy_event)
        assert engine._event_queue.full()

        # Simulate a WS trade_execution message arriving when queue is full
        from squant.infra.exchange.ws_types import WSTradeExecution

        fill_data = WSTradeExecution(
            trade_id="t-overflow",
            order_id="o-overflow",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("50000"),
            amount=Decimal("0.01"),
            fee=Decimal("0"),
            fee_currency="USDT",
            timestamp=datetime.now(UTC),
        )

        # Should not raise — the QueueFull exception is caught internally
        msg = {"type": "trade_execution", "data": fill_data}
        await engine._handle_private_ws_message(msg)

        # Queue should still be exactly at capacity (no new item added)
        assert engine._event_queue.full()
        assert engine._event_queue.qsize() == 2
