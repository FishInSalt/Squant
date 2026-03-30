"""Tests for completed order count update during reconciliation.

After _reconcile_orders removes completed orders from _live_orders,
the context's completed_orders_count should increase so the UI
shows the correct total. Also verifies that _build_state_snapshot
includes _restored_completed_orders_count after resume.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from squant.infra.exchange.types import OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.services.live_trading import LiveTradingService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return LiveTradingService(mock_session)


class TestReconcileOrderCount:
    """Completed order count should update after reconciliation."""

    async def test_count_incremented_for_removed_orders(self, service):
        """Orders removed from _live_orders should increment completed count."""
        engine = MagicMock()
        engine._pending_order_events = []

        # Context with restored count of 3 (from previous session state)
        ctx = MagicMock()
        ctx._restored_completed_orders_count = 3
        ctx._completed_orders = []
        engine._context = ctx
        engine.context = ctx

        # Live order that is now filled on exchange (not in open orders)
        live_order = MagicMock()
        live_order.internal_id = "int-1"
        live_order.exchange_order_id = "ex-1"
        live_order.symbol = "BTC/USDT"
        live_order.side = OrderSide.BUY
        live_order.filled_amount = Decimal("0.1")
        live_order.avg_fill_price = Decimal("50000")
        live_order.fee = Decimal("5")
        live_order.fee_currency = "USDT"
        live_order.status = OrderStatus.SUBMITTED

        engine._live_orders = {"int-1": live_order}
        engine._exchange_order_map = {"ex-1": "int-1"}

        # Exchange shows order filled (not in open orders)
        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(return_value=[])

        final_state = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=Decimal("50000"),
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
            fee=Decimal("5"),
        )
        adapter.get_order = AsyncMock(return_value=final_state)

        # _record_fill mock (no-op, just for fill delta tracking)
        engine._record_fill = MagicMock()

        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")

        assert report["orders_reconciled"] == 1
        # Order should be removed from live_orders
        assert "int-1" not in engine._live_orders
        # Completed count should be incremented
        assert ctx._restored_completed_orders_count == 4

    async def test_count_not_incremented_for_still_open_orders(self, service):
        """Orders still open on exchange should NOT increment completed count."""
        engine = MagicMock()
        engine._pending_order_events = []

        ctx = MagicMock()
        ctx._restored_completed_orders_count = 3
        ctx._completed_orders = []
        engine._context = ctx
        engine.context = ctx

        live_order = MagicMock()
        live_order.internal_id = "int-1"
        live_order.exchange_order_id = "ex-1"
        live_order.symbol = "BTC/USDT"
        live_order.side = OrderSide.BUY
        live_order.filled_amount = Decimal("0")
        live_order.avg_fill_price = None
        live_order.fee = Decimal("0")
        live_order.fee_currency = "USDT"
        live_order.status = OrderStatus.SUBMITTED

        engine._live_orders = {"int-1": live_order}
        engine._exchange_order_map = {"ex-1": "int-1"}

        # Order still open on exchange
        exchange_order = OrderResponse(
            order_id="ex-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            price=Decimal("48000"),
            amount=Decimal("0.1"),
            filled=Decimal("0"),
            avg_price=None,
        )
        adapter = AsyncMock()
        adapter.get_open_orders = AsyncMock(return_value=[exchange_order])

        engine._record_fill = MagicMock()

        await service._reconcile_orders(engine, adapter, "BTC/USDT")

        # Order still tracked, count unchanged
        assert "int-1" in engine._live_orders
        assert ctx._restored_completed_orders_count == 3


class TestStateSnapshotCount:
    """_build_state_snapshot should include restored count."""

    def test_includes_restored_count(self):
        """Verify the source code uses _restored_completed_orders_count in state snapshot.

        Rather than constructing a full LiveTradingEngine (which needs many
        dependencies), we verify the fix by checking the context snapshot
        method which uses the same pattern.
        """
        from squant.engine.backtest.context import BacktestContext

        ctx = BacktestContext(
            initial_capital=Decimal("10000"),
            commission_rate=Decimal("0"),
            slippage=Decimal("0"),
        )
        # Simulate restore: set restored count
        ctx._restored_completed_orders_count = 5

        snapshot = ctx.build_result_snapshot()
        # Should be restored_count + len(_completed_orders) = 5 + 0 = 5
        assert snapshot["completed_orders_count"] == 5

    def test_source_code_uses_restored_count_in_state_snapshot(self):
        """Verify engine state snapshot includes restored count (source check)."""
        import inspect

        from squant.engine.live.engine import LiveTradingEngine

        source = inspect.getsource(LiveTradingEngine._build_state_snapshot)
        assert "_restored_completed_orders_count" in source
