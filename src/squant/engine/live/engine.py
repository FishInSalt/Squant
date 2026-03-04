"""Live trading engine for real-time trading with real exchange execution.

Drives strategy execution with actual order placement via exchange adapter.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import (
    Bar,
    EquitySnapshot,
    Fill,
)
from squant.engine.backtest.types import (
    OrderType as BacktestOrderType,
)
from squant.engine.paper.engine import (
    _serialize_fill,
    _serialize_open_trade,
    _serialize_trade,
)
from squant.engine.resource_limits import ResourceLimitExceededError, resource_limiter
from squant.engine.risk import RiskConfig, RiskManager
from squant.infra.exchange.types import CancelOrderRequest, OrderRequest, OrderResponse
from squant.models.enums import OrderSide, OrderStatus

if TYPE_CHECKING:
    from squant.infra.exchange.base import ExchangeAdapter
    from squant.infra.exchange.okx.ws_types import WSCandle, WSOrderUpdate

# Callback type for synchronous snapshot persistence
SnapshotPersistCallback = Callable[[str, EquitySnapshot], Awaitable[None]]
# Callback type for synchronous result state persistence
ResultPersistCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
# Callback type for WebSocket event emission
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
# Callback type for order/trade audit persistence (LIVE-013)
OrderPersistCallback = Callable[[str, list[dict[str, Any]]], Awaitable[None]]

logger = logging.getLogger(__name__)

# WebSocket order status mapping (internal string -> OrderStatus enum).
# Both CCXT transformer and native OKX StreamManager mapper normalize to
# these internal status strings before dispatching to the engine.
_WS_STATUS_MAP: dict[str, OrderStatus] = {
    "submitted": OrderStatus.SUBMITTED,
    "partial": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "cancelled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
}


class LiveOrder:
    """Represents a live order with exchange tracking.

    Links internal order state with exchange order information.
    """

    def __init__(
        self,
        internal_id: str,
        exchange_order_id: str | None,
        symbol: str,
        side: OrderSide,
        order_type: str,
        amount: Decimal,
        price: Decimal | None,
        status: OrderStatus = OrderStatus.PENDING,
    ):
        self.internal_id = internal_id
        self.exchange_order_id = exchange_order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.amount = amount
        self.price = price
        self.status = status
        self.filled_amount = Decimal("0")
        self.avg_fill_price: Decimal | None = None
        self.fee = Decimal("0")
        self.fee_currency: str | None = None
        self.created_at: datetime | None = None
        self.updated_at: datetime | None = None
        self.error_message: str | None = None

    @property
    def remaining_amount(self) -> Decimal:
        """Get unfilled amount."""
        return self.amount - self.filled_amount

    @property
    def is_complete(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )


def _serialize_live_order(order: LiveOrder) -> dict[str, Any]:
    """Serialize a LiveOrder for persistence."""
    return {
        "internal_id": order.internal_id,
        "exchange_order_id": order.exchange_order_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "order_type": order.order_type,
        "amount": str(order.amount),
        "price": str(order.price) if order.price else None,
        "status": order.status.value,
        "filled_amount": str(order.filled_amount),
        "avg_fill_price": str(order.avg_fill_price) if order.avg_fill_price else None,
        "fee": str(order.fee),
        "fee_currency": order.fee_currency,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "error_message": order.error_message,
    }


def _fire_notification(
    run_id: UUID | str,
    level: str,
    event_type: str,
    title: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget notification from engine context.

    Safe to call from any async context — never raises, never blocks.
    """
    try:
        from squant.services.notification import emit_notification

        loop = asyncio.get_running_loop()
        loop.create_task(
            emit_notification(
                level=level,
                event_type=event_type,
                title=title,
                message=message,
                details=details,
                run_id=str(run_id),
            )
        )
    except Exception:
        pass


class LiveTradingEngine:
    """Real-time live trading engine.

    Processes WebSocket candle data and drives strategy execution
    with real order placement via exchange adapter.

    Attributes:
        run_id: Strategy run ID.
        symbol: Trading symbol.
        timeframe: Candle timeframe.
        is_running: Whether the engine is currently running.
    """

    def __init__(
        self,
        run_id: UUID,
        strategy: Strategy,
        symbol: str,
        timeframe: str,
        adapter: ExchangeAdapter,
        risk_config: RiskConfig,
        initial_equity: Decimal,
        params: dict[str, Any] | None = None,
        on_snapshot: SnapshotPersistCallback | None = None,
        on_result: ResultPersistCallback | None = None,
        on_event: EventCallback | None = None,
        on_order_persist: OrderPersistCallback | None = None,
    ):
        """Initialize live trading engine.

        Args:
            run_id: Strategy run ID.
            strategy: Strategy instance to execute.
            symbol: Trading symbol (e.g., "BTC/USDT").
            timeframe: Candle timeframe (e.g., "1m").
            adapter: Exchange adapter for order execution.
            risk_config: Risk management configuration.
            initial_equity: Initial account equity for risk calculations.
            params: Strategy parameters.
            on_snapshot: Optional callback for synchronous snapshot persistence.
            on_result: Optional callback for synchronous result state persistence.
            on_event: Optional callback for WebSocket event emission.
            on_order_persist: Optional callback for order/trade audit persistence.
        """
        self._run_id = run_id
        self._strategy = strategy
        self._symbol = symbol
        self._timeframe = timeframe
        self._adapter = adapter
        self._initial_equity = initial_equity

        # Get settings dynamically for testability
        from squant.config import get_settings

        settings = get_settings()

        # Initialize context with in-memory tracking (no simulated matching)
        self._context = BacktestContext(
            initial_capital=initial_equity,
            commission_rate=Decimal("0"),  # Real fees tracked from exchange
            slippage=Decimal("0"),  # No slippage simulation
            params=params,
            max_equity_curve=settings.paper_max_equity_curve_size,
            max_completed_orders=settings.paper_max_completed_orders,
            max_fills=settings.paper_max_fills,
            max_trades=settings.paper_max_trades,
            max_logs=settings.paper_max_logs,
            min_order_value=risk_config.min_order_value,
        )

        # Risk manager
        self._risk_manager = RiskManager(
            config=risk_config,
            initial_equity=initial_equity,
        )

        # Inject context into strategy
        self._strategy.ctx = self._context

        # Engine state
        self._is_running = False
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._error_message: str | None = None
        self._bar_count = 0
        self._last_active_at: datetime | None = None
        self._circuit_breaker_triggered = False  # Set when risk manager triggers circuit breaker
        self._warming_up = False  # True during strategy warmup on resume (IMP-009)

        # Live order tracking
        self._live_orders: dict[str, LiveOrder] = {}  # internal_id -> LiveOrder
        self._exchange_order_map: dict[str, str] = {}  # exchange_id -> internal_id

        # Pending order requests from strategy
        self._pending_order_requests: list[dict[str, Any]] = []

        # Current market price (updated from candles)
        self._current_price: Decimal | None = None

        # Synchronous persistence callbacks
        self._on_snapshot = on_snapshot
        self._on_result = on_result

        # Equity snapshots for persistence (fallback when callback fails)
        self._pending_snapshots: list[EquitySnapshot] = []
        self._snapshot_batch_size = 10

        # Risk trigger events for persistence (Issue 010)
        self._pending_risk_triggers: list[dict[str, Any]] = []

        # Emergency close in progress flag (TRD-038#6)
        self._emergency_close_in_progress: bool = False

        # Processing lock to prevent stop()/process_candle() race conditions (R3-002)
        self._processing_lock = asyncio.Lock()

        # Buffered WebSocket order updates (ISSUE-203 fix)
        # Updates are queued here and drained synchronously within process_candle
        # to prevent concurrent state mutation between WS callbacks and polling.
        self._pending_ws_updates: list[WSOrderUpdate] = []

        # WebSocket event emission callback
        self._on_event = on_event
        # Incremental tracking indexes for event delta computation
        self._last_emitted_fill_total = 0
        self._last_emitted_trade_total = 0
        self._last_emitted_log_total = 0

        # Strategy callback tracking (on_fill / on_order_done)
        self._last_callback_fill_total = 0
        self._last_callback_completed_total = 0

        # Order sync rate limiting - avoid excessive polling
        # Track last poll time per order to avoid redundant API calls
        self._order_last_poll: dict[str, datetime] = {}  # exchange_order_id -> last poll time
        self._order_poll_min_interval = 30.0  # Minimum seconds between polls for same order

        # Last exchange balance for diagnostics (LIVE-012)
        self._last_exchange_balance: Decimal | None = None

        # Order/trade audit persistence (LIVE-013)
        self._on_order_persist = on_order_persist
        self._pending_order_events: list[dict[str, Any]] = []

        # Exchange connection failure tracking (LV-3)
        # Separate counters for balance and order sync (R3-011)
        self._balance_consecutive_failures: int = 0
        self._order_sync_consecutive_failures: int = 0
        self._sync_failure_threshold: int = 5

    @property
    def run_id(self) -> UUID:
        """Get the strategy run ID."""
        return self._run_id

    @property
    def symbol(self) -> str:
        """Get the trading symbol."""
        return self._symbol

    @property
    def timeframe(self) -> str:
        """Get the candle timeframe."""
        return self._timeframe

    @property
    def is_running(self) -> bool:
        """Check if engine is currently running."""
        return self._is_running

    @property
    def started_at(self) -> datetime | None:
        """Get the start timestamp."""
        return self._started_at

    @property
    def stopped_at(self) -> datetime | None:
        """Get the stop timestamp."""
        return self._stopped_at

    @property
    def error_message(self) -> str | None:
        """Get error message if any."""
        return self._error_message

    @property
    def circuit_breaker_triggered(self) -> bool:
        """Check if circuit breaker was triggered due to consecutive losses."""
        return self._circuit_breaker_triggered

    @property
    def bar_count(self) -> int:
        """Get number of bars processed."""
        return self._bar_count

    @property
    def last_active_at(self) -> datetime | None:
        """Get last activity timestamp."""
        return self._last_active_at

    @property
    def context(self) -> BacktestContext:
        """Get the backtest context."""
        return self._context

    @property
    def risk_manager(self) -> RiskManager:
        """Get the risk manager."""
        return self._risk_manager

    async def _trigger_global_circuit_breaker(self) -> None:
        """Trigger global circuit breaker to stop all trading sessions.

        Called when this session's local circuit breaker triggers due to
        consecutive losses. This ensures all sessions stop for safety,
        implementing the global risk synchronization (Issue 033 fix).

        Also persists the circuit breaker state to Redis so it survives
        restarts and prevents new sessions from starting (LIVE-RM-002).
        """
        from squant.engine.live.manager import get_live_session_manager
        from squant.engine.paper.manager import get_session_manager

        reason = (
            f"Auto-triggered by session {self._run_id}: "
            f"{self._risk_manager.state.consecutive_losses} consecutive losses"
        )

        logger.critical(
            f"GLOBAL CIRCUIT BREAKER TRIGGERED: {reason} | Stopping all trading sessions for safety"
        )

        # Persist circuit breaker state to Redis (LIVE-RM-002)
        # This prevents new sessions from starting after restart.
        try:
            from squant.infra.redis import get_redis_client
            from squant.services.circuit_breaker import (
                CIRCUIT_BREAKER_STATE_KEY,
                CircuitBreakerState,
            )

            redis = get_redis_client()
            now = datetime.now(UTC)
            cooldown_minutes = self._risk_manager.config.circuit_breaker_cooldown_minutes
            cooldown_until = datetime.fromtimestamp(
                now.timestamp() + cooldown_minutes * 60, tz=UTC
            )
            state = CircuitBreakerState(
                is_active=True,
                triggered_at=now,
                trigger_type="auto",
                trigger_reason=reason,
                cooldown_until=cooldown_until,
            )
            await redis.set(CIRCUIT_BREAKER_STATE_KEY, json.dumps(state.to_dict()))
        except Exception:
            logger.warning("Failed to persist circuit breaker state to Redis", exc_info=True)

        # Stop all live sessions (except this one which is already stopped)
        live_manager = get_live_session_manager()
        try:
            await live_manager.stop_all(reason=f"Circuit breaker: {reason}")
        except Exception as e:
            logger.exception(f"Error stopping live sessions: {e}")

        # Stop all paper sessions
        paper_manager = get_session_manager()
        try:
            await paper_manager.stop_all(reason=f"Circuit breaker: {reason}")
        except Exception as e:
            logger.exception(f"Error stopping paper sessions: {e}")

    # Timeframe to seconds mapping for adaptive health check timeout
    _TIMEFRAME_SECONDS: dict[str, int] = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
        "1w": 604800,
    }

    def is_healthy(self, timeout_seconds: int = 300) -> bool:
        """Check if engine is healthy (recently active).

        The effective timeout adapts to the candle timeframe: it uses
        max(timeout_seconds, timeframe_seconds * 2) so that longer
        timeframes (e.g., 1h, 4h) are not incorrectly marked as stale
        between candle intervals, while still detecting genuine failures
        within a reasonable window (LIVE-MO-001: reduced from 3x to 2x).

        Args:
            timeout_seconds: Base timeout in seconds since last activity.

        Returns:
            True if healthy, False if stale or not running.
        """
        if not self._is_running:
            return False
        if self._last_active_at is None:
            return True
        tf_seconds = self._TIMEFRAME_SECONDS.get(self._timeframe, 300)
        effective_timeout = max(timeout_seconds, tf_seconds * 2)
        elapsed = (datetime.now(UTC) - self._last_active_at).total_seconds()
        return elapsed < effective_timeout

    async def start(self) -> None:
        """Start the live trading engine.

        Verifies account connection, syncs balance, and calls strategy.on_init().
        """
        if self._is_running:
            logger.warning(f"Engine {self._run_id} already running")
            return

        logger.info(f"Starting live trading engine {self._run_id}")

        try:
            # Verify adapter connection
            await self._adapter.connect()

            # Sync account balance
            await self._sync_balance()

            self._is_running = True
            self._started_at = datetime.now(UTC)
            self._last_active_at = datetime.now(UTC)

            # Call strategy initialization
            self._strategy.on_init()
            logger.info(f"Strategy initialized for live run {self._run_id}")

        except Exception as e:
            logger.exception(f"Error starting live trading engine: {e}")
            self._error_message = f"Startup failed: {e}"
            self._is_running = False
            raise

    async def stop(self, error: str | None = None, cancel_orders: bool = True) -> None:
        """Stop the live trading engine.

        Does NOT acquire _processing_lock because stop() may be called from
        within process_candle's error handler (which already holds the lock).
        Setting _is_running=False early prevents process_candle from proceeding
        if it's awaiting re-entry. (R3-002)

        Args:
            error: Optional error message if stopping due to error.
            cancel_orders: Whether to cancel open orders on stop.
        """
        if not self._is_running:
            logger.warning(f"Engine {self._run_id} not running")
            return

        logger.info(f"Stopping live trading engine {self._run_id}")

        # Set flag early to prevent further candle processing
        self._is_running = False

        if error:
            self._error_message = error

        # Cancel open orders if requested
        if cancel_orders:
            await self._cancel_all_orders()

        try:
            # Call strategy cleanup
            self._strategy.on_stop()
            logger.info(f"Strategy stopped for run {self._run_id}")
        except Exception as e:
            logger.exception(f"Error in strategy on_stop: {e}")
            if not self._error_message:
                self._error_message = f"Strategy stop failed: {e}"

        self._stopped_at = datetime.now(UTC)

        # Notification: engine stopped (LIVE-011)
        _fire_notification(
            self._run_id,
            level="critical" if self._error_message else "info",
            event_type="engine_crashed" if self._error_message else "engine_stopped",
            title="引擎异常停止" if self._error_message else "引擎已停止",
            message=self._error_message or f"实盘会话 {self._symbol} 已正常停止",
            details={"symbol": self._symbol, "bar_count": self._bar_count},
        )

        # Emit engine_stopped event via WebSocket
        if self._on_event:
            try:
                event = {
                    "event": "engine_stopped",
                    "run_id": str(self._run_id),
                    "error_message": self._error_message,
                    "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
                }
                loop = asyncio.get_running_loop()
                loop.create_task(self._on_event(event))
            except Exception:
                pass

    async def emergency_close(self) -> dict[str, Any]:
        """Emergency close all positions at market price.

        Returns:
            Dict with close operation results including:
            - run_id: Strategy run ID
            - status: "completed", "partial", "in_progress", or "not_active"
            - message: Optional message (for in_progress or errors)
            - orders_cancelled: Number of orders cancelled
            - positions_closed: Number of positions closed
            - remaining_positions: List of positions that failed to close (TRD-038#5)
            - errors: List of error details
        """
        # TRD-038#6: Check if already in progress
        if self._emergency_close_in_progress:
            return {
                "run_id": str(self._run_id),
                "status": "in_progress",
                "message": "Emergency close operation already in progress",
                "orders_cancelled": None,
                "positions_closed": None,
                "remaining_positions": None,
                "errors": None,
            }

        self._emergency_close_in_progress = True
        try:
            # Update activity timestamp to prevent health check timeout during close (LV-6)
            self._last_active_at = datetime.now(UTC)
            logger.warning(f"Emergency close triggered for run {self._run_id}")

            # Notification: emergency close (LIVE-011)
            _fire_notification(
                self._run_id,
                level="critical",
                event_type="emergency_close",
                title="紧急平仓触发",
                message=f"实盘会话 {self._symbol} 开始执行紧急平仓",
                details={"symbol": self._symbol},
            )

            results: dict[str, Any] = {
                "run_id": str(self._run_id),
                "orders_cancelled": 0,
                "positions_closed": 0,
                "remaining_positions": [],
                "errors": [],
            }

            # Cancel all open orders first
            cancelled = await self._cancel_all_orders()
            results["orders_cancelled"] = len(cancelled)

            # Close all positions at market and wait for fills
            pending_close_orders: list[tuple[str, OrderResponse]] = []  # (symbol, response)
            for symbol, position in list(self._context.positions.items()):
                if position.is_open:
                    try:
                        # Place market order to close
                        side = OrderSide.SELL if position.amount > 0 else OrderSide.BUY
                        order_request = OrderRequest(
                            symbol=symbol,
                            side=side,
                            type="market",
                            amount=abs(position.amount),
                        )

                        response = await self._adapter.place_order(order_request)
                        pending_close_orders.append((symbol, response))
                        self._last_active_at = datetime.now(UTC)
                        logger.info(
                            f"Emergency close order placed: {symbol} {side.value} "
                            f"{abs(position.amount)} (order_id={response.order_id})"
                        )

                    except Exception as e:
                        logger.exception(f"Error closing position for {symbol}: {e}")
                        results["errors"].append(
                            {
                                "symbol": symbol,
                                "error": str(e),
                            }
                        )

            # Wait for close orders to fill
            for symbol, response in pending_close_orders:
                try:
                    final = await self._wait_for_order_fill(symbol, response)
                    if final.status == OrderStatus.FILLED:
                        results["positions_closed"] += 1
                    else:
                        logger.warning(
                            f"Emergency close order not filled: {symbol} "
                            f"status={final.status.value}"
                        )
                        results["errors"].append(
                            {
                                "symbol": symbol,
                                "error": f"Order not filled: status={final.status.value}",
                            }
                        )
                except Exception as e:
                    logger.exception(f"Error waiting for close order fill: {symbol}: {e}")
                    results["errors"].append(
                        {
                            "symbol": symbol,
                            "error": f"Fill wait failed: {e}",
                        }
                    )

            # TRD-038#5: Collect remaining positions based on unfilled orders
            error_symbols = {err["symbol"] for err in results["errors"]}
            for symbol, position in self._context.positions.items():
                if position.is_open and symbol in error_symbols:
                    results["remaining_positions"].append(
                        {
                            "symbol": symbol,
                            "amount": str(position.amount),
                            "side": "long" if position.amount > 0 else "short",
                        }
                    )

            # Set status based on results
            if results["remaining_positions"]:
                results["status"] = "partial"
                results["message"] = (
                    f"Partial close: {results['positions_closed']} closed, "
                    f"{len(results['remaining_positions'])} remaining"
                )
            else:
                results["status"] = "completed"
                results["message"] = None

            # Stop the engine
            await self.stop(error="Emergency close executed", cancel_orders=False)

            return results
        finally:
            self._emergency_close_in_progress = False

    async def process_candle(self, candle: WSCandle) -> None:
        """Process a WebSocket candle update.

        Only processes closed candles. Execution flow:
        1. Update current price and context bar (fresh prices)
        2. Sync balance from exchange (cash baseline)
        3. Sync pending orders (fills adjust cash/positions)
        4. Record equity snapshot (consistent pre-strategy state)
        5. Call strategy.on_bar()
        6. Process order requests from strategy

        Args:
            candle: WebSocket candle data.
        """
        if not self._is_running or self._warming_up:
            return

        # Block new candle processing during emergency close (C-DEFER-3)
        if self._emergency_close_in_progress:
            return

        # Check if circuit breaker was triggered by order update (RSK-012)
        if self._circuit_breaker_triggered:
            logger.warning(f"Circuit breaker active for session {self._run_id}, stopping trading")

            # Notification: circuit breaker (LIVE-011)
            _fire_notification(
                self._run_id,
                level="critical",
                event_type="circuit_breaker_triggered",
                title="熔断触发",
                message=f"实盘会话 {self._symbol} 因连续亏损触发熔断，已停止交易",
                details={"symbol": self._symbol},
            )

            await self.stop(error="Circuit breaker triggered due to consecutive losses")

            # Trigger global circuit breaker to stop all sessions (Issue 033 fix)
            # This ensures that when one session triggers circuit breaker due to
            # consecutive losses, all sessions are stopped for safety
            await self._trigger_global_circuit_breaker()
            return

        # Only process closed candles
        if not candle.is_closed:
            return

        # Verify symbol matches
        if candle.symbol != self._symbol:
            logger.warning(f"Symbol mismatch: expected {self._symbol}, got {candle.symbol}")
            return

        # Acquire processing lock to prevent race with stop() (R3-002)
        async with self._processing_lock:
            if not self._is_running:
                return

            try:
                # Update last activity timestamp
                self._last_active_at = datetime.now(UTC)

                # Update current price
                self._current_price = candle.close

                # Convert WSCandle to Bar
                bar = self._candle_to_bar(candle)

                # Update context prices first so position valuations use fresh data
                self._context._set_current_bar(bar)
                self._context._add_bar_to_history(bar)

                # Drain buffered WebSocket order updates before polling to ensure
                # consistent state (ISSUE-203 fix: no concurrent mutation)
                self._drain_ws_updates()

                # Validate exchange balance (monitoring only, no cash overwrite).
                # Cash tracked incrementally via fill processing (LIVE-012).
                await self._sync_balance()
                await self._sync_pending_orders()

                # Check daily risk stats reset on each bar (LIVE-RM-005)
                self._risk_manager.check_daily_reset()

                # Update risk manager with equity computed from consistent state
                self._risk_manager.update_equity(self._context.equity)
                self._risk_manager.update_unrealized_pnl(self._context._get_unrealized_pnl())

                # Auto-stop if total loss limit triggered (IMP-005)
                if self._risk_manager.check_total_loss_limit():
                    msg = (
                        f"Risk auto-stop: total loss limit triggered "
                        f"(loss {-self._risk_manager.state.total_pnl:.2f}, "
                        f"unrealized {self._risk_manager.state.unrealized_pnl:.2f})"
                    )
                    logger.warning(f"Live engine {self._run_id}: {msg}")
                    self._context.log(msg)

                    # Notification: total loss limit (LIVE-011)
                    _fire_notification(
                        self._run_id,
                        level="critical",
                        event_type="total_loss_limit",
                        title="总亏损限额触发",
                        message=f"实盘会话 {self._symbol} 已触发总亏损限额自动停止",
                        details={
                            "symbol": self._symbol,
                            "total_pnl": float(self._risk_manager.state.total_pnl),
                            "unrealized_pnl": float(
                                self._risk_manager.state.unrealized_pnl
                            ),
                        },
                    )

                    await self.stop(error=msg)
                    return

                # Record equity snapshot BEFORE strategy execution to capture
                # the portfolio state at bar close (C-DEFER-8)
                self._context._record_equity_snapshot(bar.time)

                # Persist snapshot: try synchronous callback first, fall back to batch
                if self._context.equity_curve:
                    latest_snapshot = self._context.equity_curve[-1]
                    persisted = False
                    if self._on_snapshot:
                        try:
                            await self._on_snapshot(str(self._run_id), latest_snapshot)
                            persisted = True
                        except Exception as e:
                            logger.warning(
                                f"Snapshot persist callback failed for {self._run_id}: {e}"
                            )
                    if not persisted:
                        self._pending_snapshots.append(latest_snapshot)

                # Notify strategy of fills and completed orders (before on_bar)
                fill_delta = (
                    self._context._total_fills_added - self._last_callback_fill_total
                )
                if fill_delta > 0:
                    recent_fills = list(self._context._fills)[-fill_delta:]
                    for fill in recent_fills:
                        try:
                            self._strategy.on_fill(fill)
                        except Exception as e:
                            self._context.log(f"ERROR in on_fill: {e}")
                            logger.warning(f"Strategy on_fill error: {e}")
                self._last_callback_fill_total = self._context._total_fills_added

                completed_delta = (
                    self._context._total_completed_added
                    - self._last_callback_completed_total
                )
                if completed_delta > 0:
                    recent_completed = list(self._context._completed_orders)[
                        -completed_delta:
                    ]
                    for order in recent_completed:
                        try:
                            self._strategy.on_order_done(order)
                        except Exception as e:
                            self._context.log(f"ERROR in on_order_done: {e}")
                            logger.warning(f"Strategy on_order_done error: {e}")
                self._last_callback_completed_total = (
                    self._context._total_completed_added
                )

                # Call strategy on_bar with resource limits (STR-013)
                from squant.config import get_settings

                settings = get_settings()
                try:
                    with resource_limiter(
                        cpu_seconds=settings.strategy.cpu_limit_seconds,
                        memory_mb=settings.strategy.memory_limit_mb,
                    ):
                        self._strategy.on_bar(bar)
                except ResourceLimitExceededError as e:
                    logger.error(f"Strategy resource limit exceeded: {e}")

                    # Notification: resource limit (LIVE-011)
                    _fire_notification(
                        self._run_id,
                        level="critical",
                        event_type="strategy_resource_exceeded",
                        title="策略资源超限",
                        message=f"实盘会话 {self._symbol} 策略资源超限: {e}",
                        details={"symbol": self._symbol, "error": str(e)},
                    )

                    await self.stop(error=f"Strategy resource limit exceeded: {e}")
                    raise

                # Process pending order requests from strategy
                await self._process_order_requests()

                self._bar_count += 1

                # Persist result state for crash recovery
                if self._on_result:
                    try:
                        result_data = self.build_result_for_persistence()
                        await self._on_result(str(self._run_id), result_data)
                    except Exception as e:
                        logger.warning(f"Result persist callback failed for {self._run_id}: {e}")

                # Flush order/trade audit events (LIVE-013)
                if self._on_order_persist and self._pending_order_events:
                    events_to_persist = self._pending_order_events.copy()
                    self._pending_order_events.clear()
                    try:
                        await self._on_order_persist(
                            str(self._run_id), events_to_persist
                        )
                    except Exception as e:
                        logger.warning(f"Order persist callback failed for {self._run_id}: {e}")

                # Emit bar update event via WebSocket
                if self._on_event:
                    try:
                        event = self._build_bar_update_event()
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._on_event(event))
                    except Exception as e:
                        logger.debug(f"Event emit failed for {self._run_id}: {e}")

                logger.debug(
                    f"Processed bar {self._bar_count} at {bar.time}, equity={self._context.equity}"
                )

            except Exception as e:
                logger.exception(f"Error processing candle in live engine {self._run_id}: {e}")
                await self.stop(error=f"Error processing candle: {e}")
                raise

    def on_order_update(self, update: WSOrderUpdate) -> None:
        """Handle WebSocket order update by buffering it for later processing.

        Called when exchange pushes order status updates. Updates are queued
        and processed synchronously within process_candle via _drain_ws_updates()
        to prevent concurrent state mutation (ISSUE-203 fix).

        Args:
            update: Order update from WebSocket.
        """
        # Block order updates during emergency close to prevent
        # fill processing from modifying positions/cash mid-close (P0-2)
        if self._emergency_close_in_progress:
            logger.debug(f"Ignoring order update during emergency close: {update.order_id}")
            return

        self._pending_ws_updates.append(update)

    def _drain_ws_updates(self) -> None:
        """Process all buffered WebSocket order updates.

        Called synchronously within process_candle to ensure all WS state
        mutations happen at a controlled point, not interleaved with polling.
        """
        if not self._pending_ws_updates:
            return

        updates = self._pending_ws_updates.copy()
        self._pending_ws_updates.clear()

        for update in updates:
            self._process_single_ws_update(update)

    def _process_single_ws_update(self, update: WSOrderUpdate) -> None:
        """Process a single WebSocket order update.

        Args:
            update: Order update from WebSocket.
        """
        exchange_id = update.order_id
        internal_id = self._exchange_order_map.get(exchange_id)

        if not internal_id:
            logger.debug(f"Order update for unknown exchange order: {exchange_id}")
            return

        live_order = self._live_orders.get(internal_id)
        if not live_order:
            logger.warning(f"Live order not found for internal ID: {internal_id}")
            return

        # Convert string status to OrderStatus enum
        new_status = _WS_STATUS_MAP.get(update.status, OrderStatus.PENDING)

        # Update order state
        old_status = live_order.status
        old_filled = live_order.filled_amount  # Save before updating
        old_fee = live_order.fee  # Save old fee for incremental calculation
        live_order.status = new_status
        live_order.filled_amount = update.filled_size
        live_order.avg_fill_price = update.avg_price
        live_order.fee = update.fee or Decimal("0")
        live_order.fee_currency = update.fee_currency
        live_order.updated_at = datetime.now(UTC)

        logger.info(
            f"Order {internal_id} updated: {old_status.value} -> {new_status.value}, "
            f"filled={update.filled_size}/{live_order.amount}"
        )

        # Process fills and track trade PnL for risk management
        # Only process if there's new fill amount (incremental delta)
        fill_delta = update.filled_size - old_filled
        if new_status in (OrderStatus.PARTIAL, OrderStatus.FILLED) and fill_delta > 0:
            # Detect trade completion via _open_trade state change (not deque length,
            # which fails when _trades deque is at maxlen).
            had_open_trade = self._context._open_trade is not None
            circuit_breaker_before = self._risk_manager.state.circuit_breaker_triggered

            # Calculate incremental fee (not cumulative)
            # Only compute delta if exchange provides fee info; otherwise pass None
            # to avoid negative deltas when fee is temporarily unavailable (LV-2)
            fee_delta = None
            if update.fee is not None:
                fee_delta = update.fee - old_fee
                if fee_delta < 0:
                    fee_delta = Decimal("0")  # Fee went backwards; skip this increment
            self._process_order_fill(live_order, update, fill_delta, fee_delta)

            # Check if a trade was completed and record its PnL
            if had_open_trade and self._context._open_trade is None:
                # A new trade was completed - get its PnL
                completed_trade = self._context.trades[-1]
                if completed_trade.pnl is not None:
                    self._risk_manager.record_trade_result(completed_trade.pnl)
                    logger.info(
                        f"Recorded trade result: PnL={completed_trade.pnl}, "
                        f"consecutive_losses={self._risk_manager.state.consecutive_losses}"
                    )

                    # Check if circuit breaker was just triggered (RSK-012)
                    if (
                        not circuit_breaker_before
                        and self._risk_manager.state.circuit_breaker_triggered
                    ):
                        logger.warning(
                            f"Circuit breaker triggered for session {self._run_id} "
                            f"after {self._risk_manager.state.consecutive_losses} "
                            f"consecutive losses"
                        )
                        # Set flag for async handling - actual stop happens in main loop
                        self._circuit_breaker_triggered = True

    def _candle_to_bar(self, candle: WSCandle) -> Bar:
        """Convert WSCandle to Bar."""
        return Bar(
            time=candle.timestamp,
            symbol=candle.symbol,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )

    async def _sync_balance(self) -> None:
        """Validate account balance against local state and reconcile positions.

        Cash is NOT overwritten from exchange (LIVE-012). Local cash is tracked
        incrementally via fill processing only. Exchange balance serves as a
        health-check baseline — large discrepancies are logged as warnings.
        """
        try:
            balance = await self._adapter.get_balance()
            # Compare exchange cash vs local (monitoring only, no overwrite)
            quote_currency = self._symbol.split("/")[1]  # e.g., "USDT" from "BTC/USDT"
            quote_balance = balance.get_balance(quote_currency)
            if quote_balance:
                exchange_cash = quote_balance.available
                self._last_exchange_balance = exchange_cash
                local_cash = self._context._cash
                diff = abs(exchange_cash - local_cash)
                threshold = max(local_cash * Decimal("0.05"), Decimal("10"))
                if diff > threshold:
                    logger.warning(
                        f"Cash discrepancy for {self._symbol}: "
                        f"local={local_cash}, exchange={exchange_cash}, diff={diff}"
                    )

            # Reconcile base currency position (LIVE-005)
            base_currency = self._symbol.split("/")[0]  # e.g., "BTC" from "BTC/USDT"
            base_balance = balance.get_balance(base_currency)
            exchange_amount = base_balance.available if base_balance else Decimal("0")
            local_pos = self._context.get_position(self._symbol)
            local_amount = local_pos.amount if local_pos else Decimal("0")

            # Allow small precision differences (< 0.1% or < 0.00001)
            if local_amount > 0 or exchange_amount > 0:
                diff = abs(exchange_amount - local_amount)
                threshold = max(local_amount * Decimal("0.001"), Decimal("0.00001"))
                if diff > threshold:
                    logger.warning(
                        f"Position mismatch for {self._symbol}: "
                        f"local={local_amount}, exchange={exchange_amount}, diff={diff}"
                    )

                    # Notification: position mismatch (LIVE-011)
                    _fire_notification(
                        self._run_id,
                        level="warning",
                        event_type="position_mismatch",
                        title="仓位不匹配",
                        message=(
                            f"{self._symbol} 本地={local_amount}, "
                            f"交易所={exchange_amount}, 差异={diff}"
                        ),
                        details={
                            "symbol": self._symbol,
                            "local": str(local_amount),
                            "exchange": str(exchange_amount),
                            "diff": str(diff),
                        },
                    )

            self._balance_consecutive_failures = 0
        except Exception as e:
            self._balance_consecutive_failures += 1
            logger.warning(
                f"Failed to sync balance: {e} "
                f"(consecutive failures: {self._balance_consecutive_failures})"
            )
            if self._balance_consecutive_failures >= self._sync_failure_threshold:
                msg = (
                    f"Exchange connection lost: {self._balance_consecutive_failures} "
                    f"consecutive balance sync failures"
                )
                logger.error(f"Engine {self._run_id} stopping: {msg}")

                # Notification: balance sync failure (LIVE-011)
                _fire_notification(
                    self._run_id,
                    level="critical",
                    event_type="balance_sync_failure",
                    title="余额同步失败",
                    message=f"实盘会话 {self._symbol} 连续{self._balance_consecutive_failures}次余额同步失败",
                    details={"symbol": self._symbol, "failures": self._balance_consecutive_failures},
                )

                raise RuntimeError(msg)

    async def _sync_pending_orders(self) -> None:
        """Sync pending order status from exchange with rate limiting.

        Only polls orders that haven't been polled within the minimum interval
        to avoid excessive API calls. WebSocket updates handle most state changes,
        so polling is primarily a fallback for missed updates.
        """
        now = datetime.now(UTC)
        pending_internal_ids = [
            oid
            for oid, order in self._live_orders.items()
            if not order.is_complete and order.exchange_order_id
        ]

        polled_count = 0
        skipped_count = 0

        for internal_id in pending_internal_ids:
            live_order = self._live_orders[internal_id]
            exchange_oid = live_order.exchange_order_id

            # Check if we've polled this order recently
            if exchange_oid in self._order_last_poll:
                last_poll = self._order_last_poll[exchange_oid]
                elapsed = (now - last_poll).total_seconds()
                if elapsed < self._order_poll_min_interval:
                    skipped_count += 1
                    continue

            try:
                response = await self._adapter.get_order(
                    live_order.symbol,
                    exchange_oid,  # type: ignore
                )
                self._update_order_from_response(live_order, response)
                self._order_last_poll[exchange_oid] = now
                polled_count += 1
                self._order_sync_consecutive_failures = 0

                # Clean up tracking for completed orders
                if live_order.is_complete and exchange_oid in self._order_last_poll:
                    del self._order_last_poll[exchange_oid]

            except Exception as e:
                self._order_sync_consecutive_failures += 1
                logger.warning(
                    f"Failed to sync order {internal_id}: {e} "
                    f"(consecutive failures: {self._order_sync_consecutive_failures})"
                )
                # Still record the poll time to avoid hammering on errors
                self._order_last_poll[exchange_oid] = now
                if self._order_sync_consecutive_failures >= self._sync_failure_threshold:
                    msg = (
                        f"Exchange connection lost: {self._order_sync_consecutive_failures} "
                        f"consecutive order sync failures"
                    )
                    logger.error(f"Engine {self._run_id} stopping: {msg}")

                    # Notification: order sync failure (LIVE-011)
                    _fire_notification(
                        self._run_id,
                        level="critical",
                        event_type="order_sync_failure",
                        title="订单同步失败",
                        message=f"实盘会话 {self._symbol} 连续{self._order_sync_consecutive_failures}次订单同步失败",
                        details={
                            "symbol": self._symbol,
                            "failures": self._order_sync_consecutive_failures,
                        },
                    )

                    raise RuntimeError(msg)

        if polled_count > 0 or skipped_count > 0:
            logger.debug(
                f"Order sync: polled={polled_count}, skipped={skipped_count} "
                f"(within {self._order_poll_min_interval}s interval)"
            )

        # Cleanup completed and zombie orders (C-DEFER-4)
        self._cleanup_stale_orders()

    def _cleanup_stale_orders(self) -> None:
        """Remove completed orders and mark zombie orders as rejected.

        Completed orders (FILLED, CANCELLED, REJECTED) are removed from
        _live_orders after they've been processed. Orders without an
        exchange_order_id that are older than 60 seconds are considered
        zombies and marked as REJECTED.
        """
        stale_threshold = 60  # seconds
        now = datetime.now(UTC)
        to_remove: list[str] = []

        for internal_id, order in self._live_orders.items():
            # Remove completed orders (already processed)
            if order.is_complete:
                to_remove.append(internal_id)
                continue

            # Mark zombie orders (no exchange_order_id, stuck in non-terminal state)
            if not order.exchange_order_id and order.created_at:
                age = (now - order.created_at).total_seconds()
                if age > stale_threshold:
                    logger.warning(
                        f"Marking zombie order {internal_id} as REJECTED "
                        f"(no exchange_order_id after {age:.0f}s)"
                    )
                    order.status = OrderStatus.REJECTED
                    to_remove.append(internal_id)

        for internal_id in to_remove:
            order = self._live_orders.pop(internal_id)
            # Clean up exchange_order_map if present
            if order.exchange_order_id and order.exchange_order_id in self._exchange_order_map:
                del self._exchange_order_map[order.exchange_order_id]

    def _update_order_from_response(self, live_order: LiveOrder, response: OrderResponse) -> None:
        """Update live order from exchange response."""
        old_filled = live_order.filled_amount
        old_fee = live_order.fee  # Save old fee for incremental calculation
        live_order.status = response.status
        live_order.filled_amount = response.filled
        live_order.avg_fill_price = response.avg_price
        live_order.fee = response.fee or Decimal("0")
        live_order.fee_currency = response.fee_currency
        live_order.updated_at = datetime.now(UTC)

        # Process new fills
        if response.filled > old_filled:
            fill_amount = response.filled - old_filled
            # Only compute fee delta if fee info is available (LV-2)
            fee_delta = None
            if response.fee is not None:
                fee_delta = response.fee - old_fee
                if fee_delta < 0:
                    fee_delta = Decimal("0")  # Fee went backwards; skip this increment

            # Detect trade completion via _open_trade state change (not deque length,
            # which fails when _trades deque is at maxlen).
            had_open_trade = self._context._open_trade is not None
            circuit_breaker_before = self._risk_manager.state.circuit_breaker_triggered

            self._process_incremental_fill(live_order, fill_amount, response, fee_delta)

            # Check if a trade was completed and record its PnL for risk management
            if had_open_trade and self._context._open_trade is None:
                completed_trade = self._context.trades[-1]
                if completed_trade.pnl is not None:
                    self._risk_manager.record_trade_result(completed_trade.pnl)
                    logger.info(
                        f"[polling] Recorded trade result: PnL={completed_trade.pnl}, "
                        f"consecutive_losses="
                        f"{self._risk_manager.state.consecutive_losses}"
                    )

                    # Check if circuit breaker was just triggered
                    if (
                        not circuit_breaker_before
                        and self._risk_manager.state.circuit_breaker_triggered
                    ):
                        logger.warning(
                            f"Circuit breaker triggered for session {self._run_id} "
                            f"after {self._risk_manager.state.consecutive_losses} "
                            f"consecutive losses (detected via polling)"
                        )
                        self._circuit_breaker_triggered = True

    def _process_order_fill(
        self,
        live_order: LiveOrder,
        update: WSOrderUpdate,
        fill_delta: Decimal,
        fee_delta: Decimal | None = None,
    ) -> None:
        """Process order fill from WebSocket update.

        Args:
            live_order: The live order being filled.
            update: WebSocket order update with current state.
            fill_delta: The incremental fill amount (new fills only).
            fee_delta: The incremental fee (new fees only). If None, uses total fee.
        """
        if update.avg_price is None:
            return

        # Use incremental fee if provided, otherwise fall back to total
        fill_fee = fee_delta if fee_delta is not None else (update.fee or Decimal("0"))

        # Create fill record with incremental amount (not total)
        fill = Fill(
            order_id=live_order.internal_id,
            symbol=live_order.symbol,
            side=live_order.side,
            price=update.avg_price,
            amount=fill_delta,
            fee=fill_fee,
            timestamp=datetime.now(UTC),
        )

        # Process in context with force=True: in live trading, fills are already
        # executed on the exchange and must be recorded regardless of local
        # cash/position tracking discrepancies (ISSUE-201 fix)
        self._context._process_fill(fill, force=True)
        self._context._move_completed_orders()

        # Record fill for daily trade count limit (LIVE-RM-001)
        self._risk_manager.record_order_fill()

        # Buffer "fill" event for audit persistence (LIVE-013)
        self._pending_order_events.append({
            "type": "fill",
            "internal_id": live_order.internal_id,
            "fill_price": str(update.avg_price),
            "fill_amount": str(fill_delta),
            "fee": str(fill_fee),
            "fee_currency": live_order.fee_currency,
            "total_filled": str(live_order.filled_amount),
            "avg_fill_price": str(live_order.avg_fill_price)
            if live_order.avg_fill_price
            else None,
            "status": live_order.status.value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    def _process_incremental_fill(
        self,
        live_order: LiveOrder,
        fill_amount: Decimal,
        response: OrderResponse,
        fee_delta: Decimal | None = None,
    ) -> None:
        """Process incremental fill from polling.

        Args:
            live_order: The live order being filled.
            fill_amount: The incremental fill amount.
            response: Order response from exchange.
            fee_delta: The incremental fee. If None, uses total fee from response.
        """
        if response.avg_price is None:
            return

        # Use incremental fee if provided, otherwise fall back to total
        fill_fee = fee_delta if fee_delta is not None else (response.fee or Decimal("0"))

        fill = Fill(
            order_id=live_order.internal_id,
            symbol=live_order.symbol,
            side=live_order.side,
            price=response.avg_price,
            amount=fill_amount,
            fee=fill_fee,
            timestamp=datetime.now(UTC),
        )

        # force=True: live fills are already executed on the exchange (ISSUE-201 fix)
        self._context._process_fill(fill, force=True)
        self._context._move_completed_orders()

        # Record fill for daily trade count limit (LIVE-RM-001)
        self._risk_manager.record_order_fill()

        # Buffer "fill" event for audit persistence (LIVE-013)
        self._pending_order_events.append({
            "type": "fill",
            "internal_id": live_order.internal_id,
            "fill_price": str(response.avg_price),
            "fill_amount": str(fill_amount),
            "fee": str(fill_fee),
            "fee_currency": live_order.fee_currency,
            "total_filled": str(live_order.filled_amount),
            "avg_fill_price": str(live_order.avg_fill_price)
            if live_order.avg_fill_price
            else None,
            "status": live_order.status.value,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    async def _process_order_requests(self) -> None:
        """Process pending order requests from strategy context.

        Gets orders from the context's pending orders and submits them
        to the exchange after risk validation.
        """
        # Skip all order processing if circuit breaker was triggered
        if self._circuit_breaker_triggered:
            logger.warning("Skipping order processing: circuit breaker triggered")
            return

        # Get pending orders from context that haven't been submitted
        for order in self._context._get_pending_orders():
            # Guard: STOP/STOP_LIMIT not yet supported in live trading
            if order.type in (BacktestOrderType.STOP, BacktestOrderType.STOP_LIMIT):
                reason = (
                    f"STOP/STOP_LIMIT orders not supported in live trading yet. "
                    f"Use LIMIT or MARKET orders instead."
                )
                logger.warning(f"Order {order.id} rejected: {reason}")
                order.status = OrderStatus.REJECTED
                self._context._completed_orders.append(order)
                self._context._total_completed_added += 1
                if order in self._context._pending_orders:
                    self._context._pending_orders.remove(order)
                self._pending_risk_triggers.append(
                    {
                        "rule_type": "unsupported_order_type",
                        "trigger_type": "order_rejected",
                        "details": {
                            "reason": reason,
                            "order_symbol": order.symbol,
                            "order_side": order.side.value,
                            "order_type": order.type.value,
                            "order_amount": str(order.amount),
                        },
                    }
                )
                continue

            # Skip if already tracked as live order
            if order.id in self._live_orders:
                continue

            # Validate against risk rules
            current_position = Decimal("0")
            pos = self._context.get_position(order.symbol)
            if pos:
                current_position = pos.amount

            risk_result = self._risk_manager.validate_order(
                OrderRequest(
                    symbol=order.symbol,
                    side=order.side,
                    type=order.type,
                    amount=order.amount,
                    price=order.price,
                ),
                current_price=self._current_price or Decimal("0"),
                current_position_amount=current_position,
            )

            if not risk_result.passed:
                logger.warning(f"Order rejected by risk manager: {risk_result.reason}")
                # Mark as rejected in context
                order.status = OrderStatus.REJECTED
                self._context._completed_orders.append(order)
                self._context._total_completed_added += 1
                if order in self._context._pending_orders:
                    self._context._pending_orders.remove(order)

                # Record risk trigger for persistence (Issue 010)
                self._pending_risk_triggers.append(
                    {
                        "rule_type": risk_result.rule_type.value
                        if risk_result.rule_type
                        else "unknown",
                        "trigger_type": "order_rejected",
                        "details": {
                            "reason": risk_result.reason,
                            "order_symbol": order.symbol,
                            "order_side": order.side.value,
                            "order_amount": str(order.amount),
                            "order_price": str(order.price) if order.price else None,
                            "metadata": risk_result.metadata,
                        },
                    }
                )
                continue

            # Submit order to exchange
            await self._submit_order(order)

    async def _submit_order(self, order: Any) -> None:
        """Submit order to exchange.

        Args:
            order: SimulatedOrder from context.
        """
        try:
            request = OrderRequest(
                symbol=order.symbol,
                side=order.side,
                type=order.type,
                amount=order.amount,
                price=order.price,
                client_order_id=order.id,
            )

            response = await self._adapter.place_order(request)

            # Validate exchange returned an order ID (C-DEFER-4)
            if not response.order_id:
                raise ValueError(
                    f"Exchange returned empty order_id for {order.symbol} {order.side.value}"
                )

            # Create live order tracking
            live_order = LiveOrder(
                internal_id=order.id,
                exchange_order_id=response.order_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.type.value,
                amount=order.amount,
                price=order.price,
                status=response.status,
            )
            live_order.created_at = datetime.now(UTC)

            self._live_orders[order.id] = live_order
            self._exchange_order_map[response.order_id] = order.id

            # Update context order status
            order.status = response.status

            logger.info(
                f"Order submitted: {order.id} -> exchange:{response.order_id}, "
                f"status={response.status.value}"
            )

            # Buffer "placed" event for audit persistence (LIVE-013)
            self._pending_order_events.append({
                "type": "placed",
                "internal_id": live_order.internal_id,
                "exchange_order_id": live_order.exchange_order_id,
                "symbol": live_order.symbol,
                "side": live_order.side.value,
                "order_type": live_order.order_type,
                "amount": str(live_order.amount),
                "price": str(live_order.price) if live_order.price else None,
                "status": live_order.status.value,
                "created_at": live_order.created_at.isoformat()
                if live_order.created_at
                else datetime.now(UTC).isoformat(),
            })

        except Exception as e:
            logger.exception(f"Failed to submit order {order.id}: {e}")
            # Mark as rejected
            order.status = OrderStatus.REJECTED
            self._context._completed_orders.append(order)
            self._context._total_completed_added += 1
            if order in self._context._pending_orders:
                self._context._pending_orders.remove(order)

    async def _cancel_all_orders(self) -> list[str]:
        """Cancel all open orders.

        Returns:
            List of cancelled order IDs.
        """
        cancelled: list[str] = []

        for internal_id, live_order in self._live_orders.items():
            if not live_order.is_complete and live_order.exchange_order_id:
                try:
                    response = await self._adapter.cancel_order(
                        CancelOrderRequest(
                            symbol=live_order.symbol,
                            order_id=live_order.exchange_order_id,
                        )
                    )
                    # Use exchange response as source of truth (C-DEFER-7)
                    self._update_order_from_response(live_order, response)
                    if live_order.status == OrderStatus.CANCELLED:
                        cancelled.append(internal_id)
                        logger.info(f"Cancelled order {internal_id}")
                    else:
                        logger.warning(
                            f"Order {internal_id} was {live_order.status.value} "
                            f"before cancel took effect (filled={live_order.filled_amount})"
                        )
                except Exception as e:
                    logger.warning(f"Failed to cancel order {internal_id}: {e}")

        return cancelled

    async def _wait_for_order_fill(
        self,
        symbol: str,
        order_response: OrderResponse,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> OrderResponse:
        """Wait for an order to reach a terminal state (filled/cancelled/rejected).

        Args:
            symbol: Trading pair symbol.
            order_response: Initial order response from place_order.
            timeout: Maximum time to wait in seconds.
            poll_interval: Time between status checks in seconds.

        Returns:
            Final order response.
        """
        terminal_statuses = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED}

        if order_response.status in terminal_statuses:
            return order_response

        deadline = datetime.now(UTC).timestamp() + timeout
        order_id = order_response.order_id
        last_response = order_response

        while datetime.now(UTC).timestamp() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                last_response = await self._adapter.get_order(symbol, order_id)
                if last_response.status in terminal_statuses:
                    return last_response
            except Exception as e:
                logger.warning(f"Error polling order {order_id}: {e}")

        logger.warning(
            f"Timeout waiting for order {order_id} fill (last status: {last_response.status.value})"
        )
        return last_response

    def get_pending_snapshots(self) -> list[EquitySnapshot]:
        """Get and clear pending equity snapshots."""
        snapshots = self._pending_snapshots.copy()
        self._pending_snapshots.clear()
        return snapshots

    def peek_pending_snapshots(self) -> list[EquitySnapshot]:
        """Read pending equity snapshots without clearing them."""
        return self._pending_snapshots.copy()

    def should_persist_snapshots(self) -> bool:
        """Check if snapshots should be persisted."""
        return len(self._pending_snapshots) >= self._snapshot_batch_size

    def get_pending_risk_triggers(self) -> list[dict[str, Any]]:
        """Get and clear pending risk trigger events (Issue 010).

        Returns:
            List of risk trigger data dictionaries.
        """
        triggers = self._pending_risk_triggers.copy()
        self._pending_risk_triggers.clear()
        return triggers

    def has_pending_risk_triggers(self) -> bool:
        """Check if there are pending risk triggers to persist."""
        return len(self._pending_risk_triggers) > 0

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get current engine state snapshot for API responses.

        Extends build_result_for_persistence() with API-only fields
        (run metadata, pending orders, live orders) that are not stored in DB.
        """
        result = self.build_result_for_persistence()

        # API-only: run metadata
        result["run_id"] = str(self._run_id)
        result["symbol"] = self._symbol
        result["timeframe"] = self._timeframe
        result["is_running"] = self._is_running
        result["started_at"] = self._started_at.isoformat() if self._started_at else None
        result["stopped_at"] = self._stopped_at.isoformat() if self._stopped_at else None
        result["error_message"] = self._error_message
        result["initial_capital"] = str(self._context.initial_capital)

        # API-only: pending orders (transient, not persisted)
        result["pending_orders"] = [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "amount": str(order.amount),
                "price": str(order.price) if order.price else None,
                "status": order.status.value,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            }
            for order in self._context.pending_orders
        ]

        # API-only: live exchange orders (transient, not persisted)
        result["live_orders"] = [
            {
                "internal_id": lo.internal_id,
                "exchange_id": lo.exchange_order_id,
                "symbol": lo.symbol,
                "side": lo.side.value,
                "amount": str(lo.amount),
                "filled": str(lo.filled_amount),
                "status": lo.status.value,
            }
            for _oid, lo in self._live_orders.items()
            if not lo.is_complete
        ]

        return result

    def build_result_for_persistence(self) -> dict[str, Any]:
        """Build result dict for DB persistence (StrategyRun.result JSONB).

        Single source of truth for result snapshots. Uses context.build_result_snapshot()
        and supplements with engine-level fields.
        """
        result = self._context.build_result_snapshot()
        result["bar_count"] = self._bar_count
        result["risk_state"] = self._risk_manager.get_state_summary()
        result["risk_config"] = self._risk_manager.config.model_dump(mode="json")
        result["live_orders"] = {
            oid: _serialize_live_order(lo) for oid, lo in self._live_orders.items()
        }
        result["exchange_order_map"] = dict(self._exchange_order_map)
        return result

    def restore_live_orders(self, state: dict[str, Any]) -> None:
        """Restore live order tracking state from persisted result.

        Called during resume to rebuild _live_orders and _exchange_order_map.
        Terminal orders (FILLED/CANCELLED/REJECTED) are skipped.

        Args:
            state: Result dict from StrategyRun.result JSONB.
        """
        self._live_orders.clear()
        self._exchange_order_map.clear()

        saved_orders = state.get("live_orders", {})
        saved_map = state.get("exchange_order_map", {})

        for internal_id, order_data in saved_orders.items():
            status = OrderStatus(order_data["status"])
            if status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                continue

            live_order = LiveOrder(
                internal_id=order_data["internal_id"],
                exchange_order_id=order_data.get("exchange_order_id"),
                symbol=order_data["symbol"],
                side=OrderSide(order_data["side"]),
                order_type=order_data["order_type"],
                amount=Decimal(str(order_data["amount"])),
                price=Decimal(str(order_data["price"])) if order_data.get("price") else None,
                status=status,
            )
            live_order.filled_amount = Decimal(str(order_data.get("filled_amount", "0")))
            if order_data.get("avg_fill_price"):
                live_order.avg_fill_price = Decimal(str(order_data["avg_fill_price"]))
            live_order.fee = Decimal(str(order_data.get("fee", "0")))
            live_order.fee_currency = order_data.get("fee_currency")
            if order_data.get("created_at"):
                live_order.created_at = datetime.fromisoformat(order_data["created_at"])
            if order_data.get("updated_at"):
                live_order.updated_at = datetime.fromisoformat(order_data["updated_at"])
            live_order.error_message = order_data.get("error_message")

            self._live_orders[internal_id] = live_order

        for exchange_id, internal_id in saved_map.items():
            if internal_id in self._live_orders:
                self._exchange_order_map[exchange_id] = internal_id

        logger.info(
            f"Restored {len(self._live_orders)} live orders and "
            f"{len(self._exchange_order_map)} exchange mappings"
        )

    def _build_bar_update_event(self) -> dict[str, Any]:
        """Build incremental bar update event for WebSocket push."""
        ctx = self._context

        fill_delta = ctx._total_fills_added - self._last_emitted_fill_total
        trade_delta = ctx._total_trades_added - self._last_emitted_trade_total
        log_delta = ctx._total_logs_added - self._last_emitted_log_total

        new_fills = list(ctx._fills)[-fill_delta:] if fill_delta > 0 else []
        new_trades = list(ctx._trades)[-trade_delta:] if trade_delta > 0 else []
        new_logs = list(ctx._logs)[-log_delta:] if log_delta > 0 else []

        self._last_emitted_fill_total = ctx._total_fills_added
        self._last_emitted_trade_total = ctx._total_trades_added
        self._last_emitted_log_total = ctx._total_logs_added

        return {
            "event": "bar_update",
            "run_id": str(self._run_id),
            "bar_count": self._bar_count,
            "cash": str(ctx._cash),
            "equity": str(ctx.equity),
            "unrealized_pnl": str(ctx._get_unrealized_pnl()),
            "realized_pnl": str(sum(t.pnl for t in ctx._trades)),
            "total_fees": str(ctx._total_fees),
            "completed_orders_count": len(ctx._completed_orders),
            "trades_count": len(ctx._trades),
            "positions": {
                sym: {
                    "amount": str(pos.amount),
                    "avg_entry_price": str(pos.avg_entry_price),
                }
                for sym, pos in ctx._positions.items()
                if pos.amount != 0
            },
            "pending_orders": [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "side": o.side.value,
                    "type": o.type.value,
                    "amount": str(o.amount),
                    "price": str(o.price) if o.price else None,
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in ctx._pending_orders
            ],
            "open_trade": _serialize_open_trade(ctx._open_trade),
            "new_fills": [_serialize_fill(f) for f in new_fills],
            "new_trades": [_serialize_trade(t) for t in new_trades],
            "new_logs": new_logs,
            "risk_state": self._risk_manager.get_state_summary(),
        }
