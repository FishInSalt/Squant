"""Unit tests for exchange API endpoints."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from squant.api.deps import get_okx_exchange
from squant.infra.exchange import (
    AccountBalance,
    Balance,
    Candlestick,
    Ticker,
    TimeFrame,
)
from squant.infra.exchange import (
    OrderResponse as ExchangeOrderResponse,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.main import app
from squant.models.enums import OrderSide, OrderStatus, OrderType


@pytest.fixture
def mock_exchange() -> AsyncMock:
    """Create mock OKX exchange."""
    return AsyncMock()


@pytest.fixture
def client(mock_exchange: AsyncMock) -> TestClient:
    """Create test client with mocked exchange."""
    app.dependency_overrides[get_okx_exchange] = lambda: mock_exchange
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestBalanceEndpoints:
    """Tests for balance endpoints."""

    def test_get_balance(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting account balance."""
        mock_exchange.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="BTC", available=Decimal("1.5"), frozen=Decimal("0.5")),
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
            ],
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        response = client.get("/api/v1/exchange/balance")

        assert response.status_code == 200
        data = response.json()
        assert data["exchange"] == "okx"
        assert len(data["balances"]) == 2
        assert data["balances"][0]["currency"] == "BTC"
        assert data["balances"][0]["available"] == "1.5"
        assert Decimal(data["balances"][0]["total"]) == Decimal("2")

    def test_get_balance_currency(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting balance for specific currency."""
        mock_exchange.get_balance_currency.return_value = Balance(
            currency="BTC",
            available=Decimal("1.5"),
            frozen=Decimal("0.5"),
        )

        response = client.get("/api/v1/exchange/balance/BTC")

        assert response.status_code == 200
        data = response.json()
        assert data["currency"] == "BTC"
        assert data["available"] == "1.5"

    def test_get_balance_currency_not_found(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting balance for non-existent currency."""
        mock_exchange.get_balance_currency.return_value = None

        response = client.get("/api/v1/exchange/balance/XYZ")

        assert response.status_code == 200
        assert response.json() is None

    def test_get_balance_auth_error(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test balance endpoint with authentication error."""
        mock_exchange.get_balance.side_effect = ExchangeAuthenticationError(
            message="Invalid API key", exchange="okx"
        )

        response = client.get("/api/v1/exchange/balance")

        assert response.status_code == 401


class TestTickerEndpoints:
    """Tests for ticker endpoints."""

    def test_get_ticker(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting ticker data."""
        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT",
            last=Decimal("42000.5"),
            bid=Decimal("41999"),
            ask=Decimal("42001"),
            high_24h=Decimal("43000"),
            low_24h=Decimal("41000"),
            volume_24h=Decimal("1000"),
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        response = client.get("/api/v1/exchange/ticker/BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["last"] == "42000.5"
        assert data["bid"] == "41999"

    def test_get_tickers(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting multiple tickers."""
        mock_exchange.get_tickers.return_value = [
            Ticker(
                symbol="BTC/USDT",
                last=Decimal("42000"),
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
            Ticker(
                symbol="ETH/USDT",
                last=Decimal("2500"),
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
        ]

        response = client.get("/api/v1/exchange/tickers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_tickers_filtered(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting tickers with filter."""
        mock_exchange.get_tickers.return_value = [
            Ticker(
                symbol="BTC/USDT",
                last=Decimal("42000"),
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
        ]

        response = client.get("/api/v1/exchange/tickers?symbols=BTC/USDT")

        assert response.status_code == 200
        mock_exchange.get_tickers.assert_called_once_with(["BTC/USDT"])


class TestCandlestickEndpoints:
    """Tests for candlestick endpoints."""

    def test_get_candles(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting candlestick data."""
        mock_exchange.get_candlesticks.return_value = [
            Candlestick(
                timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                open=Decimal("42000"),
                high=Decimal("42500"),
                low=Decimal("41500"),
                close=Decimal("42300"),
                volume=Decimal("100"),
            ),
            Candlestick(
                timestamp=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                open=Decimal("42300"),
                high=Decimal("42800"),
                low=Decimal("42100"),
                close=Decimal("42600"),
                volume=Decimal("120"),
            ),
        ]

        response = client.get("/api/v1/exchange/candles/BTC/USDT?timeframe=1h&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["timeframe"] == "1h"
        assert len(data["candles"]) == 2
        mock_exchange.get_candlesticks.assert_called_once_with(
            "BTC/USDT", TimeFrame.H1, limit=2
        )

    def test_get_candles_invalid_timeframe(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting candles with invalid timeframe."""
        response = client.get("/api/v1/exchange/candles/BTC/USDT?timeframe=invalid")

        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]


class TestOrderEndpoints:
    """Tests for order endpoints."""

    def test_place_order(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test placing an order."""
        mock_exchange.place_order.return_value = ExchangeOrderResponse(
            order_id="123456",
            client_order_id="my-order-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            price=Decimal("42000"),
            amount=Decimal("0.1"),
            filled=Decimal("0"),
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        response = client.post(
            "/api/v1/exchange/orders",
            json={
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "amount": "0.1",
                "price": "42000",
                "client_order_id": "my-order-1",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["order_id"] == "123456"
        assert data["status"] == "submitted"

    def test_place_order_invalid(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test placing an invalid order."""
        mock_exchange.place_order.side_effect = InvalidOrderError(
            message="Insufficient balance", exchange="okx"
        )

        response = client.post(
            "/api/v1/exchange/orders",
            json={
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "market",
                "amount": "1000000",
            },
        )

        assert response.status_code == 400

    def test_cancel_order(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test cancelling an order."""
        mock_exchange.cancel_order.return_value = ExchangeOrderResponse(
            order_id="123456",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            amount=Decimal("0.1"),
            filled=Decimal("0"),
        )

        response = client.post(
            "/api/v1/exchange/orders/cancel",
            json={
                "symbol": "BTC/USDT",
                "order_id": "123456",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_order_not_found(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test cancelling non-existent order."""
        mock_exchange.cancel_order.side_effect = OrderNotFoundError(
            message="Order not found", exchange="okx", order_id="invalid"
        )

        response = client.post(
            "/api/v1/exchange/orders/cancel",
            json={
                "symbol": "BTC/USDT",
                "order_id": "invalid",
            },
        )

        assert response.status_code == 404

    def test_cancel_order_missing_id(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test cancelling order without ID."""
        response = client.post(
            "/api/v1/exchange/orders/cancel",
            json={
                "symbol": "BTC/USDT",
            },
        )

        assert response.status_code == 400

    def test_get_order(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting order details."""
        mock_exchange.get_order.return_value = ExchangeOrderResponse(
            order_id="123456",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            price=Decimal("42000"),
            amount=Decimal("0.1"),
            filled=Decimal("0.1"),
            avg_price=Decimal("41999.5"),
        )

        response = client.get("/api/v1/exchange/orders/123456?symbol=BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "123456"
        assert data["status"] == "filled"
        assert data["filled"] == "0.1"

    def test_get_open_orders(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test getting open orders."""
        mock_exchange.get_open_orders.return_value = [
            ExchangeOrderResponse(
                order_id="order-1",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                status=OrderStatus.SUBMITTED,
                amount=Decimal("0.1"),
                filled=Decimal("0"),
            ),
            ExchangeOrderResponse(
                order_id="order-2",
                symbol="ETH/USDT",
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                status=OrderStatus.PARTIAL,
                amount=Decimal("1"),
                filled=Decimal("0.5"),
            ),
        ]

        response = client.get("/api/v1/exchange/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["orders"]) == 2

    def test_get_open_orders_filtered(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting open orders with symbol filter."""
        mock_exchange.get_open_orders.return_value = []

        response = client.get("/api/v1/exchange/orders?symbol=BTC/USDT")

        assert response.status_code == 200
        mock_exchange.get_open_orders.assert_called_once_with("BTC/USDT")


class TestErrorHandling:
    """Tests for error handling."""

    def test_rate_limit_error(
        self, client: TestClient, mock_exchange: AsyncMock
    ) -> None:
        """Test rate limit error response."""
        mock_exchange.get_ticker.side_effect = ExchangeRateLimitError(
            message="Rate limit exceeded", exchange="okx", retry_after=5.0
        )

        response = client.get("/api/v1/exchange/ticker/BTC/USDT")

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "5"

    def test_api_error(self, client: TestClient, mock_exchange: AsyncMock) -> None:
        """Test API error response."""
        mock_exchange.get_ticker.side_effect = ExchangeAPIError(
            message="Internal error", exchange="okx", code="50000"
        )

        response = client.get("/api/v1/exchange/ticker/BTC/USDT")

        assert response.status_code == 502
