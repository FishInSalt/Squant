"""Unit tests for exchange types."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from squant.infra.exchange.types import (
    AccountBalance,
    Balance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
    WSMessageType,
)
from squant.models.enums import OrderSide, OrderStatus, OrderType


class TestTimeFrame:
    """Tests for TimeFrame enum."""

    def test_all_timeframes_exist(self):
        """Test all expected timeframes exist."""
        assert TimeFrame.M1 == "1m"
        assert TimeFrame.M5 == "5m"
        assert TimeFrame.M15 == "15m"
        assert TimeFrame.M30 == "30m"
        assert TimeFrame.H1 == "1h"
        assert TimeFrame.H4 == "4h"
        assert TimeFrame.D1 == "1d"
        assert TimeFrame.W1 == "1w"

    def test_timeframe_is_string_enum(self):
        """Test TimeFrame is string enum."""
        assert isinstance(TimeFrame.H1.value, str)
        assert TimeFrame.H1 == "1h"


class TestWSMessageType:
    """Tests for WSMessageType enum."""

    def test_all_message_types_exist(self):
        """Test all expected message types exist."""
        assert WSMessageType.TICKER == "ticker"
        assert WSMessageType.CANDLE == "candle"
        assert WSMessageType.TRADE == "trade"
        assert WSMessageType.ORDERBOOK == "orderbook"
        assert WSMessageType.ORDER_UPDATE == "order_update"
        assert WSMessageType.ACCOUNT_UPDATE == "account_update"
        assert WSMessageType.EXCHANGE_SWITCHING == "exchange_switching"


class TestBalance:
    """Tests for Balance model."""

    def test_create_balance(self):
        """Test creating a balance."""
        balance = Balance(
            currency="BTC",
            available=Decimal("1.5"),
            frozen=Decimal("0.5"),
        )

        assert balance.currency == "BTC"
        assert balance.available == Decimal("1.5")
        assert balance.frozen == Decimal("0.5")

    def test_balance_default_frozen(self):
        """Test balance default frozen value."""
        balance = Balance(currency="USDT", available=Decimal("1000"))

        assert balance.frozen == Decimal("0")

    def test_balance_total_property(self):
        """Test balance total property."""
        balance = Balance(
            currency="ETH",
            available=Decimal("2.0"),
            frozen=Decimal("0.5"),
        )

        assert balance.total == Decimal("2.5")

    def test_balance_total_with_zero_frozen(self):
        """Test balance total with zero frozen."""
        balance = Balance(currency="BTC", available=Decimal("1.0"))

        assert balance.total == Decimal("1.0")


class TestAccountBalance:
    """Tests for AccountBalance model."""

    def test_create_account_balance(self):
        """Test creating an account balance."""
        balances = [
            Balance(currency="BTC", available=Decimal("1.0")),
            Balance(currency="USDT", available=Decimal("10000")),
        ]
        account = AccountBalance(exchange="okx", balances=balances)

        assert account.exchange == "okx"
        assert len(account.balances) == 2

    def test_account_balance_default_empty(self):
        """Test account balance default empty balances."""
        account = AccountBalance(exchange="binance")

        assert account.balances == []

    def test_account_balance_has_timestamp(self):
        """Test account balance has timestamp."""
        account = AccountBalance(exchange="okx")

        assert account.timestamp is not None
        assert isinstance(account.timestamp, datetime)

    def test_get_balance_existing(self):
        """Test get_balance for existing currency."""
        btc_balance = Balance(currency="BTC", available=Decimal("1.5"))
        account = AccountBalance(exchange="okx", balances=[btc_balance])

        result = account.get_balance("BTC")

        assert result is not None
        assert result.currency == "BTC"
        assert result.available == Decimal("1.5")

    def test_get_balance_case_insensitive(self):
        """Test get_balance is case insensitive."""
        btc_balance = Balance(currency="BTC", available=Decimal("1.5"))
        account = AccountBalance(exchange="okx", balances=[btc_balance])

        result = account.get_balance("btc")

        assert result is not None
        assert result.currency == "BTC"

    def test_get_balance_not_found(self):
        """Test get_balance returns None when not found."""
        account = AccountBalance(exchange="okx", balances=[])

        result = account.get_balance("BTC")

        assert result is None


class TestTicker:
    """Tests for Ticker model."""

    def test_create_ticker_minimal(self):
        """Test creating ticker with minimal fields."""
        ticker = Ticker(symbol="BTC/USDT", last=Decimal("50000"))

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("50000")

    def test_create_ticker_full(self):
        """Test creating ticker with all fields."""
        ticker = Ticker(
            symbol="BTC/USDT",
            last=Decimal("50000"),
            bid=Decimal("49990"),
            ask=Decimal("50010"),
            high_24h=Decimal("51000"),
            low_24h=Decimal("49000"),
            volume_24h=Decimal("1000"),
            volume_quote_24h=Decimal("50000000"),
            change_24h=Decimal("1000"),
            change_pct_24h=Decimal("2.04"),
        )

        assert ticker.bid == Decimal("49990")
        assert ticker.ask == Decimal("50010")
        assert ticker.high_24h == Decimal("51000")
        assert ticker.low_24h == Decimal("49000")
        assert ticker.volume_24h == Decimal("1000")
        assert ticker.change_pct_24h == Decimal("2.04")

    def test_ticker_has_timestamp(self):
        """Test ticker has timestamp."""
        ticker = Ticker(symbol="ETH/USDT", last=Decimal("3000"))

        assert ticker.timestamp is not None

    def test_ticker_optional_fields_default_none(self):
        """Test ticker optional fields default to None."""
        ticker = Ticker(symbol="BTC/USDT", last=Decimal("50000"))

        assert ticker.bid is None
        assert ticker.ask is None
        assert ticker.high_24h is None


class TestCandlestick:
    """Tests for Candlestick model."""

    def test_create_candlestick(self):
        """Test creating a candlestick."""
        now = datetime.now(UTC)
        candle = Candlestick(
            timestamp=now,
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
        )

        assert candle.timestamp == now
        assert candle.open == Decimal("50000")
        assert candle.high == Decimal("51000")
        assert candle.low == Decimal("49000")
        assert candle.close == Decimal("50500")
        assert candle.volume == Decimal("100")

    def test_candlestick_with_quote_volume(self):
        """Test candlestick with quote volume."""
        candle = Candlestick(
            timestamp=datetime.now(UTC),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
            volume_quote=Decimal("5000000"),
        )

        assert candle.volume_quote == Decimal("5000000")

    def test_candlestick_volume_quote_optional(self):
        """Test candlestick volume_quote is optional."""
        candle = Candlestick(
            timestamp=datetime.now(UTC),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
        )

        assert candle.volume_quote is None


class TestOrderRequest:
    """Tests for OrderRequest model."""

    def test_create_market_order(self):
        """Test creating a market order request."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.amount == Decimal("0.1")

    def test_create_limit_order(self):
        """Test creating a limit order request."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=Decimal("0.5"),
            price=Decimal("55000"),
        )

        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("55000")

    def test_limit_order_requires_price(self):
        """Test limit order requires price."""
        with pytest.raises(ValueError, match="must have a price"):
            OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.1"),
            )

    def test_market_order_price_optional(self):
        """Test market order price is optional."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        assert order.price is None

    def test_order_with_client_order_id(self):
        """Test order with client order ID."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
            client_order_id="my-order-123",
        )

        assert order.client_order_id == "my-order-123"

    def test_order_amount_must_be_positive(self):
        """Test order amount must be positive."""
        with pytest.raises(ValueError):
            OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0"),
            )

    def test_order_amount_negative_fails(self):
        """Test negative amount fails."""
        with pytest.raises(ValueError):
            OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("-0.1"),
            )


class TestOrderResponse:
    """Tests for OrderResponse model."""

    def test_create_order_response(self):
        """Test creating an order response."""
        response = OrderResponse(
            order_id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50000"),
        )

        assert response.order_id == "12345"
        assert response.status == OrderStatus.FILLED
        assert response.filled == Decimal("0.1")

    def test_order_response_default_filled(self):
        """Test order response default filled is 0."""
        response = OrderResponse(
            order_id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.PENDING,
            amount=Decimal("0.1"),
        )

        assert response.filled == Decimal("0")

    def test_order_response_with_fee(self):
        """Test order response with fee."""
        response = OrderResponse(
            order_id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.1"),
            fee=Decimal("0.0001"),
            fee_currency="BTC",
        )

        assert response.fee == Decimal("0.0001")
        assert response.fee_currency == "BTC"

    def test_order_response_with_timestamps(self):
        """Test order response with timestamps."""
        now = datetime.now(UTC)
        response = OrderResponse(
            order_id="12345",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            amount=Decimal("0.1"),
            created_at=now,
            updated_at=now,
        )

        assert response.created_at == now
        assert response.updated_at == now


class TestCancelOrderRequest:
    """Tests for CancelOrderRequest model."""

    def test_create_cancel_with_order_id(self):
        """Test creating cancel request with order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id="12345",
        )

        assert request.symbol == "BTC/USDT"
        assert request.order_id == "12345"

    def test_create_cancel_with_client_order_id(self):
        """Test creating cancel request with client order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            client_order_id="my-order-123",
        )

        assert request.client_order_id == "my-order-123"

    def test_create_cancel_with_both_ids(self):
        """Test creating cancel request with both IDs."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id="12345",
            client_order_id="my-order-123",
        )

        assert request.order_id == "12345"
        assert request.client_order_id == "my-order-123"

    def test_cancel_requires_at_least_one_id(self):
        """Test cancel request requires at least one ID."""
        with pytest.raises(ValueError, match="Either order_id or client_order_id"):
            CancelOrderRequest(symbol="BTC/USDT")
