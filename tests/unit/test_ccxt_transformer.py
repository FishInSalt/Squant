"""Unit tests for CCXTDataTransformer."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer


class TestTickerTransformation:
    """Tests for ticker data transformation."""

    def test_ticker_to_ws_ticker_full_data(self) -> None:
        """Test converting a complete CCXT ticker to WSTicker."""
        ccxt_ticker = {
            "symbol": "BTC/USDT",
            "timestamp": 1704067200000,  # 2024-01-01 00:00:00 UTC
            "last": 42000.50,
            "bid": 42000.00,
            "ask": 42001.00,
            "bidVolume": 1.5,
            "askVolume": 2.0,
            "high": 43000.00,
            "low": 41000.00,
            "open": 41500.00,
            "baseVolume": 1000.0,
            "quoteVolume": 42000000.0,
        }

        result = CCXTDataTransformer.ticker_to_ws_ticker(ccxt_ticker)

        assert result.symbol == "BTC/USDT"
        assert result.last == Decimal("42000.5")
        assert result.bid == Decimal("42000.0")
        assert result.ask == Decimal("42001.0")
        assert result.bid_size == Decimal("1.5")
        assert result.ask_size == Decimal("2.0")
        assert result.high_24h == Decimal("43000.0")
        assert result.low_24h == Decimal("41000.0")
        assert result.open_24h == Decimal("41500.0")
        assert result.volume_24h == Decimal("1000.0")
        assert result.volume_quote_24h == Decimal("42000000.0")
        assert result.timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_ticker_to_ws_ticker_minimal_data(self) -> None:
        """Test converting a minimal CCXT ticker with only required fields."""
        ccxt_ticker = {
            "symbol": "ETH/USDT",
            "last": 2500.00,
            "timestamp": None,
        }

        result = CCXTDataTransformer.ticker_to_ws_ticker(ccxt_ticker)

        assert result.symbol == "ETH/USDT"
        assert result.last == Decimal("2500.0")
        assert result.bid is None
        assert result.ask is None
        assert result.timestamp is not None  # Should use current time

    def test_ticker_to_ws_ticker_none_values(self) -> None:
        """Test that None values are handled correctly."""
        ccxt_ticker = {
            "symbol": "SOL/USDT",
            "last": 100.00,
            "bid": None,
            "ask": None,
            "bidVolume": None,
            "askVolume": None,
            "high": None,
            "low": None,
            "open": None,
            "baseVolume": None,
            "quoteVolume": None,
            "timestamp": 1704067200000,
        }

        result = CCXTDataTransformer.ticker_to_ws_ticker(ccxt_ticker)

        assert result.symbol == "SOL/USDT"
        assert result.last == Decimal("100.0")
        assert result.bid is None
        assert result.ask is None


class TestOHLCVTransformation:
    """Tests for OHLCV/candle data transformation."""

    def test_ohlcv_to_ws_candle(self) -> None:
        """Test converting CCXT OHLCV array to WSCandle."""
        ohlcv = [
            1704067200000,  # timestamp
            42000.0,        # open
            43000.0,        # high
            41500.0,        # low
            42500.0,        # close
            1000.0,         # volume
        ]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(
            ohlcv, "BTC/USDT", "1h", is_closed=True
        )

        assert result.symbol == "BTC/USDT"
        assert result.timeframe == "1h"
        assert result.timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert result.open == Decimal("42000.0")
        assert result.high == Decimal("43000.0")
        assert result.low == Decimal("41500.0")
        assert result.close == Decimal("42500.0")
        assert result.volume == Decimal("1000.0")
        assert result.is_closed is True

    def test_ohlcv_to_ws_candle_not_closed(self) -> None:
        """Test converting an unclosed candle."""
        ohlcv = [1704067200000, 100.0, 105.0, 98.0, 102.0, 500.0]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(
            ohlcv, "ETH/USDT", "5m", is_closed=False
        )

        assert result.is_closed is False
        assert result.timeframe == "5m"

    def test_ohlcv_to_ws_candle_none_volume(self) -> None:
        """Test handling None volume value."""
        ohlcv = [1704067200000, 100.0, 105.0, 98.0, 102.0, None]

        result = CCXTDataTransformer.ohlcv_to_ws_candle(
            ohlcv, "SOL/USDT", "1m", is_closed=False
        )

        assert result.volume == Decimal("0")

    def test_ohlcv_to_ws_candle_invalid_length(self) -> None:
        """Test that short OHLCV array raises ValueError."""
        ohlcv_short = [1704067200000, 100.0, 105.0]  # Only 3 elements

        with pytest.raises(ValueError, match="Invalid OHLCV array length"):
            CCXTDataTransformer.ohlcv_to_ws_candle(
                ohlcv_short, "BTC/USDT", "1h", is_closed=False
            )

    def test_ohlcv_to_ws_candle_empty_array(self) -> None:
        """Test that empty OHLCV array raises ValueError."""
        with pytest.raises(ValueError, match="Invalid OHLCV array length"):
            CCXTDataTransformer.ohlcv_to_ws_candle(
                [], "BTC/USDT", "1h", is_closed=False
            )


class TestTradeTransformation:
    """Tests for trade data transformation."""

    def test_trade_to_ws_trade(self) -> None:
        """Test converting CCXT trade to WSTrade."""
        ccxt_trade = {
            "id": "12345",
            "timestamp": 1704067200000,
            "symbol": "BTC/USDT",
            "side": "buy",
            "price": 42000.0,
            "amount": 0.5,
        }

        result = CCXTDataTransformer.trade_to_ws_trade(ccxt_trade)

        assert result.trade_id == "12345"
        assert result.symbol == "BTC/USDT"
        assert result.side == "buy"
        assert result.price == Decimal("42000.0")
        assert result.size == Decimal("0.5")
        assert result.timestamp == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_trade_to_ws_trade_sell_side(self) -> None:
        """Test converting a sell trade."""
        ccxt_trade = {
            "id": "67890",
            "timestamp": 1704067200000,
            "symbol": "ETH/USDT",
            "side": "SELL",  # Uppercase to test normalization
            "price": 2500.0,
            "amount": 1.0,
        }

        result = CCXTDataTransformer.trade_to_ws_trade(ccxt_trade)

        assert result.side == "sell"


class TestOrderBookTransformation:
    """Tests for order book data transformation."""

    def test_orderbook_to_ws_orderbook(self) -> None:
        """Test converting CCXT orderbook to WSOrderBook."""
        ccxt_orderbook = {
            "timestamp": 1704067200000,
            "nonce": 12345,
            "bids": [
                [42000.0, 1.0],
                [41999.0, 2.0],
                [41998.0, 3.0],
            ],
            "asks": [
                [42001.0, 0.5],
                [42002.0, 1.5],
                [42003.0, 2.5],
            ],
        }

        result = CCXTDataTransformer.orderbook_to_ws_orderbook(
            ccxt_orderbook, "BTC/USDT", limit=3
        )

        assert result.symbol == "BTC/USDT"
        assert len(result.bids) == 3
        assert len(result.asks) == 3
        assert result.bids[0].price == Decimal("42000.0")
        assert result.bids[0].size == Decimal("1.0")
        assert result.asks[0].price == Decimal("42001.0")
        assert result.asks[0].size == Decimal("0.5")
        assert result.checksum == 12345

    def test_orderbook_to_ws_orderbook_with_limit(self) -> None:
        """Test that limit parameter restricts the number of levels."""
        ccxt_orderbook = {
            "timestamp": 1704067200000,
            "bids": [[42000.0 - i, 1.0] for i in range(10)],
            "asks": [[42001.0 + i, 1.0] for i in range(10)],
        }

        result = CCXTDataTransformer.orderbook_to_ws_orderbook(
            ccxt_orderbook, "BTC/USDT", limit=5
        )

        assert len(result.bids) == 5
        assert len(result.asks) == 5


class TestOrderTransformation:
    """Tests for order data transformation."""

    def test_order_to_ws_order_update(self) -> None:
        """Test converting CCXT order to WSOrderUpdate."""
        ccxt_order = {
            "id": "order-123",
            "clientOrderId": "client-456",
            "timestamp": 1704067200000,
            "lastTradeTimestamp": 1704067201000,
            "symbol": "BTC/USDT",
            "type": "limit",
            "side": "buy",
            "price": 42000.0,
            "amount": 0.1,
            "filled": 0.05,
            "status": "open",
            "average": 41999.0,
            "fee": {"cost": 0.01, "currency": "USDT"},
        }

        result = CCXTDataTransformer.order_to_ws_order_update(ccxt_order)

        assert result.order_id == "order-123"
        assert result.client_order_id == "client-456"
        assert result.symbol == "BTC/USDT"
        assert result.order_type == "limit"
        assert result.side == "buy"
        assert result.price == Decimal("42000.0")
        assert result.size == Decimal("0.1")
        assert result.filled_size == Decimal("0.05")
        assert result.status == "submitted"  # 'open' maps to 'submitted'
        assert result.avg_price == Decimal("41999.0")
        assert result.fee == Decimal("0.01")
        assert result.fee_currency == "USDT"

    def test_order_status_mapping(self) -> None:
        """Test that order statuses are mapped correctly."""
        status_tests = [
            ("open", "submitted"),
            ("closed", "filled"),
            ("canceled", "cancelled"),
            ("expired", "cancelled"),
            ("rejected", "rejected"),
        ]

        for ccxt_status, expected_status in status_tests:
            ccxt_order = {
                "id": "test",
                "symbol": "BTC/USDT",
                "type": "market",
                "side": "buy",
                "amount": 0.1,
                "status": ccxt_status,
            }
            result = CCXTDataTransformer.order_to_ws_order_update(ccxt_order)
            assert result.status == expected_status, f"Failed for {ccxt_status}"


class TestBalanceTransformation:
    """Tests for balance/account data transformation."""

    def test_balance_to_ws_account_update(self) -> None:
        """Test converting CCXT balance to WSAccountUpdate."""
        ccxt_balance = {
            "timestamp": 1704067200000,
            "free": {"BTC": 1.0, "USDT": 10000.0, "ETH": 0.0},
            "used": {"BTC": 0.5, "USDT": 5000.0, "ETH": 0.0},
        }

        result = CCXTDataTransformer.balance_to_ws_account_update(ccxt_balance)

        assert len(result.balances) == 2  # ETH should be excluded (zero balance)

        btc_balance = next((b for b in result.balances if b.currency == "BTC"), None)
        assert btc_balance is not None
        assert btc_balance.available == Decimal("1.0")
        assert btc_balance.frozen == Decimal("0.5")

        usdt_balance = next((b for b in result.balances if b.currency == "USDT"), None)
        assert usdt_balance is not None
        assert usdt_balance.available == Decimal("10000.0")
        assert usdt_balance.frozen == Decimal("5000.0")

    def test_balance_to_ws_account_update_only_used(self) -> None:
        """Test that currencies only in used_balances are included."""
        ccxt_balance = {
            "timestamp": 1704067200000,
            "free": {"BTC": 1.0},
            "used": {"BTC": 0.5, "ETH": 2.0},  # ETH only in used
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


class TestTimestampParsing:
    """Tests for timestamp parsing."""

    def test_parse_timestamp_valid(self) -> None:
        """Test parsing a valid timestamp."""
        result = CCXTDataTransformer._parse_timestamp(1704067200000)

        assert result == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_parse_timestamp_none(self) -> None:
        """Test parsing None timestamp returns current time."""
        before = datetime.now(UTC)
        result = CCXTDataTransformer._parse_timestamp(None)
        after = datetime.now(UTC)

        assert before <= result <= after
