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
        high: Decimal | None = None,
        low: Decimal | None = None,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
    ) -> Fill | None:
        """Fill a market order at the best available price.

        When bid/ask data is available (from ticker stream), uses actual
        spread pricing: BUY fills at ask, SELL fills at bid. This provides
        more realistic simulation than fixed slippage.

        When bid/ask is not available, falls back to slippage-based pricing:
        BUY: current_price * (1 + slippage), SELL: current_price * (1 - slippage).

        When high/low are provided, the fill price is clamped to [low, high]
        to ensure it stays within the bar's traded range.

        Args:
            order: Market order to fill.
            current_price: Current market price.
            timestamp: Fill timestamp.
            volume: Bar volume (legacy, used when volume_budget not provided).
            volume_budget: Pre-computed shared volume budget (takes priority).
            high: Candle high price (optional, for clamping).
            low: Candle low price (optional, for clamping).
            bid: Best bid price from ticker (for sell orders).
            ask: Best ask price from ticker (for buy orders).

        Returns:
            Fill if order is a valid pending market order, None otherwise.
        """
        if order.type != OrderType.MARKET:
            return None
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return None

        fill_price, price_source = self._compute_market_fill_price(
            order.side,
            current_price,
            bid=bid,
            ask=ask,
        )

        # Clamp to bar range (consistent with backtest matching engine)
        if high is not None and low is not None:
            fill_price = max(low, min(high, fill_price))

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

        # Compute spread percentage
        spread_pct: Decimal | None = None
        if current_price and current_price > 0:
            spread_pct = abs(fill_price - current_price) / current_price * 100

        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            amount=fill_amount,
            fee=fee,
            timestamp=timestamp,
            price_source=price_source,
            reference_price=current_price,
            spread_pct=spread_pct,
        )

    def _compute_market_fill_price(
        self,
        side: OrderSide,
        current_price: Decimal,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
    ) -> tuple[Decimal, str]:
        """Compute fill price for market-style execution.

        Uses bid/ask when available (spread simulation), otherwise falls
        back to current_price with slippage applied.

        Args:
            side: Order side (BUY or SELL).
            current_price: Current market price (candle close).
            bid: Best bid price from ticker.
            ask: Best ask price from ticker.

        Returns:
            Tuple of (fill_price, price_source) where price_source is one of
            "ask", "bid", "slippage", "last".
        """
        if side == OrderSide.BUY:
            if ask is not None:
                return ask, "ask"
            if self.slippage > 0:
                return current_price * (1 + self.slippage), "slippage"
            return current_price, "last"
        else:
            if bid is not None:
                return bid, "bid"
            if self.slippage > 0:
                return current_price * (1 - self.slippage), "slippage"
            return current_price, "last"

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
                    price_source="limit",
                )
            )

            # Deduct from shared budget
            if remaining_budget is not None:
                remaining_budget -= fill_amount

        return fills

    def _check_stop_trigger_tick(
        self,
        order: SimulatedOrder,
        current_price: Decimal,
        high: Decimal | None = None,
        low: Decimal | None = None,
    ) -> bool:
        """Check if a stop order's trigger condition is met at tick level.

        With high/low (closed candle): uses range-based check (same as backtest).
        Without high/low (unclosed candle): uses current_price (close) as proxy.

        Args:
            order: Stop or stop-limit order.
            current_price: Current market price (candle close).
            high: Candle high price (for closed candles).
            low: Candle low price (for closed candles).

        Returns:
            True if trigger condition is met.
        """
        if order.stop_price is None:
            return False
        if order.side == OrderSide.BUY:
            check_price = high if high is not None else current_price
            return check_price >= order.stop_price
        else:
            check_price = low if low is not None else current_price
            return check_price <= order.stop_price

    def fill_stop_order(
        self,
        order: SimulatedOrder,
        current_price: Decimal,
        timestamp: datetime,
        high: Decimal | None = None,
        low: Decimal | None = None,
        volume_budget: Decimal | None = None,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
    ) -> Fill | None:
        """Fill a stop order if triggered, using market-order style execution.

        After the stop triggers, the order fills as a market order using
        bid/ask spread pricing (when available) or slippage fallback.

        Args:
            order: Stop order to fill.
            current_price: Current market price.
            timestamp: Fill timestamp.
            high: Candle high price.
            low: Candle low price.
            volume_budget: Pre-computed shared volume budget.
            bid: Best bid price from ticker (for sell orders).
            ask: Best ask price from ticker (for buy orders).

        Returns:
            Fill if triggered, None otherwise.
        """
        if order.type != OrderType.STOP:
            return None
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return None
        if order.stop_price is None:
            return None

        if not self._check_stop_trigger_tick(order, current_price, high, low):
            return None

        # Triggered — fill as market order using spread or slippage
        fill_price, price_source = self._compute_market_fill_price(
            order.side,
            current_price,
            bid=bid,
            ask=ask,
        )

        # Clamp to bar range
        if high is not None and low is not None:
            fill_price = max(low, min(high, fill_price))

        fill_amount = order.remaining

        # Cap fill amount by volume budget
        if volume_budget is not None:
            if volume_budget <= 0:
                return None
            fill_amount = min(fill_amount, volume_budget)

        fill_value = fill_price * fill_amount
        fee = fill_value * self.commission_rate

        # Compute spread percentage
        spread_pct: Decimal | None = None
        if current_price and current_price > 0:
            spread_pct = abs(fill_price - current_price) / current_price * 100

        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            amount=fill_amount,
            fee=fee,
            timestamp=timestamp,
            price_source=price_source,
            reference_price=current_price,
            spread_pct=spread_pct,
        )

    def _try_fill_as_limit(
        self,
        order: SimulatedOrder,
        current_price: Decimal,
        timestamp: datetime,
        high: Decimal | None = None,
        low: Decimal | None = None,
        open_price: Decimal | None = None,
        volume_budget: Decimal | None = None,
    ) -> Fill | None:
        """Try to fill a triggered stop-limit order as a limit order.

        Shared logic between match_pending_limits and match_pending_stop_limits.

        Args:
            order: Order with a limit price to check.
            current_price: Current market price.
            timestamp: Fill timestamp.
            high: Candle high.
            low: Candle low.
            open_price: Candle open (for gap-open price improvement).
            volume_budget: Pre-computed shared volume budget.

        Returns:
            Fill if limit is reachable, None otherwise.
        """
        if order.price is None:
            return None

        limit_price = order.price
        can_fill = False

        if order.side == OrderSide.BUY:
            check_price = low if low is not None else current_price
            if check_price <= limit_price:
                can_fill = True
        else:
            check_price = high if high is not None else current_price
            if check_price >= limit_price:
                can_fill = True

        if not can_fill:
            return None

        # Gap-open price improvement
        if open_price is not None:
            if order.side == OrderSide.BUY:
                fill_price = min(limit_price, open_price)
            else:
                fill_price = max(limit_price, open_price)
        else:
            fill_price = limit_price

        fill_amount = order.remaining

        # Cap fill amount by volume budget
        if volume_budget is not None:
            if volume_budget <= 0:
                return None
            fill_amount = min(fill_amount, volume_budget)

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
            price_source="stop_limit",
        )

    def match_pending_stop_limits(
        self,
        orders: list[SimulatedOrder],
        current_price: Decimal,
        timestamp: datetime,
        high: Decimal | None = None,
        low: Decimal | None = None,
        open_price: Decimal | None = None,
        volume_budget: Decimal | None = None,
    ) -> list[Fill]:
        """Check pending stop-limit orders: trigger and attempt limit fill.

        For untriggered orders, checks trigger condition and marks triggered=True.
        For triggered orders, attempts limit fill.

        Args:
            orders: List of pending stop-limit orders.
            current_price: Current market price.
            timestamp: Fill timestamp.
            high: Candle high price.
            low: Candle low price.
            open_price: Candle open price.
            volume_budget: Pre-computed shared volume budget.

        Returns:
            List of fills for orders that triggered and limit was reachable.
        """
        fills: list[Fill] = []
        remaining_budget = volume_budget

        for order in orders:
            if order.type != OrderType.STOP_LIMIT:
                continue
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                continue

            if not order.triggered:
                # Check trigger condition
                if not self._check_stop_trigger_tick(order, current_price, high, low):
                    continue
                # Mark as triggered
                order.triggered = True

            # Attempt limit fill
            fill = self._try_fill_as_limit(
                order,
                current_price,
                timestamp,
                high=high,
                low=low,
                open_price=open_price,
                volume_budget=remaining_budget,
            )
            if fill:
                fills.append(fill)
                if remaining_budget is not None:
                    remaining_budget -= fill.amount

        return fills
