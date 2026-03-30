"""Unit tests for account API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.infra.database import get_session
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.exchange.types import AccountBalance, Balance
from squant.main import app


@pytest.fixture
def mock_account():
    """Create a mock exchange account."""
    account = MagicMock()
    account.id = str(uuid4())
    account.exchange = "okx"
    account.name = "test_account"
    account.is_active = True
    account.testnet = False
    account.nonce = b"valid_nonce_12"  # 12 bytes, valid nonce
    account.api_key_enc = b"encrypted_key"
    account.api_secret_enc = b"encrypted_secret"
    account.passphrase_enc = b"encrypted_pass"
    account.created_at = datetime.now(UTC)
    return account


@pytest.fixture
def mock_session(mock_account):
    """Create a mock database session."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_account
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_adapter():
    """Create a mock CCXTRestAdapter."""
    adapter = MagicMock()
    adapter.__aenter__ = AsyncMock(return_value=adapter)
    adapter.__aexit__ = AsyncMock(return_value=None)
    adapter.connect = AsyncMock()
    adapter.close = AsyncMock()
    return adapter


@pytest_asyncio.fixture
async def client(mock_session) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked database session."""

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
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
        self, client: AsyncClient, mock_adapter, sample_account_balance
    ) -> None:
        """Test successful balance retrieval."""
        mock_adapter.get_balance = AsyncMock(return_value=sample_account_balance)

        with (
            patch(
                "squant.api.v1.account._create_adapter_from_account",
                return_value=mock_adapter,
            ),
        ):
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
    async def test_get_balance_empty(self, client: AsyncClient, mock_adapter) -> None:
        """Test balance retrieval with no balances."""
        empty_balance = AccountBalance(
            exchange="okx",
            balances=[],
            timestamp=datetime.now(UTC),
        )
        mock_adapter.get_balance = AsyncMock(return_value=empty_balance)

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["balances"] == []

    @pytest.mark.asyncio
    async def test_get_balance_authentication_error(
        self, client: AsyncClient, mock_adapter
    ) -> None:
        """Test balance retrieval with authentication error."""
        mock_adapter.get_balance = AsyncMock(
            side_effect=ExchangeAuthenticationError("Invalid API key")
        )

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_balance_connection_error(self, client: AsyncClient, mock_adapter) -> None:
        """Test balance retrieval with connection error."""
        mock_adapter.get_balance = AsyncMock(
            side_effect=ExchangeConnectionError("Connection timeout")
        )

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance")

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_get_balance_no_active_account(self, client: AsyncClient) -> None:
        """Test balance retrieval when no active account exists."""
        with patch(
            "squant.api.v1.account._get_active_account",
            side_effect=MagicMock(
                side_effect=__import__("fastapi").HTTPException(
                    status_code=400,
                    detail="No active exchange account found.",
                )
            ),
        ):
            # Re-patch to raise HTTPException directly
            from fastapi import HTTPException

            with patch(
                "squant.api.v1.account._get_active_account",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=400,
                    detail="No active exchange account found.",
                ),
            ):
                response = await client.get("/api/v1/account/balance")

        assert response.status_code == 400


class TestGetBalanceCurrency:
    """Tests for GET /api/v1/account/balance/{currency} endpoint."""

    @pytest.mark.asyncio
    async def test_get_balance_currency_success(
        self, client: AsyncClient, mock_adapter, sample_balance
    ) -> None:
        """Test successful single currency balance retrieval."""
        mock_adapter.get_balance_currency = AsyncMock(return_value=sample_balance)

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
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
    async def test_get_balance_currency_not_found(self, client: AsyncClient, mock_adapter) -> None:
        """Test balance retrieval for non-existent currency."""
        mock_adapter.get_balance_currency = AsyncMock(return_value=None)

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance/XYZ")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"] is None

    @pytest.mark.asyncio
    async def test_get_balance_currency_case_insensitive(
        self, client: AsyncClient, mock_adapter, sample_balance
    ) -> None:
        """Test balance retrieval with different case."""
        mock_adapter.get_balance_currency = AsyncMock(return_value=sample_balance)

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance/btc")

        assert response.status_code == 200
        mock_adapter.get_balance_currency.assert_called_once_with("btc")

    @pytest.mark.asyncio
    async def test_get_balance_currency_authentication_error(
        self, client: AsyncClient, mock_adapter
    ) -> None:
        """Test currency balance retrieval with authentication error."""
        mock_adapter.get_balance_currency = AsyncMock(
            side_effect=ExchangeAuthenticationError("Invalid API key")
        )

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_balance_currency_connection_error(
        self, client: AsyncClient, mock_adapter
    ) -> None:
        """Test currency balance retrieval with connection error."""
        mock_adapter.get_balance_currency = AsyncMock(
            side_effect=ExchangeConnectionError("Connection timeout")
        )

        with patch(
            "squant.api.v1.account._create_adapter_from_account",
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/account/balance/BTC")

        assert response.status_code == 503
