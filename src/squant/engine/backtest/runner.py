"""Backtest runner for executing strategy backtests.

The BacktestRunner orchestrates the complete backtest workflow:
1. Compile and instantiate the strategy
2. Initialize the backtest context
3. Loop through historical bars
4. Match orders and update positions
5. Calculate performance metrics
"""

import logging
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.matching import MatchingEngine
from squant.engine.backtest.metrics import calculate_metrics
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import BacktestResult, Bar
from squant.engine.resource_limits import ResourceLimitExceededError, resource_limiter
from squant.engine.sandbox import compile_strategy

logger = logging.getLogger(__name__)


class BacktestError(Exception):
    """Error during backtest execution."""

    pass


class BacktestCancelledError(BacktestError):
    """Backtest was cancelled by user."""

    def __init__(self, run_id: str | None = None):
        self.run_id = run_id
        message = f"Backtest cancelled: {run_id}" if run_id else "Backtest cancelled"
        super().__init__(message)


class StrategyInstantiationError(BacktestError):
    """Error instantiating strategy from code."""

    pass


class BacktestRunner:
    """Executes backtests on historical data.

    The runner handles:
    - Strategy code compilation and instantiation
    - Context and matching engine setup
    - Bar-by-bar simulation loop
    - Progress reporting
    - Result compilation
    """

    def __init__(
        self,
        strategy_code: str,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
    ):
        """Initialize backtest runner.

        Args:
            strategy_code: Python code defining the strategy class.
            strategy_name: Name of the strategy for result reporting.
            symbol: Trading symbol (e.g., "BTC/USDT").
            timeframe: Candle timeframe (e.g., "1h").
            initial_capital: Starting capital.
            commission_rate: Commission rate as decimal.
            slippage: Slippage rate for market orders.
            params: Strategy parameters.
        """
        self.strategy_code = strategy_code
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.params = params or {}

        self._context: BacktestContext | None = None
        self._strategy: Strategy | None = None
        self._matching_engine: MatchingEngine | None = None
        self._bar_count = 0
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None
        self._cancelled = False
        self._run_id: str | None = None

    def cancel(self) -> None:
        """Cancel the running backtest.

        Sets a flag that will be checked during bar processing.
        The backtest will stop at the next bar iteration.
        """
        self._cancelled = True
        logger.info(f"Backtest cancel requested: {self._run_id}")

    @property
    def is_cancelled(self) -> bool:
        """Check if backtest has been cancelled."""
        return self._cancelled

    def set_run_id(self, run_id: str) -> None:
        """Set the run ID for this backtest."""
        self._run_id = run_id

    async def run(
        self,
        bars: AsyncIterator[Bar],
        progress_callback: Callable[[int, int], None] | None = None,
        total_bars: int | None = None,
    ) -> BacktestResult:
        """Run the backtest on provided bar data.

        Args:
            bars: Async iterator of Bar objects.
            progress_callback: Optional callback(current, total) for progress updates.
            total_bars: Total number of bars (for progress reporting).

        Returns:
            BacktestResult with complete backtest data.

        Raises:
            BacktestError: If backtest fails.
        """
        try:
            # Step 1: Setup
            self._setup()

            # Step 2: Run strategy on_init
            self._strategy.on_init()

            # Step 3: Process bars
            self._bar_count = 0
            async for bar in bars:
                # Check for cancellation before processing each bar (TRD-008#3)
                if self._cancelled:
                    logger.info(f"Backtest cancelled after {self._bar_count} bars")
                    raise BacktestCancelledError(self._run_id)

                self._process_bar(bar)
                self._bar_count += 1

                if progress_callback and total_bars:
                    progress_callback(self._bar_count, total_bars)

            # Step 4: Run strategy on_stop
            self._strategy.on_stop()

            # Step 5: Build and return result
            return self._build_result()

        except BacktestCancelledError:
            # Re-raise cancellation errors without wrapping (TRD-008#3)
            raise
        except Exception as e:
            logger.exception(f"Backtest failed: {e}")
            raise BacktestError(f"Backtest execution failed: {e}") from e

    def _setup(self) -> None:
        """Setup backtest components."""
        # Initialize context
        self._context = BacktestContext(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
            slippage=self.slippage,
            params=self.params,
        )

        # Initialize matching engine
        self._matching_engine = MatchingEngine(
            commission_rate=self.commission_rate,
            slippage=self.slippage,
        )

        # Compile and instantiate strategy
        self._strategy = self._instantiate_strategy()

        # Inject context
        self._strategy.ctx = self._context

    def _instantiate_strategy(self) -> Strategy:
        """Compile strategy code and instantiate the strategy class.

        Returns:
            Strategy instance.

        Raises:
            StrategyInstantiationError: If strategy cannot be instantiated.
        """
        try:
            # Compile with RestrictedPython
            compiled = compile_strategy(self.strategy_code)

            # Inject Strategy base class into globals
            from squant.engine.backtest.strategy_base import Strategy as StrategyBase
            from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position

            compiled.restricted_globals["Strategy"] = StrategyBase
            compiled.restricted_globals["Bar"] = Bar
            compiled.restricted_globals["Position"] = Position
            compiled.restricted_globals["OrderSide"] = OrderSide
            compiled.restricted_globals["OrderType"] = OrderType

            # Execute the code to define the class
            local_namespace: dict[str, Any] = {}
            exec(compiled.code_object, compiled.restricted_globals, local_namespace)

            # Find the strategy class (subclass of Strategy)
            strategy_class = None
            for _name, obj in local_namespace.items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, StrategyBase)
                    and obj is not StrategyBase
                ):
                    strategy_class = obj
                    break

            if strategy_class is None:
                raise StrategyInstantiationError("No Strategy subclass found in strategy code")

            # Instantiate
            return strategy_class()

        except ValueError as e:
            raise StrategyInstantiationError(f"Strategy compilation failed: {e}") from e
        except Exception as e:
            raise StrategyInstantiationError(f"Strategy instantiation failed: {e}") from e

    def _process_bar(self, bar: Bar) -> None:
        """Process a single bar through the backtest loop.

        Order of operations:
        1. Process pending orders from previous bar (fills at this bar's open)
        2. Update context with fills
        3. Set current bar in context
        4. Add bar to history
        5. Call strategy.on_bar() (with resource limits)
        6. Record equity snapshot

        Args:
            bar: The bar to process.

        Raises:
            BacktestError: If strategy exceeds resource limits (STR-013).
        """
        # Track time range
        if self._start_time is None:
            self._start_time = bar.time
        self._end_time = bar.time

        # 1. Match pending orders against this bar
        pending_orders = self._context._get_pending_orders()
        fills = self._matching_engine.process_bar(bar, pending_orders)

        # 2. Process fills (catch ValueError for gap scenarios where cost exceeds cash)
        for fill in fills:
            try:
                self._context._process_fill(fill)
            except ValueError as e:
                # Order can't be filled (e.g., gap-up made market buy too expensive)
                # Cancel the order instead of crashing the backtest
                self._context.log(f"Order {fill.order_id} rejected at fill: {e}")
                logger.warning(f"Fill rejected for order {fill.order_id}: {e}")
                for order in self._context._get_pending_orders():
                    if order.id == fill.order_id:
                        self._context.cancel_order(order.id)
                        break

        # 2a. Move completed orders (before expiry, so FILLED orders are removed first)
        self._context._move_completed_orders()

        # 2b. Expire stale limit orders (decrement bars_remaining, cancel if <= 0)
        self._expire_stale_orders()

        # 4. Update current bar
        self._context._set_current_bar(bar)

        # 5. Add to history
        self._context._add_bar_to_history(bar)

        # 6. Record equity snapshot (before strategy, consistent with live engine P0-1)
        self._context._record_equity_snapshot(bar.time)

        # 7. Call strategy with resource limits (STR-013)
        # Get settings dynamically for testability
        from squant.config import get_settings

        settings = get_settings()

        try:
            with resource_limiter(
                cpu_seconds=settings.strategy.cpu_limit_seconds,
                memory_mb=settings.strategy.memory_limit_mb,
            ):
                self._strategy.on_bar(bar)
        except ResourceLimitExceededError as e:
            self._context.log(f"RESOURCE LIMIT EXCEEDED: {e}")
            logger.error(f"Strategy resource limit exceeded: {e}")
            raise BacktestError(f"Strategy resource limit exceeded: {e}") from e
        except Exception as e:
            self._context.log(f"ERROR in on_bar: {e}")
            logger.warning(f"Strategy on_bar error: {e}")

    def _expire_stale_orders(self) -> None:
        """Expire limit orders whose bars_remaining has reached zero.

        Decrements bars_remaining for each pending limit order. Orders that
        reach zero are cancelled and moved to completed orders.
        Mirrors PaperTradingEngine._expire_stale_orders().
        """
        from squant.engine.backtest.types import OrderStatus, OrderType

        expired = []
        remaining = []
        for order in self._context._pending_orders:
            # Skip already-completed orders (FILLED/CANCELLED) to avoid overwriting status
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                remaining.append(order)
                continue
            if (
                order.type in (OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT)
                and order.bars_remaining is not None
            ):
                order.bars_remaining -= 1
                if order.bars_remaining <= 0:
                    order.status = OrderStatus.CANCELLED
                    self._context._completed_orders.append(order)
                    price_info = f"@{order.price}" if order.price else ""
                    stop_info = f"止损@{order.stop_price}" if order.stop_price else ""
                    self._context.log(
                        f"订单过期: {order.side.value} {order.symbol} "
                        f"{order.amount}{stop_info}{price_info}"
                    )
                    expired.append(order)
                    continue
            remaining.append(order)

        if expired:
            self._context._pending_orders = remaining

    def _build_result(self) -> BacktestResult:
        """Build the final backtest result.

        Returns:
            Complete BacktestResult.
        """
        # Calculate performance metrics
        metrics = calculate_metrics(
            equity_curve=self._context.equity_curve,
            trades=self._context.trades,
            initial_capital=self.initial_capital,
            total_fees=self._context.total_fees,
            timeframe=self.timeframe,
        )

        return BacktestResult(
            run_id="",  # Will be set by service layer
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_time=self._start_time or datetime.now(),
            end_time=self._end_time or datetime.now(),
            bar_count=self._bar_count,
            initial_capital=self.initial_capital,
            final_equity=self._context.equity,
            commission_rate=self.commission_rate,
            slippage=self.slippage,
            metrics=metrics.to_dict(),
            equity_curve=self._context.equity_curve,
            trades=self._context.trades,
            orders=self._context.completed_orders,
            logs=self._context.logs,
        )


async def run_backtest(
    strategy_code: str,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    bars: AsyncIterator[Bar],
    initial_capital: Decimal,
    commission_rate: Decimal = Decimal("0.001"),
    slippage: Decimal = Decimal("0"),
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    total_bars: int | None = None,
) -> BacktestResult:
    """Convenience function to run a backtest.

    Args:
        strategy_code: Python code defining the strategy.
        strategy_name: Name of the strategy.
        symbol: Trading symbol.
        timeframe: Candle timeframe.
        bars: Async iterator of bars.
        initial_capital: Starting capital.
        commission_rate: Commission rate.
        slippage: Slippage rate.
        params: Strategy parameters.
        progress_callback: Progress callback function.
        total_bars: Total number of bars.

    Returns:
        BacktestResult with complete backtest data.
    """
    runner = BacktestRunner(
        strategy_code=strategy_code,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        params=params,
    )
    return await runner.run(bars, progress_callback, total_bars)
