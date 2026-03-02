"""Backtest engine data types."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Bar:
    """OHLCV bar data.

    Immutable dataclass representing a single candlestick.
    """

    time: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Validate bar data."""
        if self.high < self.low:
            raise ValueError("High cannot be less than low")
        if self.open < self.low or self.open > self.high:
            raise ValueError("Open must be between low and high")
        if self.close < self.low or self.close > self.high:
            raise ValueError("Close must be between low and high")


@dataclass
class Position:
    """Position information.

    Tracks the current position for a symbol including average entry price.
    """

    symbol: str
    amount: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")

    @property
    def is_open(self) -> bool:
        """Check if position is open (non-zero amount)."""
        return self.amount != Decimal("0")

    def update(self, filled_amount: Decimal, fill_price: Decimal, side: OrderSide) -> None:
        """Update position after a fill.

        This is a SPOT trading system - short positions are not allowed.

        Args:
            filled_amount: Amount filled (always positive).
            fill_price: Price at which the fill occurred.
            side: Order side (buy/sell).

        Raises:
            ValueError: If sell would result in negative position (short selling).
        """
        if side == OrderSide.BUY:
            # Buying increases position
            new_amount = self.amount + filled_amount
            if new_amount != Decimal("0"):
                # Weighted average entry price
                total_cost = (self.amount * self.avg_entry_price) + (filled_amount * fill_price)
                self.avg_entry_price = total_cost / new_amount
            self.amount = new_amount
        else:
            # Selling decreases position
            new_amount = self.amount - filled_amount
            if new_amount < Decimal("0"):
                # SPOT trading: short selling is not allowed
                raise ValueError(
                    f"Cannot sell more than current position: "
                    f"position={self.amount}, sell_amount={filled_amount}"
                )
            self.amount = new_amount
            if self.amount == Decimal("0"):
                # Position fully closed
                self.avg_entry_price = Decimal("0")


@dataclass
class SimulatedOrder:
    """Simulated order for backtesting.

    Tracks order state during backtest execution.
    """

    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    amount: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None  # Trigger price for STOP and STOP_LIMIT orders
    triggered: bool = False  # Whether a STOP_LIMIT order has been triggered
    status: OrderStatus = OrderStatus.PENDING
    filled: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
    created_at: datetime | None = None
    filled_at: datetime | None = None
    bars_remaining: int | None = None  # None = GTC, positive int = expire after N bars

    @classmethod
    def create(
        cls,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        created_at: datetime | None = None,
        bars_remaining: int | None = None,
    ) -> "SimulatedOrder":
        """Create a new simulated order."""
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("Limit orders require a price")
        if order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("Stop orders require a stop_price")
            if price is not None:
                raise ValueError("Stop orders must not have a limit price (use STOP_LIMIT)")
        if order_type == OrderType.STOP_LIMIT:
            if stop_price is None:
                raise ValueError("Stop-limit orders require a stop_price")
            if price is None:
                raise ValueError("Stop-limit orders require a limit price")
        return cls(
            id=str(uuid4()),
            symbol=symbol,
            side=side,
            type=order_type,
            amount=amount,
            price=price,
            stop_price=stop_price,
            created_at=created_at,
            bars_remaining=bars_remaining,
        )

    @property
    def remaining(self) -> Decimal:
        """Get remaining unfilled amount."""
        return self.amount - self.filled

    @property
    def is_complete(self) -> bool:
        """Check if order is fully filled or cancelled."""
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED)


@dataclass
class Fill:
    """Order fill event.

    Represents a single fill execution.
    """

    order_id: str
    symbol: str
    side: OrderSide
    price: Decimal
    amount: Decimal
    fee: Decimal
    timestamp: datetime
    # 价格来源元数据（模拟交易撮合引擎填充，回测为 None）
    price_source: str | None = None  # "ask", "bid", "slippage", "limit", "stop_limit"
    reference_price: Decimal | None = None  # last price
    spread_pct: Decimal | None = None  # spread 百分比


@dataclass
class TradeRecord:
    """Completed trade record for performance analysis.

    A trade is opened when a position is entered and closed when exited.
    """

    symbol: str
    side: OrderSide
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime | None = None
    exit_price: Decimal | None = None
    amount: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    pnl_pct: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")

    @property
    def is_closed(self) -> bool:
        """Check if trade is closed."""
        return self.exit_time is not None


@dataclass
class EquitySnapshot:
    """Equity curve snapshot at a point in time."""

    time: datetime
    equity: Decimal
    cash: Decimal
    position_value: Decimal
    unrealized_pnl: Decimal
    benchmark_equity: Decimal = Decimal("0")


@dataclass
class BacktestResult:
    """Complete backtest result.

    Contains all data from a completed backtest run.
    """

    # Run metadata
    run_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    bar_count: int

    # Capital settings
    initial_capital: Decimal
    final_equity: Decimal
    commission_rate: Decimal
    slippage: Decimal

    # Performance metrics (computed separately)
    metrics: dict[str, Any] = field(default_factory=dict)

    # Detailed data
    equity_curve: list[EquitySnapshot] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    orders: list[SimulatedOrder] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
