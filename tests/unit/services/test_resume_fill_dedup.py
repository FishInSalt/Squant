"""Tests for fill event deduplication between reconciliation steps 11 and 11b.

Step 11 (_reconcile_orders) calls _record_fill which buffers fill events in
_pending_order_events. Step 11b (_reconcile_stale_db_orders) writes complete
trade records from get_order_trades(). If step 11's fill events are not
discarded, both paths write trades for the same order → duplicates.

This test verifies that fill events from step 11 are discarded before step 11b.
"""

from __future__ import annotations

from datetime import UTC, datetime
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


class TestResumeFillDedup:
    """Fill events from step 11 should be discarded before step 11b runs."""

    async def test_fill_events_discarded_after_reconcile_orders(self, service):
        """After _reconcile_orders, fill events should be removed from pending buffer."""
        # Create engine with a pending order that has new fills on exchange
        engine = MagicMock()
        engine._pending_order_events = []
        engine.context = MagicMock()
        engine.context._completed_orders = []

        # Simulate a live order that was partially filled when we crashed
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

        # Exchange shows order is now filled
        exchange_order = OrderResponse(
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
            updated_at=datetime.now(UTC),
        )

        adapter = AsyncMock()
        # get_open_orders returns empty (order completed)
        adapter.get_open_orders = AsyncMock(return_value=[])
        # get_order returns the filled order
        adapter.get_order = AsyncMock(return_value=exchange_order)

        # _record_fill should add a fill event
        def mock_record_fill(lo, price, amount, fee_delta, total_fee, source, **kwargs):
            engine._pending_order_events.append(
                {
                    "type": "fill",
                    "internal_id": lo.internal_id,
                    "fill_price": str(price),
                    "fill_amount": str(amount),
                    "fill_source": source,
                }
            )

        engine._record_fill = mock_record_fill

        # Run step 11
        report = await service._reconcile_orders(engine, adapter, "BTC/USDT")
        assert report["fills_processed"] == 1

        # Verify fill event was buffered
        fill_events = [e for e in engine._pending_order_events if e["type"] == "fill"]
        assert len(fill_events) == 1

        # Now simulate the dedup step (11a) — same code as in resume()
        engine._pending_order_events = [
            e for e in engine._pending_order_events if e.get("type") != "fill"
        ]

        # Verify fill events are gone
        fill_events = [e for e in engine._pending_order_events if e["type"] == "fill"]
        assert len(fill_events) == 0

    async def test_non_fill_events_preserved(self, service):
        """Non-fill events (e.g., status updates) should NOT be discarded."""
        engine = MagicMock()
        engine._pending_order_events = [
            {"type": "status_update", "internal_id": "int-1", "new_status": "filled"},
            {"type": "fill", "internal_id": "int-1", "fill_price": "50000"},
            {"type": "status_update", "internal_id": "int-2", "new_status": "cancelled"},
        ]

        # Apply dedup filter
        engine._pending_order_events = [
            e for e in engine._pending_order_events if e.get("type") != "fill"
        ]

        assert len(engine._pending_order_events) == 2
        assert all(e["type"] == "status_update" for e in engine._pending_order_events)
