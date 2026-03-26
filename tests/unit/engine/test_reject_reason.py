"""Tests for order rejection reason and REJECTED status."""

from decimal import Decimal

from squant.engine.backtest.types import OrderStatus, SimulatedOrder


class TestOrderStatusRejected:
    def test_rejected_value_exists(self):
        assert OrderStatus.REJECTED == "rejected"

    def test_rejected_is_distinct_from_cancelled(self):
        assert OrderStatus.REJECTED != OrderStatus.CANCELLED


class TestSimulatedOrderRejectReason:
    def test_default_reject_reason_is_none(self):
        order = SimulatedOrder(
            id="test-1", symbol="BTC/USDT",
            side="buy", type="market", amount=Decimal("0.01"),
        )
        assert order.reject_reason is None

    def test_reject_reason_can_be_set(self):
        order = SimulatedOrder(
            id="test-1", symbol="BTC/USDT",
            side="buy", type="market", amount=Decimal("0.01"),
        )
        order.reject_reason = "insufficient_funds"
        assert order.reject_reason == "insufficient_funds"

    def test_reject_reason_with_rejected_status(self):
        order = SimulatedOrder(
            id="test-1", symbol="BTC/USDT",
            side="buy", type="market", amount=Decimal("0.01"),
            status=OrderStatus.REJECTED,
            reject_reason="exchange_unavailable",
        )
        assert order.status == OrderStatus.REJECTED
        assert order.reject_reason == "exchange_unavailable"

    def test_is_complete_includes_rejected(self):
        order = SimulatedOrder(
            id="test-1", symbol="BTC/USDT",
            side="buy", type="market", amount=Decimal("0.01"),
            status=OrderStatus.REJECTED,
        )
        assert order.is_complete is True
