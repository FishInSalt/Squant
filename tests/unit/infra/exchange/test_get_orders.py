# tests/unit/infra/exchange/test_get_orders.py
"""Tests for CCXTRestAdapter.get_orders() with pagination."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.exchange.types import OrderResponse


def _make_raw_order(order_id: str, status: str = "closed", timestamp: int = 1711000000000):
    """Helper to create a raw CCXT order dict."""
    return {
        "id": order_id,
        "clientOrderId": None,
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "status": status,
        "price": 60000.0,
        "amount": 0.1,
        "filled": 0.1 if status == "closed" else 0.0,
        "average": 60000.0 if status == "closed" else None,
        "fee": {"cost": 0.06, "currency": "USDT"},
        "timestamp": timestamp,
        "lastTradeTimestamp": timestamp,
    }


class TestGetOrders:
    """Tests for the get_orders adapter method."""

    @pytest.fixture
    def adapter(self):
        """Create a connected adapter with mocked exchange."""
        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)
        adapter._exchange = MagicMock()
        adapter._exchange.fetch_closed_orders = AsyncMock(return_value=[])
        adapter._exchange.fetch_open_orders = AsyncMock(return_value=[])
        adapter._exchange_id = "okx"
        adapter._credentials = MagicMock()
        adapter._connected = True
        return adapter

    async def test_combines_open_and_closed(self, adapter):
        """Returns both open and closed orders."""
        closed_order = _make_raw_order("c001", status="closed")
        open_order = _make_raw_order("o001", status="open")
        open_order["filled"] = 0.0
        open_order["average"] = None

        adapter._exchange.fetch_closed_orders.return_value = [closed_order]
        adapter._exchange.fetch_open_orders.return_value = [open_order]

        result = await adapter.get_orders("BTC/USDT")

        assert len(result) == 2
        assert all(isinstance(r, OrderResponse) for r in result)
        order_ids = {r.order_id for r in result}
        assert order_ids == {"c001", "o001"}

    async def test_with_since_parameter(self, adapter):
        """Passes since as millisecond timestamp to fetch calls."""
        since_dt = datetime(2024, 3, 20, 12, 0, 0, tzinfo=UTC)
        since_ms = int(since_dt.timestamp() * 1000)

        adapter._exchange.fetch_closed_orders.return_value = []
        adapter._exchange.fetch_open_orders.return_value = []

        await adapter.get_orders("BTC/USDT", since=since_dt)

        # Verify closed orders called with since_ms
        adapter._exchange.fetch_closed_orders.assert_called_once_with(
            "BTC/USDT", since=since_ms, limit=100
        )
        # Verify open orders called with since_ms
        adapter._exchange.fetch_open_orders.assert_called_once_with(
            "BTC/USDT", since=since_ms
        )

    async def test_pagination_loops_until_short_page(self, adapter):
        """When first page returns 100 orders, fetches next page; stops at short page."""
        # Page 1: 100 orders
        page1 = [_make_raw_order(f"ord-{i:03d}", timestamp=1711000000000 + i * 1000) for i in range(100)]
        # Page 2: 30 orders (short page -> stop)
        page2 = [_make_raw_order(f"ord-{i:03d}", timestamp=1711000100000 + i * 1000) for i in range(100, 130)]

        adapter._exchange.fetch_closed_orders.side_effect = [page1, page2]
        adapter._exchange.fetch_open_orders.return_value = []

        result = await adapter.get_orders("BTC/USDT")

        assert len(result) == 130
        assert adapter._exchange.fetch_closed_orders.call_count == 2

        # Second call should use last timestamp + 1 as cursor
        last_ts_page1 = page1[-1]["timestamp"]
        second_call = adapter._exchange.fetch_closed_orders.call_args_list[1]
        assert second_call == call("BTC/USDT", since=last_ts_page1 + 1, limit=100)

    async def test_deduplicates_by_order_id(self, adapter):
        """Duplicate orders from pagination overlap are deduplicated."""
        # Same order appears in both pages (overlap scenario)
        order_a = _make_raw_order("dup-001", timestamp=1711000000000)
        order_b = _make_raw_order("dup-001", timestamp=1711000000000)  # duplicate
        order_c = _make_raw_order("unique-002", timestamp=1711000001000)

        # First page: full page of 1 order (simulate with short page for simplicity)
        # We test dedup between closed and open orders
        adapter._exchange.fetch_closed_orders.return_value = [order_a, order_c]
        # Same order also appears as open (edge case)
        adapter._exchange.fetch_open_orders.return_value = [order_b]

        result = await adapter.get_orders("BTC/USDT")

        order_ids = [r.order_id for r in result]
        assert len(order_ids) == 2
        assert "dup-001" in order_ids
        assert "unique-002" in order_ids

    async def test_no_credentials_raises(self, adapter):
        """Should raise ExchangeAuthenticationError when no credentials."""
        adapter._credentials = None

        with pytest.raises(ExchangeAuthenticationError):
            await adapter.get_orders("BTC/USDT")

    async def test_no_exchange_raises(self, adapter):
        """Should raise when exchange is not connected."""
        adapter._exchange = None

        with pytest.raises(ExchangeConnectionError):
            await adapter.get_orders("BTC/USDT")

    async def test_empty_results(self, adapter):
        """Returns empty list when no orders exist."""
        adapter._exchange.fetch_closed_orders.return_value = []
        adapter._exchange.fetch_open_orders.return_value = []

        result = await adapter.get_orders("BTC/USDT")

        assert result == []

    async def test_without_since_parameter(self, adapter):
        """When since is None, passes None to fetch calls."""
        adapter._exchange.fetch_closed_orders.return_value = []
        adapter._exchange.fetch_open_orders.return_value = []

        await adapter.get_orders("BTC/USDT")

        adapter._exchange.fetch_closed_orders.assert_called_once_with(
            "BTC/USDT", since=None, limit=100
        )
        adapter._exchange.fetch_open_orders.assert_called_once_with(
            "BTC/USDT", since=None
        )

    async def test_until_filters_closed_orders(self, adapter):
        """Closed orders after until timestamp are excluded."""
        t1 = 1711000000000  # within range
        t2 = 1711000001000  # within range
        t3 = 1711000010000  # beyond until
        order1 = _make_raw_order("o1", timestamp=t1)
        order2 = _make_raw_order("o2", timestamp=t2)
        order3 = _make_raw_order("o3", timestamp=t3)  # should be filtered

        adapter._exchange.fetch_closed_orders.return_value = [order1, order2, order3]
        adapter._exchange.fetch_open_orders.return_value = []

        # until is between t2 and t3
        until_dt = datetime(2024, 3, 21, 14, 46, 42, tzinfo=UTC)
        until_ms = int(until_dt.timestamp() * 1000)
        # Make t3 clearly after until
        order3["timestamp"] = until_ms + 5000

        result = await adapter.get_orders("BTC/USDT", until=until_dt)

        order_ids = {r.order_id for r in result}
        assert "o1" in order_ids
        assert "o2" in order_ids
        assert "o3" not in order_ids

    async def test_until_filters_open_orders(self, adapter):
        """Open orders after until timestamp are excluded."""
        adapter._exchange.fetch_closed_orders.return_value = []

        until_dt = datetime(2024, 3, 21, 12, 0, 0, tzinfo=UTC)
        until_ms = int(until_dt.timestamp() * 1000)

        open_in_range = _make_raw_order("o1", status="open", timestamp=until_ms - 1000)
        open_out_range = _make_raw_order("o2", status="open", timestamp=until_ms + 1000)

        adapter._exchange.fetch_open_orders.return_value = [open_in_range, open_out_range]

        result = await adapter.get_orders("BTC/USDT", until=until_dt)

        order_ids = {r.order_id for r in result}
        assert "o1" in order_ids
        assert "o2" not in order_ids

    async def test_until_stops_pagination_early(self, adapter):
        """When until boundary is hit during pagination, stops fetching more pages."""
        until_dt = datetime(2024, 3, 21, 12, 0, 0, tzinfo=UTC)
        until_ms = int(until_dt.timestamp() * 1000)

        # Full page of 100 orders, last one is beyond until
        page1 = [
            _make_raw_order(f"ord-{i:03d}", timestamp=until_ms - (100 - i) * 1000)
            for i in range(99)
        ]
        # 100th order is beyond until
        page1.append(_make_raw_order("ord-099", timestamp=until_ms + 1000))

        adapter._exchange.fetch_closed_orders.return_value = page1
        adapter._exchange.fetch_open_orders.return_value = []

        result = await adapter.get_orders("BTC/USDT", until=until_dt)

        # Should have 99 orders (the 100th is beyond until)
        assert len(result) == 99
        # Should NOT fetch a second page since we hit the until boundary
        assert adapter._exchange.fetch_closed_orders.call_count == 1
