"""Paper trading engine for real-time simulated trading.

Uses WebSocket market data to drive strategy execution with local order matching.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.matching import MatchingEngine
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import Bar, EquitySnapshot
from squant.engine.resource_limits import ResourceLimitExceededError, resource_limiter
from squant.infra.exchange.okx.ws_types import WSCandle

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
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
    ):
        """Initialize paper trading engine.

        Args:
            run_id: Strategy run ID.
            strategy: Strategy instance to execute.
            symbol: Trading symbol (e.g., "BTC/USDT").
            timeframe: Candle timeframe (e.g., "1m").
            initial_capital: Starting capital.
            commission_rate: Commission rate.
            slippage: Slippage rate.
            params: Strategy parameters.
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

        # Initialize matching engine (reused from backtest)
        self._matching_engine = MatchingEngine(
            commission_rate=commission_rate,
            slippage=slippage,
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

        # Pending equity snapshots for batch persistence
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
            return True  # Just started, no candles processed yet
        elapsed = (datetime.now(UTC) - self._last_active_at).total_seconds()
        return elapsed < timeout_seconds

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
        """Process a WebSocket candle update.

        Only processes closed candles. Execution flow:
        1. Match pending orders against new bar
        2. Process fills
        3. Update current bar
        4. Add to history
        5. Call strategy.on_bar()
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

        # Acquire processing lock so stop() waits for completion (PP-C05)
        async with self._processing_lock:
            try:
                # Update last activity timestamp
                self._last_active_at = datetime.now(UTC)

                # Convert WSCandle to Bar
                bar = self._candle_to_bar(candle)

                # 1. Match pending orders
                pending = self._context._get_pending_orders()
                fills = self._matching_engine.process_bar(bar, pending)

                # 2. Process fills (TRD-025#3: insufficient cash → log, don't crash)
                for fill in fills:
                    try:
                        self._context._process_fill(fill)
                    except ValueError as e:
                        logger.warning(f"Fill rejected in engine {self._run_id}: {e}")
                        self._context.log(f"Order fill rejected: {e}")

                # 3. Move completed orders
                self._context._move_completed_orders()

                # 4. Update current bar
                self._context._set_current_bar(bar)

                # 5. Add to history (for strategy lookback)
                self._context._add_bar_to_history(bar)

                # 6. Record equity snapshot (before strategy, consistent with live engine P0-1)
                self._context._record_equity_snapshot(bar.time)

                # Track pending snapshot for persistence
                if self._context.equity_curve:
                    self._pending_snapshots.append(self._context.equity_curve[-1])

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

                logger.debug(
                    f"Processed bar {self._bar_count} at {bar.time}, "
                    f"equity={self._context.equity}"
                )

            except Exception as e:
                logger.exception(f"Error processing candle in engine {self._run_id}: {e}")
                await self.stop(error=f"Error processing candle: {e}")
                raise

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

    def should_persist_snapshots(self) -> bool:
        """Check if snapshots should be persisted.

        Returns:
            True if pending snapshots exceed batch size.
        """
        return len(self._pending_snapshots) >= self._snapshot_batch_size

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get current engine state snapshot.

        Returns:
            State dictionary for API responses.
        """
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
            "completed_orders_count": len(self._context.completed_orders),
            "trades_count": len(self._context.trades),
        }
