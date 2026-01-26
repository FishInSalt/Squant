"""Matching engine for order execution simulation.

The matching engine simulates order execution during backtesting:
- Market orders execute at next bar's open (preventing look-ahead bias)
- Limit orders execute when price touches the limit price
- Slippage is applied to market order fills
- Commission is calculated on fill value
"""

from decimal import Decimal

from squant.engine.backtest.types import (
    Bar,
    Fill,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedOrder,
)


class MatchingEngine:
    """Simulates order matching and execution.

    The matching engine processes pending orders against market data,
    generating fills when orders can be executed.

    Attributes:
        commission_rate: Commission rate as decimal (e.g., 0.001 = 0.1%).
        slippage: Slippage rate for market orders.
    """

    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0"),
    ):
        """Initialize matching engine.

        Args:
            commission_rate: Commission rate as decimal.
            slippage: Slippage rate for market orders as decimal.
        """
        self.commission_rate = commission_rate
        self.slippage = slippage

    def process_bar(
        self,
        bar: Bar,
        pending_orders: list[SimulatedOrder],
    ) -> list[Fill]:
        """Process a bar and match pending orders.

        Market orders are filled at the bar's open price (with slippage).
        Limit orders are filled if the bar's price range touches the limit.

        Args:
            bar: The current OHLCV bar.
            pending_orders: List of pending orders to process.

        Returns:
            List of fills generated from order matching.
        """
        fills: list[Fill] = []

        for order in pending_orders:
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                continue

            if order.symbol != bar.symbol:
                continue

            fill = self._try_fill_order(order, bar)
            if fill:
                fills.append(fill)

        return fills

    def _try_fill_order(self, order: SimulatedOrder, bar: Bar) -> Fill | None:
        """Attempt to fill an order against a bar.

        Args:
            order: Order to fill.
            bar: Current bar data.

        Returns:
            Fill if order can be executed, None otherwise.
        """
        if order.type == OrderType.MARKET:
            return self._fill_market_order(order, bar)
        else:
            return self._fill_limit_order(order, bar)

    def _fill_market_order(self, order: SimulatedOrder, bar: Bar) -> Fill:
        """Fill a market order at open price with slippage.

        Market orders always fill at the bar's open price.
        Slippage is applied in the direction unfavorable to the trader.

        Args:
            order: Market order to fill.
            bar: Current bar data.

        Returns:
            Fill for the market order.
        """
        base_price = bar.open

        # Apply slippage in unfavorable direction
        if self.slippage > 0:
            if order.side == OrderSide.BUY:
                # Slippage increases buy price
                fill_price = base_price * (1 + self.slippage)
            else:
                # Slippage decreases sell price
                fill_price = base_price * (1 - self.slippage)
        else:
            fill_price = base_price

        # Ensure fill price is within bar's range
        fill_price = max(bar.low, min(bar.high, fill_price))

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
            timestamp=bar.time,
        )

    def _fill_limit_order(self, order: SimulatedOrder, bar: Bar) -> Fill | None:
        """Fill a limit order if price touches the limit.

        Buy limit orders fill when price drops to or below the limit.
        Sell limit orders fill when price rises to or above the limit.

        For simplicity, we assume complete fill if the limit is touched.
        More sophisticated engines could model partial fills.

        Args:
            order: Limit order to fill.
            bar: Current bar data.

        Returns:
            Fill if limit is touched, None otherwise.
        """
        if order.price is None:
            return None

        limit_price = order.price
        can_fill = False

        if order.side == OrderSide.BUY:
            # Buy limit fills when price goes low enough
            if bar.low <= limit_price:
                can_fill = True
                # Fill at limit price or better (could get open if it gaps down)
                fill_price = min(limit_price, bar.open)
        else:
            # Sell limit fills when price goes high enough
            if bar.high >= limit_price:
                can_fill = True
                # Fill at limit price or better (could get open if it gaps up)
                fill_price = max(limit_price, bar.open)

        if not can_fill:
            return None

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
            timestamp=bar.time,
        )

    def validate_order(self, order: SimulatedOrder, cash: Decimal) -> tuple[bool, str]:
        """Validate if an order can be placed.

        Checks:
        - Sufficient cash for buy orders (at estimated price)
        - Order amount is positive

        Args:
            order: Order to validate.
            cash: Available cash.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if order.amount <= 0:
            return False, "Order amount must be positive"

        if order.side == OrderSide.BUY:
            # Estimate required cash (use limit price or a reasonable estimate)
            if order.type == OrderType.LIMIT and order.price:
                estimated_cost = order.price * order.amount
            else:
                # For market orders, we can't know the exact cost ahead of time
                # This is a basic check that will be refined during fill
                estimated_cost = Decimal("0")  # Market orders validated at fill time

            if order.type == OrderType.LIMIT:
                required = estimated_cost * (1 + self.commission_rate)
                if cash < required:
                    return False, f"Insufficient cash: {cash} < {required}"

        return True, ""
