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

    def test_fill_market_clamps_slippage_to_bar_range_buy(self):
        """BUY slippage-adjusted price is clamped to bar high."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.01"),  # 1% slippage
        )
        order = _market_order(OrderSide.BUY)
        # Close=50000, slippage would make fill_price=50500, but high=50200
        fill = engine.fill_market_order(
            order, Decimal("50000"), TS,
            high=Decimal("50200"), low=Decimal("49800"),
        )
        assert fill is not None
        assert fill.price == Decimal("50200")  # Clamped to high

    def test_fill_market_clamps_slippage_to_bar_range_sell(self):
        """SELL slippage-adjusted price is clamped to bar low."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.01"),  # 1% slippage
        )
        order = _market_order(OrderSide.SELL)
        # Close=50000, slippage would make fill_price=49500, but low=49800
        fill = engine.fill_market_order(
            order, Decimal("50000"), TS,
            high=Decimal("50200"), low=Decimal("49800"),
        )
        assert fill is not None
        assert fill.price == Decimal("49800")  # Clamped to low

    def test_fill_market_no_clamp_without_high_low(self):
        """Without high/low, slippage is not clamped (unclosed candles)."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            slippage=Decimal("0.01"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(order, Decimal("50000"), TS)
        assert fill is not None
        # No clamping: 50000 * 1.01 = 50500
        assert fill.price == Decimal("50000") * (1 + Decimal("0.01"))

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


class TestVolumeParticipation:
    """Tests for volume participation limiting."""

    def test_market_order_capped_by_volume(self):
        """Market order fill amount should be capped by max_volume_participation * volume."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),  # 10% of volume
        )
        # Order for 1.0 BTC but bar volume is only 5.0 BTC -> max fill = 0.5
        order = _market_order(OrderSide.BUY, "1.0")
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=Decimal("5.0"))

        assert fill is not None
        assert fill.amount == Decimal("0.5")

    def test_market_order_within_volume_fills_fully(self):
        """Market order within volume limit should fill completely."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        # Order for 0.1 BTC, bar volume is 10 BTC -> max fill = 1.0 > order size
        order = _market_order(OrderSide.BUY, "0.1")
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=Decimal("10"))

        assert fill is not None
        assert fill.amount == Decimal("0.1")

    def test_limit_order_capped_by_volume(self):
        """Limit order fill amount should be capped by volume participation."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        # BUY LIMIT order for 2.0 BTC, bar volume is 5.0 -> max fill = 0.5
        order = _limit_order(OrderSide.BUY, "49000", "2.0")
        fills = engine.match_pending_limits([order], Decimal("48000"), TS, volume=Decimal("5.0"))

        assert len(fills) == 1
        assert fills[0].amount == Decimal("0.5")

    def test_no_volume_limit_when_disabled(self):
        """Without max_volume_participation, orders fill fully."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _market_order(OrderSide.BUY, "100")
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=Decimal("5"))

        assert fill is not None
        assert fill.amount == Decimal("100")  # No cap applied

    def test_no_volume_limit_when_volume_is_none(self):
        """When volume is not provided, no cap applies even with participation set."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        order = _market_order(OrderSide.BUY, "100")
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=None)

        assert fill is not None
        assert fill.amount == Decimal("100")


class TestGapOpenPriceImprovement:
    """Tests for limit order gap-open price improvement.

    When the bar opens through the limit price, the fill should occur
    at the open price (better than limit), consistent with backtest engine.
    """

    def test_buy_limit_gap_down_fills_at_open(self):
        """BUY LIMIT at 43K, bar opens at 41K → fill at 41K (price improvement)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "43000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("42000"),
            timestamp=TS,
            high=Decimal("42500"),
            low=Decimal("40500"),
            open_price=Decimal("41000"),
        )
        assert len(fills) == 1
        # Gap down: open 41K < limit 43K → fill at 41K
        assert fills[0].price == Decimal("41000")

    def test_buy_limit_no_gap_fills_at_limit(self):
        """BUY LIMIT at 43K, bar opens at 44K, dips to 42.5K → fill at 43K."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "43000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("43500"),
            timestamp=TS,
            high=Decimal("44500"),
            low=Decimal("42500"),
            open_price=Decimal("44000"),
        )
        assert len(fills) == 1
        # No gap: open 44K > limit 43K → fill at limit 43K
        assert fills[0].price == Decimal("43000")

    def test_sell_limit_gap_up_fills_at_open(self):
        """SELL LIMIT at 47K, bar opens at 49K → fill at 49K (price improvement)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "47000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("48000"),
            timestamp=TS,
            high=Decimal("49500"),
            low=Decimal("47500"),
            open_price=Decimal("49000"),
        )
        assert len(fills) == 1
        # Gap up: open 49K > limit 47K → fill at 49K
        assert fills[0].price == Decimal("49000")

    def test_sell_limit_no_gap_fills_at_limit(self):
        """SELL LIMIT at 47K, bar opens at 46K, rises to 47.5K → fill at 47K."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.SELL, "47000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("46500"),
            timestamp=TS,
            high=Decimal("47500"),
            low=Decimal("45500"),
            open_price=Decimal("46000"),
        )
        assert len(fills) == 1
        # No gap: open 46K < limit 47K → fill at limit 47K
        assert fills[0].price == Decimal("47000")

    def test_no_open_price_falls_back_to_limit(self):
        """Without open_price (unclosed candle), fills at limit price."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _limit_order(OrderSide.BUY, "43000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("42000"),
            timestamp=TS,
            high=Decimal("43500"),
            low=Decimal("41500"),
            # No open_price
        )
        assert len(fills) == 1
        assert fills[0].price == Decimal("43000")


class TestZeroVolumeBarBlocking:
    """Tests that zero-volume bars block fills when volume participation is set."""

    def test_market_order_blocked_on_zero_volume(self):
        """Market order should not fill on a zero-volume bar."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=Decimal("0"))

        assert fill is None

    def test_limit_order_blocked_on_zero_volume(self):
        """Limit order should not fill on a zero-volume bar."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        order = _limit_order(OrderSide.BUY, "50000")
        fills = engine.match_pending_limits(
            [order],
            current_price=Decimal("49000"),
            timestamp=TS,
            high=Decimal("50500"),
            low=Decimal("48500"),
            volume=Decimal("0"),
        )

        assert len(fills) == 0

    def test_market_order_fills_without_participation_limit(self):
        """Without max_volume_participation, zero-volume doesn't block fills."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(order, Decimal("50000"), TS, volume=Decimal("0"))

        assert fill is not None
        assert fill.amount == Decimal("0.1")


class TestSharedVolumeBudget:
    """Tests for shared volume budget across market and limit orders."""

    def test_two_limits_share_budget(self):
        """Two limit orders on same candle share the volume budget."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        # Budget = 100 * 0.1 = 10 BTC
        budget = engine.compute_volume_budget(Decimal("100"))
        assert budget == Decimal("10")

        # Two buy limits, each wanting 8 BTC
        order1 = _limit_order(OrderSide.BUY, "50000", "8")
        order2 = _limit_order(OrderSide.BUY, "49000", "8")

        fills = engine.match_pending_limits(
            [order1, order2],
            Decimal("48000"),
            TS,
            volume_budget=budget,
        )

        # First order gets 8 BTC, second gets only 2 BTC (remaining budget)
        assert len(fills) == 2
        assert fills[0].amount == Decimal("8")
        assert fills[1].amount == Decimal("2")
        total_filled = sum(f.amount for f in fills)
        assert total_filled == Decimal("10")  # Exactly the budget

    def test_market_and_limit_share_budget(self):
        """Market order consumes from budget, leaving less for limit orders."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        # Budget = 50 * 0.1 = 5 BTC
        budget = engine.compute_volume_budget(Decimal("50"))

        # Market order takes 3 BTC from budget
        market = _market_order(OrderSide.BUY, "3")
        fill = engine.fill_market_order(market, Decimal("50000"), TS, volume_budget=budget)
        assert fill is not None
        assert fill.amount == Decimal("3")

        # Remaining budget = 5 - 3 = 2 BTC
        remaining = budget - fill.amount

        # Limit order wants 4 BTC but only 2 BTC budget remains
        limit = _limit_order(OrderSide.BUY, "50000", "4")
        fills = engine.match_pending_limits(
            [limit],
            Decimal("49000"),
            TS,
            volume_budget=remaining,
        )
        assert len(fills) == 1
        assert fills[0].amount == Decimal("2")

    def test_no_participation_limit_no_budget(self):
        """Without max_volume_participation, compute_volume_budget returns None."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"))
        assert engine.compute_volume_budget(Decimal("100")) is None

    def test_zero_volume_gives_zero_budget(self):
        """Zero volume produces zero budget, blocking all fills."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"),
            max_volume_participation=Decimal("0.1"),
        )
        budget = engine.compute_volume_budget(Decimal("0"))
        assert budget == Decimal("0")

        order = _limit_order(OrderSide.BUY, "50000", "1")
        fills = engine.match_pending_limits([order], Decimal("49000"), TS, volume_budget=budget)
        assert len(fills) == 0


def _stop_order(side: OrderSide, stop_price: str, amount: str = "0.1") -> SimulatedOrder:
    return SimulatedOrder.create(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.STOP,
        amount=Decimal(amount),
        stop_price=Decimal(stop_price),
    )


def _stop_limit_order(
    side: OrderSide, stop_price: str, price: str, amount: str = "0.1"
) -> SimulatedOrder:
    return SimulatedOrder.create(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.STOP_LIMIT,
        amount=Decimal(amount),
        stop_price=Decimal(stop_price),
        price=Decimal(price),
    )


class TestStopOrderPaper:
    """Tests for stop order tick-level matching."""

    def test_buy_stop_triggers_with_high_low(self):
        """Buy STOP triggers when high >= stop_price (closed candle)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.BUY, "43000")
        fill = engine.fill_stop_order(
            order, Decimal("42500"), TS, high=Decimal("43500"), low=Decimal("41000")
        )
        assert fill is not None
        assert fill.price == Decimal("42500")  # current_price, no slippage

    def test_buy_stop_does_not_trigger_with_high_low(self):
        """Buy STOP does not trigger when high < stop_price."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.BUY, "45000")
        fill = engine.fill_stop_order(
            order, Decimal("42500"), TS, high=Decimal("44000"), low=Decimal("41000")
        )
        assert fill is None

    def test_sell_stop_triggers_with_high_low(self):
        """Sell STOP triggers when low <= stop_price (closed candle)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.SELL, "41500")
        fill = engine.fill_stop_order(
            order, Decimal("41200"), TS, high=Decimal("43000"), low=Decimal("41000")
        )
        assert fill is not None
        assert fill.price == Decimal("41200")

    def test_sell_stop_does_not_trigger_with_high_low(self):
        """Sell STOP does not trigger when low > stop_price."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.SELL, "40000")
        fill = engine.fill_stop_order(
            order, Decimal("41200"), TS, high=Decimal("43000"), low=Decimal("41000")
        )
        assert fill is None

    def test_buy_stop_triggers_on_current_price_no_high_low(self):
        """Buy STOP triggers using current_price when no high/low (unclosed candle)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.BUY, "43000")
        fill = engine.fill_stop_order(order, Decimal("43500"), TS)
        assert fill is not None

    def test_buy_stop_does_not_trigger_on_current_price(self):
        """Buy STOP does not trigger when current_price < stop_price (unclosed)."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.BUY, "43000")
        fill = engine.fill_stop_order(order, Decimal("42500"), TS)
        assert fill is None

    def test_stop_order_with_slippage(self):
        """Stop order applies slippage to fill price."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.001")
        )
        order = _stop_order(OrderSide.BUY, "43000")
        fill = engine.fill_stop_order(
            order, Decimal("43000"), TS, high=Decimal("44000"), low=Decimal("42000")
        )
        assert fill is not None
        expected = Decimal("43000") * (1 + Decimal("0.001"))
        assert fill.price == expected

    def test_stop_order_respects_volume_budget(self):
        """Stop order fill amount is capped by volume budget."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_order(OrderSide.BUY, "43000", amount="10")
        fill = engine.fill_stop_order(
            order, Decimal("43500"), TS,
            high=Decimal("44000"), low=Decimal("42000"),
            volume_budget=Decimal("5"),
        )
        assert fill is not None
        assert fill.amount == Decimal("5")


class TestStopLimitOrderPaper:
    """Tests for stop-limit order tick-level matching."""

    def test_stop_limit_triggers_and_fills(self):
        """STOP_LIMIT triggers and limit is reachable → fills."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_limit_order(OrderSide.BUY, "43000", "43500")
        fills = engine.match_pending_stop_limits(
            [order], Decimal("43200"), TS,
            high=Decimal("44000"), low=Decimal("41000"),
        )
        assert len(fills) == 1
        assert order.triggered is True
        # Buy limit fill: limit_price=43500, low=41000 <= 43500 → can fill
        assert fills[0].price == Decimal("43500")

    def test_stop_limit_triggers_but_limit_not_reachable(self):
        """STOP_LIMIT triggers but limit not reachable → triggered=True, no fill."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        # Buy stop-limit: stop at 43000, limit at 40000 (too low to fill)
        order = _stop_limit_order(OrderSide.BUY, "43000", "40000")
        fills = engine.match_pending_stop_limits(
            [order], Decimal("43200"), TS,
            high=Decimal("44000"), low=Decimal("41000"),
        )
        assert len(fills) == 0
        assert order.triggered is True

    def test_stop_limit_does_not_trigger(self):
        """STOP_LIMIT does not trigger → triggered=False, no fill."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_limit_order(OrderSide.BUY, "45000", "45500")
        fills = engine.match_pending_stop_limits(
            [order], Decimal("43200"), TS,
            high=Decimal("44000"), low=Decimal("41000"),
        )
        assert len(fills) == 0
        assert order.triggered is False

    def test_sell_stop_limit_triggers_and_fills(self):
        """Sell STOP_LIMIT triggers and fills correctly."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_limit_order(OrderSide.SELL, "41500", "41000")
        fills = engine.match_pending_stop_limits(
            [order], Decimal("41200"), TS,
            high=Decimal("43000"), low=Decimal("40500"),
        )
        assert len(fills) == 1
        assert order.triggered is True
        # Sell limit fill: limit_price=41000, high=43000 >= 41000 → can fill
        assert fills[0].price == Decimal("41000")

    def test_already_triggered_stop_limit_fills_as_limit(self):
        """Already-triggered STOP_LIMIT fills as a limit order."""
        engine = PaperMatchingEngine(commission_rate=Decimal("0.001"), slippage=Decimal("0"))
        order = _stop_limit_order(OrderSide.BUY, "43000", "42000")
        order.triggered = True  # Pre-triggered
        fills = engine.match_pending_stop_limits(
            [order], Decimal("41500"), TS,
            high=Decimal("42500"), low=Decimal("41000"),
        )
        assert len(fills) == 1
        assert fills[0].price == Decimal("42000")


class TestSpreadSimulation:
    """Tests for bid/ask spread-based fill pricing."""

    def test_market_buy_uses_ask_price(self):
        """BUY market order fills at ask price when available."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS, ask=Decimal("42050"),
        )
        assert fill is not None
        # Should use ask price, NOT close + slippage
        assert fill.price == Decimal("42050")

    def test_market_sell_uses_bid_price(self):
        """SELL market order fills at bid price when available."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _market_order(OrderSide.SELL)
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS, bid=Decimal("41950"),
        )
        assert fill is not None
        # Should use bid price, NOT close - slippage
        assert fill.price == Decimal("41950")

    def test_market_buy_fallback_to_slippage(self):
        """BUY market order falls back to slippage when no ask available."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _market_order(OrderSide.BUY)
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS,
        )
        assert fill is not None
        # No ask → close * (1 + slippage) = 42000 * 1.005 = 42210
        assert fill.price == Decimal("42000") * (1 + Decimal("0.005"))

    def test_market_sell_fallback_to_slippage(self):
        """SELL market order falls back to slippage when no bid available."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _market_order(OrderSide.SELL)
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS,
        )
        assert fill is not None
        # No bid → close * (1 - slippage) = 42000 * 0.995 = 41790
        assert fill.price == Decimal("42000") * (1 - Decimal("0.005"))

    def test_stop_order_buy_uses_ask_on_trigger(self):
        """STOP BUY uses ask price after triggering."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _stop_order(OrderSide.BUY, "43000")
        fill = engine.fill_stop_order(
            order, Decimal("43200"), TS,
            high=Decimal("44000"), low=Decimal("42000"),
            ask=Decimal("43250"),
        )
        assert fill is not None
        assert fill.price == Decimal("43250")

    def test_stop_order_sell_uses_bid_on_trigger(self):
        """STOP SELL uses bid price after triggering."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0.005"),
        )
        order = _stop_order(OrderSide.SELL, "41000")
        fill = engine.fill_stop_order(
            order, Decimal("40800"), TS,
            high=Decimal("42000"), low=Decimal("40500"),
            bid=Decimal("40750"),
        )
        assert fill is not None
        assert fill.price == Decimal("40750")

    def test_spread_with_bar_clamp(self):
        """Spread price is clamped to bar range [low, high]."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0"),
        )
        order = _market_order(OrderSide.BUY)
        # Ask is above candle high — should be clamped to high
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS,
            high=Decimal("42100"), low=Decimal("41900"),
            ask=Decimal("42200"),
        )
        assert fill is not None
        assert fill.price == Decimal("42100")  # Clamped to high

    def test_spread_with_volume_budget(self):
        """Spread simulation respects volume participation budget."""
        engine = PaperMatchingEngine(
            commission_rate=Decimal("0.001"), slippage=Decimal("0"),
            max_volume_participation=Decimal("0.1"),
        )
        order = _market_order(OrderSide.BUY, amount="10")
        fill = engine.fill_market_order(
            order, Decimal("42000"), TS,
            volume_budget=Decimal("5"),
            ask=Decimal("42050"),
        )
        assert fill is not None
        assert fill.price == Decimal("42050")
        assert fill.amount == Decimal("5")  # Capped by volume budget
