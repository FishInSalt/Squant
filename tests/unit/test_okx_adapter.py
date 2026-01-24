"""Unit tests for OKX exchange adapter."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from squant.infra.exchange import (
    AccountBalance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.infra.exchange.okx import OKXAdapter, OKXClient
from squant.models.enums import OrderSide, OrderStatus, OrderType


class TestOKXClient:
    """Tests for OKX HTTP client."""

    def test_signature_generation(self) -> None:
        """Test HMAC-SHA256 signature generation."""
        client = OKXClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )

        # Test signature generation with known values
        timestamp = "2024-01-15T10:30:00.000Z"
        method = "GET"
        request_path = "/api/v5/account/balance"
        body = ""

        signature = client._generate_signature(timestamp, method, request_path, body)

        # Signature should be base64 encoded
        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_auth_headers_construction(self) -> None:
        """Test authentication headers are built correctly."""
        client = OKXClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
            testnet=False,
        )

        timestamp = "2024-01-15T10:30:00.000Z"
        headers = client._build_auth_headers(timestamp, "GET", "/api/v5/account/balance")

        assert headers["OK-ACCESS-KEY"] == "test-key"
        assert headers["OK-ACCESS-TIMESTAMP"] == timestamp
        assert headers["OK-ACCESS-PASSPHRASE"] == "test-passphrase"
        assert "OK-ACCESS-SIGN" in headers
        assert "x-simulated-trading" not in headers

    def test_auth_headers_testnet(self) -> None:
        """Test testnet header is included for simulated trading."""
        client = OKXClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
            testnet=True,
        )

        timestamp = "2024-01-15T10:30:00.000Z"
        headers = client._build_auth_headers(timestamp, "GET", "/api/v5/account/balance")

        assert headers["x-simulated-trading"] == "1"

    def test_timestamp_format(self) -> None:
        """Test timestamp is in correct ISO 8601 format."""
        client = OKXClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )

        timestamp = client._get_timestamp()

        # Should be in format: 2024-01-15T10:30:00.000Z
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        # Should parse without error
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


class TestOKXAdapter:
    """Tests for OKX adapter."""

    def test_symbol_conversion(self) -> None:
        """Test symbol format conversion."""
        # Standard to OKX
        assert OKXAdapter._to_okx_symbol("BTC/USDT") == "BTC-USDT"
        assert OKXAdapter._to_okx_symbol("ETH/BTC") == "ETH-BTC"

        # OKX to standard
        assert OKXAdapter._from_okx_symbol("BTC-USDT") == "BTC/USDT"
        assert OKXAdapter._from_okx_symbol("ETH-BTC") == "ETH/BTC"

    def test_order_status_mapping(self) -> None:
        """Test OKX order status to standard status mapping."""
        assert OKXAdapter.ORDER_STATUS_MAP["live"] == OrderStatus.SUBMITTED
        assert OKXAdapter.ORDER_STATUS_MAP["partially_filled"] == OrderStatus.PARTIAL
        assert OKXAdapter.ORDER_STATUS_MAP["filled"] == OrderStatus.FILLED
        assert OKXAdapter.ORDER_STATUS_MAP["canceled"] == OrderStatus.CANCELLED

    def test_timeframe_mapping(self) -> None:
        """Test timeframe conversion to OKX format."""
        assert OKXAdapter.TIMEFRAME_MAP[TimeFrame.M1] == "1m"
        assert OKXAdapter.TIMEFRAME_MAP[TimeFrame.H1] == "1H"
        assert OKXAdapter.TIMEFRAME_MAP[TimeFrame.D1] == "1D"

    def test_adapter_properties(self) -> None:
        """Test adapter properties."""
        adapter = OKXAdapter(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
            testnet=True,
        )

        assert adapter.name == "okx"
        assert adapter.is_testnet is True


class TestOKXAdapterParsing:
    """Tests for OKX response parsing."""

    @pytest.fixture
    def adapter(self) -> OKXAdapter:
        """Create test adapter."""
        return OKXAdapter(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )

    def test_parse_ticker(self, adapter: OKXAdapter) -> None:
        """Test ticker data parsing."""
        okx_ticker_data = {
            "instId": "BTC-USDT",
            "last": "42000.5",
            "bidPx": "41999.0",
            "askPx": "42001.0",
            "high24h": "43000.0",
            "low24h": "41000.0",
            "vol24h": "1000.5",
            "volCcy24h": "42000000.0",
        }

        ticker = adapter._parse_ticker(okx_ticker_data)

        assert isinstance(ticker, Ticker)
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("42000.5")
        assert ticker.bid == Decimal("41999.0")
        assert ticker.ask == Decimal("42001.0")
        assert ticker.high_24h == Decimal("43000.0")
        assert ticker.low_24h == Decimal("41000.0")
        assert ticker.volume_24h == Decimal("1000.5")

    def test_parse_order(self, adapter: OKXAdapter) -> None:
        """Test order data parsing."""
        okx_order_data = {
            "ordId": "1234567890",
            "clOrdId": "client-order-1",
            "instId": "BTC-USDT",
            "side": "buy",
            "ordType": "limit",
            "state": "live",
            "px": "42000.0",
            "sz": "0.1",
            "accFillSz": "0",
            "avgPx": "",
            "fee": "-0.0001",
            "feeCcy": "BTC",
            "cTime": "1705315800000",
            "uTime": "1705315800000",
        }

        order = adapter._parse_order(okx_order_data)

        assert isinstance(order, OrderResponse)
        assert order.order_id == "1234567890"
        assert order.client_order_id == "client-order-1"
        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.LIMIT
        assert order.status == OrderStatus.SUBMITTED
        assert order.price == Decimal("42000.0")
        assert order.amount == Decimal("0.1")
        assert order.filled == Decimal("0")
        assert order.fee == Decimal("-0.0001")
        assert order.fee_currency == "BTC"

    def test_parse_order_filled(self, adapter: OKXAdapter) -> None:
        """Test parsing a filled order."""
        okx_order_data = {
            "ordId": "1234567890",
            "instId": "ETH-USDT",
            "side": "sell",
            "ordType": "market",
            "state": "filled",
            "px": "",
            "sz": "1.0",
            "accFillSz": "1.0",
            "avgPx": "2500.0",
            "cTime": "1705315800000",
            "uTime": "1705315900000",
        }

        order = adapter._parse_order(okx_order_data)

        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.SELL
        assert order.type == OrderType.MARKET
        assert order.filled == Decimal("1.0")
        assert order.avg_price == Decimal("2500.0")


class TestOKXAdapterIntegration:
    """Integration tests for OKX adapter with mocked responses."""

    @pytest.fixture
    def adapter(self) -> OKXAdapter:
        """Create test adapter."""
        return OKXAdapter(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )

    @pytest.mark.asyncio
    async def test_get_balance(self, adapter: OKXAdapter) -> None:
        """Test getting account balance."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "details": [
                        {"ccy": "BTC", "availBal": "1.5", "frozenBal": "0.5"},
                        {"ccy": "USDT", "availBal": "10000.0", "frozenBal": "0"},
                        {"ccy": "ETH", "availBal": "0", "frozenBal": "0"},  # Should be excluded
                    ]
                }
            ],
        }

        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            await adapter._client.connect()

            balance = await adapter.get_balance()

            assert isinstance(balance, AccountBalance)
            assert balance.exchange == "okx"
            assert len(balance.balances) == 2  # ETH excluded (zero balance)

            btc = balance.get_balance("BTC")
            assert btc is not None
            assert btc.available == Decimal("1.5")
            assert btc.frozen == Decimal("0.5")
            assert btc.total == Decimal("2.0")

    @pytest.mark.asyncio
    async def test_get_ticker(self, adapter: OKXAdapter) -> None:
        """Test getting ticker data."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "instId": "BTC-USDT",
                    "last": "42000.5",
                    "bidPx": "41999.0",
                    "askPx": "42001.0",
                    "high24h": "43000.0",
                    "low24h": "41000.0",
                    "vol24h": "1000.5",
                }
            ],
        }

        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            ticker = await adapter.get_ticker("BTC/USDT")

            assert isinstance(ticker, Ticker)
            assert ticker.symbol == "BTC/USDT"
            assert ticker.last == Decimal("42000.5")
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_candlesticks(self, adapter: OKXAdapter) -> None:
        """Test getting candlestick data."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                ["1705315800000", "42000", "42500", "41500", "42300", "100", "4200000"],
                ["1705312200000", "41800", "42100", "41700", "42000", "80", "3360000"],
            ],
        }

        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            candles = await adapter.get_candlesticks("BTC/USDT", TimeFrame.H1, limit=10)

            assert len(candles) == 2
            assert all(isinstance(c, Candlestick) for c in candles)
            # Should be sorted ascending
            assert candles[0].timestamp < candles[1].timestamp
            assert candles[1].open == Decimal("42000")
            assert candles[1].high == Decimal("42500")
            assert candles[1].low == Decimal("41500")
            assert candles[1].close == Decimal("42300")

    @pytest.mark.asyncio
    async def test_place_order(self, adapter: OKXAdapter) -> None:
        """Test placing an order."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "1234567890",
                    "clOrdId": "my-order-1",
                    "sCode": "0",
                    "sMsg": "",
                }
            ],
        }

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            request = OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.1"),
                price=Decimal("42000.0"),
                client_order_id="my-order-1",
            )

            response = await adapter.place_order(request)

            assert isinstance(response, OrderResponse)
            assert response.order_id == "1234567890"
            assert response.client_order_id == "my-order-1"
            assert response.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_place_order_error(self, adapter: OKXAdapter) -> None:
        """Test order placement error handling."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "",
                    "clOrdId": "",
                    "sCode": "51000",
                    "sMsg": "Parameter error",
                }
            ],
        }

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            request = OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )

            with pytest.raises(InvalidOrderError) as exc_info:
                await adapter.place_order(request)

            assert "Parameter error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, adapter: OKXAdapter) -> None:
        """Test cancelling non-existent order."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "invalid-id",
                    "sCode": "51400",
                    "sMsg": "Order does not exist",
                }
            ],
        }

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            request = CancelOrderRequest(
                symbol="BTC/USDT",
                order_id="invalid-id",
            )

            with pytest.raises(OrderNotFoundError) as exc_info:
                await adapter.cancel_order(request)

            assert exc_info.value.order_id == "invalid-id"

    @pytest.mark.asyncio
    async def test_get_open_orders(self, adapter: OKXAdapter) -> None:
        """Test getting open orders."""
        mock_response = {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": "order-1",
                    "instId": "BTC-USDT",
                    "side": "buy",
                    "ordType": "limit",
                    "state": "live",
                    "px": "40000.0",
                    "sz": "0.1",
                    "accFillSz": "0",
                    "cTime": "1705315800000",
                    "uTime": "1705315800000",
                },
                {
                    "ordId": "order-2",
                    "instId": "ETH-USDT",
                    "side": "sell",
                    "ordType": "limit",
                    "state": "live",
                    "px": "2500.0",
                    "sz": "1.0",
                    "accFillSz": "0",
                    "cTime": "1705315900000",
                    "uTime": "1705315900000",
                },
            ],
        }

        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            orders = await adapter.get_open_orders()

            assert len(orders) == 2
            assert orders[0].order_id == "order-1"
            assert orders[0].symbol == "BTC/USDT"
            assert orders[1].order_id == "order-2"
            assert orders[1].symbol == "ETH/USDT"


class TestOKXClientErrorHandling:
    """Tests for OKX client error handling."""

    @pytest.fixture
    def client(self) -> OKXClient:
        """Create test client."""
        return OKXClient(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )

    def test_parse_rate_limit_error(self, client: OKXClient) -> None:
        """Test rate limit error parsing."""

        class MockResponse:
            def json(self) -> dict:
                return {"code": "50011", "msg": "Rate limit exceeded", "data": []}

        with pytest.raises(ExchangeRateLimitError) as exc_info:
            client._parse_response(MockResponse())  # type: ignore

        assert exc_info.value.exchange == "okx"
        assert exc_info.value.retry_after == 1.0

    def test_parse_auth_error(self, client: OKXClient) -> None:
        """Test authentication error parsing."""

        class MockResponse:
            def json(self) -> dict:
                return {"code": "50100", "msg": "Invalid API key", "data": []}

        with pytest.raises(ExchangeAuthenticationError) as exc_info:
            client._parse_response(MockResponse())  # type: ignore

        assert exc_info.value.exchange == "okx"

    def test_parse_api_error(self, client: OKXClient) -> None:
        """Test general API error parsing."""

        class MockResponse:
            def json(self) -> dict:
                return {"code": "51000", "msg": "Parameter error", "data": []}

        with pytest.raises(ExchangeAPIError) as exc_info:
            client._parse_response(MockResponse())  # type: ignore

        assert exc_info.value.code == "51000"
        assert "Parameter error" in str(exc_info.value)


class TestOrderRequestValidation:
    """Tests for order request validation."""

    def test_limit_order_requires_price(self) -> None:
        """Test that limit orders require a price."""
        with pytest.raises(ValueError, match="Limit orders must have a price"):
            OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.1"),
                price=None,
            )

    def test_limit_order_with_price(self) -> None:
        """Test valid limit order creation."""
        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.1"),
            price=Decimal("42000.0"),
        )
        assert request.price == Decimal("42000.0")

    def test_market_order_without_price(self) -> None:
        """Test market order can be created without price."""
        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )
        assert request.price is None


class TestCancelOrderRequestValidation:
    """Tests for cancel order request validation."""

    def test_requires_order_id(self) -> None:
        """Test that at least one ID is required."""
        with pytest.raises(ValueError, match="Either order_id or client_order_id"):
            CancelOrderRequest(
                symbol="BTC/USDT",
                order_id=None,
                client_order_id=None,
            )

    def test_with_order_id(self) -> None:
        """Test cancel request with order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id="123456",
        )
        assert request.order_id == "123456"

    def test_with_client_order_id(self) -> None:
        """Test cancel request with client order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            client_order_id="my-order-1",
        )
        assert request.client_order_id == "my-order-1"
