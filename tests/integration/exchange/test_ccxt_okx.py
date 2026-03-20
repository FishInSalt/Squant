"""Layer 1 exchange connectivity integration tests for OKX demo trading.

These tests verify that CCXTRestAdapter correctly communicates with the OKX
demo (sandbox) environment.  They exercise connection, balance queries,
ticker retrieval, and the full order lifecycle (place / query / cancel / fill).

Requirements:
    - OKX demo trading credentials in environment (OKX_API_KEY, OKX_API_SECRET,
      OKX_PASSPHRASE)
    - Network access to OKX sandbox API

Run:
    uv run pytest tests/integration/exchange/test_ccxt_okx.py -v

All tests are marked with ``@pytest.mark.integration`` (auto-applied by
the integration conftest) and ``@pytest.mark.okx_private`` so they can be
selected or excluded easily.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest

from squant.infra.exchange.ccxt import CCXTRestAdapter
from squant.infra.exchange.types import (
    AccountBalance,
    CancelOrderRequest,
    OrderRequest,
    OrderResponse,
    Ticker,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType

from .conftest import requires_okx_credentials

# All tests in this module require OKX demo credentials
pytestmark = [pytest.mark.integration, pytest.mark.okx_private, requires_okx_credentials]

# ---------------------------------------------------------------------------
# Symbol used across tests — must exist on OKX demo/sandbox
# ---------------------------------------------------------------------------
TEST_SYMBOL = "BTC/USDT"

# Small order amount for market order tests (0.0001 BTC ~ a few dollars)
SMALL_ORDER_AMOUNT = Decimal("0.0001")

# Price far below market so limit orders stay open and never fill
LIMIT_BUY_PRICE_FAR_BELOW = Decimal("100.00")


# ===========================================================================
# Connection & balance
# ===========================================================================


class TestConnectionAndBalance:
    """Verify we can connect to OKX demo and query account balance."""

    async def test_connection_and_balance(self, okx_adapter: CCXTRestAdapter) -> None:
        """Connect to OKX demo, query balance, verify AccountBalance returned."""
        balance = await okx_adapter.get_balance()

        # Must return the correct Pydantic model
        assert isinstance(balance, AccountBalance)
        assert balance.exchange == "okx"

        # Demo accounts usually have pre-funded balances; at minimum the list
        # should be populated (demo accounts typically have USDT).
        assert isinstance(balance.balances, list)
        # We don't assert len > 0 because a brand-new demo account might
        # have zero balances until funded, but the type must be correct.
        assert balance.timestamp is not None


# ===========================================================================
# Market data
# ===========================================================================


class TestMarketData:
    """Verify market data retrieval through the adapter."""

    async def test_load_markets_and_ticker(self, okx_adapter: CCXTRestAdapter) -> None:
        """Get ticker for BTC/USDT, verify symbol and positive price."""
        ticker = await okx_adapter.get_ticker(TEST_SYMBOL)

        assert isinstance(ticker, Ticker)
        assert ticker.symbol == TEST_SYMBOL
        assert ticker.last > 0
        assert ticker.timestamp is not None

        # Bid/ask should be present for a liquid pair
        if ticker.bid is not None:
            assert ticker.bid > 0
        if ticker.ask is not None:
            assert ticker.ask > 0


# ===========================================================================
# Order lifecycle: place -> query -> cancel
# ===========================================================================


class TestOrderLifecycle:
    """Place a limit order far below market, query it, then cancel it."""

    async def test_place_query_cancel_order(self, okx_adapter: CCXTRestAdapter) -> None:
        """Full lifecycle: place limit buy, query, cancel."""
        client_oid = f"test-{uuid.uuid4().hex[:16]}"

        # -- 1. Place a limit buy far below market so it stays open ----------
        request = OrderRequest(
            symbol=TEST_SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=SMALL_ORDER_AMOUNT,
            price=LIMIT_BUY_PRICE_FAR_BELOW,
            client_order_id=client_oid,
        )

        place_resp = await okx_adapter.place_order(request)
        assert isinstance(place_resp, OrderResponse)
        assert place_resp.order_id  # exchange must assign an ID
        assert place_resp.symbol == TEST_SYMBOL
        assert place_resp.side == OrderSide.BUY
        assert place_resp.type == OrderType.LIMIT

        order_id = place_resp.order_id

        # -- 2. Query the order by exchange ID --------------------------------
        # Small delay to let the exchange register the order
        await asyncio.sleep(1)

        query_resp = await okx_adapter.get_order(TEST_SYMBOL, order_id)
        assert isinstance(query_resp, OrderResponse)
        assert query_resp.order_id == order_id
        assert query_resp.symbol == TEST_SYMBOL
        # Order should be open (SUBMITTED) since the price is far below market
        assert query_resp.status in (OrderStatus.SUBMITTED, OrderStatus.PARTIAL)
        assert query_resp.amount == SMALL_ORDER_AMOUNT
        assert query_resp.filled == Decimal("0") or query_resp.filled < query_resp.amount

        # -- 3. Cancel the order ----------------------------------------------
        cancel_req = CancelOrderRequest(
            symbol=TEST_SYMBOL,
            order_id=order_id,
        )

        cancel_resp = await okx_adapter.cancel_order(cancel_req)
        assert isinstance(cancel_resp, OrderResponse)
        # After cancel the status should reflect cancellation
        # (some exchanges return the final state, others return the cancel ack)
        assert cancel_resp.order_id == order_id

        # -- 4. Verify the order is no longer open ----------------------------
        await asyncio.sleep(1)

        final_resp = await okx_adapter.get_order(TEST_SYMBOL, order_id)
        assert final_resp.status == OrderStatus.CANCELLED


# ===========================================================================
# Market order fill + cleanup
# ===========================================================================


class TestMarketOrderFill:
    """Place a small market buy, verify fill, sell back to clean up."""

    async def test_market_order_fill(self, okx_adapter: CCXTRestAdapter) -> None:
        """Place small market buy, verify it fills, sell back."""
        # -- 1. Place market buy ---------------------------------------------
        buy_request = OrderRequest(
            symbol=TEST_SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=SMALL_ORDER_AMOUNT,
        )

        buy_resp = await okx_adapter.place_order(buy_request)
        assert isinstance(buy_resp, OrderResponse)
        assert buy_resp.order_id
        assert buy_resp.symbol == TEST_SYMBOL
        assert buy_resp.side == OrderSide.BUY
        assert buy_resp.type == OrderType.MARKET

        # Market orders should fill immediately (or very quickly)
        await asyncio.sleep(2)

        buy_detail = await okx_adapter.get_order(TEST_SYMBOL, buy_resp.order_id)
        assert buy_detail.status == OrderStatus.FILLED
        assert buy_detail.filled > Decimal("0")

        # avg_price should be set for a filled market order
        if buy_detail.avg_price is not None:
            assert buy_detail.avg_price > Decimal("0")

        # -- 2. Sell back the same amount to clean up -------------------------
        sell_request = OrderRequest(
            symbol=TEST_SYMBOL,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=SMALL_ORDER_AMOUNT,
        )

        sell_resp = await okx_adapter.place_order(sell_request)
        assert isinstance(sell_resp, OrderResponse)
        assert sell_resp.order_id

        await asyncio.sleep(2)

        sell_detail = await okx_adapter.get_order(TEST_SYMBOL, sell_resp.order_id)
        assert sell_detail.status == OrderStatus.FILLED
        assert sell_detail.filled > Decimal("0")
