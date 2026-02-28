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
        max_volume_participation: Decimal | None = None,
    ):
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.max_volume_participation = max_volume_participation

    def compute_volume_budget(self, volume: Decimal | None) -> Decimal | None:
        """Compute the shared volume budget for a single candle.

        All orders (market + limit) on the same candle share this budget.

        Args:
            volume: Bar volume (or cumulative volume for unclosed candles).

        Returns:
            Volume budget in base currency, or None if no participation limit.
        """
        if self.max_volume_participation is None or volume is None:
            return None
        if volume <= 0:
            return Decimal("0")
        return volume * self.max_volume_participation

    def fill_market_order(
        self,
        order: SimulatedOrder,
        current_price: Decimal,
        timestamp: datetime,
        volume: Decimal | None = None,
        volume_budget: Decimal | None = None,
    ) -> Fill | None:
        """Fill a market order immediately at current_price with slippage.

        BUY: fill_price = current_price * (1 + slippage)
        SELL: fill_price = current_price * (1 - slippage)

        When volume_budget is provided, it is used directly as the fill cap.
        Otherwise, falls back to computing from volume * max_volume_participation.

        Args:
            order: Market order to fill.
            current_price: Current market price.
            timestamp: Fill timestamp.
            volume: Bar volume (legacy, used when volume_budget not provided).
            volume_budget: Pre-computed shared volume budget (takes priority).

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

        # Cap fill amount by volume budget (shared) or volume (legacy)
        if volume_budget is not None:
            if volume_budget <= 0:
                return None
            fill_amount = min(fill_amount, volume_budget)
        elif self.max_volume_participation is not None and volume is not None:
            if volume <= 0:
                return None
            max_amount = volume * self.max_volume_participation
            fill_amount = min(fill_amount, max_amount)

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
        volume: Decimal | None = None,
        open_price: Decimal | None = None,
        volume_budget: Decimal | None = None,
    ) -> list[Fill]:
        """Check pending limit orders against current price (and high/low range).

        When high/low are provided (closed candles), uses range-based triggering:
          BUY LIMIT: triggers when low <= limit_price
          SELL LIMIT: triggers when high >= limit_price

        When high/low are None (unclosed candles), falls back to close price:
          BUY LIMIT: triggers when current_price <= limit_price
          SELL LIMIT: triggers when current_price >= limit_price

        Triggered orders fill at their limit price or better (gap-open price
        improvement). When open_price is provided and the bar opens through the
        limit price, the fill price improves to the open price — consistent
        with the backtest matching engine.

        Volume participation: when volume_budget is provided, it is used as a
        shared pool across all limit orders. Otherwise, falls back to computing
        independently from volume * max_volume_participation per order.

        Args:
            orders: List of pending limit orders to check.
            current_price: Current market price (candle close).
            timestamp: Fill timestamp.
            high: Candle high price (optional, for closed candles).
            low: Candle low price (optional, for closed candles).
            volume: Bar volume (legacy, used when volume_budget not provided).
            open_price: Candle open price (optional, for gap-open price improvement).
            volume_budget: Pre-computed shared volume budget (takes priority).

        Returns:
            List of fills for triggered orders.
        """
        fills: list[Fill] = []

        # Track remaining budget when using shared volume pool
        remaining_budget = volume_budget

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

            # Gap-open price improvement: if the bar opens through the limit,
            # fill at the open price (better than limit). Consistent with
            # backtest matching engine behavior.
            if open_price is not None:
                if order.side == OrderSide.BUY:
                    fill_price = min(limit_price, open_price)
                else:
                    fill_price = max(limit_price, open_price)
            else:
                fill_price = limit_price

            fill_amount = order.remaining

            # Cap fill amount by volume budget (shared) or volume (legacy)
            if remaining_budget is not None:
                if remaining_budget <= 0:
                    continue  # Budget exhausted
                fill_amount = min(fill_amount, remaining_budget)
            elif self.max_volume_participation is not None and volume is not None:
                if volume <= 0:
                    continue
                max_amount = volume * self.max_volume_participation
                fill_amount = min(fill_amount, max_amount)

            fill_value = fill_price * fill_amount
            fee = fill_value * self.commission_rate

            fills.append(
                Fill(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    price=fill_price,
                    amount=fill_amount,
                    fee=fee,
                    timestamp=timestamp,
                )
            )

            # Deduct from shared budget
            if remaining_budget is not None:
                remaining_budget -= fill_amount

        return fills
