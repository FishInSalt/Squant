"""Unit tests for CCXT adapter and transformer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer
from squant.infra.exchange.ccxt.types import (
    SUPPORTED_EXCHANGES,
    TIMEFRAME_MAP,
    ExchangeCredentials,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.infra.exchange.types import CancelOrderRequest, OrderRequest, TimeFrame
from squant.models.enums import OrderSide, OrderStatus, OrderType


class TestExchangeCredentials:
    """Tests for ExchangeCredentials dataclass."""

    def test_create_minimal_credentials(self):
        """Test creating credentials with required fields only."""
        creds = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
        )

        assert creds.api_key == "test-key"
        assert creds.api_secret == "test-secret"
        assert creds.passphrase is None
        assert creds.sandbox is False

    def test_create_full_credentials(self):
        """Test creating credentials with all fields."""
        creds = ExchangeCredentials(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-pass",
            sandbox=True,
        )

        assert creds.passphrase == "test-pass"
        assert creds.sandbox is True


class TestSupportedExchanges:
    """Tests for SUPPORTED_EXCHANGES constant."""

    def test_okx_supported(self):
        """Test OKX is supported."""
        assert "okx" in SUPPORTED_EXCHANGES

    def test_binance_supported(self):
        """Test Binance is supported."""
        assert "binance" in SUPPORTED_EXCHANGES

    def test_bybit_supported(self):
        """Test Bybit is supported."""
        assert "bybit" in SUPPORTED_EXCHANGES

    def test_is_frozenset(self):
        """Test SUPPORTED_EXCHANGES is immutable."""
        assert isinstance(SUPPORTED_EXCHANGES, frozenset)


class TestTimeframeMap:
    """Tests for TIMEFRAME_MAP constant."""

    def test_all_timeframes_mapped(self):
        """Test all expected timeframes are mapped."""
        expected = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

        for tf in expected:
            assert tf in TIMEFRAME_MAP


class TestCCXTDataTransformer:
    """Tests for CCXTDataTransformer."""

    def test_ticker_to_ws_ticker(self):
        """Test converting CCXT ticker to WSTicker."""
        ticker = {
            "symbol": "BTC/USDT",
            "timestamp": 1704067200000,  # 2024-01-01 00:00:00 UTC
            "last": 50000.0,
            "bid": 49990.0,
            "ask": 50010.0,
            "bidVolume": 1.5,
            "askVolume": 2.0,
            "high": 51000.0,
            "low": 49000.0,
            "baseVolume": 1000.0,
            "quoteVolume": 50000000.0,
            "open": 49000.0,
        }

        result = CCXTDataTransformer.ticker_to_ws_ticker(ticker)

        assert result.symbol == "BTC/USDT"
        assert result.last == Decimal("50000.0")
        assert result.bid == Decimal("49990.0")
        assert result.ask == Decimal("50010.0")
        assert result.high_24h == Decimal("51000.0")
        assert result.low_24h == Decimal("49000.0")
        assert result.volume_24h == Decimal("1000.0")

    def test_ticker_to_ws_ticker_minimal(self):
        """Test converting ticker with minimal fields."""
        ticker = {"symbol": "ETH/USDT", "last": 3000.0}

        result = CCXTDataTransformer.ticker_to_ws_ticker(ticker)

        assert result.symbol == "ETH/USDT"
        assert result.last == Decimal("3000.0")
        assert result.bid is None
        assert result.ask is None

    def test_ticker_to_ws_ticker_none_last(self):
        """Test ticker with None last price."""
        ticker = {"symbol": "BTC/USDT", "last": None}

        result = CCXTDataTransformer.ticker_to_ws_ticker(ticker)

        assert result.last == Decimal("0")

    def test_ohlcv_to_ws_candle(self):
        """Test converting OHLCV to WSCandle."""
        ohlcv = [1704067200000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(ohlcv, symbol="BTC/USDT", timeframe="1h")

        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1h"
        assert result.open == Decimal("50000.0")
        assert result.high == Decimal("51000.0")
        assert result.low == Decimal("49000.0")
        assert result.close == Decimal("50500.0")
        assert result.volume == Decimal("100.0")

    def test_ohlcv_to_ws_candle_invalid_length(self):
        """Test OHLCV with invalid length raises error."""
        ohlcv = [1704067200000, 50000.0]  # Too short

        with pytest.raises(ValueError, match="Invalid OHLCV array length"):
            CCXTDataTransformer.ohlcv_to_ws_candle(ohlcv, symbol="BTC/USDT", timeframe="1h")

    def test_ohlcv_to_ws_candle_with_is_closed(self):
        """Test OHLCV with is_closed flag."""
        ohlcv = [1704067200000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(
            ohlcv, symbol="BTC/USDT", timeframe="1h", is_closed=True
        )

        assert result.is_closed is True

    def test_trade_to_ws_trade(self):
        """Test converting trade to WSTrade."""
        trade = {
            "symbol": "BTC/USDT",
            "id": "12345",
            "timestamp": 1704067200000,
            "price": 50000.0,
            "amount": 0.1,
            "side": "buy",
        }

        result = CCXTDataTransformer.trade_to_ws_trade(trade)

        assert result.symbol == "BTC/USDT"
        assert result.trade_id == "12345"
        assert result.price == Decimal("50000.0")
        assert result.size == Decimal("0.1")
        assert result.side == "buy"

    def test_orderbook_to_ws_orderbook(self):
        """Test converting orderbook to WSOrderBook."""
        orderbook = {
            "timestamp": 1704067200000,
            "nonce": 12345,
            "bids": [[49990.0, 1.5], [49980.0, 2.0], [49970.0, 3.0]],
            "asks": [[50010.0, 1.0], [50020.0, 1.5], [50030.0, 2.0]],
        }

        result = CCXTDataTransformer.orderbook_to_ws_orderbook(
            orderbook, symbol="BTC/USDT", limit=2
        )

        assert result.symbol == "BTC/USDT"
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        assert result.bids[0].price == Decimal("49990.0")
        assert result.bids[0].size == Decimal("1.5")
        assert result.checksum == 12345

    def test_order_to_ws_order_update(self):
        """Test converting order to WSOrderUpdate."""
        order = {
            "id": "12345",
            "clientOrderId": "my-order-1",
            "timestamp": 1704067200000,
            "lastTradeTimestamp": 1704067200500,
            "symbol": "BTC/USDT",
            "type": "limit",
            "side": "buy",
            "price": 50000.0,
            "amount": 0.1,
            "filled": 0.05,
            "status": "open",
            "fee": {"cost": 0.01, "currency": "USDT"},
            "average": 50000.0,
        }

        result = CCXTDataTransformer.order_to_ws_order_update(order)

        assert result.order_id == "12345"
        assert result.client_order_id == "my-order-1"
        assert result.symbol == "BTC/USDT"
        assert result.side == "buy"
        assert result.order_type == "limit"
        assert result.status == "submitted"  # Mapped from 'open'
        assert result.price == Decimal("50000.0")
        assert result.size == Decimal("0.1")
        assert result.filled_size == Decimal("0.05")
        assert result.fee == Decimal("0.01")
        assert result.fee_currency == "USDT"

    def test_balance_to_ws_account_update(self):
        """Test converting balance to WSAccountUpdate."""
        balance = {
            "timestamp": 1704067200000,
            "free": {"BTC": 1.0, "USDT": 10000.0},
            "used": {"BTC": 0.5, "USDT": 5000.0},
        }

        result = CCXTDataTransformer.balance_to_ws_account_update(balance)

        assert len(result.balances) == 2
        # Find BTC balance
        btc_balance = next((b for b in result.balances if b.currency == "BTC"), None)
        assert btc_balance is not None
        assert btc_balance.available == Decimal("1.0")
        assert btc_balance.frozen == Decimal("0.5")

    def test_balance_skips_zero_balances(self):
        """Test balance conversion skips zero balances."""
        balance = {
            "free": {"BTC": 1.0, "ETH": 0, "USDT": 0},
            "used": {"BTC": 0, "ETH": 0, "USDT": 0},
        }

        result = CCXTDataTransformer.balance_to_ws_account_update(balance)

        assert len(result.balances) == 1
        assert result.balances[0].currency == "BTC"

    def test_parse_timestamp_none(self):
        """Test _parse_timestamp with None returns current time."""
        result = CCXTDataTransformer._parse_timestamp(None)

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_timestamp_valid(self):
        """Test _parse_timestamp with valid timestamp."""
        ts = 1704067200000  # 2024-01-01 00:00:00 UTC

        result = CCXTDataTransformer._parse_timestamp(ts)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_map_order_status(self):
        """Test _map_order_status mapping."""
        assert CCXTDataTransformer._map_order_status("open") == "submitted"
        assert CCXTDataTransformer._map_order_status("closed") == "filled"
        assert CCXTDataTransformer._map_order_status("canceled") == "cancelled"
        assert CCXTDataTransformer._map_order_status("expired") == "cancelled"
        assert CCXTDataTransformer._map_order_status("rejected") == "rejected"
        assert CCXTDataTransformer._map_order_status("unknown") == "unknown"

    def test_ohlcv_to_ws_candle_none_volume(self):
        """Test handling None volume value in OHLCV data."""
        ohlcv = [1704067200000, 100.0, 105.0, 98.0, 102.0, None]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(ohlcv, "SOL/USDT", "1m", is_closed=False)

        assert result.volume == Decimal("0")

    def test_ohlcv_to_ws_candle_empty_array(self):
        """Test that empty OHLCV array raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OHLCV array length"):
            CCXTDataTransformer.ohlcv_to_ws_candle([], "BTC/USDT", "1h", is_closed=False)

    def test_trade_to_ws_trade_sell_side(self):
        """Test converting a sell trade with uppercase side is normalized."""
        ccxt_trade = {
            "id": "67890",
            "timestamp": 1704067200000,
            "symbol": "ETH/USDT",
            "side": "SELL",
            "price": 2500.0,
            "amount": 1.0,
        }

        result = CCXTDataTransformer.trade_to_ws_trade(ccxt_trade)

        assert result.side == "sell"

    def test_orderbook_to_ws_orderbook_with_larger_limit(self):
        """Test that limit parameter restricts the number of levels from a larger dataset."""
        ccxt_orderbook = {
            "timestamp": 1704067200000,
            "bids": [[42000.0 - i, 1.0] for i in range(10)],
            "asks": [[42001.0 + i, 1.0] for i in range(10)],
        }

        result = CCXTDataTransformer.orderbook_to_ws_orderbook(ccxt_orderbook, "BTC/USDT", limit=5)

        assert len(result.bids) == 5
        assert len(result.asks) == 5

    def test_balance_to_ws_account_update_only_used(self):
        """Test that currencies only in used_balances are included."""
        ccxt_balance = {
            "timestamp": 1704067200000,
            "free": {"BTC": 1.0},
            "used": {"BTC": 0.5, "ETH": 2.0},
        }

        result = CCXTDataTransformer.balance_to_ws_account_update(ccxt_balance)

        assert len(result.balances) == 2

        btc_balance = next((b for b in result.balances if b.currency == "BTC"), None)
        assert btc_balance is not None
        assert btc_balance.available == Decimal("1.0")
        assert btc_balance.frozen == Decimal("0.5")

        eth_balance = next((b for b in result.balances if b.currency == "ETH"), None)
        assert eth_balance is not None
        assert eth_balance.available == Decimal("0")
        assert eth_balance.frozen == Decimal("2.0")


class TestCCXTRestAdapterInit:
    """Tests for CCXTRestAdapter initialization."""

    def test_init_with_supported_exchange(self):
        """Test initialization with supported exchange."""
        adapter = CCXTRestAdapter("okx")

        assert adapter.name == "okx"
        assert adapter.is_testnet is False

    def test_init_case_insensitive(self):
        """Test initialization is case insensitive."""
        adapter = CCXTRestAdapter("OKX")

        assert adapter.name == "okx"

    def test_init_with_credentials(self):
        """Test initialization with credentials."""
        creds = ExchangeCredentials(
            api_key="key",
            api_secret="secret",
            sandbox=True,
        )
        adapter = CCXTRestAdapter("binance", credentials=creds)

        assert adapter.is_testnet is True

    def test_init_unsupported_exchange_raises(self):
        """Test initialization with unsupported exchange raises error."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            CCXTRestAdapter("unsupported_exchange")


class TestCCXTRestAdapterConnect:
    """Tests for CCXTRestAdapter connect method."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        adapter = CCXTRestAdapter("okx")

        with patch("squant.infra.exchange.ccxt.rest_adapter.ccxt") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock()
            mock_ccxt.okx.return_value = mock_exchange

            await adapter.connect()

            mock_exchange.load_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Test connect when already connected does nothing."""
        adapter = CCXTRestAdapter("okx")
        adapter._connected = True

        # Should not raise
        await adapter.connect()

    @pytest.mark.asyncio
    async def test_connect_network_error_raises(self):
        """Test connect with network error raises ExchangeConnectionError."""
        adapter = CCXTRestAdapter("okx")

        with patch("squant.infra.exchange.ccxt.rest_adapter.ccxt") as mock_ccxt:
            import ccxt.async_support as ccxt_async

            mock_exchange = MagicMock()
            mock_exchange.load_markets = AsyncMock(
                side_effect=ccxt_async.NetworkError("Network error")
            )
            mock_ccxt.okx.return_value = mock_exchange
            mock_ccxt.NetworkError = ccxt_async.NetworkError
            mock_ccxt.ExchangeNotAvailable = ccxt_async.ExchangeNotAvailable

            with pytest.raises(ExchangeConnectionError):
                await adapter.connect()


class TestCCXTRestAdapterClose:
    """Tests for CCXTRestAdapter close method."""

    @pytest.mark.asyncio
    async def test_close_connected(self):
        """Test closing connected adapter."""
        adapter = CCXTRestAdapter("okx")
        mock_exchange = MagicMock()
        mock_exchange.close = AsyncMock()
        adapter._exchange = mock_exchange
        adapter._connected = True

        await adapter.close()

        # Verify close was called (using saved reference since adapter._exchange is now None)
        mock_exchange.close.assert_called_once()
        assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_close_not_connected(self):
        """Test closing when not connected."""
        adapter = CCXTRestAdapter("okx")

        # Should not raise
        await adapter.close()


class TestCCXTRestAdapterMarketData:
    """Tests for CCXTRestAdapter market data methods."""

    @pytest.fixture
    def connected_adapter(self):
        """Create a connected adapter with mocked exchange."""
        adapter = CCXTRestAdapter("okx")
        adapter._exchange = MagicMock()
        adapter._connected = True
        return adapter

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, connected_adapter):
        """Test get_ticker success."""
        connected_adapter._exchange.fetch_ticker = AsyncMock(
            return_value={
                "symbol": "BTC/USDT",
                "last": 50000.0,
                "bid": 49990.0,
                "ask": 50010.0,
                "high": 51000.0,
                "low": 49000.0,
                "baseVolume": 1000.0,
                "quoteVolume": 50000000.0,
                "open": 49000.0,
                "timestamp": 1704067200000,
            }
        )

        result = await connected_adapter.get_ticker("BTC/USDT")

        assert result.symbol == "BTC/USDT"
        assert result.last == Decimal("50000.0")

    @pytest.mark.asyncio
    async def test_get_ticker_not_connected_raises(self):
        """Test get_ticker when not connected raises error."""
        adapter = CCXTRestAdapter("okx")

        with pytest.raises(ExchangeConnectionError, match="not connected"):
            await adapter.get_ticker("BTC/USDT")

    @pytest.mark.asyncio
    async def test_get_tickers_success(self, connected_adapter):
        """Test get_tickers success."""
        connected_adapter._exchange.fetch_tickers = AsyncMock(
            return_value={
                "BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "last": 50000.0,
                    "timestamp": 1704067200000,
                },
                "ETH/USDT": {
                    "symbol": "ETH/USDT",
                    "last": 3000.0,
                    "timestamp": 1704067200000,
                },
            }
        )

        result = await connected_adapter.get_tickers()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_candlesticks_success(self, connected_adapter):
        """Test get_candlesticks success."""
        connected_adapter._exchange.fetch_ohlcv = AsyncMock(
            return_value=[
                [1704067200000, 50000.0, 51000.0, 49000.0, 50500.0, 100.0],
                [1704070800000, 50500.0, 51500.0, 50000.0, 51000.0, 150.0],
            ]
        )

        result = await connected_adapter.get_candlesticks("BTC/USDT", TimeFrame.H1, limit=2)

        assert len(result) == 2
        assert result[0].open == Decimal("50000.0")
        assert result[1].close == Decimal("51000.0")


class TestCCXTRestAdapterAccountMethods:
    """Tests for CCXTRestAdapter account methods."""

    @pytest.fixture
    def authenticated_adapter(self):
        """Create an authenticated adapter with mocked exchange."""
        creds = ExchangeCredentials(api_key="key", api_secret="secret")
        adapter = CCXTRestAdapter("okx", credentials=creds)
        adapter._exchange = MagicMock()
        adapter._connected = True
        return adapter

    @pytest.mark.asyncio
    async def test_get_balance_success(self, authenticated_adapter):
        """Test get_balance success."""
        authenticated_adapter._exchange.fetch_balance = AsyncMock(
            return_value={
                "free": {"BTC": 1.0, "USDT": 10000.0},
                "used": {"BTC": 0.5, "USDT": 5000.0},
            }
        )

        result = await authenticated_adapter.get_balance()

        assert result.exchange == "okx"
        assert len(result.balances) == 2

    @pytest.mark.asyncio
    async def test_get_balance_no_credentials_raises(self):
        """Test get_balance without credentials raises error."""
        adapter = CCXTRestAdapter("okx")
        adapter._exchange = MagicMock()
        adapter._connected = True

        with pytest.raises(ExchangeAuthenticationError, match="Credentials required"):
            await adapter.get_balance()


class TestCCXTRestAdapterOrderMethods:
    """Tests for CCXTRestAdapter order methods."""

    @pytest.fixture
    def authenticated_adapter(self):
        """Create an authenticated adapter with mocked exchange."""
        creds = ExchangeCredentials(api_key="key", api_secret="secret")
        adapter = CCXTRestAdapter("okx", credentials=creds)
        adapter._exchange = MagicMock()
        adapter._connected = True
        return adapter

    @pytest.mark.asyncio
    async def test_place_order_success(self, authenticated_adapter):
        """Test place_order success."""
        authenticated_adapter._exchange.create_order = AsyncMock(
            return_value={
                "id": "12345",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.1,
                "filled": 0.1,
                "status": "closed",
                "timestamp": 1704067200000,
            }
        )

        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        result = await authenticated_adapter.place_order(request)

        assert result.order_id == "12345"
        authenticated_adapter._exchange.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, authenticated_adapter):
        """Test cancel_order success."""
        authenticated_adapter._exchange.cancel_order = AsyncMock(
            return_value={
                "id": "12345",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": 0.1,
                "status": "canceled",
                "timestamp": 1704067200000,
            }
        )

        request = CancelOrderRequest(symbol="BTC/USDT", order_id="12345")

        result = await authenticated_adapter.cancel_order(request)

        assert result.order_id == "12345"

    @pytest.mark.asyncio
    async def test_get_order_success(self, authenticated_adapter):
        """Test get_order success."""
        authenticated_adapter._exchange.fetch_order = AsyncMock(
            return_value={
                "id": "12345",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": 0.1,
                "filled": 0.1,
                "status": "closed",
                "timestamp": 1704067200000,
            }
        )

        result = await authenticated_adapter.get_order("BTC/USDT", "12345")

        assert result.order_id == "12345"

    @pytest.mark.asyncio
    async def test_get_open_orders_success(self, authenticated_adapter):
        """Test get_open_orders success."""
        authenticated_adapter._exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    "id": "12345",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "type": "limit",
                    "amount": 0.1,
                    "status": "open",
                    "timestamp": 1704067200000,
                },
            ]
        )

        result = await authenticated_adapter.get_open_orders("BTC/USDT")

        assert len(result) == 1
        assert result[0].order_id == "12345"


class TestCCXTRestAdapterContextManager:
    """Tests for CCXTRestAdapter context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager calls connect and close."""
        adapter = CCXTRestAdapter("okx")
        adapter.connect = AsyncMock()
        adapter.close = AsyncMock()

        async with adapter:
            adapter.connect.assert_called_once()

        adapter.close.assert_called_once()


class TestCCXTRestAdapterExceptionHandling:
    """Tests for CCXT exception mapping across all REST methods."""

    @pytest.fixture
    def authenticated_adapter(self):
        """Create an authenticated adapter with mocked exchange."""
        creds = ExchangeCredentials(api_key="key", api_secret="secret")
        adapter = CCXTRestAdapter("okx", credentials=creds)
        adapter._exchange = MagicMock()
        adapter._connected = True
        return adapter

    # --- place_order exception tests ---

    @pytest.mark.asyncio
    async def test_place_order_insufficient_funds(self, authenticated_adapter):
        """Test place_order maps InsufficientFunds to InvalidOrderError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.create_order = AsyncMock(
            side_effect=ccxt_lib.InsufficientFunds("not enough balance")
        )
        request = OrderRequest(
            symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, amount=Decimal("1.0")
        )
        with pytest.raises(InvalidOrderError, match="Insufficient funds"):
            await authenticated_adapter.place_order(request)

    @pytest.mark.asyncio
    async def test_place_order_invalid_order(self, authenticated_adapter):
        """Test place_order maps InvalidOrder to InvalidOrderError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.create_order = AsyncMock(
            side_effect=ccxt_lib.InvalidOrder("bad order")
        )
        request = OrderRequest(
            symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, amount=Decimal("1.0")
        )
        with pytest.raises(InvalidOrderError, match="Invalid order"):
            await authenticated_adapter.place_order(request)

    @pytest.mark.asyncio
    async def test_place_order_rate_limit(self, authenticated_adapter):
        """Test place_order maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.create_order = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        request = OrderRequest(
            symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, amount=Decimal("1.0")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.place_order(request)

    @pytest.mark.asyncio
    async def test_place_order_auth_error(self, authenticated_adapter):
        """Test place_order maps AuthenticationError to ExchangeAuthenticationError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.create_order = AsyncMock(
            side_effect=ccxt_lib.AuthenticationError("invalid key")
        )
        request = OrderRequest(
            symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.MARKET, amount=Decimal("1.0")
        )
        with pytest.raises(ExchangeAuthenticationError, match="Authentication failed"):
            await authenticated_adapter.place_order(request)

    # --- cancel_order exception tests ---

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, authenticated_adapter):
        """Test cancel_order maps OrderNotFound to OrderNotFoundError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.cancel_order = AsyncMock(
            side_effect=ccxt_lib.OrderNotFound("no such order")
        )
        request = CancelOrderRequest(order_id="12345", symbol="BTC/USDT")
        with pytest.raises(OrderNotFoundError, match="Order not found"):
            await authenticated_adapter.cancel_order(request)

    @pytest.mark.asyncio
    async def test_cancel_order_rate_limit(self, authenticated_adapter):
        """Test cancel_order maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.cancel_order = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        request = CancelOrderRequest(order_id="12345", symbol="BTC/USDT")
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.cancel_order(request)

    # --- get_order exception tests ---

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, authenticated_adapter):
        """Test get_order maps OrderNotFound to OrderNotFoundError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_order = AsyncMock(
            side_effect=ccxt_lib.OrderNotFound("no such order")
        )
        with pytest.raises(OrderNotFoundError, match="Order not found"):
            await authenticated_adapter.get_order("BTC/USDT", "12345")

    @pytest.mark.asyncio
    async def test_get_order_rate_limit(self, authenticated_adapter):
        """Test get_order maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_order = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_order("BTC/USDT", "12345")

    # --- get_open_orders exception tests ---

    @pytest.mark.asyncio
    async def test_get_open_orders_rate_limit(self, authenticated_adapter):
        """Test get_open_orders maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_open_orders = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_open_orders("BTC/USDT")

    # --- get_balance exception tests ---

    @pytest.mark.asyncio
    async def test_get_balance_rate_limit(self, authenticated_adapter):
        """Test get_balance maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_balance = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_balance()

    @pytest.mark.asyncio
    async def test_get_balance_auth_error(self, authenticated_adapter):
        """Test get_balance maps AuthenticationError to ExchangeAuthenticationError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_balance = AsyncMock(
            side_effect=ccxt_lib.AuthenticationError("invalid key")
        )
        with pytest.raises(ExchangeAuthenticationError, match="Authentication failed"):
            await authenticated_adapter.get_balance()

    # --- get_ticker exception tests ---

    @pytest.mark.asyncio
    async def test_get_ticker_bad_symbol(self, authenticated_adapter):
        """Test get_ticker maps BadSymbol to ExchangeAPIError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_ticker = AsyncMock(
            side_effect=ccxt_lib.BadSymbol("invalid symbol")
        )
        with pytest.raises(ExchangeAPIError, match="Invalid symbol"):
            await authenticated_adapter.get_ticker("INVALID/PAIR")

    @pytest.mark.asyncio
    async def test_get_ticker_rate_limit(self, authenticated_adapter):
        """Test get_ticker maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_ticker = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_ticker("BTC/USDT")

    # --- get_tickers exception tests ---

    @pytest.mark.asyncio
    async def test_get_tickers_rate_limit(self, authenticated_adapter):
        """Test get_tickers maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.has = {"fetchTickers": True}
        authenticated_adapter._exchange.fetch_tickers = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_tickers(["BTC/USDT"])

    # --- get_candlesticks exception tests ---

    @pytest.mark.asyncio
    async def test_get_candlesticks_rate_limit(self, authenticated_adapter):
        """Test get_candlesticks maps RateLimitExceeded to ExchangeRateLimitError."""
        import ccxt.async_support as ccxt_lib

        authenticated_adapter._exchange.fetch_ohlcv = AsyncMock(
            side_effect=ccxt_lib.RateLimitExceeded("too many requests")
        )
        with pytest.raises(ExchangeRateLimitError, match="Rate limit exceeded"):
            await authenticated_adapter.get_candlesticks("BTC/USDT", TimeFrame.H1)


class TestCCXTRestAdapterPartialStatus:
    """Tests for PARTIAL order status detection in _map_order_status."""

    def test_open_with_partial_fill_returns_partial(self):
        """CCXT 'open' + filled > 0 should map to PARTIAL."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("open", filled=Decimal("0.5"), amount=Decimal("1.0"))
        assert result == OrderStatus.PARTIAL

    def test_open_without_fill_returns_submitted(self):
        """CCXT 'open' + filled == 0 should map to SUBMITTED."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("open", filled=Decimal("0"), amount=Decimal("1.0"))
        assert result == OrderStatus.SUBMITTED

    def test_open_fully_filled_returns_submitted(self):
        """CCXT 'open' + filled == amount should NOT be PARTIAL (edge case)."""
        adapter = CCXTRestAdapter("okx")
        # filled == amount means fully filled, but CCXT reports "open" — use SUBMITTED as fallback
        result = adapter._map_order_status("open", filled=Decimal("1.0"), amount=Decimal("1.0"))
        assert result == OrderStatus.SUBMITTED

    def test_closed_returns_filled(self):
        """CCXT 'closed' should always map to FILLED regardless of fill."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("closed", filled=Decimal("0.5"), amount=Decimal("1.0"))
        assert result == OrderStatus.FILLED

    def test_canceled_returns_cancelled(self):
        """CCXT 'canceled' should map to CANCELLED."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("canceled")
        assert result == OrderStatus.CANCELLED

    def test_expired_returns_cancelled(self):
        """CCXT 'expired' should map to CANCELLED."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("expired")
        assert result == OrderStatus.CANCELLED

    def test_rejected_returns_rejected(self):
        """CCXT 'rejected' should map to REJECTED."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("rejected")
        assert result == OrderStatus.REJECTED

    def test_unknown_status_defaults_to_submitted(self):
        """Unknown status should default to SUBMITTED."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("weird_status")
        assert result == OrderStatus.SUBMITTED

    def test_case_insensitive(self):
        """Status mapping should be case insensitive."""
        adapter = CCXTRestAdapter("okx")
        result = adapter._map_order_status("Open", filled=Decimal("0.3"), amount=Decimal("1.0"))
        assert result == OrderStatus.PARTIAL

    def test_transform_order_passes_filled_to_status_mapper(self):
        """_transform_order should pass filled/amount to _map_order_status for PARTIAL detection."""
        adapter = CCXTRestAdapter("okx")
        order_data = {
            "id": "123",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "amount": 1.0,
            "filled": 0.5,
            "status": "open",
            "timestamp": 1704067200000,
        }
        result = adapter._transform_order(order_data)
        assert result.status == OrderStatus.PARTIAL
