"""Unit tests for market and account API endpoints.

These tests use httpx.AsyncClient with pytest-asyncio to properly test
async endpoints with mocked async dependencies.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from squant.api.deps import get_exchange, get_okx_exchange
from squant.infra.exchange import (
    AccountBalance,
    Balance,
    Candlestick,
    Ticker,
    TimeFrame,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeRateLimitError,
)
from squant.main import app


@pytest.fixture
def mock_exchange() -> AsyncMock:
    """Create mock OKX exchange."""
    return AsyncMock()


@pytest.fixture
async def client(mock_exchange: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked exchange.

    Properly overrides async generator dependencies using httpx.AsyncClient.
    Overrides both get_okx_exchange and get_exchange to handle both account
    and market endpoints.
    """

    async def override_get_okx_exchange() -> AsyncGenerator[AsyncMock, None]:
        """Override dependency with async generator that yields the mock."""
        yield mock_exchange

    async def override_get_exchange() -> AsyncGenerator[AsyncMock, None]:
        """Override dependency with async generator that yields the mock."""
        yield mock_exchange

    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange
    app.dependency_overrides[get_exchange] = override_get_exchange

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestAccountBalanceEndpoints:
    """Tests for account balance endpoints."""

    @pytest.mark.asyncio
    async def test_get_balance(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
        """Test getting account balance."""
        mock_exchange.get_balance.return_value = AccountBalance(
            exchange="okx",
            balances=[
                Balance(currency="BTC", available=Decimal("1.5"), frozen=Decimal("0.5")),
                Balance(currency="USDT", available=Decimal("10000"), frozen=Decimal("0")),
            ],
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        assert json_resp["message"] == "success"
        data = json_resp["data"]
        assert data["exchange"] == "okx"
        assert len(data["balances"]) == 2
        assert data["balances"][0]["currency"] == "BTC"
        assert data["balances"][0]["available"] == "1.5"
        assert Decimal(data["balances"][0]["total"]) == Decimal("2")

    @pytest.mark.asyncio
    async def test_get_balance_currency(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting balance for specific currency."""
        mock_exchange.get_balance_currency.return_value = Balance(
            currency="BTC",
            available=Decimal("1.5"),
            frozen=Decimal("0.5"),
        )

        response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        data = json_resp["data"]
        assert data["currency"] == "BTC"
        assert data["available"] == "1.5"

    @pytest.mark.asyncio
    async def test_get_balance_currency_not_found(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting balance for non-existent currency."""
        mock_exchange.get_balance_currency.return_value = None

        response = await client.get("/api/v1/account/balance/XYZ")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        assert json_resp["data"] is None

    @pytest.mark.asyncio
    async def test_get_balance_auth_error(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test balance endpoint with authentication error."""
        mock_exchange.get_balance.side_effect = ExchangeAuthenticationError(
            message="Invalid API key", exchange="okx"
        )

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 401


class TestMarketTickerEndpoints:
    """Tests for market ticker endpoints."""

    @pytest.mark.asyncio
    async def test_get_ticker(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
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

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        data = json_resp["data"]
        assert data["symbol"] == "BTC/USDT"
        assert data["last"] == "42000.5"
        assert data["bid"] == "41999"

    @pytest.mark.asyncio
    async def test_get_tickers(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
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

        response = await client.get("/api/v1/market/tickers")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        data = json_resp["data"]
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_tickers_filtered(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting tickers with filter."""
        mock_exchange.get_tickers.return_value = [
            Ticker(
                symbol="BTC/USDT",
                last=Decimal("42000"),
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
        ]

        response = await client.get("/api/v1/market/tickers?symbols=BTC/USDT")

        assert response.status_code == 200
        mock_exchange.get_tickers.assert_called_once_with(["BTC/USDT"])

    @pytest.mark.asyncio
    async def test_get_tickers_empty_symbols_filtered(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting tickers with trailing comma filters empty strings."""
        mock_exchange.get_tickers.return_value = [
            Ticker(
                symbol="BTC/USDT",
                last=Decimal("42000"),
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            ),
        ]

        # Trailing comma should not produce empty string in list
        response = await client.get("/api/v1/market/tickers?symbols=BTC/USDT,")

        assert response.status_code == 200
        # Should filter out empty string
        mock_exchange.get_tickers.assert_called_once_with(["BTC/USDT"])


class TestMarketCandlestickEndpoints:
    """Tests for market candlestick endpoints."""

    @pytest.mark.asyncio
    async def test_get_candles(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
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

        response = await client.get("/api/v1/market/candles/BTC/USDT?timeframe=1h&limit=2")

        assert response.status_code == 200
        json_resp = response.json()
        assert json_resp["code"] == 0
        data = json_resp["data"]
        assert data["symbol"] == "BTC/USDT"
        assert data["timeframe"] == "1h"
        assert len(data["candles"]) == 2
        mock_exchange.get_candlesticks.assert_called_once_with("BTC/USDT", TimeFrame.H1, limit=2)

    @pytest.mark.asyncio
    async def test_get_candles_invalid_timeframe(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test getting candles with invalid timeframe."""
        response = await client.get("/api/v1/market/candles/BTC/USDT?timeframe=invalid")

        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
        """Test rate limit error response."""
        mock_exchange.get_ticker.side_effect = ExchangeRateLimitError(
            message="Rate limit exceeded", exchange="okx", retry_after=5.0
        )

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "5"

    @pytest.mark.asyncio
    async def test_api_error(self, client: AsyncClient, mock_exchange: AsyncMock) -> None:
        """Test API error response."""
        mock_exchange.get_ticker.side_effect = ExchangeAPIError(
            message="Internal error", exchange="okx", code="50000"
        )

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_internal_error_hides_details(
        self, client: AsyncClient, mock_exchange: AsyncMock
    ) -> None:
        """Test that internal errors don't expose sensitive details."""
        mock_exchange.get_ticker.side_effect = RuntimeError(
            "Database connection failed: password=secret123"
        )

        response = await client.get("/api/v1/market/ticker/BTC/USDT")

        assert response.status_code == 500
        # Should not expose internal error details
        assert response.json()["detail"] == "Internal server error"
        assert "secret123" not in response.text
        assert "Database" not in response.text
