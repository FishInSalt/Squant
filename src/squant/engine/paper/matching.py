"""Tick-level matching engine for paper trading.

Unlike the backtest MatchingEngine (bar-level, fills at next bar open),
this engine fills orders immediately at the current market price,
simulating real exchange behavior.
"""

from datetime import datetime
from decimal import Decimal

from squant.engine.backtest.types import (
    Fill,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedOrder,
)


class PaperMatchingEngine:
    """Tick-level matching engine for paper trading.

    Stateless engine that fills market orders immediately and checks
    limit orders against the current price on every tick/candle update.

    Attributes:
        commission_rate: Commission rate as decimal (e.g., 0.001 = 0.1%).
        slippage: Slippage rate for market orders.
    """

    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
    ):
        self.commission_rate = commission_rate
        self.slippage = slippage

    def fill_market_order(
        self,
        order: SimulatedOrder,
        current_price: Decimal,
        timestamp: datetime,
    ) -> Fill | None:
        """Fill a market order immediately at current_price with slippage.

        BUY: fill_price = current_price * (1 + slippage)
        SELL: fill_price = current_price * (1 - slippage)

        Args:
            order: Market order to fill.
            current_price: Current market price.
            timestamp: Fill timestamp.

        Returns:
            Fill if order is a valid pending market order, None otherwise.
        """
        if order.type != OrderType.MARKET:
            return None
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return None

        if self.slippage > 0:
            if order.side == OrderSide.BUY:
                fill_price = current_price * (1 + self.slippage)
            else:
                fill_price = current_price * (1 - self.slippage)
        else:
            fill_price = current_price

        fill_amount = order.remaining
        fill_value = fill_price * fill_amount
        fee = fill_value * self.commission_rate

        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            amount=fill_amount,
            fee=fee,
            timestamp=timestamp,
        )

    def match_pending_limits(
        self,
        orders: list[SimulatedOrder],
        current_price: Decimal,
        timestamp: datetime,
        high: Decimal | None = None,
        low: Decimal | None = None,
    ) -> list[Fill]:
        """Check pending limit orders against current price (and high/low range).

        When high/low are provided (closed candles), uses range-based triggering:
          BUY LIMIT: triggers when low <= limit_price
          SELL LIMIT: triggers when high >= limit_price

        When high/low are None (unclosed candles), falls back to close price:
          BUY LIMIT: triggers when current_price <= limit_price
          SELL LIMIT: triggers when current_price >= limit_price

        Triggered orders fill at their limit price (price improvement).

        Args:
            orders: List of pending limit orders to check.
            current_price: Current market price (candle close).
            timestamp: Fill timestamp.
            high: Candle high price (optional, for closed candles).
            low: Candle low price (optional, for closed candles).

        Returns:
            List of fills for triggered orders.
        """
        fills: list[Fill] = []

        for order in orders:
            if order.type != OrderType.LIMIT:
                continue
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                continue
            if order.price is None:
                continue

            limit_price = order.price
            can_fill = False

            if order.side == OrderSide.BUY:
                # BUY LIMIT: price must touch or go below limit
                check_price = low if low is not None else current_price
                if check_price <= limit_price:
                    can_fill = True
            else:
                # SELL LIMIT: price must touch or go above limit
                check_price = high if high is not None else current_price
                if check_price >= limit_price:
                    can_fill = True

            if not can_fill:
                continue

            fill_amount = order.remaining
            fill_value = limit_price * fill_amount
            fee = fill_value * self.commission_rate

            fills.append(
                Fill(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    price=limit_price,
                    amount=fill_amount,
                    fee=fee,
                    timestamp=timestamp,
                )
            )

        return fills
