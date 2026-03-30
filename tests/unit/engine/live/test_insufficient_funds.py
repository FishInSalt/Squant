"""Tests for insufficient funds notification in _submit_order (B2).

Verifies that when an order is rejected due to insufficient funds
(InvalidOrderError with field="amount"), a notification is fired
with the appropriate message depending on order side.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.engine.backtest.types import SimulatedOrder
from squant.engine.live.engine import LiveTradingEngine
from squant.infra.exchange.exceptions import InvalidOrderError
from squant.models.enums import OrderSide, OrderStatus, OrderType


@pytest.fixture
def engine():
    """Create a minimal LiveTradingEngine via __new__ for _submit_order testing."""
    engine = LiveTradingEngine.__new__(LiveTradingEngine)
    engine._run_id = uuid4()
    engine._symbol = "BTC/USDT"
    engine._is_running = True
    engine._adapter = AsyncMock()
    engine._live_orders = {}
    engine._exchange_order_map = {}
    engine._timed_out_orders = {}
    engine._pending_order_events = []

    # Context mock with required attributes
    engine._context = MagicMock()
    engine._context._pending_orders = []
    engine._context._completed_orders = deque()
    engine._context._total_completed_added = 0

    return engine


def _make_order(side: OrderSide = OrderSide.BUY) -> SimulatedOrder:
    """Create a SimulatedOrder for testing."""
    return SimulatedOrder(
        id=str(uuid4()).replace("-", "")[:16],
        symbol="BTC/USDT",
        side=side,
        type=OrderType.MARKET,
        amount=Decimal("0.01"),
    )


class TestInsufficientFundsNotification:
    """Tests for insufficient funds detection and notification in _submit_order."""

    @pytest.mark.asyncio
    async def test_buy_insufficient_funds_fires_notification(self, engine):
        """BUY order rejected with InvalidOrderError(field='amount') should
        fire notification with title '余额不足'."""
        order = _make_order(OrderSide.BUY)
        engine._context._pending_orders = [order]

        # Adapter raises InvalidOrderError with field="amount"
        engine._adapter.place_order = AsyncMock(
            side_effect=InvalidOrderError(
                message="Insufficient balance", exchange="okx", field="amount"
            )
        )

        with patch("squant.engine.live.engine._fire_notification") as mock_notify:
            await engine._submit_order(order)

            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            assert kwargs["level"] == "warning"
            assert kwargs["event_type"] == "insufficient_funds"
            assert kwargs["title"] == "余额不足"
            assert "买入失败" in kwargs["message"]
            assert "BTC/USDT" in kwargs["message"]

        # Order should still be REJECTED
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_sell_insufficient_funds_fires_notification(self, engine):
        """SELL order rejected with InvalidOrderError(field='amount') should
        fire notification with title '持仓不足'."""
        order = _make_order(OrderSide.SELL)
        engine._context._pending_orders = [order]

        engine._adapter.place_order = AsyncMock(
            side_effect=InvalidOrderError(
                message="Insufficient balance", exchange="okx", field="amount"
            )
        )

        with patch("squant.engine.live.engine._fire_notification") as mock_notify:
            await engine._submit_order(order)

            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            assert kwargs["title"] == "持仓不足"
            assert "卖出失败" in kwargs["message"]
            assert "BTC/USDT" in kwargs["message"]

        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_other_invalid_order_no_notification(self, engine):
        """InvalidOrderError with field='price' should NOT fire notification."""
        order = _make_order(OrderSide.BUY)
        engine._context._pending_orders = [order]

        engine._adapter.place_order = AsyncMock(
            side_effect=InvalidOrderError(message="Invalid price", exchange="okx", field="price")
        )

        with patch("squant.engine.live.engine._fire_notification") as mock_notify:
            await engine._submit_order(order)

            mock_notify.assert_not_called()

        # Order should still be REJECTED (standard rejection logic)
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_generic_exception_no_notification(self, engine):
        """Regular Exception should NOT fire insufficient funds notification."""
        order = _make_order(OrderSide.BUY)
        engine._context._pending_orders = [order]

        engine._adapter.place_order = AsyncMock(side_effect=RuntimeError("Something went wrong"))

        with patch("squant.engine.live.engine._fire_notification") as mock_notify:
            await engine._submit_order(order)

            mock_notify.assert_not_called()

        # Order should still be REJECTED
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_insufficient_funds_order_moved_to_completed(self, engine):
        """Insufficient funds order should be moved to completed orders."""
        order = _make_order(OrderSide.BUY)
        engine._context._pending_orders = [order]

        engine._adapter.place_order = AsyncMock(
            side_effect=InvalidOrderError(
                message="Insufficient balance", exchange="okx", field="amount"
            )
        )

        with patch("squant.engine.live.engine._fire_notification"):
            await engine._submit_order(order)

        # Order moved to completed
        assert order in engine._context._completed_orders
        assert order not in engine._context._pending_orders
