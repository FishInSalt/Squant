"""Live trading engine for real-time trading with real exchange execution.

Drives strategy execution with actual order placement via exchange adapter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar, EquitySnapshot, Fill
from squant.engine.risk import RiskCheckResult, RiskConfig, RiskManager
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

    @property
    def context(self) -> BacktestContext:
        """Get the backtest context."""
        return self._context

    @property
    def risk_manager(self) -> RiskManager:
        """Get the risk manager."""
        return self._risk_manager

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
        elapsed = (datetime.now(timezone.utc) - self._last_active_at).total_seconds()
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
            self._started_at = datetime.now(timezone.utc)
            self._last_active_at = datetime.now(timezone.utc)

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
        self._stopped_at = datetime.now(timezone.utc)

    async def emergency_close(self) -> dict[str, Any]:
        """Emergency close all positions at market price.

        Returns:
            Dict with close operation results.
        """
        logger.warning(f"Emergency close triggered for run {self._run_id}")

        results: dict[str, Any] = {
            "orders_cancelled": 0,
            "positions_closed": 0,
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

                    response = await self._adapter.place_order(order_request)
                    results["positions_closed"] += 1
                    logger.info(f"Emergency close order placed: {symbol} {side.value} {abs(position.amount)}")

                except Exception as e:
                    logger.exception(f"Error closing position for {symbol}: {e}")
                    results["errors"].append({
                        "symbol": symbol,
                        "error": str(e),
                    })

        # Stop the engine
        await self.stop(error="Emergency close executed", cancel_orders=False)

        return results

    async def process_candle(self, candle: WSCandle) -> None:
        """Process a WebSocket candle update.

        Only processes closed candles. Execution flow:
        1. Update current price
        2. Sync pending orders status
        3. Update context with new bar
        4. Call strategy.on_bar()
        5. Process order requests from strategy
        6. Record equity snapshot

        Args:
            candle: WebSocket candle data.
        """
        if not self._is_running:
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
            self._last_active_at = datetime.now(timezone.utc)

            # Update current price
            self._current_price = candle.close

            # Convert WSCandle to Bar
            bar = self._candle_to_bar(candle)

            # Sync order status from exchange (poll pending orders)
            await self._sync_pending_orders()

            # Update context
            self._context._set_current_bar(bar)
            self._context._add_bar_to_history(bar)

            # Update risk manager with current equity
            await self._sync_balance()
            self._risk_manager.update_equity(self._context.equity)

            # Call strategy on_bar
            self._strategy.on_bar(bar)

            # Process pending order requests from strategy
            await self._process_order_requests()

            # Record equity snapshot
            self._context._record_equity_snapshot(bar.time)

            # Track pending snapshot for persistence
            if self._context.equity_curve:
                self._pending_snapshots.append(self._context.equity_curve[-1])

            self._bar_count += 1

            logger.debug(
                f"Processed bar {self._bar_count} at {bar.time}, "
                f"equity={self._context.equity}"
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
        live_order.status = new_status
        live_order.filled_amount = update.filled_size
        live_order.avg_fill_price = update.avg_price
        live_order.fee = update.fee or Decimal("0")
        live_order.fee_currency = update.fee_currency
        live_order.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Order {internal_id} updated: {old_status.value} -> {new_status.value}, "
            f"filled={update.filled_size}/{live_order.amount}"
        )

        # Process fills
        if new_status in (OrderStatus.PARTIAL, OrderStatus.FILLED):
            self._process_order_fill(live_order, update)

        # Record trade result for risk tracking
        if new_status == OrderStatus.FILLED and live_order.avg_fill_price:
            # Calculate PnL for completed trade
            # Note: Simplified - full PnL tracking would need more context
            pass

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
        """Sync pending order status from exchange."""
        pending_internal_ids = [
            oid for oid, order in self._live_orders.items()
            if not order.is_complete and order.exchange_order_id
        ]

        for internal_id in pending_internal_ids:
            live_order = self._live_orders[internal_id]
            try:
                response = await self._adapter.get_order(
                    live_order.symbol,
                    live_order.exchange_order_id,  # type: ignore
                )
                self._update_order_from_response(live_order, response)
            except Exception as e:
                logger.warning(f"Failed to sync order {internal_id}: {e}")

    def _update_order_from_response(self, live_order: LiveOrder, response: OrderResponse) -> None:
        """Update live order from exchange response."""
        old_filled = live_order.filled_amount
        live_order.status = response.status
        live_order.filled_amount = response.filled
        live_order.avg_fill_price = response.avg_price
        live_order.fee = response.fee or Decimal("0")
        live_order.fee_currency = response.fee_currency
        live_order.updated_at = datetime.now(timezone.utc)

        # Process new fills
        if response.filled > old_filled:
            fill_amount = response.filled - old_filled
            self._process_incremental_fill(live_order, fill_amount, response)

    def _process_order_fill(self, live_order: LiveOrder, update: WSOrderUpdate) -> None:
        """Process order fill from WebSocket update."""
        if not update.avg_price:
            return

        # Create fill record
        fill = Fill(
            order_id=live_order.internal_id,
            symbol=live_order.symbol,
            side=live_order.side,
            price=update.avg_price,
            amount=update.filled_size,
            fee=update.fee or Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        # Process in context
        self._context._process_fill(fill)
        self._context._move_completed_orders()

    def _process_incremental_fill(
        self,
        live_order: LiveOrder,
        fill_amount: Decimal,
        response: OrderResponse,
    ) -> None:
        """Process incremental fill from polling."""
        if not response.avg_price:
            return

        fill = Fill(
            order_id=live_order.internal_id,
            symbol=live_order.symbol,
            side=live_order.side,
            price=response.avg_price,
            amount=fill_amount,
            fee=response.fee or Decimal("0"),
            timestamp=datetime.now(timezone.utc),
        )

        self._context._process_fill(fill)
        self._context._move_completed_orders()

    async def _process_order_requests(self) -> None:
        """Process pending order requests from strategy context.

        Gets orders from the context's pending orders and submits them
        to the exchange after risk validation.
        """
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
                logger.warning(
                    f"Order rejected by risk manager: {risk_result.reason}"
                )
                # Mark as rejected in context
                order.status = OrderStatus.REJECTED
                self._context._completed_orders.append(order)
                self._context._pending_orders.remove(order)
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
            live_order.created_at = datetime.now(timezone.utc)

            self._live_orders[order.id] = live_order
            self._exchange_order_map[response.order_id] = order.id

            # Update context order status
            order.status = response.status

            logger.info(
                f"Order submitted: {order.id} -> exchange:{response.order_id}, "
                f"status={response.status.value}"
            )

            # Record trade for risk tracking
            self._risk_manager.state.daily_trade_count += 1

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
                    await self._adapter.cancel_order(
                        CancelOrderRequest(
                            symbol=live_order.symbol,
                            order_id=live_order.exchange_order_id,
                        )
                    )
                    live_order.status = OrderStatus.CANCELLED
                    cancelled.append(internal_id)
                    logger.info(f"Cancelled order {internal_id}")
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
            pending_orders.append({
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "amount": str(order.amount),
                "price": str(order.price) if order.price else None,
                "status": order.status.value,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            })

        # Get live order details
        live_orders = []
        for oid, lo in self._live_orders.items():
            if not lo.is_complete:
                live_orders.append({
                    "internal_id": lo.internal_id,
                    "exchange_id": lo.exchange_order_id,
                    "symbol": lo.symbol,
                    "side": lo.side.value,
                    "amount": str(lo.amount),
                    "filled": str(lo.filled_amount),
                    "status": lo.status.value,
                })

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
