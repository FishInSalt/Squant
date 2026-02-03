"""Unit tests for account API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.api.deps import get_okx_exchange
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.exchange.types import AccountBalance, Balance
from squant.main import app


@pytest.fixture
def mock_exchange():
    """Create a mock OKX exchange adapter."""
    return MagicMock()


@pytest_asyncio.fixture
async def client(mock_exchange) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked exchange dependency."""

    async def override_get_okx_exchange():
        yield mock_exchange

    app.dependency_overrides[get_okx_exchange] = override_get_okx_exchange
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def sample_account_balance():
    """Create sample account balance."""
    return AccountBalance(
        exchange="okx",
        balances=[
            Balance(currency="BTC", available=1.5, frozen=0.5),
            Balance(currency="USDT", available=10000.0, frozen=500.0),
            Balance(currency="ETH", available=5.0, frozen=0.0),
        ],
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_balance():
    """Create sample single balance."""
    return Balance(currency="BTC", available=1.5, frozen=0.5)


class TestGetBalance:
    """Tests for GET /api/v1/account/balance endpoint."""

    @pytest.mark.asyncio
    async def test_get_balance_success(
        self, client: AsyncClient, mock_exchange, sample_account_balance
    ) -> None:
        """Test successful balance retrieval."""
        mock_exchange.get_balance = AsyncMock(return_value=sample_account_balance)

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["exchange"] == "okx"
        assert len(data["data"]["balances"]) == 3

        # Check BTC balance (Decimal serializes as string in JSON)
        btc_balance = next(b for b in data["data"]["balances"] if b["currency"] == "BTC")
        assert float(btc_balance["available"]) == 1.5
        assert float(btc_balance["frozen"]) == 0.5
        assert float(btc_balance["total"]) == 2.0

    @pytest.mark.asyncio
    async def test_get_balance_empty(self, client: AsyncClient, mock_exchange) -> None:
        """Test balance retrieval with no balances."""
        empty_balance = AccountBalance(
            exchange="okx",
            balances=[],
            timestamp=datetime.now(UTC),
        )
        mock_exchange.get_balance = AsyncMock(return_value=empty_balance)

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["balances"] == []

    @pytest.mark.asyncio
    async def test_get_balance_authentication_error(
        self, client: AsyncClient, mock_exchange
    ) -> None:
        """Test balance retrieval with authentication error."""
        mock_exchange.get_balance = AsyncMock(
            side_effect=ExchangeAuthenticationError("Invalid API key")
        )

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_balance_connection_error(self, client: AsyncClient, mock_exchange) -> None:
        """Test balance retrieval with connection error."""
        mock_exchange.get_balance = AsyncMock(
            side_effect=ExchangeConnectionError("Connection timeout")
        )

        response = await client.get("/api/v1/account/balance")

        assert response.status_code == 503


class TestGetBalanceCurrency:
    """Tests for GET /api/v1/account/balance/{currency} endpoint."""

    @pytest.mark.asyncio
    async def test_get_balance_currency_success(
        self, client: AsyncClient, mock_exchange, sample_balance
    ) -> None:
        """Test successful single currency balance retrieval."""
        mock_exchange.get_balance_currency = AsyncMock(return_value=sample_balance)

        response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["currency"] == "BTC"
        # Decimal serializes as string in JSON
        assert float(data["data"]["available"]) == 1.5
        assert float(data["data"]["frozen"]) == 0.5
        assert float(data["data"]["total"]) == 2.0

    @pytest.mark.asyncio
    async def test_get_balance_currency_not_found(self, client: AsyncClient, mock_exchange) -> None:
        """Test balance retrieval for non-existent currency."""
        mock_exchange.get_balance_currency = AsyncMock(return_value=None)

        response = await client.get("/api/v1/account/balance/XYZ")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"] is None

    @pytest.mark.asyncio
    async def test_get_balance_currency_case_insensitive(
        self, client: AsyncClient, mock_exchange, sample_balance
    ) -> None:
        """Test balance retrieval with different case."""
        mock_exchange.get_balance_currency = AsyncMock(return_value=sample_balance)

        response = await client.get("/api/v1/account/balance/btc")

        assert response.status_code == 200
        mock_exchange.get_balance_currency.assert_called_once_with("btc")

    @pytest.mark.asyncio
    async def test_get_balance_currency_authentication_error(
        self, client: AsyncClient, mock_exchange
    ) -> None:
        """Test currency balance retrieval with authentication error."""
        mock_exchange.get_balance_currency = AsyncMock(
            side_effect=ExchangeAuthenticationError("Invalid API key")
        )

        response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_balance_currency_connection_error(
        self, client: AsyncClient, mock_exchange
    ) -> None:
        """Test currency balance retrieval with connection error."""
        mock_exchange.get_balance_currency = AsyncMock(
            side_effect=ExchangeConnectionError("Connection timeout")
        )

        response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 503
