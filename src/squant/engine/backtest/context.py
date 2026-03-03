"""Backtest context providing strategy runtime API.

The BacktestContext is injected into user strategies and provides:
- Market data access (current and historical bars)
- Order placement (buy/sell)
- Position queries
- Account state (cash, equity)
- Logging
"""

from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from squant.engine.backtest.types import (
    Bar,
    EquitySnapshot,
    Fill,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    SimulatedOrder,
    TradeRecord,
)


class BacktestContext:
    """Context object providing runtime API for strategy execution.

    This class maintains the complete state of a backtest run and provides
    methods for strategies to interact with the simulated market.

    Attributes:
        params: Strategy parameters dictionary.
        cash: Current cash balance.
        equity: Total equity (cash + position value).
        positions: Dict of symbol -> Position.
    """

    def __init__(
        self,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
        params: dict[str, Any] | None = None,
        max_bar_history: int = 1000,
        max_equity_curve: int | None = None,
        max_completed_orders: int | None = None,
        max_fills: int = 5000,
        max_trades: int | None = None,
        max_logs: int = 1000,
        min_order_value: Decimal = Decimal("5"),
    ):
        """Initialize backtest context.

        Args:
            initial_capital: Starting capital.
            commission_rate: Commission rate as a decimal (e.g., 0.001 = 0.1%).
            slippage: Slippage rate for market orders.
            params: Strategy parameters.
            max_bar_history: Maximum bars to keep in history buffer.
            max_equity_curve: Maximum equity snapshots to keep (None=unlimited).
            max_completed_orders: Maximum completed orders to keep.
            max_fills: Maximum fills to keep.
            max_trades: Maximum trades to keep.
            max_logs: Maximum log entries to keep.
            min_order_value: Minimum order notional value in quote currency.
                Orders below this value are silently rejected (returns None).
        """
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._commission_rate = commission_rate
        self._slippage = slippage
        self._min_order_value = min_order_value
        self._params = params or {}
        self._max_bar_history = max_bar_history

        # Position tracking
        self._positions: dict[str, Position] = {}

        # Order management
        self._pending_orders: list[SimulatedOrder] = []
        self._completed_orders: deque[SimulatedOrder] = deque(maxlen=max_completed_orders)
        self._restored_completed_orders_count: int = 0  # base count from session restore
        self._order_counter = 0

        # Fill and trade tracking
        self._fills: deque[Fill] = deque(maxlen=max_fills)
        self._trades: deque[TradeRecord] = deque(maxlen=max_trades)
        self._open_trade: TradeRecord | None = None
        self._partial_exit_pnl: Decimal = Decimal("0")  # accumulated PnL from partial exits
        self._exit_fill_notional: Decimal = Decimal("0")  # accumulated exit price * amount
        self._exit_fill_amount: Decimal = Decimal("0")  # accumulated exit fill amount

        # Bar history (deque for efficient append/pop)
        self._bar_history: deque[Bar] = deque(maxlen=max_bar_history)
        self._current_bar: Bar | None = None

        # Equity tracking (no limit — all snapshots needed for metrics & display)
        self._equity_curve: deque[EquitySnapshot] = deque(maxlen=max_equity_curve)

        # Benchmark tracking (buy-and-hold)
        self._benchmark_initial_price: Decimal | None = None

        # Logging
        self._logs: deque[str] = deque(maxlen=max_logs)

        # Cumulative counters for incremental WebSocket tracking.
        # Deque maxlen causes old items to be evicted, so len(deque) plateaus.
        # These counters track total items ever added, enabling correct delta calculation.
        self._total_fills_added: int = 0
        self._total_trades_added: int = 0
        self._total_logs_added: int = 0

        # Total fees paid
        self._total_fees = Decimal("0")

        # Price cache for multi-symbol equity calculation
        self._last_prices: dict[str, Decimal] = {}

        # Latest ask price from ticker (set by paper engine for better market order
        # cost estimation; None in backtest where ticker data is unavailable)
        self._ref_ask: Decimal | None = None

    # =========================================================================
    # Public Properties
    # =========================================================================

    @property
    def params(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self._params

    @property
    def cash(self) -> Decimal:
        """Get current cash balance."""
        return self._cash

    @property
    def initial_capital(self) -> Decimal:
        """Get initial capital."""
        return self._initial_capital

    @property
    def commission_rate(self) -> Decimal:
        """Get commission rate."""
        return self._commission_rate

    @property
    def slippage(self) -> Decimal:
        """Get slippage rate."""
        return self._slippage

    @property
    def equity(self) -> Decimal:
        """Get total equity (cash + position value)."""
        return self._cash + self._get_position_value()

    @property
    def positions(self) -> dict[str, Position]:
        """Get all positions (read-only copy)."""
        return {
            k: Position(v.symbol, v.amount, v.avg_entry_price) for k, v in self._positions.items()
        }

    @property
    def current_bar(self) -> Bar | None:
        """Get the current bar being processed."""
        return self._current_bar

    @property
    def pending_orders(self) -> list[SimulatedOrder]:
        """Get list of pending orders."""
        return list(self._pending_orders)

    @property
    def completed_orders(self) -> list[SimulatedOrder]:
        """Get list of completed orders."""
        return list(self._completed_orders)

    @property
    def fills(self) -> list[Fill]:
        """Get list of all fills."""
        return list(self._fills)

    @property
    def trades(self) -> list[TradeRecord]:
        """Get list of completed trades."""
        return list(self._trades)

    @property
    def equity_curve(self) -> list[EquitySnapshot]:
        """Get equity curve snapshots."""
        return list(self._equity_curve)

    @property
    def logs(self) -> list[str]:
        """Get strategy logs."""
        return list(self._logs)

    @property
    def total_fees(self) -> Decimal:
        """Get total fees paid."""
        return self._total_fees

    # =========================================================================
    # Order Placement
    # =========================================================================

    def buy(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        valid_for_bars: int | None = None,
    ) -> str | None:
        """Place a buy order.

        Args:
            symbol: Trading symbol.
            amount: Amount to buy (must be positive).
            price: Limit price (None for market order; required for STOP_LIMIT).
            stop_price: Stop trigger price (for STOP or STOP_LIMIT orders).
            valid_for_bars: Number of bars before the order expires
                (None = GTC, applicable to non-market orders).

        Returns:
            Order ID, or None if the order notional is below min_order_value.

        Raises:
            ValueError: If amount is not positive or insufficient cash.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        amount = Decimal(str(amount))

        # Minimum order value check — silently reject dust orders
        ref_price = (
            Decimal(str(price)) if price is not None
            else Decimal(str(stop_price)) if stop_price is not None
            else self._current_bar.close if self._current_bar
            else None
        )
        if ref_price is not None and amount * ref_price < self._min_order_value:
            return None

        # Determine order type
        if stop_price is not None and price is not None:
            order_type = OrderType.STOP_LIMIT
        elif stop_price is not None:
            order_type = OrderType.STOP
        elif price is not None:
            order_type = OrderType.LIMIT
        else:
            order_type = OrderType.MARKET

        # Validate sufficient cash for buy orders, accounting for pending buys
        if order_type == OrderType.LIMIT:
            estimated_cost = Decimal(str(price)) * amount * (1 + self._commission_rate)
        elif order_type == OrderType.STOP_LIMIT:
            # Limit price caps the cost
            estimated_cost = Decimal(str(price)) * amount * (1 + self._commission_rate)
        elif order_type == OrderType.STOP:
            # Worst case: triggered at stop_price + slippage
            estimated_cost = (
                Decimal(str(stop_price))
                * amount
                * (1 + self._slippage)
                * (1 + self._commission_rate)
            )
        elif self._current_bar:
            # Market order: estimate using the best available price reference.
            # When ticker ask is available (paper trading), use the higher of
            # close+slippage and ask to avoid underestimating cost — the fill
            # will use ask price, which may exceed close*(1+slippage).
            ref_price = self._current_bar.close * (1 + self._slippage)
            if self._ref_ask is not None:
                ref_price = max(ref_price, self._ref_ask)
            estimated_cost = ref_price * amount * (1 + self._commission_rate)
        else:
            # No bar yet, skip validation (will be caught at fill time)
            estimated_cost = Decimal("0")

        # Reserve cash for existing pending buy orders (mirrors sell's pending_sell_amount)
        pending_buy_cost = Decimal("0")
        for order in self._pending_orders:
            if order.side == OrderSide.BUY:
                if order.type == OrderType.STOP_LIMIT and order.price is not None:
                    pending_buy_cost += order.price * order.remaining * (1 + self._commission_rate)
                elif order.type == OrderType.STOP and order.stop_price is not None:
                    pending_buy_cost += (
                        order.stop_price
                        * order.remaining
                        * (1 + self._slippage)
                        * (1 + self._commission_rate)
                    )
                elif order.price is not None:
                    pending_buy_cost += order.price * order.remaining * (1 + self._commission_rate)
                elif self._current_bar:
                    pending_ref = self._current_bar.close * (1 + self._slippage)
                    if self._ref_ask is not None:
                        pending_ref = max(pending_ref, self._ref_ask)
                    pending_buy_cost += (
                        pending_ref
                        * order.remaining
                        * (1 + self._commission_rate)
                    )

        available_cash = self._cash - pending_buy_cost
        if estimated_cost > 0 and available_cash < estimated_cost:
            raise ValueError(
                f"Insufficient cash for buy order: available={available_cash}, "
                f"estimated_cost={estimated_cost} "
                f"(cash={self._cash}, reserved_for_pending={pending_buy_cost})"
            )

        order = SimulatedOrder.create(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=order_type,
            amount=amount,
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            created_at=self._current_bar.time if self._current_bar else None,
            bars_remaining=valid_for_bars if order_type != OrderType.MARKET else None,
        )
        self._pending_orders.append(order)

        if order_type == OrderType.STOP:
            price_info = f"止损@{stop_price}"
        elif order_type == OrderType.STOP_LIMIT:
            price_info = f"止损@{stop_price}限价@{price}"
        elif order_type == OrderType.LIMIT:
            price_info = f"@{price}"
        else:
            price_info = "市价"
        short_id = order.id[:8]
        self.log(f"提交买入 {symbol} {amount} {price_info} #{short_id}")
        return order.id

    def sell(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        valid_for_bars: int | None = None,
    ) -> str | None:
        """Place a sell order.

        This is a SPOT trading system - short selling is not allowed.
        You can only sell what you own.

        Args:
            symbol: Trading symbol.
            amount: Amount to sell (must be positive).
            price: Limit price (None for market order; required for STOP_LIMIT).
            stop_price: Stop trigger price (for STOP or STOP_LIMIT orders).
            valid_for_bars: Number of bars before the order expires
                (None = GTC, applicable to non-market orders).

        Returns:
            Order ID, or None if the order notional is below min_order_value.

        Raises:
            ValueError: If amount is not positive or exceeds position.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        amount = Decimal(str(amount))

        # Minimum order value check — silently reject dust orders
        ref_price = (
            Decimal(str(price)) if price is not None
            else Decimal(str(stop_price)) if stop_price is not None
            else self._current_bar.close if self._current_bar
            else None
        )
        if ref_price is not None and amount * ref_price < self._min_order_value:
            return None

        # Determine order type
        if stop_price is not None and price is not None:
            order_type = OrderType.STOP_LIMIT
        elif stop_price is not None:
            order_type = OrderType.STOP
        elif price is not None:
            order_type = OrderType.LIMIT
        else:
            order_type = OrderType.MARKET

        # Validate sufficient position (spot trading - no short selling)
        position = self._positions.get(symbol)
        current_position = position.amount if position else Decimal("0")

        # Calculate total pending sell amount for this symbol
        pending_sell_amount = Decimal("0")
        for order in self._pending_orders:
            if order.symbol == symbol and order.side == OrderSide.SELL:
                pending_sell_amount += order.remaining

        available_to_sell = current_position - pending_sell_amount
        if amount > available_to_sell:
            raise ValueError(
                f"Insufficient position for sell order: available={available_to_sell}, "
                f"requested={amount} (position={current_position}, pending_sells={pending_sell_amount})"
            )

        order = SimulatedOrder.create(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=order_type,
            amount=amount,
            price=Decimal(str(price)) if price is not None else None,
            stop_price=Decimal(str(stop_price)) if stop_price is not None else None,
            created_at=self._current_bar.time if self._current_bar else None,
            bars_remaining=valid_for_bars if order_type != OrderType.MARKET else None,
        )
        self._pending_orders.append(order)

        if order_type == OrderType.STOP:
            price_info = f"止损@{stop_price}"
        elif order_type == OrderType.STOP_LIMIT:
            price_info = f"止损@{stop_price}限价@{price}"
        elif order_type == OrderType.LIMIT:
            price_info = f"@{price}"
        else:
            price_info = "市价"
        short_id = order.id[:8]
        self.log(f"提交卖出 {symbol} {amount} {price_info} #{short_id}")
        return order.id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            True if order was cancelled, False if not found or already filled.
        """
        for i, order in enumerate(self._pending_orders):
            if order.id == order_id:
                order.status = OrderStatus.CANCELLED
                self._completed_orders.append(order)
                self._pending_orders.pop(i)
                return True
        return False

    def get_order(self, order_id: str) -> SimulatedOrder | None:
        """Get order by ID.

        Args:
            order_id: Order ID.

        Returns:
            Order if found, None otherwise.
        """
        for order in self._pending_orders:
            if order.id == order_id:
                return order
        for order in self._completed_orders:
            if order.id == order_id:
                return order
        return None

    # =========================================================================
    # Position Queries
    # =========================================================================

    def get_position(self, symbol: str) -> Position | None:
        """Get position for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Position if exists and is open, None otherwise.
        """
        pos = self._positions.get(symbol)
        if pos and pos.is_open:
            return Position(pos.symbol, pos.amount, pos.avg_entry_price)
        return None

    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            True if position exists and is open.
        """
        pos = self._positions.get(symbol)
        return pos is not None and pos.is_open

    # =========================================================================
    # Market Data Access
    # =========================================================================

    def get_closes(self, n: int = 1) -> list[Decimal]:
        """Get the last n close prices.

        Args:
            n: Number of close prices to retrieve.

        Returns:
            List of close prices (oldest first).
        """
        bars = list(self._bar_history)
        if n > len(bars):
            return [bar.close for bar in bars]
        return [bar.close for bar in bars[-n:]]

    def get_bars(self, n: int = 1) -> list[Bar]:
        """Get the last n bars.

        Args:
            n: Number of bars to retrieve.

        Returns:
            List of bars (oldest first).
        """
        bars = list(self._bar_history)
        if n > len(bars):
            return bars
        return bars[-n:]

    def get_opens(self, n: int = 1) -> list[Decimal]:
        """Get the last n open prices."""
        bars = list(self._bar_history)
        if n > len(bars):
            return [bar.open for bar in bars]
        return [bar.open for bar in bars[-n:]]

    def get_highs(self, n: int = 1) -> list[Decimal]:
        """Get the last n high prices."""
        bars = list(self._bar_history)
        if n > len(bars):
            return [bar.high for bar in bars]
        return [bar.high for bar in bars[-n:]]

    def get_lows(self, n: int = 1) -> list[Decimal]:
        """Get the last n low prices."""
        bars = list(self._bar_history)
        if n > len(bars):
            return [bar.low for bar in bars]
        return [bar.low for bar in bars[-n:]]

    def get_volumes(self, n: int = 1) -> list[Decimal]:
        """Get the last n volumes."""
        bars = list(self._bar_history)
        if n > len(bars):
            return [bar.volume for bar in bars]
        return [bar.volume for bar in bars[-n:]]

    # =========================================================================
    # Logging
    # =========================================================================

    def log(self, message: str) -> None:
        """Log a message.

        Args:
            message: Message to log.
        """
        timestamp = self._current_bar.time if self._current_bar else datetime.now(UTC)
        self._logs.append(f"[{timestamp}] {message}")
        self._total_logs_added += 1

    # =========================================================================
    # Internal Methods (called by BacktestRunner)
    # =========================================================================

    def _set_current_bar(self, bar: Bar) -> None:
        """Set the current bar being processed."""
        self._current_bar = bar
        # Update price cache for multi-symbol equity calculation
        self._last_prices[bar.symbol] = bar.close

    def _add_bar_to_history(self, bar: Bar) -> None:
        """Add a bar to the history buffer."""
        self._bar_history.append(bar)

    def _get_pending_orders(self) -> list[SimulatedOrder]:
        """Get pending orders for matching engine."""
        return self._pending_orders

    def _process_fill(self, fill: Fill, force: bool = False) -> None:
        """Process a fill from the matching engine.

        Updates positions, cash, and tracks the fill.

        Args:
            fill: Fill event to process.
            force: If True, skip cash/position validation. Used by live trading
                engine where fills are already executed on the exchange and must
                be recorded locally regardless of tracking discrepancies.

        Raises:
            ValueError: If insufficient cash for buy order or insufficient position
                for sell (only when force=False).
        """
        # Update position
        if fill.symbol not in self._positions:
            self._positions[fill.symbol] = Position(fill.symbol)

        position = self._positions[fill.symbol]
        prev_amount = position.amount

        # Calculate trade cost/proceeds and validate
        if fill.side == OrderSide.BUY:
            cost = fill.price * fill.amount + fill.fee
            # Validate sufficient cash before executing
            if not force and self._cash < cost:
                raise ValueError(
                    f"Insufficient cash for fill: available={self._cash}, "
                    f"required={cost} (price={fill.price}, amount={fill.amount}, fee={fill.fee})"
                )
            self._cash -= cost
        else:
            # Validate sufficient position before executing (spot trading - no short)
            if not force and position.amount < fill.amount:
                raise ValueError(
                    f"Insufficient position for sell fill: position={position.amount}, "
                    f"fill_amount={fill.amount}"
                )
            proceeds = fill.price * fill.amount - fill.fee
            self._cash += proceeds

        # Record the fill (only after validation passes)
        self._fills.append(fill)
        self._total_fills_added += 1
        self._total_fees += fill.fee

        # Update position (this may also raise if trying to go short)
        position.update(fill.amount, fill.price, fill.side)

        # Track trades (entry/exit)
        self._update_trade_tracking(fill, prev_amount, position.amount)

        # Update the order status
        for order in self._pending_orders:
            if order.id == fill.order_id:
                order.filled += fill.amount
                if order.filled >= order.amount:
                    order.status = OrderStatus.FILLED
                else:
                    order.status = OrderStatus.PARTIAL
                # Update average fill price
                if order.avg_fill_price == Decimal("0"):
                    order.avg_fill_price = fill.price
                else:
                    total_filled = order.filled
                    prev_filled = total_filled - fill.amount
                    order.avg_fill_price = (
                        order.avg_fill_price * prev_filled + fill.price * fill.amount
                    ) / total_filled
                order.filled_at = fill.timestamp
                break

    def _move_completed_orders(self) -> None:
        """Move completed orders from pending to completed list."""
        still_pending = []
        for order in self._pending_orders:
            if order.is_complete:
                self._completed_orders.append(order)
            else:
                still_pending.append(order)
        self._pending_orders = still_pending

    def _update_trade_tracking(
        self,
        fill: Fill,
        prev_amount: Decimal,
        new_amount: Decimal,
    ) -> None:
        """Update trade tracking based on position changes.

        Args:
            fill: The fill that caused the position change.
            prev_amount: Position amount before the fill.
            new_amount: Position amount after the fill.
        """
        side_label = "买入成交" if fill.side == OrderSide.BUY else "卖出成交"
        short_id = fill.order_id[:8]
        price_detail = self._format_price_detail(fill)

        # Position opened
        if prev_amount == Decimal("0") and new_amount != Decimal("0"):
            self._partial_exit_pnl = Decimal("0")
            self._exit_fill_notional = Decimal("0")
            self._exit_fill_amount = Decimal("0")
            self._open_trade = TradeRecord(
                symbol=fill.symbol,
                side=fill.side,
                entry_time=fill.timestamp,
                entry_price=fill.price,
                amount=abs(new_amount),
                fees=fill.fee,
            )
            self.log(
                f"{side_label} #{short_id} {fill.symbol} "
                f"{fill.amount}@{fill.price} [开仓] "
                f"{price_detail}手续费={fill.fee}"
            )

        # Position increased
        elif (prev_amount > 0 and new_amount > prev_amount) or (
            prev_amount < 0 and new_amount < prev_amount
        ):
            if self._open_trade:
                # Calculate weighted average entry price
                added_amount = abs(new_amount) - abs(prev_amount)
                prev_value = self._open_trade.entry_price * abs(prev_amount)
                new_value = fill.price * added_amount
                self._open_trade.entry_price = (prev_value + new_value) / abs(new_amount)
                self._open_trade.fees += fill.fee
                self._open_trade.amount = abs(new_amount)
                avg = self._open_trade.entry_price
                self.log(
                    f"{side_label} #{short_id} {fill.symbol} "
                    f"{added_amount}@{fill.price} "
                    f"[加仓→{abs(new_amount)} 均价={avg:.4f}] "
                    f"{price_detail}手续费={fill.fee}"
                )

        # Position decreased or closed
        elif self._open_trade:
            self._open_trade.fees += fill.fee
            fill_amount = abs(prev_amount) - abs(new_amount)

            # Compute realized PnL for this fill
            if self._open_trade.side == OrderSide.BUY:
                fill_pnl = (fill.price - self._open_trade.entry_price) * fill_amount
            else:
                fill_pnl = (self._open_trade.entry_price - fill.price) * fill_amount
            self._partial_exit_pnl += fill_pnl

            # Accumulate exit fill data for weighted average exit price
            self._exit_fill_notional += fill.price * fill_amount
            self._exit_fill_amount += fill_amount

            # Position closed
            if new_amount == Decimal("0"):
                self._open_trade.exit_time = fill.timestamp
                # Weighted average exit price across all partial exits
                if self._exit_fill_amount > 0:
                    self._open_trade.exit_price = (
                        self._exit_fill_notional / self._exit_fill_amount
                    )
                else:
                    self._open_trade.exit_price = fill.price

                # Total PnL = sum of all partial exit PnLs - total fees
                pnl = self._partial_exit_pnl - self._open_trade.fees
                self._open_trade.pnl = pnl

                cost_basis = self._open_trade.entry_price * self._open_trade.amount
                if cost_basis != Decimal("0"):
                    self._open_trade.pnl_pct = pnl / cost_basis * 100

                pnl_sign = "+" if pnl >= 0 else ""
                self.log(
                    f"{side_label} #{short_id} {fill.symbol} "
                    f"{fill_amount}@{fill.price} [平仓] "
                    f"{price_detail}"
                    f"盈亏={pnl_sign}{pnl:.4f}({pnl_sign}{self._open_trade.pnl_pct:.2f}%) "
                    f"手续费={self._open_trade.fees}"
                )

                self._trades.append(self._open_trade)
                self._total_trades_added += 1
                self._open_trade = None
            else:
                self.log(
                    f"{side_label} #{short_id} {fill.symbol} "
                    f"{fill_amount}@{fill.price} [减仓→{abs(new_amount)}] "
                    f"{price_detail}手续费={fill.fee}"
                )

            # Note: Position reversal (long→short or short→long) is not supported
            # in spot trading. sell() validation prevents negative positions.

    def _format_price_detail(self, fill: Fill) -> str:
        """Format price source detail for fill logs.

        Returns a string describing the price source (bid/ask, slippage, or limit).
        Trailing space included when non-empty for easy concatenation.
        Returns empty string when no price source metadata (e.g. backtest fills).
        """
        if fill.price_source is None:
            return ""
        if fill.price_source in ("ask", "bid"):
            parts = [f"{fill.price_source}={fill.price}"]
            if fill.reference_price is not None:
                parts.append(f"last={fill.reference_price}")
            if fill.spread_pct is not None:
                parts.append(f"spread={fill.spread_pct:.2f}%")
            return " ".join(parts) + " "
        elif fill.price_source == "slippage":
            parts = ["slippage"]
            if fill.reference_price is not None:
                parts.append(f"last={fill.reference_price}")
            if fill.spread_pct is not None:
                parts.append(f"spread={fill.spread_pct:.2f}%")
            return " ".join(parts) + " "
        elif fill.price_source in ("limit", "stop_limit"):
            return "限价成交 "
        elif fill.price_source == "last":
            return ""
        return ""

    def _record_equity_snapshot(self, time: datetime) -> None:
        """Record an equity snapshot.

        Args:
            time: Timestamp for the snapshot.
        """
        position_value = self._get_position_value()
        unrealized_pnl = self._get_unrealized_pnl()

        # Compute buy-and-hold benchmark equity
        benchmark_equity = self._initial_capital
        if self._current_bar:
            current_price = self._current_bar.close
            if self._benchmark_initial_price is None:
                self._benchmark_initial_price = current_price
            if self._benchmark_initial_price > 0:
                benchmark_equity = (
                    self._initial_capital * current_price / self._benchmark_initial_price
                )

        snapshot = EquitySnapshot(
            time=time,
            equity=self._cash + position_value,
            cash=self._cash,
            position_value=position_value,
            unrealized_pnl=unrealized_pnl,
            benchmark_equity=benchmark_equity,
        )
        self._equity_curve.append(snapshot)

    def _get_position_value(self) -> Decimal:
        """Calculate total position value at current market price.

        Uses cached prices for multi-symbol strategies.
        """
        total = Decimal("0")
        for symbol, position in self._positions.items():
            if position.is_open:
                price = self._last_prices.get(symbol)
                if price is not None:
                    total += position.amount * price
        return total

    def _get_unrealized_pnl(self) -> Decimal:
        """Calculate unrealized PnL for all positions.

        Uses cached prices for multi-symbol strategies.
        """
        total = Decimal("0")
        for symbol, position in self._positions.items():
            if position.is_open:
                price = self._last_prices.get(symbol)
                if price is not None:
                    if position.amount > 0:
                        # Long position
                        total += (price - position.avg_entry_price) * position.amount
                    else:
                        # Short position
                        total += (position.avg_entry_price - price) * abs(position.amount)
        return total

    def build_result_snapshot(self) -> dict[str, Any]:
        """Build a minimal result snapshot for persistence.

        Contains only the fields needed by restore_state() to resume a session.
        Called after each candle to keep the DB up-to-date for crash recovery.

        Returns:
            Dict suitable for storing in StrategyRun.result JSONB.
        """
        positions: dict[str, dict[str, str | None]] = {}
        for symbol, pos in self._positions.items():
            if pos.is_open:
                price = self._last_prices.get(symbol)
                unrealized = None
                if price is not None:
                    if pos.amount > 0:
                        unrealized = str((price - pos.avg_entry_price) * pos.amount)
                    else:
                        unrealized = str((pos.avg_entry_price - price) * abs(pos.amount))
                positions[symbol] = {
                    "amount": str(pos.amount),
                    "avg_entry_price": str(pos.avg_entry_price),
                    "current_price": str(price) if price is not None else None,
                    "unrealized_pnl": unrealized,
                }

        trades = [
            {
                "symbol": t.symbol,
                "side": t.side.value,
                "entry_time": t.entry_time.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_price": str(t.exit_price) if t.exit_price is not None else None,
                "amount": str(t.amount),
                "pnl": str(t.pnl),
                "pnl_pct": str(t.pnl_pct),
                "fees": str(t.fees),
            }
            for t in self._trades
        ]

        # Compute totals
        unrealized_pnl_total = Decimal("0")
        for pos_data in positions.values():
            if pos_data.get("unrealized_pnl") is not None:
                unrealized_pnl_total += Decimal(pos_data["unrealized_pnl"])

        realized_pnl = sum((t.pnl for t in self._trades), Decimal("0"))

        open_trade = None
        if self._open_trade:
            t = self._open_trade
            open_trade = {
                "symbol": t.symbol,
                "side": t.side.value,
                "entry_time": t.entry_time.isoformat(),
                "entry_price": str(t.entry_price),
                "amount": str(t.amount),
                "fees": str(t.fees),
                "partial_exit_pnl": str(self._partial_exit_pnl),
                "exit_fill_notional": str(self._exit_fill_notional),
                "exit_fill_amount": str(self._exit_fill_amount),
            }

        fills = [
            {
                "order_id": f.order_id,
                "symbol": f.symbol,
                "side": f.side.value,
                "price": str(f.price),
                "amount": str(f.amount),
                "fee": str(f.fee),
                "timestamp": f.timestamp.isoformat(),
            }
            for f in self._fills
        ]

        return {
            "cash": str(self._cash),
            "equity": str(self.equity),
            "total_fees": str(self._total_fees),
            "unrealized_pnl": str(unrealized_pnl_total),
            "realized_pnl": str(realized_pnl),
            "positions": positions,
            "trades": trades,
            "open_trade": open_trade,
            "fills": fills,
            "trades_count": len(self._trades),
            "completed_orders_count": self._restored_completed_orders_count
            + len(self._completed_orders),
            "logs": list(self._logs),
            "benchmark_initial_price": (
                str(self._benchmark_initial_price)
                if self._benchmark_initial_price is not None
                else None
            ),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore trading state from a saved result snapshot.

        Used when resuming a paper/live trading session. Restores financial
        state (cash, positions, trades); strategy internal state is rebuilt
        via warmup bar replay.

        Args:
            state: Result dict from StrategyRun.result JSONB.
        """
        # Restore cash
        if "cash" in state:
            self._cash = Decimal(str(state["cash"]))

        # Restore total fees
        if "total_fees" in state:
            self._total_fees = Decimal(str(state["total_fees"]))

        # Restore positions
        if "positions" in state:
            self._positions.clear()
            for symbol, pos_data in state["positions"].items():
                pos = Position(
                    symbol=symbol,
                    amount=Decimal(str(pos_data["amount"])),
                    avg_entry_price=Decimal(str(pos_data["avg_entry_price"])),
                )
                self._positions[symbol] = pos
                # Restore last_prices for equity calculation
                if pos_data.get("current_price"):
                    self._last_prices[symbol] = Decimal(str(pos_data["current_price"]))

        # Restore closed trades (for display and metrics)
        if "trades" in state:
            self._trades.clear()
            for t in state["trades"]:
                trade = TradeRecord(
                    symbol=t["symbol"],
                    side=OrderSide(t["side"]),
                    entry_time=datetime.fromisoformat(t["entry_time"]),
                    entry_price=Decimal(str(t["entry_price"])),
                    exit_time=(
                        datetime.fromisoformat(t["exit_time"]) if t.get("exit_time") else None
                    ),
                    exit_price=(
                        Decimal(str(t["exit_price"])) if t.get("exit_price") is not None else None
                    ),
                    amount=Decimal(str(t["amount"])),
                    pnl=Decimal(str(t["pnl"])),
                    pnl_pct=Decimal(str(t["pnl_pct"])),
                    fees=Decimal(str(t["fees"])),
                )
                self._trades.append(trade)
            self._total_trades_added = len(self._trades)

        # Restore fills (for display and strategy access after resume)
        if "fills" in state:
            self._fills.clear()
            for f in state["fills"]:
                fill = Fill(
                    order_id=f["order_id"],
                    symbol=f["symbol"],
                    side=OrderSide(f["side"]),
                    price=Decimal(str(f["price"])),
                    amount=Decimal(str(f["amount"])),
                    fee=Decimal(str(f["fee"])),
                    timestamp=datetime.fromisoformat(f["timestamp"]),
                )
                self._fills.append(fill)
            self._total_fills_added = len(self._fills)

        # Restore completed orders count (content not serialized, only count)
        self._restored_completed_orders_count = state.get("completed_orders_count", 0)

        # Restore logs
        if "logs" in state:
            self._logs.clear()
            for log_entry in state["logs"]:
                self._logs.append(log_entry)
            self._total_logs_added = len(self._logs)

        # Restore benchmark initial price for buy-and-hold comparison
        bip = state.get("benchmark_initial_price")
        if bip is not None:
            self._benchmark_initial_price = Decimal(str(bip))

        # Rebuild _open_trade from snapshot or positions
        self._open_trade = None
        self._partial_exit_pnl = Decimal("0")
        self._exit_fill_notional = Decimal("0")
        self._exit_fill_amount = Decimal("0")
        if state.get("open_trade"):
            ot = state["open_trade"]
            self._open_trade = TradeRecord(
                symbol=ot["symbol"],
                side=OrderSide(ot["side"]),
                entry_time=datetime.fromisoformat(ot["entry_time"]),
                entry_price=Decimal(str(ot["entry_price"])),
                amount=Decimal(str(ot["amount"])),
                fees=Decimal(str(ot["fees"])),
            )
            if ot.get("partial_exit_pnl") is not None:
                self._partial_exit_pnl = Decimal(str(ot["partial_exit_pnl"]))
            if ot.get("exit_fill_notional") is not None:
                self._exit_fill_notional = Decimal(str(ot["exit_fill_notional"]))
            if ot.get("exit_fill_amount") is not None:
                self._exit_fill_amount = Decimal(str(ot["exit_fill_amount"]))
        else:
            # Fallback: rebuild from positions (no entry_time available)
            for symbol, pos in self._positions.items():
                if pos.is_open:
                    self._open_trade = TradeRecord(
                        symbol=symbol,
                        side=OrderSide.BUY if pos.amount > 0 else OrderSide.SELL,
                        entry_time=datetime.now(UTC),
                        entry_price=pos.avg_entry_price,
                        amount=abs(pos.amount),
                        fees=Decimal("0"),
                    )
                    break
