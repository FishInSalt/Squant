"""Backtest context providing strategy runtime API.

The BacktestContext is injected into user strategies and provides:
- Market data access (current and historical bars)
- Order placement (buy/sell)
- Position queries
- Account state (cash, equity)
- Logging
"""

from collections import deque
from datetime import datetime
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
        max_equity_curve: int = 10000,
        max_completed_orders: int = 1000,
        max_fills: int = 5000,
        max_trades: int = 1000,
        max_logs: int = 1000,
    ):
        """Initialize backtest context.

        Args:
            initial_capital: Starting capital.
            commission_rate: Commission rate as a decimal (e.g., 0.001 = 0.1%).
            slippage: Slippage rate for market orders.
            params: Strategy parameters.
            max_bar_history: Maximum bars to keep in history buffer.
            max_equity_curve: Maximum equity snapshots to keep.
            max_completed_orders: Maximum completed orders to keep.
            max_fills: Maximum fills to keep.
            max_trades: Maximum trades to keep.
            max_logs: Maximum log entries to keep.
        """
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._commission_rate = commission_rate
        self._slippage = slippage
        self._params = params or {}
        self._max_bar_history = max_bar_history

        # Position tracking
        self._positions: dict[str, Position] = {}

        # Order management
        self._pending_orders: list[SimulatedOrder] = []
        self._completed_orders: deque[SimulatedOrder] = deque(maxlen=max_completed_orders)
        self._order_counter = 0

        # Fill and trade tracking
        self._fills: deque[Fill] = deque(maxlen=max_fills)
        self._trades: deque[TradeRecord] = deque(maxlen=max_trades)
        self._open_trade: TradeRecord | None = None

        # Bar history (deque for efficient append/pop)
        self._bar_history: deque[Bar] = deque(maxlen=max_bar_history)
        self._current_bar: Bar | None = None

        # Equity tracking
        self._equity_curve: deque[EquitySnapshot] = deque(maxlen=max_equity_curve)

        # Logging
        self._logs: deque[str] = deque(maxlen=max_logs)

        # Total fees paid
        self._total_fees = Decimal("0")

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
    ) -> str:
        """Place a buy order.

        Args:
            symbol: Trading symbol.
            amount: Amount to buy (must be positive).
            price: Limit price (None for market order).

        Returns:
            Order ID.

        Raises:
            ValueError: If amount is not positive or insufficient cash.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        amount = Decimal(str(amount))

        # Validate sufficient cash for buy orders
        if price is not None:
            # Limit order: use limit price
            estimated_cost = Decimal(str(price)) * amount * (1 + self._commission_rate)
        elif self._current_bar:
            # Market order: estimate using current bar's close price
            estimated_cost = self._current_bar.close * amount * (1 + self._commission_rate)
        else:
            # No bar yet, skip validation (will be caught at fill time)
            estimated_cost = Decimal("0")

        if estimated_cost > 0 and self._cash < estimated_cost:
            raise ValueError(
                f"Insufficient cash for buy order: available={self._cash}, "
                f"estimated_cost={estimated_cost}"
            )

        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        order = SimulatedOrder.create(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=order_type,
            amount=amount,
            price=Decimal(str(price)) if price is not None else None,
            created_at=self._current_bar.time if self._current_bar else None,
        )
        self._pending_orders.append(order)
        return order.id

    def sell(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal | None = None,
    ) -> str:
        """Place a sell order.

        This is a SPOT trading system - short selling is not allowed.
        You can only sell what you own.

        Args:
            symbol: Trading symbol.
            amount: Amount to sell (must be positive).
            price: Limit price (None for market order).

        Returns:
            Order ID.

        Raises:
            ValueError: If amount is not positive or exceeds position.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        amount = Decimal(str(amount))

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

        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        order = SimulatedOrder.create(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=order_type,
            amount=amount,
            price=Decimal(str(price)) if price is not None else None,
            created_at=self._current_bar.time if self._current_bar else None,
        )
        self._pending_orders.append(order)
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
        timestamp = self._current_bar.time if self._current_bar else datetime.now()
        self._logs.append(f"[{timestamp}] {message}")

    # =========================================================================
    # Internal Methods (called by BacktestRunner)
    # =========================================================================

    def _set_current_bar(self, bar: Bar) -> None:
        """Set the current bar being processed."""
        self._current_bar = bar

    def _add_bar_to_history(self, bar: Bar) -> None:
        """Add a bar to the history buffer."""
        self._bar_history.append(bar)

    def _get_pending_orders(self) -> list[SimulatedOrder]:
        """Get pending orders for matching engine."""
        return self._pending_orders

    def _process_fill(self, fill: Fill) -> None:
        """Process a fill from the matching engine.

        Updates positions, cash, and tracks the fill.

        Args:
            fill: Fill event to process.

        Raises:
            ValueError: If insufficient cash for buy order or insufficient position for sell.
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
            if self._cash < cost:
                raise ValueError(
                    f"Insufficient cash for fill: available={self._cash}, "
                    f"required={cost} (price={fill.price}, amount={fill.amount}, fee={fill.fee})"
                )
            self._cash -= cost
        else:
            # Validate sufficient position before executing (spot trading - no short)
            if position.amount < fill.amount:
                raise ValueError(
                    f"Insufficient position for sell fill: position={position.amount}, "
                    f"fill_amount={fill.amount}"
                )
            proceeds = fill.price * fill.amount - fill.fee
            self._cash += proceeds

        # Record the fill (only after validation passes)
        self._fills.append(fill)
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
        # Position opened
        if prev_amount == Decimal("0") and new_amount != Decimal("0"):
            self._open_trade = TradeRecord(
                symbol=fill.symbol,
                side=fill.side,
                entry_time=fill.timestamp,
                entry_price=fill.price,
                amount=abs(new_amount),
                fees=fill.fee,
            )

        # Position increased
        elif (prev_amount > 0 and new_amount > prev_amount) or (
            prev_amount < 0 and new_amount < prev_amount
        ):
            if self._open_trade:
                # Average into existing trade
                self._open_trade.fees += fill.fee
                self._open_trade.amount = abs(new_amount)

        # Position decreased or closed
        elif self._open_trade:
            self._open_trade.fees += fill.fee

            # Position closed
            if new_amount == Decimal("0"):
                self._open_trade.exit_time = fill.timestamp
                self._open_trade.exit_price = fill.price

                # Calculate PnL
                if self._open_trade.side == OrderSide.BUY:
                    pnl = (fill.price - self._open_trade.entry_price) * self._open_trade.amount
                else:
                    pnl = (self._open_trade.entry_price - fill.price) * self._open_trade.amount
                pnl -= self._open_trade.fees
                self._open_trade.pnl = pnl

                if self._open_trade.entry_price != Decimal("0"):
                    self._open_trade.pnl_pct = (
                        pnl / (self._open_trade.entry_price * self._open_trade.amount) * 100
                    )

                self._trades.append(self._open_trade)
                self._open_trade = None

            # Position reversed
            elif (prev_amount > 0 and new_amount < 0) or (prev_amount < 0 and new_amount > 0):
                # Close existing trade
                self._open_trade.exit_time = fill.timestamp
                self._open_trade.exit_price = fill.price
                self._open_trade.amount = abs(prev_amount)

                # Calculate PnL for closed portion
                if self._open_trade.side == OrderSide.BUY:
                    pnl = (fill.price - self._open_trade.entry_price) * abs(prev_amount)
                else:
                    pnl = (self._open_trade.entry_price - fill.price) * abs(prev_amount)
                pnl -= self._open_trade.fees
                self._open_trade.pnl = pnl

                if self._open_trade.entry_price != Decimal("0"):
                    self._open_trade.pnl_pct = (
                        pnl / (self._open_trade.entry_price * abs(prev_amount)) * 100
                    )

                self._trades.append(self._open_trade)

                # Open new trade in the direction of the fill that opened it
                self._open_trade = TradeRecord(
                    symbol=fill.symbol,
                    side=fill.side,
                    entry_time=fill.timestamp,
                    entry_price=fill.price,
                    amount=abs(new_amount),
                    fees=Decimal("0"),
                )

    def _record_equity_snapshot(self, time: datetime) -> None:
        """Record an equity snapshot.

        Args:
            time: Timestamp for the snapshot.
        """
        position_value = self._get_position_value()
        unrealized_pnl = self._get_unrealized_pnl()

        snapshot = EquitySnapshot(
            time=time,
            equity=self._cash + position_value,
            cash=self._cash,
            position_value=position_value,
            unrealized_pnl=unrealized_pnl,
        )
        self._equity_curve.append(snapshot)

    def _get_position_value(self) -> Decimal:
        """Calculate total position value at current market price."""
        if not self._current_bar:
            return Decimal("0")

        total = Decimal("0")
        for symbol, position in self._positions.items():
            if position.is_open and symbol == self._current_bar.symbol:
                total += position.amount * self._current_bar.close
        return total

    def _get_unrealized_pnl(self) -> Decimal:
        """Calculate unrealized PnL for all positions."""
        if not self._current_bar:
            return Decimal("0")

        total = Decimal("0")
        for symbol, position in self._positions.items():
            if position.is_open and symbol == self._current_bar.symbol:
                if position.amount > 0:
                    # Long position
                    total += (self._current_bar.close - position.avg_entry_price) * position.amount
                else:
                    # Short position
                    total += (position.avg_entry_price - self._current_bar.close) * abs(
                        position.amount
                    )
        return total
