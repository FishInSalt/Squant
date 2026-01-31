"""Unit tests for Binance adapter."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from squant.infra.exchange.binance import BinanceAdapter
from squant.infra.exchange.types import OrderRequest, TimeFrame
from squant.models.enums import OrderSide, OrderStatus, OrderType


class TestBinanceAdapter:
    """Tests for BinanceAdapter."""

    def test_symbol_conversion(self):
        """Test symbol format conversion."""
        # Standard to Binance
        assert BinanceAdapter._to_binance_symbol("BTC/USDT") == "BTCUSDT"
        assert BinanceAdapter._to_binance_symbol("ETH/BTC") == "ETHBTC"

        # Binance to standard
        assert BinanceAdapter._from_binance_symbol("BTCUSDT") == "BTC/USDT"
        assert BinanceAdapter._from_binance_symbol("ETHBTC") == "ETH/BTC"
        assert BinanceAdapter._from_binance_symbol("SOLUSDC") == "SOL/USDC"
        assert BinanceAdapter._from_binance_symbol("BNBBUSD") == "BNB/BUSD"

    def test_timeframe_mapping(self):
        """Test timeframe mapping."""
        assert BinanceAdapter.TIMEFRAME_MAP[TimeFrame.M1] == "1m"
        assert BinanceAdapter.TIMEFRAME_MAP[TimeFrame.H1] == "1h"
        assert BinanceAdapter.TIMEFRAME_MAP[TimeFrame.D1] == "1d"

    def test_order_status_mapping(self):
        """Test order status mapping."""
        assert BinanceAdapter.ORDER_STATUS_MAP["NEW"] == OrderStatus.SUBMITTED
        assert BinanceAdapter.ORDER_STATUS_MAP["FILLED"] == OrderStatus.FILLED
        assert BinanceAdapter.ORDER_STATUS_MAP["CANCELED"] == OrderStatus.CANCELLED
        assert BinanceAdapter.ORDER_STATUS_MAP["PARTIALLY_FILLED"] == OrderStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test get_balance method."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        mock_response = {
            "balances": [
                {"asset": "BTC", "free": "1.5", "locked": "0.1"},
                {"asset": "USDT", "free": "1000.0", "locked": "0"},
                {"asset": "ETH", "free": "0", "locked": "0"},  # Should be filtered out
            ]
        }

        with patch.object(adapter._client, "connect", new_callable=AsyncMock), patch.object(
            adapter._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            await adapter.connect()
            balance = await adapter.get_balance()

        assert balance.exchange == "binance"
        assert len(balance.balances) == 2  # ETH filtered out (zero balance)

        btc_balance = next(b for b in balance.balances if b.currency == "BTC")
        assert btc_balance.available == Decimal("1.5")
        assert btc_balance.frozen == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_get_ticker(self):
        """Test get_ticker method."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        mock_response = {
            "symbol": "BTCUSDT",
            "lastPrice": "42000.50",
            "bidPrice": "42000.00",
            "askPrice": "42001.00",
            "highPrice": "43000.00",
            "lowPrice": "41000.00",
            "volume": "1234.56",
            "quoteVolume": "51851040.00",
            "priceChange": "500.50",
            "priceChangePercent": "1.21",
        }

        with patch.object(adapter._client, "connect", new_callable=AsyncMock), patch.object(
            adapter._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            await adapter.connect()
            ticker = await adapter.get_ticker("BTC/USDT")

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("42000.50")
        assert ticker.bid == Decimal("42000.00")
        assert ticker.ask == Decimal("42001.00")
        assert ticker.change_24h == Decimal("500.50")

    @pytest.mark.asyncio
    async def test_place_limit_order(self):
        """Test placing a limit order."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        mock_response = {
            "orderId": 12345678,
            "clientOrderId": "my_order_1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "status": "NEW",
            "price": "42000.00",
            "origQty": "0.1",
            "executedQty": "0",
        }

        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.1"),
            price=Decimal("42000.00"),
            client_order_id="my_order_1",
        )

        with patch.object(adapter._client, "connect", new_callable=AsyncMock), patch.object(
            adapter._client, "post", new_callable=AsyncMock, return_value=mock_response
        ):
            await adapter.connect()
            response = await adapter.place_order(request)

        assert response.order_id == "12345678"
        assert response.client_order_id == "my_order_1"
        assert response.symbol == "BTC/USDT"
        assert response.side == OrderSide.BUY
        assert response.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_parse_order(self):
        """Test order parsing."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        order_data = {
            "orderId": 12345678,
            "clientOrderId": "my_order_1",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "status": "PARTIALLY_FILLED",
            "price": "3000.00",
            "origQty": "1.0",
            "executedQty": "0.5",
            "cummulativeQuoteQty": "1500.00",
            "time": 1704067200000,
            "updateTime": 1704067300000,
        }

        order = adapter._parse_order(order_data)

        assert order.order_id == "12345678"
        assert order.symbol == "ETH/USDT"
        assert order.side == OrderSide.SELL
        assert order.type == OrderType.LIMIT
        assert order.status == OrderStatus.PARTIAL
        assert order.amount == Decimal("1.0")
        assert order.filled == Decimal("0.5")
        assert order.avg_price == Decimal("3000.00")  # 1500 / 0.5


class TestBinanceClient:
    """Tests for BinanceClient."""

    def test_signature_generation(self):
        """Test HMAC-SHA256 signature generation."""
        from squant.infra.exchange.binance import BinanceClient

        client = BinanceClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        # Test with known values
        query_string = "symbol=BTCUSDT&timestamp=1704067200000"
        signature = client._generate_signature(query_string)

        # Signature should be a 64-char hex string
        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)

    def test_base_url(self):
        """Test base URL selection."""
        from squant.infra.exchange.binance import BinanceClient

        mainnet_client = BinanceClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=False,
        )
        assert mainnet_client.base_url == "https://api.binance.com"

        testnet_client = BinanceClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )
        assert testnet_client.base_url == "https://testnet.binance.vision"
