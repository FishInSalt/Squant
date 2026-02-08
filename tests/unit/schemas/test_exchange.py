"""Unit tests for exchange schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.schemas.exchange import (
    BalanceItem,
    BalanceResponse,
    CancelOrderRequest,
    CandlestickItem,
    CandlestickResponse,
    OpenOrdersResponse,
    OrderResponse,
    PlaceOrderRequest,
    TickerResponse,
)


class TestBalanceItem:
    """Tests for BalanceItem schema."""

    def test_valid_balance(self):
        """Test creating valid balance item."""
        balance = BalanceItem(
            currency="BTC",
            available=Decimal("1.5"),
            frozen=Decimal("0.5"),
            total=Decimal("2.0"),
        )

        assert balance.currency == "BTC"
        assert balance.available == Decimal("1.5")
        assert balance.frozen == Decimal("0.5")
        assert balance.total == Decimal("2.0")

    def test_zero_balance(self):
        """Test zero balance."""
        balance = BalanceItem(
            currency="ETH",
            available=Decimal("0"),
            frozen=Decimal("0"),
            total=Decimal("0"),
        )

        assert balance.available == Decimal("0")

    def test_currency_required(self):
        """Test currency is required."""
        with pytest.raises(ValidationError):
            BalanceItem(
                available=Decimal("1.0"),
                frozen=Decimal("0"),
                total=Decimal("1.0"),
            )


class TestBalanceResponse:
    """Tests for BalanceResponse schema."""

    def test_with_balances(self):
        """Test response with multiple balances."""
        now = datetime.now(UTC)
        response = BalanceResponse(
            exchange="okx",
            balances=[
                BalanceItem(
                    currency="BTC",
                    available=Decimal("1.0"),
                    frozen=Decimal("0"),
                    total=Decimal("1.0"),
                ),
                BalanceItem(
                    currency="USDT",
                    available=Decimal("10000"),
                    frozen=Decimal("500"),
                    total=Decimal("10500"),
                ),
            ],
            timestamp=now,
        )

        assert response.exchange == "okx"
        assert len(response.balances) == 2

    def test_empty_balances(self):
        """Test response with empty balances."""
        now = datetime.now(UTC)
        response = BalanceResponse(
            exchange="binance",
            balances=[],
            timestamp=now,
        )

        assert response.balances == []

    def test_total_usd_value_default_none(self):
        """Test total_usd_value defaults to None (AC-003)."""
        now = datetime.now(UTC)
        response = BalanceResponse(
            exchange="okx",
            balances=[],
            timestamp=now,
        )
        assert response.total_usd_value is None

    def test_total_usd_value_with_value(self):
        """Test total_usd_value can be set (AC-003)."""
        now = datetime.now(UTC)
        response = BalanceResponse(
            exchange="okx",
            balances=[],
            timestamp=now,
            total_usd_value=Decimal("50000.50"),
        )
        assert response.total_usd_value == Decimal("50000.50")
        data = response.model_dump(mode="json")
        assert isinstance(data["total_usd_value"], float)


class TestTickerResponse:
    """Tests for TickerResponse schema."""

    def test_full_ticker(self):
        """Test creating full ticker response."""
        now = datetime.now(UTC)
        ticker = TickerResponse(
            symbol="BTC/USDT",
            last=Decimal("50000"),
            bid=Decimal("49999"),
            ask=Decimal("50001"),
            high_24h=Decimal("51000"),
            low_24h=Decimal("49000"),
            volume_24h=Decimal("1000"),
            volume_quote_24h=Decimal("50000000"),
            change_24h=Decimal("500"),
            change_pct_24h=Decimal("1.01"),
            timestamp=now,
        )

        assert ticker.symbol == "BTC/USDT"
        assert ticker.last == Decimal("50000")
        assert ticker.bid == Decimal("49999")
        assert ticker.ask == Decimal("50001")

    def test_minimal_ticker(self):
        """Test minimal ticker with required fields only."""
        now = datetime.now(UTC)
        ticker = TickerResponse(
            symbol="ETH/USDT",
            last=Decimal("3000"),
            timestamp=now,
        )

        assert ticker.symbol == "ETH/USDT"
        assert ticker.bid is None
        assert ticker.ask is None
        assert ticker.high_24h is None

    def test_required_fields(self):
        """Test required fields validation."""
        with pytest.raises(ValidationError):
            TickerResponse(
                last=Decimal("50000"),
                timestamp=datetime.now(UTC),
            )


class TestCandlestickItem:
    """Tests for CandlestickItem schema."""

    def test_valid_candle(self):
        """Test creating valid candlestick."""
        now = datetime.now(UTC)
        candle = CandlestickItem(
            timestamp=now,
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49500"),
            close=Decimal("50500"),
            volume=Decimal("100"),
        )

        assert candle.open == Decimal("50000")
        assert candle.high == Decimal("51000")
        assert candle.low == Decimal("49500")
        assert candle.close == Decimal("50500")
        assert candle.volume == Decimal("100")

    def test_all_fields_required(self):
        """Test all fields are required."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            CandlestickItem(
                timestamp=now,
                open=Decimal("50000"),
                high=Decimal("51000"),
                # missing low, close, volume
            )


class TestCandlestickResponse:
    """Tests for CandlestickResponse schema."""

    def test_with_candles(self):
        """Test response with candles."""
        now = datetime.now(UTC)
        response = CandlestickResponse(
            symbol="BTC/USDT",
            timeframe="1h",
            candles=[
                CandlestickItem(
                    timestamp=now,
                    open=Decimal("50000"),
                    high=Decimal("51000"),
                    low=Decimal("49500"),
                    close=Decimal("50500"),
                    volume=Decimal("100"),
                ),
            ],
        )

        assert response.symbol == "BTC/USDT"
        assert response.timeframe == "1h"
        assert len(response.candles) == 1

    def test_empty_candles(self):
        """Test response with empty candles."""
        response = CandlestickResponse(
            symbol="ETH/USDT",
            timeframe="4h",
            candles=[],
        )

        assert response.candles == []


class TestPlaceOrderRequest:
    """Tests for PlaceOrderRequest schema."""

    def test_market_order(self):
        """Test creating market order."""
        order = PlaceOrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),
        )

        assert order.symbol == "BTC/USDT"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.amount == Decimal("0.1")
        assert order.price is None

    def test_limit_order(self):
        """Test creating limit order."""
        order = PlaceOrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            amount=Decimal("0.5"),
            price=Decimal("55000"),
        )

        assert order.side == OrderSide.SELL
        assert order.type == OrderType.LIMIT
        assert order.price == Decimal("55000")

    def test_with_client_order_id(self):
        """Test order with client order ID."""
        order = PlaceOrderRequest(
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("1.0"),
            price=Decimal("3000"),
            client_order_id="my-order-123",
        )

        assert order.client_order_id == "my-order-123"

    def test_amount_must_be_positive(self):
        """Test amount must be positive."""
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0"),
            )

        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("-0.1"),
            )

    def test_client_order_id_max_length(self):
        """Test client_order_id max length."""
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
                client_order_id="x" * 33,
            )

    def test_symbol_required(self):
        """Test symbol is required."""
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )


class TestOrderResponse:
    """Tests for OrderResponse schema."""

    def test_filled_order(self):
        """Test filled order response."""
        now = datetime.now(UTC)
        order = OrderResponse(
            order_id="12345",
            client_order_id="my-order",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            price=None,
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("50100"),
            created_at=now,
        )

        assert order.order_id == "12345"
        assert order.status == OrderStatus.FILLED
        assert order.filled == order.amount

    def test_pending_order(self):
        """Test pending order response."""
        order = OrderResponse(
            order_id="67890",
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            status=OrderStatus.PENDING,
            price=Decimal("3500"),
            amount=Decimal("1.0"),
            filled=Decimal("0"),
        )

        assert order.status == OrderStatus.PENDING
        assert order.filled == Decimal("0")
        assert order.client_order_id is None

    def test_partially_filled_order(self):
        """Test partially filled order response."""
        order = OrderResponse(
            order_id="11111",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.PARTIAL,
            price=Decimal("49000"),
            amount=Decimal("1.0"),
            filled=Decimal("0.3"),
            avg_price=Decimal("49010"),
        )

        assert order.status == OrderStatus.PARTIAL
        assert order.filled == Decimal("0.3")


class TestCancelOrderRequest:
    """Tests for CancelOrderRequest schema."""

    def test_cancel_by_order_id(self):
        """Test cancel by order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            order_id="12345",
        )

        assert request.symbol == "BTC/USDT"
        assert request.order_id == "12345"
        assert request.client_order_id is None

    def test_cancel_by_client_order_id(self):
        """Test cancel by client order ID."""
        request = CancelOrderRequest(
            symbol="BTC/USDT",
            client_order_id="my-order-123",
        )

        assert request.client_order_id == "my-order-123"
        assert request.order_id is None

    def test_symbol_required(self):
        """Test symbol is required."""
        with pytest.raises(ValidationError):
            CancelOrderRequest(
                order_id="12345",
            )


class TestOpenOrdersResponse:
    """Tests for OpenOrdersResponse schema."""

    def test_with_orders(self):
        """Test response with orders."""
        response = OpenOrdersResponse(
            orders=[
                OrderResponse(
                    order_id="1",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    status=OrderStatus.PENDING,
                    price=Decimal("48000"),
                    amount=Decimal("0.1"),
                    filled=Decimal("0"),
                ),
                OrderResponse(
                    order_id="2",
                    symbol="ETH/USDT",
                    side=OrderSide.SELL,
                    type=OrderType.LIMIT,
                    status=OrderStatus.PENDING,
                    price=Decimal("3500"),
                    amount=Decimal("1.0"),
                    filled=Decimal("0"),
                ),
            ],
            total=2,
        )

        assert len(response.orders) == 2
        assert response.total == 2

    def test_no_orders(self):
        """Test response with no orders."""
        response = OpenOrdersResponse(
            orders=[],
            total=0,
        )

        assert response.orders == []
        assert response.total == 0
