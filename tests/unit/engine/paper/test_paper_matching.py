"""Unit tests for PaperMatchingEngine (tick-level matching)."""

from datetime import UTC, datetime
from decimal import Decimal

from squant.engine.backtest.types import (
    OrderSide,
    OrderStatus,
    OrderType,
    SimulatedOrder,
)
from squant.engine.paper.matching import PaperMatchingEngine

SYMBOL = "BTC/USDT"
TS = datetime(2024, 1, 1, tzinfo=UTC)


def _market_order(side: OrderSide, amount: str = "0.1") -> SimulatedOrder:
    return SimulatedOrder.create(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        amount=Decimal(amount),
    )


def _limit_order(side: OrderSide, price: str, amount: str = "0.1") -> SimulatedOrder:
    return SimulatedOrder.create(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.LIMIT,
        amount=Decimal(amount),
        price=Decimal(price),
    )


class TestFillMarketOrder:
    """Tests for fill_market_order()."""

    def test_fill_market_buy(self):
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.001"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(order, Decimal("50000"), TS)

        assert fill is not None
        # BUY: price = 50000 * (1 + 0.001) = 50050
        assert fill.price == Decimal("50000") * (1 + Decimal("0.001"))
        assert fill.amount == Decimal("0.1")
        assert fill.side == OrderSide.BUY
        assert fill.fee == fill.price * fill.amount * Decimal("0.001")
        assert fill.timestamp == TS

    def test_fill_market_sell(self):
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.001"),
        )
        order = _market_order(OrderSide.SELL)
        fill = engine.fill_market_order(order, Decimal("50000"), TS)

        assert fill is not None
        # SELL: price = 50000 * (1 - 0.001) = 49950
        assert fill.price == Decimal("50000") * (1 - Decimal("0.001"))
        assert fill.amount == Decimal("0.1")
        assert fill.side == OrderSide.SELL

    def test_fill_market_zero_slippage(self):
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(order, Decimal("50000"), TS)

        assert fill is not None
        assert fill.price == Decimal("50000")

    def test_returns_none_for_limit_order(self):
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.BUY, "49000")
        fill = engine.fill_market_order(order, Decimal("50000"), TS)
        assert fill is None

    def test_returns_none_for_filled_order(self):
        engine = PaperMatchingEngine()
        order = _market_order(OrderSide.BUY)
        order.status = OrderStatus.FILLED
        fill = engine.fill_market_order(order, Decimal("50000"), TS)
        assert fill is None

    def test_returns_none_for_cancelled_order(self):
        engine = PaperMatchingEngine()
        order = _market_order(OrderSide.BUY)
        order.status = OrderStatus.CANCELLED
        fill = engine.fill_market_order(order, Decimal("50000"), TS)
        assert fill is None

    def test_full_amount_fill(self):
        """Order amount is fully filled (no partial fills)."""
        engine = PaperMatchingEngine()
        order = _market_order(OrderSide.BUY, "1.5")
        fill = engine.fill_market_order(order, Decimal("50000"), TS)

        assert fill is not None
        assert fill.amount == Decimal("1.5")


class TestMatchPendingLimits:
    """Tests for match_pending_limits()."""

    def test_limit_buy_triggers(self):
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        # current_price (48500) <= limit (49000) → triggers
        fills = engine.match_pending_limits([order], Decimal("48500"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")  # fills at limit price
        assert fills[0].amount == Decimal("0.1")
        assert fills[0].side == OrderSide.BUY

    def test_limit_buy_triggers_at_exact_price(self):
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        fills = engine.match_pending_limits([order], Decimal("49000"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")

    def test_limit_buy_not_triggered(self):
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.BUY, "49000")
        # current_price (50000) > limit (49000) → no fill
        fills = engine.match_pending_limits([order], Decimal("50000"), TS)

        assert len(fills) == 0

    def test_limit_sell_triggers(self):
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "51000")
        # current_price (52000) >= limit (51000) → triggers
        fills = engine.match_pending_limits([order], Decimal("52000"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("51000")  # fills at limit price
        assert fills[0].side == OrderSide.SELL

    def test_limit_sell_triggers_at_exact_price(self):
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "51000")
        fills = engine.match_pending_limits([order], Decimal("51000"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("51000")

    def test_limit_sell_not_triggered(self):
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.SELL, "51000")
        # current_price (50000) < limit (51000) → no fill
        fills = engine.match_pending_limits([order], Decimal("50000"), TS)

        assert len(fills) == 0

    def test_limit_price_improvement(self):
        """Triggered orders fill at limit_price, not current_price."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        # Price drops well below limit → still fills at limit price
        fills = engine.match_pending_limits([order], Decimal("47000"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")

    def test_multiple_limits_batch(self):
        """Multiple limit orders can trigger simultaneously."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        orders = [
            _limit_order(OrderSide.BUY, "49000", "0.1"),
            _limit_order(OrderSide.BUY, "48000", "0.2"),
            _limit_order(OrderSide.SELL, "51000", "0.3"),  # won't trigger
        ]
        # Price at 47000: both buy limits trigger, sell does not
        fills = engine.match_pending_limits(orders, Decimal("47000"), TS)

        assert len(fills) == 2
        assert fills[0].price == Decimal("49000")
        assert fills[0].amount == Decimal("0.1")
        assert fills[1].price == Decimal("48000")
        assert fills[1].amount == Decimal("0.2")

    def test_skips_market_orders(self):
        engine = PaperMatchingEngine()
        order = _market_order(OrderSide.BUY)
        fills = engine.match_pending_limits([order], Decimal("50000"), TS)
        assert len(fills) == 0

    def test_skips_filled_orders(self):
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.BUY, "49000")
        order.status = OrderStatus.FILLED
        fills = engine.match_pending_limits([order], Decimal("48000"), TS)
        assert len(fills) == 0

    def test_skips_cancelled_orders(self):
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.BUY, "49000")
        order.status = OrderStatus.CANCELLED
        fills = engine.match_pending_limits([order], Decimal("48000"), TS)
        assert len(fills) == 0

    def test_fee_calculation(self):
        engine = PaperMatchingEngine(commission_rate=Decimal("0.002"))
        order = _limit_order(OrderSide.BUY, "49000", "0.5")
        fills = engine.match_pending_limits([order], Decimal("48000"), TS)

        assert len(fills) == 1
        expected_fee = Decimal("49000") * Decimal("0.5") * Decimal("0.002")
        assert fills[0].fee == expected_fee

    def test_empty_orders_list(self):
        engine = PaperMatchingEngine()
        fills = engine.match_pending_limits([], Decimal("50000"), TS)
        assert fills == []


class TestMatchPendingLimitsHighLow:
    """Tests for match_pending_limits() with high/low range matching."""

    def test_limit_buy_triggers_with_low(self):
        """BUY LIMIT triggers when low <= limit_price (even if close > limit)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        # close=50000 (above limit), but low=48500 (below limit) → triggers
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("51000"), low=Decimal("48500")
        )

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")

    def test_limit_buy_not_triggered_with_low(self):
        """BUY LIMIT does not trigger when low > limit_price."""
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.BUY, "49000")
        # low=49500 > limit=49000 → no fill
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("51000"), low=Decimal("49500")
        )

        assert len(fills) == 0

    def test_limit_sell_triggers_with_high(self):
        """SELL LIMIT triggers when high >= limit_price (even if close < limit)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "51000")
        # close=50000 (below limit), but high=51500 (above limit) → triggers
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("51500"), low=Decimal("49000")
        )

        assert len(fills) == 1
        assert fills[0].price == Decimal("51000")

    def test_limit_sell_not_triggered_with_high(self):
        """SELL LIMIT does not trigger when high < limit_price."""
        engine = PaperMatchingEngine()
        order = _limit_order(OrderSide.SELL, "51000")
        # high=50500 < limit=51000 → no fill
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("50500"), low=Decimal("49000")
        )

        assert len(fills) == 0

    def test_fallback_to_close_when_no_highlow(self):
        """When high/low are None, falls back to close price for triggering."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        # No high/low → uses close=48000 <= 49000 → triggers
        fills = engine.match_pending_limits([order], Decimal("48000"), TS)

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")

    def test_buy_limit_exact_low(self):
        """BUY LIMIT triggers when low == limit_price exactly."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "49000")
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("51000"), low=Decimal("49000")
        )

        assert len(fills) == 1
        assert fills[0].price == Decimal("49000")

    def test_sell_limit_exact_high(self):
        """SELL LIMIT triggers when high == limit_price exactly."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "51000")
        fills = engine.match_pending_limits(
            [order], Decimal("50000"), TS, high=Decimal("51000"), low=Decimal("49000")
        )

        assert len(fills) == 1
        assert fills[0].price == Decimal("51000")
