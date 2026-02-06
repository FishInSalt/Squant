"""Live trading engine for real-time trading with real exchange execution.

Drives strategy execution with actual order placement via exchange adapter.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar, EquitySnapshot, Fill
from squant.engine.resource_limits import ResourceLimitExceededError, resource_limiter
from squant.engine.risk import RiskConfig, RiskManager
from squant.infra.exchange.types import CancelOrderRequest, OrderRequest, OrderResponse
from squant.models.enums import OrderSide, OrderStatus

if TYPE_CHECKING:
    from squant.infra.exchange.base import ExchangeAdapter
    from squant.infra.exchange.okx.ws_types import WSCandle, WSOrderUpdate

logger = logging.getLogger(__name__)

# OKX WebSocket order status mapping (string -> OrderStatus enum)
_WS_STATUS_MAP: dict[str, OrderStatus] = {
    "live": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "mmp_canceled": OrderStatus.CANCELLED,
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

        # Live order tracking
        self._live_orders: dict[str, LiveOrder] = {}  # internal_id -> LiveOrder
        self._exchange_order_map: dict[str, str] = {}  # exchange_id -> internal_id

        # Pending order requests from strategy
        self._pending_order_requests: list[dict[str, Any]] = []

        # Current market price (updated from candles)
        self._current_price: Decimal | None = None

        # Equity snapshots for persistence
        self._pending_snapshots: list[EquitySnapshot] = []
        self._snapshot_batch_size = 10

        # Risk trigger events for persistence (Issue 010)
        self._pending_risk_triggers: list[dict[str, Any]] = []

        # Emergency close in progress flag (TRD-038#6)
        self._emergency_close_in_progress: bool = False

        # Order sync rate limiting - avoid excessive polling
        # Track last poll time per order to avoid redundant API calls
        self._order_last_poll: dict[str, datetime] = {}  # exchange_order_id -> last poll time
        self._order_poll_min_interval = 30.0  # Minimum seconds between polls for same order

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

    def is_healthy(self, timeout_seconds: int = 300) -> bool:
        """Check if engine is healthy (recently active).

        Args:
            timeout_seconds: Maximum seconds since last activity.

        Returns:
            True if healthy, False if stale or not running.
        """
        if not self._is_running:
            return False
        if self._last_active_at is None:
            return True
        elapsed = (datetime.now(UTC) - self._last_active_at).total_seconds()
        return elapsed < timeout_seconds

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

        Args:
            error: Optional error message if stopping due to error.
            cancel_orders: Whether to cancel open orders on stop.
        """
        if not self._is_running:
            logger.warning(f"Engine {self._run_id} not running")
            return

        logger.info(f"Stopping live trading engine {self._run_id}")

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

        self._is_running = False
        self._stopped_at = datetime.now(UTC)

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
            logger.warning(f"Emergency close triggered for run {self._run_id}")

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

            # Close all positions at market
            for symbol, position in self._context.positions.items():
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

                        await self._adapter.place_order(order_request)
                        results["positions_closed"] += 1
                        logger.info(
                            f"Emergency close order placed: {symbol} {side.value} {abs(position.amount)}"
                        )

                    except Exception as e:
                        logger.exception(f"Error closing position for {symbol}: {e}")
                        results["errors"].append(
                            {
                                "symbol": symbol,
                                "error": str(e),
                            }
                        )

            # TRD-038#5: Collect remaining positions after close attempts
            for symbol, position in self._context.positions.items():
                if position.is_open:
                    # Check if this position had an error (meaning it wasn't closed)
                    had_error = any(err["symbol"] == symbol for err in results["errors"])
                    if had_error:
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
        if not self._is_running:
            return

        # Block new candle processing during emergency close (C-DEFER-3)
        if self._emergency_close_in_progress:
            return

        # Check if circuit breaker was triggered by order update (RSK-012)
        if self._circuit_breaker_triggered:
            logger.warning(f"Circuit breaker active for session {self._run_id}, stopping trading")
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

            # Sync balance as baseline, then sync orders so fills adjust
            # cash incrementally on top of exchange truth (C-DEFER-8)
            await self._sync_balance()
            await self._sync_pending_orders()

            # Update risk manager with equity computed from consistent state
            self._risk_manager.update_equity(self._context.equity)

            # Record equity snapshot BEFORE strategy execution to capture
            # the portfolio state at bar close (C-DEFER-8)
            self._context._record_equity_snapshot(bar.time)

            # Track pending snapshot for persistence
            if self._context.equity_curve:
                self._pending_snapshots.append(self._context.equity_curve[-1])

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
                await self.stop(error=f"Strategy resource limit exceeded: {e}")
                raise

            # Process pending order requests from strategy
            await self._process_order_requests()

            self._bar_count += 1

            logger.debug(
                f"Processed bar {self._bar_count} at {bar.time}, equity={self._context.equity}"
            )

        except Exception as e:
            logger.exception(f"Error processing candle in live engine {self._run_id}: {e}")
            await self.stop(error=f"Error processing candle: {e}")
            raise

    def on_order_update(self, update: WSOrderUpdate) -> None:
        """Handle WebSocket order update.

        Called when exchange pushes order status updates.

        Args:
            update: Order update from WebSocket.
        """
        # Block order updates during emergency close to prevent
        # fill processing from modifying positions/cash mid-close (P0-2)
        if self._emergency_close_in_progress:
            logger.debug(f"Ignoring order update during emergency close: {update.order_id}")
            return

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
            # Record trade count before processing to detect new completed trades
            trades_before = len(self._context.trades)
            circuit_breaker_before = self._risk_manager.state.circuit_breaker_triggered

            # Calculate incremental fee (not cumulative)
            fee_delta = (update.fee or Decimal("0")) - old_fee
            self._process_order_fill(live_order, update, fill_delta, fee_delta)

            # Check if a trade was completed and record its PnL
            trades_after = len(self._context.trades)
            if trades_after > trades_before:
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
                            f"after {self._risk_manager.state.consecutive_losses} consecutive losses"
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
        """Sync account balance from exchange."""
        try:
            balance = await self._adapter.get_balance()
            # Update context cash from quote currency balance
            quote_currency = self._symbol.split("/")[1]  # e.g., "USDT" from "BTC/USDT"
            quote_balance = balance.get_balance(quote_currency)
            if quote_balance:
                self._context._cash = quote_balance.available
        except Exception as e:
            logger.warning(f"Failed to sync balance: {e}")

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

                # Clean up tracking for completed orders
                if live_order.is_complete and exchange_oid in self._order_last_poll:
                    del self._order_last_poll[exchange_oid]

            except Exception as e:
                logger.warning(f"Failed to sync order {internal_id}: {e}")
                # Still record the poll time to avoid hammering on errors
                self._order_last_poll[exchange_oid] = now

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
            fee_delta = (response.fee or Decimal("0")) - old_fee

            # Track trade count and circuit breaker state before processing
            trades_before = len(self._context.trades)
            circuit_breaker_before = self._risk_manager.state.circuit_breaker_triggered

            self._process_incremental_fill(live_order, fill_amount, response, fee_delta)

            # Check if a trade was completed and record its PnL for risk management
            trades_after = len(self._context.trades)
            if trades_after > trades_before:
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

        # Process in context
        self._context._process_fill(fill)
        self._context._move_completed_orders()

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

        self._context._process_fill(fill)
        self._context._move_completed_orders()

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

        except Exception as e:
            logger.exception(f"Failed to submit order {order.id}: {e}")
            # Mark as rejected
            order.status = OrderStatus.REJECTED
            self._context._completed_orders.append(order)
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

    def get_pending_snapshots(self) -> list[EquitySnapshot]:
        """Get and clear pending equity snapshots."""
        snapshots = self._pending_snapshots.copy()
        self._pending_snapshots.clear()
        return snapshots

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
        """Get current engine state snapshot."""
        positions = {}
        for symbol, pos in self._context.positions.items():
            if pos.is_open:
                positions[symbol] = {
                    "amount": str(pos.amount),
                    "avg_entry_price": str(pos.avg_entry_price),
                }

        pending_orders = []
        for order in self._context.pending_orders:
            pending_orders.append(
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
            )

        # Get live order details
        live_orders = []
        for _oid, lo in self._live_orders.items():
            if not lo.is_complete:
                live_orders.append(
                    {
                        "internal_id": lo.internal_id,
                        "exchange_id": lo.exchange_order_id,
                        "symbol": lo.symbol,
                        "side": lo.side.value,
                        "amount": str(lo.amount),
                        "filled": str(lo.filled_amount),
                        "status": lo.status.value,
                    }
                )

        return {
            "run_id": str(self._run_id),
            "symbol": self._symbol,
            "timeframe": self._timeframe,
            "is_running": self._is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "error_message": self._error_message,
            "bar_count": self._bar_count,
            "cash": str(self._context.cash),
            "equity": str(self._context.equity),
            "initial_capital": str(self._context.initial_capital),
            "total_fees": str(self._context.total_fees),
            "positions": positions,
            "pending_orders": pending_orders,
            "live_orders": live_orders,
            "completed_orders_count": len(self._context.completed_orders),
            "trades_count": len(self._context.trades),
            "risk_state": self._risk_manager.get_state_summary(),
        }
