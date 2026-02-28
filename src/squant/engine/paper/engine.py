"""Paper trading engine for real-time simulated trading.

Uses WebSocket market data to drive strategy execution with local order matching.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar, EquitySnapshot, OrderType
from squant.engine.paper.matching import PaperMatchingEngine
from squant.engine.resource_limits import ResourceLimitExceededError, resource_limiter
from squant.engine.risk.manager import RiskManager
from squant.engine.risk.models import RiskConfig
from squant.infra.exchange.okx.ws_types import WSCandle
from squant.infra.exchange.types import OrderRequest
from squant.models.enums import OrderSide as ExchangeOrderSide
from squant.models.enums import OrderType as ExchangeOrderType

# Callback type for synchronous snapshot persistence
SnapshotPersistCallback = Callable[[str, EquitySnapshot], Awaitable[None]]
# Callback type for synchronous result state persistence
ResultPersistCallback = Callable[[str, dict[str, Any]], Awaitable[None]]

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Real-time paper trading engine.

    Processes WebSocket candle data and drives strategy execution
    with local order matching simulation.

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
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0.0005"),
        params: dict[str, Any] | None = None,
        on_snapshot: SnapshotPersistCallback | None = None,
        on_result: ResultPersistCallback | None = None,
        risk_config: RiskConfig | None = None,
    ):
        """Initialize paper trading engine.

        Args:
            run_id: Strategy run ID.
            strategy: Strategy instance to execute.
            symbol: Trading symbol (e.g., "BTC/USDT").
            timeframe: Candle timeframe (e.g., "1m").
            initial_capital: Starting capital.
            commission_rate: Commission rate.
            slippage: Slippage rate (default 5bps to cover typical spread).
            params: Strategy parameters.
            on_snapshot: Optional callback for synchronous snapshot persistence.
                Called after each equity snapshot is recorded. If the callback
                succeeds, the snapshot is not added to the pending batch.
            on_result: Optional callback for synchronous result state persistence.
                Called after each bar is fully processed (including strategy on_bar).
                Persists the trading state needed for crash recovery.
            risk_config: Optional risk management configuration. When provided,
                orders are validated against risk rules before execution.
        """
        self._run_id = run_id
        self._strategy = strategy
        self._symbol = symbol
        self._timeframe = timeframe

        # Get settings dynamically (not at module level) for better testability
        from squant.config import get_settings

        settings = get_settings()

        # Initialize context (reused from backtest) with memory limits from config
        self._context = BacktestContext(
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
            params=params,
            max_equity_curve=settings.paper_max_equity_curve_size,
            max_completed_orders=settings.paper_max_completed_orders,
            max_fills=settings.paper_max_fills,
            max_trades=settings.paper_max_trades,
            max_logs=settings.paper_max_logs,
        )

        # Tick-level matching engine (paper-specific, not bar-level backtest engine)
        self._matching_engine = PaperMatchingEngine(
            commission_rate=commission_rate,
            slippage=slippage,
        )

        # Risk manager (optional, mirrors live trading pattern)
        self._risk_manager: RiskManager | None = None
        if risk_config:
            self._risk_manager = RiskManager(
                config=risk_config,
                initial_equity=initial_capital,
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

        # Synchronous persistence callbacks
        self._on_snapshot = on_snapshot
        self._on_result = on_result

        # Pending equity snapshots for batch persistence (fallback when callback fails)
        self._pending_snapshots: list[EquitySnapshot] = []
        self._snapshot_batch_size = 10  # Persist every N bars

        # Lock to ensure stop() waits for in-progress candle processing (PP-C05)
        self._processing_lock = asyncio.Lock()

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
    def bar_count(self) -> int:
        """Get number of bars processed."""
        return self._bar_count

    @property
    def last_active_at(self) -> datetime | None:
        """Get last activity timestamp."""
        return self._last_active_at

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
        max(timeout_seconds, timeframe_seconds * 3) so that longer
        timeframes (e.g., 1h, 4h) are not incorrectly marked as stale
        between candle intervals.

        Args:
            timeout_seconds: Base timeout in seconds since last activity.

        Returns:
            True if healthy, False if stale or not running.
        """
        if not self._is_running:
            return False
        if self._last_active_at is None:
            return True  # Just started, no candles processed yet
        tf_seconds = self._TIMEFRAME_SECONDS.get(self._timeframe, 300)
        effective_timeout = max(timeout_seconds, tf_seconds * 3)
        elapsed = (datetime.now(UTC) - self._last_active_at).total_seconds()
        return elapsed < effective_timeout

    @property
    def context(self) -> BacktestContext:
        """Get the backtest context."""
        return self._context

    async def start(self) -> None:
        """Start the paper trading engine.

        Calls strategy.on_init() and marks the engine as running.
        """
        if self._is_running:
            logger.warning(f"Engine {self._run_id} already running")
            return

        logger.info(f"Starting paper trading engine {self._run_id}")
        self._is_running = True
        self._started_at = datetime.now(UTC)
        self._last_active_at = datetime.now(UTC)

        try:
            # Call strategy initialization
            self._strategy.on_init()
            logger.info(f"Strategy initialized for run {self._run_id}")
        except Exception as e:
            logger.exception(f"Error in strategy on_init: {e}")
            self._error_message = f"Strategy initialization failed: {e}"
            self._is_running = False
            raise

    async def stop(self, error: str | None = None) -> None:
        """Stop the paper trading engine.

        Waits for any in-progress candle processing to complete,
        then calls strategy.on_stop() and marks the engine as stopped.

        Args:
            error: Optional error message if stopping due to error.
        """
        if not self._is_running:
            logger.warning(f"Engine {self._run_id} not running")
            return

        logger.info(f"Stopping paper trading engine {self._run_id}")

        if error:
            self._error_message = error

        # Wait for any in-progress candle processing to finish (PP-C05)
        async with self._processing_lock:
            self._stop_impl()

    def _stop_impl(self) -> None:
        """Internal stop logic (must be called with _processing_lock held or from within it)."""
        try:
            # Call strategy cleanup
            self._strategy.on_stop()
            logger.info(f"Strategy stopped for run {self._run_id}")
        except Exception as e:
            logger.exception(f"Error in strategy on_stop: {e}")
            if not self._error_message:
                self._error_message = f"Strategy stop failed: {e}"

        self._is_running = False
        self._stopped_at = datetime.now(UTC)

    async def process_candle(self, candle: WSCandle) -> None:
        """Process a WebSocket candle update (tick-level matching).

        Every candle update (closed or not) triggers order matching against
        the current price. Strategy on_bar() is only called on closed candles.

        For each candle update (closed or unclosed):
          1. Fill new market orders immediately at candle.close
          2. Check pending limit orders against candle.close
          3. Move completed orders

        Additionally, when is_closed=True (completed bar):
          4. Set current bar and add to history
          5. Record equity snapshot
          6. Persist snapshot
          7. Call strategy.on_bar()
          8. Persist result state

        Args:
            candle: WebSocket candle data.
        """
        if not self._is_running:
            return

        # Verify symbol matches
        if candle.symbol != self._symbol:
            logger.warning(f"Symbol mismatch: expected {self._symbol}, got {candle.symbol}")
            return

        # Acquire processing lock so stop() waits for completion (PP-C05)
        async with self._processing_lock:
            try:
                # Update last activity timestamp
                self._last_active_at = datetime.now(UTC)

                current_price = candle.close
                timestamp = candle.timestamp

                # 1-2. Fill new orders and match pending limits at current price
                # For unclosed candles, only use close; for closed, also pass high/low
                if candle.is_closed:
                    self._fill_new_orders(
                        current_price,
                        timestamp,
                        high=candle.high,
                        low=candle.low,
                    )
                else:
                    self._fill_new_orders(current_price, timestamp)

                # 3. Move completed orders
                self._context._move_completed_orders()

                # Only process bar-level events on closed candles
                if not candle.is_closed:
                    return

                # Convert WSCandle to Bar
                bar = self._candle_to_bar(candle)

                # 4. Update current bar and add to history
                self._context._set_current_bar(bar)
                self._context._add_bar_to_history(bar)

                # 5. Record equity snapshot (before strategy, consistent with live engine P0-1)
                self._context._record_equity_snapshot(bar.time)

                # 5a. Update risk manager equity (after snapshot, mirrors live engine)
                if self._risk_manager:
                    self._risk_manager.update_equity(self._context.equity)

                # 6. Persist snapshot: try synchronous callback first, fall back to batch
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

                # 7. Call strategy on_bar with resource limits (STR-013)
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
                    self._error_message = f"Strategy resource limit exceeded: {e}"
                    self._stop_impl()
                    raise
                except Exception as e:
                    # TRD-025#3: strategy errors (e.g., insufficient cash) should
                    # be logged but not crash the engine — consistent with backtest runner
                    logger.warning(f"Strategy on_bar error in engine {self._run_id}: {e}")
                    self._context.log(f"ERROR in on_bar: {e}")

                self._bar_count += 1

                # 8. Persist result state for crash recovery
                if self._on_result:
                    try:
                        result_data = self.build_result_for_persistence()
                        await self._on_result(str(self._run_id), result_data)
                    except Exception as e:
                        logger.warning(f"Result persist callback failed for {self._run_id}: {e}")

                logger.debug(
                    f"Processed bar {self._bar_count} at {bar.time}, equity={self._context.equity}"
                )

            except Exception as e:
                logger.exception(f"Error processing candle in engine {self._run_id}: {e}")
                # Use _stop_impl() directly since we already hold _processing_lock.
                # Calling stop() would deadlock because asyncio.Lock is not re-entrant
                # (ISSUE-300 fix). Only set error_message if not already set by an
                # inner handler (e.g., ResourceLimitExceededError sets its own message).
                if not self._error_message:
                    self._error_message = f"Error processing candle: {e}"
                if self._is_running:
                    self._stop_impl()
                raise

    def _fill_new_orders(
        self,
        current_price: Decimal,
        timestamp: datetime,
        high: Decimal | None = None,
        low: Decimal | None = None,
    ) -> None:
        """Fill new market orders immediately and check limit orders.

        Iterates over all pending orders:
        - Market orders are filled immediately at current_price (with slippage)
        - Limit orders are checked against current_price (and high/low if available)

        Args:
            current_price: Current market price (candle close).
            timestamp: Current timestamp for fills.
            high: Candle high price (for closed candles, improves limit trigger accuracy).
            low: Candle low price (for closed candles, improves limit trigger accuracy).
        """
        pending = self._context._get_pending_orders()
        if not pending:
            return

        # Separate market and limit orders for processing
        limit_orders = []
        for order in pending:
            if order.type == OrderType.MARKET:
                # Risk check before filling market order
                if not self._validate_order_risk(order, current_price):
                    continue
                fill = self._matching_engine.fill_market_order(order, current_price, timestamp)
                if fill:
                    self._process_fill_safe(fill)
            elif order.type == OrderType.LIMIT:
                limit_orders.append(order)

        # Match limit orders
        if limit_orders:
            fills = self._matching_engine.match_pending_limits(
                limit_orders, current_price, timestamp, high=high, low=low
            )
            for fill in fills:
                # Risk check before processing limit fill
                # Find the original order for validation
                order = next((o for o in limit_orders if o.id == fill.order_id), None)
                if order and not self._validate_order_risk(order, current_price):
                    continue
                self._process_fill_safe(fill)

    def _validate_order_risk(self, order: Any, current_price: Decimal) -> bool:
        """Validate an order against risk rules.

        Args:
            order: SimulatedOrder to validate.
            current_price: Current market price.

        Returns:
            True if order passes risk checks (or no risk manager), False if rejected.
        """
        if not self._risk_manager:
            return True

        # Convert backtest enums to exchange enums (same string values)
        exchange_side = ExchangeOrderSide(order.side.value)
        exchange_type = ExchangeOrderType(order.type.value)

        # Get current position amount for position size check
        position = self._context._positions.get(self._symbol)
        current_position_amount = position.amount if position and position.is_open else Decimal("0")

        order_request = OrderRequest(
            symbol=order.symbol,
            side=exchange_side,
            type=exchange_type,
            amount=order.amount,
            price=order.price,
        )

        result = self._risk_manager.validate_order(
            order_request, current_price, current_position_amount
        )

        if not result.passed:
            from squant.engine.backtest.types import OrderStatus

            order.status = OrderStatus.CANCELLED
            reason = result.reason or "Risk check failed"
            logger.warning(f"Order rejected by risk manager in {self._run_id}: {reason}")
            self._context.log(f"Order rejected (risk): {reason}")
            return False

        return True

    def _process_fill_safe(self, fill: Any) -> None:
        """Process a fill with error handling and trade result tracking.

        Args:
            fill: Fill to process.
        """
        # Track trades count before fill for detecting trade completion
        trades_count_before = len(self._context._trades)

        try:
            self._context._process_fill(fill)
        except ValueError as e:
            logger.warning(f"Fill rejected in engine {self._run_id}: {e}")
            self._context.log(f"Order fill rejected: {e}")
            return

        # Check if a trade was completed (closed) by this fill
        if self._risk_manager and len(self._context._trades) > trades_count_before:
            # A new trade was added to _trades — it just closed
            completed_trade = self._context._trades[-1]
            self._risk_manager.record_trade_result(completed_trade.pnl)

    def _candle_to_bar(self, candle: WSCandle) -> Bar:
        """Convert WSCandle to Bar.

        Args:
            candle: WebSocket candle.

        Returns:
            Bar instance.
        """
        return Bar(
            time=candle.timestamp,
            symbol=candle.symbol,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )

    def get_pending_snapshots(self) -> list[EquitySnapshot]:
        """Get and clear pending equity snapshots.

        Returns:
            List of pending snapshots for persistence.
        """
        snapshots = self._pending_snapshots.copy()
        self._pending_snapshots.clear()
        return snapshots

    def peek_pending_snapshots(self) -> list[EquitySnapshot]:
        """Read pending equity snapshots without clearing them.

        Returns:
            Copy of pending snapshots (non-destructive).
        """
        return self._pending_snapshots.copy()

    def should_persist_snapshots(self) -> bool:
        """Check if snapshots should be persisted.

        Returns:
            True if pending snapshots exceed batch size.
        """
        return len(self._pending_snapshots) >= self._snapshot_batch_size

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get current engine state snapshot for API responses.

        Extends build_result_for_persistence() with API-only fields
        (run metadata, pending orders) that are not stored in DB.
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

        # API-only: risk state (transient summary for display)
        result["risk_state"] = (
            self._risk_manager.get_state_summary() if self._risk_manager else None
        )

        return result

    def build_result_for_persistence(self) -> dict[str, Any]:
        """Build result dict for DB persistence (StrategyRun.result JSONB).

        Single source of truth for result snapshots. Uses context.build_result_snapshot()
        and supplements with engine-level fields.
        """
        result = self._context.build_result_snapshot()
        result["bar_count"] = self._bar_count
        if self._risk_manager:
            result["risk_state"] = self._risk_manager.get_state_summary()
        return result
