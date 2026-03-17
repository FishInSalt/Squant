"""Integration tests for OKX exchange adapter.

These tests connect to OKX testnet (simulated trading) to verify
the complete exchange integration flow.

Requirements:
    - OKX_API_KEY: API key for testnet
    - OKX_API_SECRET: API secret for testnet
    - OKX_PASSPHRASE: API passphrase for testnet

Credentials can be set via environment variables or in .env file.

Run with:
    conda run -n squant python -m pytest tests/integration/test_okx_integration.py -v

Skip private tests (no credentials):
    conda run -n squant python -m pytest tests/integration/test_okx_integration.py -v -m "not okx_private"
"""

import os
from decimal import Decimal

import pytest

from squant.config import get_settings
from squant.infra.exchange import TimeFrame
from squant.infra.exchange.exceptions import InvalidOrderError, OrderNotFoundError
from squant.infra.exchange.okx import OKXAdapter
from squant.infra.exchange.types import CancelOrderRequest, OrderRequest
from squant.models.enums import OrderSide, OrderStatus, OrderType


def get_okx_credentials() -> tuple[str, str, str] | None:
    """Get OKX API credentials from settings (.env file or environment)."""
    settings = get_settings()

    if settings.okx_api_key and settings.okx_api_secret and settings.okx_passphrase:
        return (
            settings.okx_api_key.get_secret_value(),
            settings.okx_api_secret.get_secret_value(),
            settings.okx_passphrase.get_secret_value(),
        )
    return None


# Check if credentials are available
HAS_CREDENTIALS = get_okx_credentials() is not None

# Check if running in CI environment
IS_CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

# Custom markers
pytestmark = pytest.mark.integration

# Skip marker for tests requiring credentials
# Skip in CI environment to avoid flaky tests due to network/credential issues
okx_private = pytest.mark.skipif(
    not HAS_CREDENTIALS or IS_CI,
    reason="OKX private tests skipped: no credentials or running in CI environment",
)


@pytest.fixture
async def okx_adapter():
    """Create OKX adapter using settings from .env file."""
    settings = get_settings()
    credentials = get_okx_credentials()

    if credentials:
        api_key, api_secret, passphrase = credentials
    else:
        # Use dummy credentials for public endpoint tests
        api_key, api_secret, passphrase = "dummy", "dummy", "dummy"

    # Integration tests always use production (sandbox flag is per-account in live trading)
    adapter = OKXAdapter(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        testnet=False,
    )
    await adapter.connect()
    yield adapter
    await adapter.close()


class TestOKXPublicEndpoints:
    """Tests for public OKX endpoints (no authentication required)."""

    @pytest.mark.asyncio
    async def test_get_ticker(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching ticker data for BTC/USDT."""
        ticker = await okx_adapter.get_ticker("BTC/USDT")

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last > 0
        assert ticker.bid is not None
        assert ticker.ask is not None
        assert ticker.high_24h is not None
        assert ticker.low_24h is not None
        assert ticker.volume_24h is not None

    @pytest.mark.asyncio
    async def test_get_ticker_eth(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching ticker for ETH/USDT."""
        ticker = await okx_adapter.get_ticker("ETH/USDT")

        assert ticker.symbol == "ETH/USDT"
        assert ticker.last > 0

    @pytest.mark.asyncio
    async def test_get_tickers(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching multiple tickers."""
        tickers = await okx_adapter.get_tickers()

        assert len(tickers) > 0
        # Check that we got some common pairs
        symbols = {t.symbol for t in tickers}
        assert "BTC/USDT" in symbols

    @pytest.mark.asyncio
    async def test_get_tickers_filtered(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching specific tickers."""
        tickers = await okx_adapter.get_tickers(["BTC/USDT", "ETH/USDT"])

        assert len(tickers) == 2
        symbols = {t.symbol for t in tickers}
        assert symbols == {"BTC/USDT", "ETH/USDT"}

    @pytest.mark.asyncio
    async def test_get_candlesticks_1h(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching 1-hour candlesticks."""
        candles = await okx_adapter.get_candlesticks(
            symbol="BTC/USDT",
            timeframe=TimeFrame.H1,
            limit=10,
        )

        assert len(candles) == 10
        for candle in candles:
            assert candle.open > 0
            assert candle.high >= candle.low
            assert candle.high >= candle.open
            assert candle.high >= candle.close
            assert candle.low <= candle.open
            assert candle.low <= candle.close
            assert candle.volume >= 0

        # Check that candles are sorted ascending by timestamp
        timestamps = [c.timestamp for c in candles]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_get_candlesticks_various_timeframes(self, okx_adapter: OKXAdapter) -> None:
        """Test various timeframes."""
        timeframes = [TimeFrame.M1, TimeFrame.M5, TimeFrame.M15, TimeFrame.D1]

        for tf in timeframes:
            candles = await okx_adapter.get_candlesticks(
                symbol="BTC/USDT",
                timeframe=tf,
                limit=5,
            )
            assert len(candles) > 0, f"No candles for timeframe {tf}"


@okx_private
class TestOKXPrivateEndpoints:
    """Tests for private OKX endpoints (authentication required).

    These tests require valid OKX testnet API credentials.
    """

    @pytest.mark.asyncio
    async def test_get_balance(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching account balance."""
        balance = await okx_adapter.get_balance()

        assert balance.exchange == "okx"
        assert balance.timestamp is not None
        # Testnet account should have some balance
        # (new testnet accounts get virtual funds)

    @pytest.mark.asyncio
    async def test_get_balance_currency(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching balance for specific currency."""
        # Get USDT balance (testnet accounts typically have USDT)
        balance = await okx_adapter.get_balance_currency("USDT")

        # Balance might be None if no USDT, but shouldn't error
        if balance is not None:
            assert balance.currency == "USDT"
            assert balance.available >= 0
            assert balance.frozen >= 0

    @pytest.mark.asyncio
    async def test_get_open_orders_empty(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching open orders when none exist."""
        orders = await okx_adapter.get_open_orders()

        # Result should be a list (possibly empty)
        assert isinstance(orders, list)

    @pytest.mark.asyncio
    async def test_get_open_orders_by_symbol(self, okx_adapter: OKXAdapter) -> None:
        """Test fetching open orders filtered by symbol."""
        orders = await okx_adapter.get_open_orders(symbol="BTC/USDT")

        assert isinstance(orders, list)


@okx_private
class TestOKXOrderFlow:
    """Tests for complete order flow on testnet.

    These tests place real orders on the testnet, so they require
    valid credentials and testnet funds.
    """

    @pytest.mark.asyncio
    async def test_place_and_cancel_limit_order(self, okx_adapter: OKXAdapter) -> None:
        """Test placing and cancelling a limit order."""
        # Get current price to set limit far from market
        ticker = await okx_adapter.get_ticker("BTC/USDT")
        # Set buy price 20% below market (won't fill)
        limit_price = ticker.last * Decimal("0.8")

        # Place limit order
        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.0001"),  # Minimum amount
            price=limit_price.quantize(Decimal("0.1")),  # Round to tick size
        )

        order = await okx_adapter.place_order(order_request)

        assert order.order_id
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.LIMIT
        assert order.status == OrderStatus.SUBMITTED

        # Get order details
        order_detail = await okx_adapter.get_order("BTC/USDT", order.order_id)
        assert order_detail.order_id == order.order_id

        # Cancel the order
        cancel_request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id=order.order_id,
        )
        cancelled = await okx_adapter.cancel_order(cancel_request)

        assert cancelled.order_id == order.order_id
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_place_order_with_client_id(self, okx_adapter: OKXAdapter) -> None:
        """Test placing order with client order ID."""
        ticker = await okx_adapter.get_ticker("BTC/USDT")
        limit_price = ticker.last * Decimal("0.8")

        import uuid

        # OKX clOrdId: alphanumeric only, max 32 chars
        client_order_id = f"t{uuid.uuid4().hex[:15]}"

        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=limit_price.quantize(Decimal("0.1")),
            client_order_id=client_order_id,
        )

        order = await okx_adapter.place_order(order_request)

        assert order.client_order_id == client_order_id

        # Cleanup: cancel the order
        cancel_request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id=order.order_id,
        )
        await okx_adapter.cancel_order(cancel_request)

    @pytest.mark.asyncio
    async def test_cancel_by_client_order_id(self, okx_adapter: OKXAdapter) -> None:
        """Test cancelling order by client order ID."""
        ticker = await okx_adapter.get_ticker("BTC/USDT")
        limit_price = ticker.last * Decimal("0.8")

        import uuid

        # OKX clOrdId: alphanumeric only, max 32 chars
        client_order_id = f"c{uuid.uuid4().hex[:15]}"

        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=limit_price.quantize(Decimal("0.1")),
            client_order_id=client_order_id,
        )

        await okx_adapter.place_order(order_request)

        # Cancel using client order ID
        cancel_request = CancelOrderRequest(
            symbol="BTC/USDT",
            client_order_id=client_order_id,
        )
        cancelled = await okx_adapter.cancel_order(cancel_request)

        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_nonexistent_order(self, okx_adapter: OKXAdapter) -> None:
        """Test getting a non-existent order raises error."""
        # Use a valid numeric format that doesn't exist
        with pytest.raises(OrderNotFoundError):
            await okx_adapter.get_order("BTC/USDT", "123456789012345678")

    @pytest.mark.asyncio
    async def test_place_limit_order_without_price(self, okx_adapter: OKXAdapter) -> None:
        """Test that limit order without price raises error."""
        with pytest.raises(ValueError, match="Limit orders must have a price"):
            OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.0001"),
                # No price specified
            )


@okx_private
class TestOKXEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_order(self, okx_adapter: OKXAdapter) -> None:
        """Test cancelling an already cancelled order."""
        # First, place and cancel an order
        ticker = await okx_adapter.get_ticker("BTC/USDT")
        limit_price = ticker.last * Decimal("0.8")

        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=limit_price.quantize(Decimal("0.1")),
        )

        order = await okx_adapter.place_order(order_request)

        # Cancel the order
        cancel_request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id=order.order_id,
        )
        await okx_adapter.cancel_order(cancel_request)

        # Try to cancel again - should raise OrderNotFoundError
        with pytest.raises(OrderNotFoundError):
            await okx_adapter.cancel_order(cancel_request)

    @pytest.mark.asyncio
    async def test_place_order_insufficient_balance(self, okx_adapter: OKXAdapter) -> None:
        """Test placing order with insufficient balance."""
        ticker = await okx_adapter.get_ticker("BTC/USDT")

        # Try to buy an enormous amount
        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("1000000"),  # 1 million BTC
            price=ticker.last,
        )

        with pytest.raises(InvalidOrderError):
            await okx_adapter.place_order(order_request)

    @pytest.mark.asyncio
    async def test_place_sell_order(self, okx_adapter: OKXAdapter) -> None:
        """Test placing a sell order."""
        ticker = await okx_adapter.get_ticker("BTC/USDT")
        # Set sell price 20% above market (won't fill)
        limit_price = ticker.last * Decimal("1.2")

        order_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=limit_price.quantize(Decimal("0.1")),
        )

        # This may fail if testnet account doesn't have BTC
        # That's expected behavior - we're testing the request works
        try:
            order = await okx_adapter.place_order(order_request)
            # If it succeeds, cancel it
            cancel_request = CancelOrderRequest(
                symbol="BTC/USDT",
                order_id=order.order_id,
            )
            await okx_adapter.cancel_order(cancel_request)
        except InvalidOrderError:
            # Expected if no BTC balance
            pass
