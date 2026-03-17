"""TDD tests for live trading code review fixes.

Each test class targets a specific bug found during code review.
Tests are written RED first (expected to fail), then fixed GREEN.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar
from squant.engine.live.engine import LiveOrder, LiveTradingEngine
from squant.engine.risk import RiskConfig
from squant.infra.exchange.ws_types import WSCandle, WSOrderUpdate
from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    OrderResponse,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType

# ---------------------------------------------------------------------------
# Test strategies
# ---------------------------------------------------------------------------


class BuyOnEveryBarStrategy(Strategy):
    """Strategy that submits a buy order on every bar."""

    def on_init(self) -> None:
        self.bar_count = 0

    def on_bar(self, bar: Bar) -> None:
        self.bar_count += 1
        self.ctx.buy(bar.symbol, Decimal("0.001"))

    def on_stop(self) -> None:
        pass


class DoNothingStrategy(Strategy):
    """Strategy that does nothing on each bar."""

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> None:
        pass

    def on_stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_settings_mock():
    settings = MagicMock()
    settings.paper_max_equity_curve_size = 10000
    settings.paper_max_completed_orders = 1000
    settings.paper_max_fills = 1000
    settings.paper_max_trades = 1000
    settings.paper_max_logs = 1000
    settings.strategy.max_bar_history = 1000
    settings.strategy.cpu_limit_seconds = 10
    settings.strategy.memory_limit_mb = 256
    return settings


def _make_adapter():
    adapter = AsyncMock()
    adapter.connect = AsyncMock()
    adapter.close = AsyncMock()
    adapter.supports_dead_man_switch = False
    adapter.get_balance = AsyncMock(
        return_value=AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
                Balance(currency="BTC", available=Decimal("0"), frozen=Decimal("0")),
            ],
        )
    )
    adapter.place_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-001",
            client_order_id=None,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.001"),
            filled=Decimal("0"),
        )
    )
    adapter.get_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            price=None,
            amount=Decimal("0.001"),
            filled=Decimal("0"),
        )
    )
    adapter.cancel_order = AsyncMock(
        return_value=OrderResponse(
            order_id="exchange-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            price=Decimal("40000"),
            amount=Decimal("0.001"),
            filled=Decimal("0"),
        )
    )
    return adapter


def _make_risk_config(**overrides):
    defaults = {
        "max_position_size": Decimal("0.5"),
        "max_order_size": Decimal("0.1"),
        "daily_trade_limit": 100,
        "daily_loss_limit": Decimal("0.1"),
        "max_price_deviation": Decimal("0.05"),
        "circuit_breaker_enabled": True,
        "circuit_breaker_loss_count": 5,
        "circuit_breaker_cooldown_minutes": 30,
    }
    defaults.update(overrides)
    return RiskConfig(**defaults)


def _make_engine(strategy, adapter=None, risk_config=None, **kwargs):
    adapter = adapter or _make_adapter()
    risk_config = risk_config or _make_risk_config()
    with patch("squant.config.get_settings") as mock_settings:
        mock_settings.return_value = _make_settings_mock()
        return LiveTradingEngine(
            run_id=uuid4(),
            strategy=strategy,
            symbol="BTC/USDT",
            timeframe="1m",
            adapter=adapter,
            risk_config=risk_config,
            initial_equity=Decimal("10000"),
            params={},
            **kwargs,
        )


def _make_closed_candle(close=Decimal("50000"), ts=None):
    return WSCandle(
        symbol="BTC/USDT",
        timeframe="1m",
        timestamp=ts or datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
        open=Decimal("49000"),
        high=Decimal("51000"),
        low=Decimal("48000"),
        close=close,
        volume=Decimal("100"),
        is_closed=True,
    )


# ===========================================================================
# C-1: stop() / process_candle() race — orders submitted after stop
# ===========================================================================


class TestC1StopProcessCandleRace:
    """C-1: After stop() sets _is_running=False and cancels orders,
    a concurrent process_candle that already passed the _is_running guard
    should NOT submit new orders via _process_order_requests().

    The fix: _process_order_requests should re-check _is_running before
    submitting each order.
    """

    async def test_process_order_requests_skips_when_not_running(self):
        """_process_order_requests should not submit orders when _is_running is False.

        Simulates the race: process_candle already entered the lock,
        then stop() sets _is_running=False from outside. The order
        processing within the lock should detect this and skip submission.
        """
        adapter = _make_adapter()
        strategy = BuyOnEveryBarStrategy()
        engine = _make_engine(strategy, adapter=adapter)

        # Manually start engine state (skip full start to avoid adapter calls)
        engine._is_running = True
        engine._started_at = datetime.now(UTC)
        engine._last_active_at = datetime.now(UTC)
        strategy.on_init()

        # Process a candle so the strategy submits a buy order
        candle = _make_closed_candle()
        # Before processing, set _is_running=False to simulate stop() race
        # We need the strategy to run on_bar first to create the order,
        # then _process_order_requests should check _is_running

        # Step 1: run on_bar to create pending order
        bar = engine._candle_to_bar(candle)
        engine._context._set_current_bar(bar)
        engine._context._add_bar_to_history(bar)
        engine._current_price = candle.close
        with patch("squant.engine.resource_limits.resource_limiter"):
            strategy.on_bar(bar)

        # Verify order is pending
        assert len(engine._context._pending_orders) > 0

        # Step 2: simulate stop() racing — set _is_running=False
        engine._is_running = False

        # Step 3: call _process_order_requests — should NOT submit
        await engine._process_order_requests()

        # The order should NOT have been submitted to the exchange
        adapter.place_order.assert_not_called()


# ===========================================================================
# C-2: Polling path _update_order_from_response lacks filled_amount regression guard
# ===========================================================================


class TestC2PollingFilledAmountRegression:
    """C-2: When WS updates filled_amount to a higher value, a subsequent
    poll response with a lower filled_amount should NOT regress the value.

    The fix: _update_order_from_response should use max() like the WS path.
    """

    def test_poll_does_not_regress_filled_amount(self):
        """Polling with a stale (lower) filled_amount must not overwrite
        a higher value already set by a WebSocket update."""
        adapter = _make_adapter()
        strategy = DoNothingStrategy()
        engine = _make_engine(strategy, adapter=adapter)
        engine._is_running = True
        engine._current_price = Decimal("50000")

        # Create and register a live order
        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("1.0"),
            price=Decimal("50000"),
            status=OrderStatus.PARTIAL,
        )
        # Simulate WS already updated filled_amount to 0.7
        live_order.filled_amount = Decimal("0.7")
        live_order.avg_fill_price = Decimal("50000")
        live_order.fee = Decimal("0.35")

        engine._live_orders["order-1"] = live_order
        engine._exchange_order_map["ex-1"] = "order-1"

        # Now a stale poll response arrives with filled=0.5 (lower than 0.7)
        stale_response = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,
            price=Decimal("50000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),
            avg_price=Decimal("50000"),
            fee=Decimal("0.25"),
        )

        engine._update_order_from_response(live_order, stale_response)

        # filled_amount should NOT regress to 0.5
        assert live_order.filled_amount >= Decimal("0.7"), (
            f"filled_amount regressed from 0.7 to {live_order.filled_amount}"
        )


# ===========================================================================
# C-3: _transform_order defaults unknown side to BUY
# ===========================================================================


class TestC3UnknownOrderSideDefault:
    """C-3: When CCXT returns an unknown order side string, _transform_order
    should raise an error, NOT silently default to BUY.

    Defaulting to BUY in live trading can cause incorrect position tracking.
    """

    def test_unknown_order_side_raises_error(self):
        """An unknown order side from CCXT should raise an exception."""
        from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter

        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)

        # Build a minimal CCXT order dict with an unknown side
        ccxt_order = {
            "id": "123",
            "clientOrderId": None,
            "symbol": "BTC/USDT",
            "side": "unknown_side",  # Invalid side
            "type": "limit",
            "status": "open",
            "price": 50000.0,
            "amount": 0.1,
            "filled": 0.0,
            "average": None,
            "fee": None,
            "datetime": "2024-01-01T00:00:00.000Z",
            "timestamp": 1704067200000,
        }

        # Should raise an error, not silently default to BUY
        with pytest.raises(Exception):
            adapter._transform_order(ccxt_order)


# ===========================================================================
# I-2: DMS heartbeat failure — no escalation mechanism
# ===========================================================================


class TestI2DmsHeartbeatEscalation:
    """I-2: When DMS heartbeat refresh fails repeatedly, the engine should
    escalate (log error or stop) rather than silently continuing.

    Currently _refresh_dead_man_switch only logs a warning on failure,
    with no consecutive failure tracking.
    """

    async def test_consecutive_dms_failures_tracked(self):
        """After multiple consecutive DMS heartbeat failures, engine should
        track the failure count for potential escalation."""
        adapter = _make_adapter()
        adapter.supports_dead_man_switch = True
        adapter.setup_dead_man_switch = AsyncMock(side_effect=Exception("network error"))
        adapter.cancel_dead_man_switch = AsyncMock()

        strategy = DoNothingStrategy()
        engine = _make_engine(strategy, adapter=adapter)
        engine._dms_enabled = True
        engine._is_running = True

        # Refresh DMS multiple times — all fail
        for _ in range(5):
            await engine._refresh_dead_man_switch()

        # Engine should track the consecutive failures
        assert hasattr(engine, "_dms_consecutive_failures"), (
            "Engine should track DMS consecutive failures"
        )
        assert engine._dms_consecutive_failures >= 5


# ===========================================================================
# I-3: Circuit breaker cooldown does not reset consecutive_losses
# ===========================================================================


class TestI3CircuitBreakerCooldownReset:
    """I-3: When circuit breaker cooldown expires, consecutive_losses should
    be reset to 0. Otherwise the very next loss immediately re-triggers.
    """

    def test_circuit_breaker_expired_resets_consecutive_losses(self):
        """After cooldown expires, consecutive_losses should be 0."""
        from squant.engine.risk.models import RiskState

        state = RiskState()
        state.consecutive_losses = 5
        state.circuit_breaker_triggered = True
        # Set cooldown_until to the past so it's already expired
        state.circuit_breaker_until = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)

        # Check expiry — takes no arguments, uses datetime.now() internally
        expired = state.check_circuit_breaker_expired()

        assert expired is True
        assert state.circuit_breaker_triggered is False
        # consecutive_losses should be reset to 0
        assert state.consecutive_losses == 0, (
            f"consecutive_losses should be 0 after cooldown, got {state.consecutive_losses}"
        )


# ===========================================================================
# I-4: emergency_close API leaks internal error details
# ===========================================================================


class TestI4EmergencyCloseErrorLeakage:
    """I-4: The emergency_close API endpoint returns raw exception messages
    to the client, potentially leaking internal details.

    This is tested at the API route level.
    """

    async def test_emergency_close_error_sanitized(self):
        """Error response should not contain raw internal exception details."""
        from unittest.mock import patch as mock_patch

        from httpx import ASGITransport, AsyncClient

        from squant.main import app

        with mock_patch("squant.api.v1.live_trading.LiveTradingService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.emergency_close = AsyncMock(
                side_effect=Exception(
                    "psycopg2.OperationalError: connection refused to db at 10.0.0.5:5432"
                )
            )
            mock_svc_cls.return_value = mock_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/api/v1/live/{uuid4()}/emergency-close")

            body = response.json()
            # Should NOT contain raw internal error details
            if "message" in body:
                assert "psycopg2" not in body["message"], "Internal error details leaked to client"
                assert "10.0.0.5" not in body["message"], "Internal IP address leaked to client"


# ===========================================================================
# I-5: current_price == 0 silently passes price deviation check
# ===========================================================================


class TestI5ZeroPriceDeviationCheck:
    """I-5: When current_price is 0 (data feed failure), the price deviation
    check should reject orders rather than silently passing them.

    Tests the _check_price_deviation method directly since the full
    validate_order path rejects early due to min_order_value with price=0.
    """

    def test_price_deviation_rejects_when_current_price_zero(self):
        """_check_price_deviation should reject when current_price is 0."""
        from squant.engine.risk import RiskManager

        config = _make_risk_config(max_price_deviation=Decimal("0.05"))
        manager = RiskManager(config=config, initial_equity=Decimal("10000"))

        # Call the internal check directly to bypass min_order_value guard
        result = manager._check_price_deviation(
            order_price=Decimal("50000"),
            current_price=Decimal("0"),  # Anomalous zero price
            side=OrderSide.BUY,
        )

        # Should NOT pass — zero price indicates data feed failure
        assert not result.passed, (
            "Price deviation check should reject when current_price is 0 (data feed failure)"
        )


# ===========================================================================
# I-10: dispatch_order_update does not acquire lock
# ===========================================================================


class TestI10DispatchOrderUpdateLocking:
    """I-10: dispatch_order_update should acquire _lock for consistency
    with dispatch_candle, which does acquire the lock."""

    async def test_dispatch_order_update_is_async_with_lock(self):
        """dispatch_order_update should be an async method that acquires _lock."""
        import inspect

        from squant.engine.live.manager import LiveSessionManager

        manager = LiveSessionManager()

        # dispatch_order_update should be a coroutine (async) to use the lock
        # Currently it's synchronous and doesn't acquire _lock
        assert inspect.iscoroutinefunction(manager.dispatch_order_update), (
            "dispatch_order_update should be async to properly acquire _lock"
        )


# ===========================================================================
# M-1: _pending_ws_updates has no upper bound
# ===========================================================================


class TestM1PendingWsUpdatesBound:
    """M-1: _pending_ws_updates should have an upper bound to prevent
    unbounded memory growth when the engine is stalled."""

    def test_pending_ws_updates_bounded(self):
        """Excess WS updates should be dropped when buffer is full."""
        adapter = _make_adapter()
        strategy = DoNothingStrategy()
        engine = _make_engine(strategy, adapter=adapter)
        engine._is_running = True

        # Flood with many updates
        for i in range(2000):
            update = WSOrderUpdate(
                order_id=f"ex-{i}",
                symbol="BTC/USDT",
                side="buy",
                order_type="limit",
                status="submitted",
                size=Decimal("0.1"),
                filled_size=Decimal("0"),
                avg_price=None,
                fee=None,
                fee_currency=None,
                updated_at=datetime.now(UTC),
            )
            engine.on_order_update(update)

        # Should be bounded (not 2000)
        assert len(engine._pending_ws_updates) <= 1000, (
            f"_pending_ws_updates grew to {len(engine._pending_ws_updates)}, should be bounded"
        )


# ===========================================================================
# M-2: _cancel_all_orders iterates without dict snapshot
# ===========================================================================


class TestM2CancelAllOrdersIteration:
    """M-2: _cancel_all_orders should iterate over a snapshot (list()) of
    _live_orders.items() to prevent RuntimeError if dict is modified."""

    def test_cancel_all_orders_uses_list_snapshot(self):
        """_cancel_all_orders source code should use list() around .items() iteration."""
        import ast
        import inspect
        import textwrap

        from squant.engine.live.engine import LiveTradingEngine

        source = textwrap.dedent(inspect.getsource(LiveTradingEngine._cancel_all_orders))
        tree = ast.parse(source)

        # Look for `list(self._live_orders.items())` pattern in the for loop
        uses_list_snapshot = False
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                # Check if the iter is list(self._live_orders.items())
                iter_node = node.iter
                if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Name):
                    if iter_node.func.id == "list":
                        uses_list_snapshot = True

        assert uses_list_snapshot, (
            "_cancel_all_orders should use list(self._live_orders.items()) for safe iteration"
        )


# ===========================================================================
# M-5: list_by_mode uses `if status:` instead of `if status is not None:`
# ===========================================================================


class TestM5ListByModeStatusFilter:
    """M-5: list_by_mode should use `if status is not None:` to correctly
    handle all enum values."""

    def test_list_by_mode_status_none_check(self):
        """Verify the repository uses 'is not None' check for status parameter."""
        import inspect

        from squant.services.live_trading import LiveStrategyRunRepository

        source = inspect.getsource(LiveStrategyRunRepository.list_by_mode)
        assert "status is not None" in source, (
            "list_by_mode should use 'if status is not None:' not 'if status:'"
        )
        assert "\n        if status:\n" not in source, (
            "list_by_mode should not use truthy check 'if status:'"
        )


# ===========================================================================
# BUG-1: Stale poll response overwrites avg_price/fee/status even when
#         filled_amount is protected by max()
# ===========================================================================


class TestBug1StaleResponseSkipsEntireUpdate:
    """BUG-1: When a poll response has filled < current filled_amount (stale),
    the entire update should be skipped. The previous C-2 fix only protected
    filled_amount with max(), but avg_fill_price, fee, and status were still
    overwritten by the stale response.
    """

    def test_stale_poll_does_not_overwrite_avg_price(self):
        """avg_fill_price should not regress from a stale poll response."""
        engine = _make_engine(DoNothingStrategy())
        engine._is_running = True
        engine._current_price = Decimal("50000")

        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("1.0"),
            price=Decimal("50000"),
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.7")
        live_order.avg_fill_price = Decimal("50100")
        live_order.fee = Decimal("0.35")

        engine._live_orders["order-1"] = live_order

        stale_response = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,
            price=Decimal("50000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),  # stale: less than current 0.7
            avg_price=Decimal("49900"),  # stale avg
            fee=Decimal("0.25"),  # stale fee
        )

        engine._update_order_from_response(live_order, stale_response)

        assert live_order.avg_fill_price == Decimal("50100"), (
            f"avg_fill_price regressed from 50100 to {live_order.avg_fill_price}"
        )

    def test_stale_poll_does_not_overwrite_fee(self):
        """fee should not regress from a stale poll response."""
        engine = _make_engine(DoNothingStrategy())
        engine._is_running = True
        engine._current_price = Decimal("50000")

        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("1.0"),
            price=Decimal("50000"),
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.7")
        live_order.avg_fill_price = Decimal("50000")
        live_order.fee = Decimal("0.35")

        engine._live_orders["order-1"] = live_order

        stale_response = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,
            price=Decimal("50000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),
            avg_price=Decimal("50000"),
            fee=Decimal("0.25"),  # stale: less than current 0.35
        )

        engine._update_order_from_response(live_order, stale_response)

        assert live_order.fee == Decimal("0.35"), (
            f"fee regressed from 0.35 to {live_order.fee}"
        )

    def test_stale_poll_does_not_regress_status(self):
        """status should not regress from FILLED to PARTIAL via stale poll."""
        engine = _make_engine(DoNothingStrategy())
        engine._is_running = True
        engine._current_price = Decimal("50000")

        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("1.0"),
            price=Decimal("50000"),
            status=OrderStatus.FILLED,
        )
        live_order.filled_amount = Decimal("1.0")
        live_order.avg_fill_price = Decimal("50000")
        live_order.fee = Decimal("0.50")

        engine._live_orders["order-1"] = live_order

        stale_response = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,  # stale: was already FILLED
            price=Decimal("50000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.5"),  # stale
            avg_price=Decimal("50000"),
            fee=Decimal("0.25"),
        )

        engine._update_order_from_response(live_order, stale_response)

        assert live_order.status == OrderStatus.FILLED, (
            f"status regressed from FILLED to {live_order.status.value}"
        )

    def test_fresh_poll_still_updates_normally(self):
        """A poll response with higher filled should still update all fields."""
        engine = _make_engine(DoNothingStrategy())
        engine._is_running = True
        engine._current_price = Decimal("50000")

        live_order = LiveOrder(
            internal_id="order-1",
            exchange_order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="limit",
            amount=Decimal("1.0"),
            price=Decimal("50000"),
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.3")
        live_order.avg_fill_price = Decimal("50000")
        live_order.fee = Decimal("0.15")

        engine._live_orders["order-1"] = live_order

        fresh_response = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,
            price=Decimal("50000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.7"),  # fresh: more than current 0.3
            avg_price=Decimal("50050"),
            fee=Decimal("0.35"),
        )

        engine._update_order_from_response(live_order, fresh_response)

        assert live_order.filled_amount == Decimal("0.7")
        assert live_order.avg_fill_price == Decimal("50050")
        assert live_order.fee == Decimal("0.35")
        assert live_order.status == OrderStatus.PARTIAL


# ===========================================================================
# BUG-3: DMS notification fires on every failure after threshold, not just once
# ===========================================================================


class TestBug3DmsNotificationOnlyOnce:
    """BUG-3: _fire_notification should only be called once when DMS failures
    first reach the threshold, not on every subsequent failure."""

    async def test_dms_notification_fires_once_at_threshold(self):
        """Notification should fire exactly once when threshold is first reached."""
        adapter = _make_adapter()
        adapter.supports_dead_man_switch = True
        adapter.setup_dead_man_switch = AsyncMock(side_effect=Exception("network error"))

        engine = _make_engine(DoNothingStrategy(), adapter=adapter)
        engine._dms_enabled = True
        engine._is_running = True

        with patch("squant.engine.live.engine._fire_notification") as mock_notify:
            # Fail 10 times (threshold is 3)
            for _ in range(10):
                await engine._refresh_dead_man_switch()

            # Should fire exactly once at failure #3, not on #4..#10
            dms_calls = [
                c for c in mock_notify.call_args_list
                if any(
                    a == "dms_heartbeat_lost"
                    for a in c.args + tuple(c.kwargs.values())
                )
            ]
            assert len(dms_calls) == 1, (
                f"DMS notification should fire once, but fired {len(dms_calls)} times"
            )


# ===========================================================================
# DESIGN-1: _pending_ws_updates should use deque(maxlen=) not list.pop(0)
# ===========================================================================


class TestDesign1WsBufferDeque:
    """DESIGN-1: _pending_ws_updates should be a deque with maxlen for O(1)
    append/eviction, instead of list with O(n) pop(0)."""

    def test_pending_ws_updates_is_deque(self):
        """_pending_ws_updates should be a collections.deque."""
        from collections import deque

        engine = _make_engine(DoNothingStrategy())

        assert isinstance(engine._pending_ws_updates, deque), (
            f"_pending_ws_updates should be deque, got {type(engine._pending_ws_updates).__name__}"
        )

    def test_deque_has_maxlen(self):
        """deque should have a maxlen set to prevent unbounded growth."""
        engine = _make_engine(DoNothingStrategy())

        assert engine._pending_ws_updates.maxlen is not None, (
            "_pending_ws_updates deque should have maxlen set"
        )
        assert engine._pending_ws_updates.maxlen <= 1000


# ===========================================================================
# DESIGN-2: _MAX_PENDING_WS_UPDATES should be class-level constant
# ===========================================================================


class TestDesign2ConstantLocation:
    """DESIGN-2: The WS update buffer cap should be a class-level constant,
    not a local variable recreated on every call."""

    def test_max_pending_ws_updates_is_class_attribute(self):
        """_MAX_PENDING_WS_UPDATES should be accessible as a class attribute."""
        assert hasattr(LiveTradingEngine, "_MAX_PENDING_WS_UPDATES"), (
            "_MAX_PENDING_WS_UPDATES should be a class-level constant"
        )


# ===========================================================================
# STYLE-1: exception chaining in _transform_order
# ===========================================================================


class TestStyle1ExceptionChaining:
    """STYLE-1: ExchangeAPIError raised from ValueError should use `from e`
    to preserve the exception chain."""

    def test_unknown_side_preserves_exception_chain(self):
        """ExchangeAPIError for unknown side should chain the original ValueError."""
        from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
        from squant.infra.exchange.exceptions import ExchangeAPIError

        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)
        ccxt_order = {
            "id": "123",
            "clientOrderId": None,
            "symbol": "BTC/USDT",
            "side": "unknown_side",
            "type": "limit",
            "status": "open",
            "price": 50000.0,
            "amount": 0.1,
            "filled": 0.0,
            "average": None,
            "fee": None,
            "datetime": "2024-01-01T00:00:00.000Z",
            "timestamp": 1704067200000,
        }

        with pytest.raises(ExchangeAPIError) as exc_info:
            adapter._transform_order(ccxt_order)

        assert exc_info.value.__cause__ is not None, (
            "ExchangeAPIError should chain the original ValueError via 'from e'"
        )
