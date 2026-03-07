"""Unit tests for Binance WebSocket client."""

from datetime import UTC, datetime
from decimal import Decimal

from squant.infra.exchange.binance.ws_client import (
    BinanceWebSocketClient,
    _from_binance_symbol,
    _to_binance_symbol,
)
from squant.infra.exchange.binance.ws_types import (
    KLINE_INTERVALS,
    BinanceCandle,
    BinanceOrderBook,
    BinanceTicker,
    BinanceTrade,
)


class TestSymbolConversion:
    """Tests for symbol conversion functions."""

    def test_to_binance_symbol(self):
        """Test converting standard symbol to Binance format."""
        assert _to_binance_symbol("BTC/USDT") == "btcusdt"
        assert _to_binance_symbol("ETH/BTC") == "ethbtc"
        assert _to_binance_symbol("SOL/USDC") == "solusdc"

    def test_from_binance_symbol(self):
        """Test converting Binance symbol to standard format."""
        assert _from_binance_symbol("btcusdt") == "BTC/USDT"
        assert _from_binance_symbol("ETHBTC") == "ETH/BTC"
        assert _from_binance_symbol("solusdc") == "SOL/USDC"
        assert _from_binance_symbol("bnbbusd") == "BNB/BUSD"


class TestBinanceWebSocketClient:
    """Tests for BinanceWebSocketClient."""

    def test_init(self):
        """Test client initialization."""
        client = BinanceWebSocketClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )
        assert client.api_key == "test_key"
        assert client.api_secret == "test_secret"
        assert client.testnet is True
        assert client.private is False
        assert not client.is_connected

    def test_base_url(self):
        """Test base URL selection."""
        mainnet_client = BinanceWebSocketClient(testnet=False)
        assert mainnet_client.base_url == "wss://stream.binance.com:9443"

        testnet_client = BinanceWebSocketClient(testnet=True)
        assert testnet_client.base_url == "wss://testnet.binance.vision"

    def test_build_stream_url_with_subscriptions(self):
        """Test stream URL building with subscriptions."""
        client = BinanceWebSocketClient(testnet=False)
        client._subscriptions = {"btcusdt@ticker", "ethusdt@ticker"}

        url = client._build_stream_url()
        assert "stream.binance.com" in url
        assert "streams=" in url
        assert "btcusdt@ticker" in url
        assert "ethusdt@ticker" in url

    def test_build_stream_url_private(self):
        """Test stream URL building for private streams."""
        client = BinanceWebSocketClient(
            api_key="test_key",
            api_secret="test_secret",
            testnet=False,
            private=True,
        )
        client._listen_key = "test_listen_key"

        url = client._build_stream_url()
        assert url == "wss://stream.binance.com:9443/ws/test_listen_key"

    def test_add_remove_handler(self):
        """Test adding and removing message handlers."""
        client = BinanceWebSocketClient()

        async def test_handler(msg):
            pass

        client.add_handler(test_handler)
        assert test_handler in client._handlers

        client.remove_handler(test_handler)
        assert test_handler not in client._handlers

    def test_parse_ticker(self):
        """Test ticker data parsing."""
        client = BinanceWebSocketClient()

        raw_data = {
            "e": "24hrTicker",
            "E": 1704067200000,
            "s": "BTCUSDT",
            "c": "42000.50",
            "b": "42000.00",
            "a": "42001.00",
            "B": "1.5",
            "A": "2.0",
            "h": "43000.00",
            "l": "41000.00",
            "v": "1234.56",
            "q": "51851040.00",
            "o": "41500.00",
            "p": "500.50",
            "P": "1.21",
        }

        parsed = client._parse_ticker(raw_data, "BTC/USDT")

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["last"] == Decimal("42000.50")
        assert parsed["bid"] == Decimal("42000.00")
        assert parsed["ask"] == Decimal("42001.00")
        assert parsed["high_24h"] == Decimal("43000.00")
        assert parsed["low_24h"] == Decimal("41000.00")
        assert parsed["volume_24h"] == Decimal("1234.56")

    def test_parse_kline(self):
        """Test kline/candlestick data parsing."""
        client = BinanceWebSocketClient()

        raw_data = {
            "e": "kline",
            "E": 1704067200000,
            "s": "BTCUSDT",
            "k": {
                "t": 1704067200000,
                "o": "42000.00",
                "h": "42500.00",
                "l": "41800.00",
                "c": "42300.00",
                "v": "100.5",
                "q": "4221150.00",
                "n": 1500,
                "x": True,
            },
        }

        parsed = client._parse_kline(raw_data, "BTC/USDT", "1m")

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["timeframe"] == "1m"
        assert parsed["open"] == Decimal("42000.00")
        assert parsed["high"] == Decimal("42500.00")
        assert parsed["low"] == Decimal("41800.00")
        assert parsed["close"] == Decimal("42300.00")
        assert parsed["volume"] == Decimal("100.5")
        assert parsed["trades"] == 1500
        assert parsed["is_closed"] is True

    def test_parse_trade(self):
        """Test trade data parsing."""
        client = BinanceWebSocketClient()

        raw_data = {
            "e": "trade",
            "E": 1704067200000,
            "s": "BTCUSDT",
            "t": 123456789,
            "p": "42000.50",
            "q": "0.1",
            "T": 1704067200000,
            "m": False,
        }

        parsed = client._parse_trade(raw_data, "BTC/USDT")

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["trade_id"] == "123456789"
        assert parsed["price"] == Decimal("42000.50")
        assert parsed["size"] == Decimal("0.1")
        assert parsed["side"] == "buy"
        assert parsed["buyer_is_maker"] is False

    def test_parse_depth(self):
        """Test order book depth parsing."""
        client = BinanceWebSocketClient()

        raw_data = {
            "lastUpdateId": 123456789,
            "bids": [
                ["42000.00", "1.5"],
                ["41999.00", "2.0"],
            ],
            "asks": [
                ["42001.00", "1.0"],
                ["42002.00", "1.5"],
            ],
        }

        parsed = client._parse_depth(raw_data, "BTC/USDT")

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["last_update_id"] == 123456789
        assert len(parsed["bids"]) == 2
        assert len(parsed["asks"]) == 2
        assert parsed["bids"][0]["price"] == Decimal("42000.00")
        assert parsed["bids"][0]["size"] == Decimal("1.5")

    def test_parse_order_update(self):
        """Test order update parsing from user data stream."""
        client = BinanceWebSocketClient()

        raw_data = {
            "e": "executionReport",
            "E": 1704067200000,
            "s": "BTCUSDT",
            "c": "my_client_order_1",
            "S": "BUY",
            "o": "LIMIT",
            "f": "GTC",
            "q": "0.1",
            "p": "42000.00",
            "X": "FILLED",
            "i": 12345678,
            "z": "0.1",
            "Z": "4200.00",
            "L": "42000.00",
            "l": "0.1",
            "n": "0.001",
            "N": "BNB",
            "t": 98765,
            "O": 1704067100000,
            "T": 1704067200000,
        }

        parsed = client._parse_order_update(raw_data)

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["order_id"] == "12345678"
        assert parsed["client_order_id"] == "my_client_order_1"
        assert parsed["side"] == "BUY"
        assert parsed["order_type"] == "LIMIT"
        assert parsed["status"] == "FILLED"
        assert parsed["quantity"] == Decimal("0.1")
        assert parsed["filled_quantity"] == Decimal("0.1")

    def test_parse_account_update(self):
        """Test account update parsing from user data stream."""
        client = BinanceWebSocketClient()

        raw_data = {
            "e": "outboundAccountPosition",
            "E": 1704067200000,
            "u": 1704067200000,
            "B": [
                {"a": "BTC", "f": "1.5", "l": "0.1"},
                {"a": "USDT", "f": "10000.0", "l": "0"},
            ],
        }

        parsed = client._parse_account_update(raw_data)

        assert len(parsed["balances"]) == 2
        assert parsed["balances"][0]["asset"] == "BTC"
        assert parsed["balances"][0]["free"] == Decimal("1.5")
        assert parsed["balances"][0]["locked"] == Decimal("0.1")


class TestKlineIntervals:
    """Tests for kline interval constants."""

    def test_kline_intervals(self):
        """Test that common kline intervals are defined."""
        assert "1m" in KLINE_INTERVALS
        assert "5m" in KLINE_INTERVALS
        assert "15m" in KLINE_INTERVALS
        assert "1h" in KLINE_INTERVALS
        assert "4h" in KLINE_INTERVALS
        assert "1d" in KLINE_INTERVALS
        assert "1w" in KLINE_INTERVALS


class TestWebSocketTypes:
    """Tests for WebSocket type models."""

    def test_binance_ticker_model(self):
        """Test BinanceTicker model."""
        ticker = BinanceTicker(
            symbol="BTC/USDT",
            last=Decimal("42000.50"),
            bid=Decimal("42000.00"),
            ask=Decimal("42001.00"),
        )
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("42000.50")

    def test_binance_candle_model(self):
        """Test BinanceCandle model."""
        candle = BinanceCandle(
            symbol="BTC/USDT",
            timeframe="1m",
            timestamp=datetime.now(UTC),
            open=Decimal("42000.00"),
            high=Decimal("42500.00"),
            low=Decimal("41800.00"),
            close=Decimal("42300.00"),
            volume=Decimal("100.5"),
        )
        assert candle.symbol == "BTC/USDT"
        assert candle.timeframe == "1m"

    def test_binance_trade_model(self):
        """Test BinanceTrade model."""
        trade = BinanceTrade(
            symbol="BTC/USDT",
            trade_id="123456",
            price=Decimal("42000.50"),
            size=Decimal("0.1"),
            side="buy",
            timestamp=datetime.now(UTC),
        )
        assert trade.symbol == "BTC/USDT"
        assert trade.price == Decimal("42000.50")

    def test_binance_orderbook_model(self):
        """Test BinanceOrderBook model."""
        orderbook = BinanceOrderBook(
            symbol="BTC/USDT",
            bids=[],
            asks=[],
        )
        assert orderbook.symbol == "BTC/USDT"
