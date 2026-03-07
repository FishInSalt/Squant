"""Unit tests for exchange accounts API endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from squant.api.v1.exchange_accounts import router
from squant.models.exchange import ExchangeAccount
from squant.services.account import (
    AccountInUseError,
    AccountNameExistsError,
    AccountNotFoundError,
)


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/exchange-accounts")
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_account() -> MagicMock:
    """Create a mock exchange account."""
    account = MagicMock(spec=ExchangeAccount)
    account.id = uuid4()
    account.exchange = "okx"
    account.name = "test-account"
    account.testnet = True
    account.is_active = True
    account.created_at = datetime.now(UTC)
    account.updated_at = datetime.now(UTC)
    return account


class TestCreateExchangeAccount:
    """Tests for POST /exchange-accounts."""

    @pytest.mark.asyncio
    async def test_create_okx_account_success(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test successful OKX account creation."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.create = AsyncMock(return_value=mock_account)

                response = await client.post(
                    "/exchange-accounts",
                    json={
                        "exchange": "okx",
                        "name": "test-account",
                        "api_key": "key123",
                        "api_secret": "secret456",
                        "passphrase": "pass789",
                        "testnet": True,
                    },
                )

                assert response.status_code == 201
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["name"] == "test-account"
                assert data["data"]["exchange"] == "okx"

    @pytest.mark.asyncio
    async def test_create_okx_without_passphrase_fails(self, client: AsyncClient) -> None:
        """Test OKX account creation without passphrase fails."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            response = await client.post(
                "/exchange-accounts",
                json={
                    "exchange": "okx",
                    "name": "test-account",
                    "api_key": "key123",
                    "api_secret": "secret456",
                },
            )

            assert response.status_code == 400
            assert "passphrase" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_binance_without_passphrase_succeeds(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test Binance account creation without passphrase succeeds."""
        mock_account.exchange = "binance"

        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.create = AsyncMock(return_value=mock_account)

                response = await client.post(
                    "/exchange-accounts",
                    json={
                        "exchange": "binance",
                        "name": "test-account",
                        "api_key": "key123",
                        "api_secret": "secret456",
                    },
                )

                assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        """Test creating account with duplicate name returns 409."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.create = AsyncMock(
                    side_effect=AccountNameExistsError("okx", "existing-account")
                )

                response = await client.post(
                    "/exchange-accounts",
                    json={
                        "exchange": "okx",
                        "name": "existing-account",
                        "api_key": "key",
                        "api_secret": "secret",
                        "passphrase": "pass",
                    },
                )

                assert response.status_code == 409


class TestListExchangeAccounts:
    """Tests for GET /exchange-accounts."""

    @pytest.mark.asyncio
    async def test_list_all_accounts(self, client: AsyncClient, mock_account: MagicMock) -> None:
        """Test listing all accounts."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.list = AsyncMock(return_value=[mock_account])

                response = await client.get("/exchange-accounts")

                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert len(data["data"]) == 1

    @pytest.mark.asyncio
    async def test_list_with_exchange_filter(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test listing accounts with exchange filter."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.list = AsyncMock(return_value=[mock_account])

                response = await client.get("/exchange-accounts?exchange=okx")

                assert response.status_code == 200
                service.list.assert_called_once()


class TestGetExchangeAccount:
    """Tests for GET /exchange-accounts/{id}."""

    @pytest.mark.asyncio
    async def test_get_account_success(self, client: AsyncClient, mock_account: MagicMock) -> None:
        """Test getting an existing account."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.get = AsyncMock(return_value=mock_account)

                response = await client.get(f"/exchange-accounts/{mock_account.id}")

                assert response.status_code == 200
                data = response.json()
                assert data["data"]["name"] == "test-account"

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent account returns 404."""
        account_id = uuid4()

        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.get = AsyncMock(side_effect=AccountNotFoundError(account_id))

                response = await client.get(f"/exchange-accounts/{account_id}")

                assert response.status_code == 404


class TestUpdateExchangeAccount:
    """Tests for PUT /exchange-accounts/{id}."""

    @pytest.mark.asyncio
    async def test_update_account_success(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test successful account update."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.update = AsyncMock(return_value=mock_account)

                response = await client.put(
                    f"/exchange-accounts/{mock_account.id}",
                    json={"name": "updated-name"},
                )

                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_account_not_found(self, client: AsyncClient) -> None:
        """Test updating non-existent account returns 404."""
        account_id = uuid4()

        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.update = AsyncMock(side_effect=AccountNotFoundError(account_id))

                response = await client.put(
                    f"/exchange-accounts/{account_id}",
                    json={"name": "new-name"},
                )

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_duplicate_name_returns_409(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test updating to duplicate name returns 409."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.update = AsyncMock(side_effect=AccountNameExistsError("okx", "existing"))

                response = await client.put(
                    f"/exchange-accounts/{mock_account.id}",
                    json={"name": "existing"},
                )

                assert response.status_code == 409


class TestDeleteExchangeAccount:
    """Tests for DELETE /exchange-accounts/{id}."""

    @pytest.mark.asyncio
    async def test_delete_account_success(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test successful account deletion."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.delete = AsyncMock()

                response = await client.delete(f"/exchange-accounts/{mock_account.id}")

                assert response.status_code == 200
                data = response.json()
                assert data["message"] == "Account deleted"

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, client: AsyncClient) -> None:
        """Test deleting non-existent account returns 404."""
        account_id = uuid4()

        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.delete = AsyncMock(side_effect=AccountNotFoundError(account_id))

                response = await client.delete(f"/exchange-accounts/{account_id}")

                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_account_in_use_returns_409(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test deleting account in use returns 409."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.delete = AsyncMock(
                    side_effect=AccountInUseError(mock_account.id, "has associated orders")
                )

                response = await client.delete(f"/exchange-accounts/{mock_account.id}")

                assert response.status_code == 409
                assert "in use" in response.json()["detail"].lower()


class TestConnectionTest:
    """Tests for POST /exchange-accounts/{id}/test."""

    @pytest.mark.asyncio
    async def test_connection_test_success(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test successful connection test."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.test_connection = AsyncMock(
                    return_value={
                        "success": True,
                        "message": None,
                        "balance_count": 5,
                    }
                )

                response = await client.post(f"/exchange-accounts/{mock_account.id}/test")

                assert response.status_code == 200
                data = response.json()
                assert data["data"]["success"] is True
                assert data["data"]["balance_count"] == 5

    @pytest.mark.asyncio
    async def test_connection_test_failure(
        self, client: AsyncClient, mock_account: MagicMock
    ) -> None:
        """Test failed connection test."""
        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.test_connection = AsyncMock(
                    return_value={
                        "success": False,
                        "message": "Invalid API key",
                        "balance_count": None,
                    }
                )

                response = await client.post(f"/exchange-accounts/{mock_account.id}/test")

                assert response.status_code == 200
                data = response.json()
                assert data["data"]["success"] is False
                assert "Invalid API key" in data["data"]["message"]

    @pytest.mark.asyncio
    async def test_connection_test_account_not_found(self, client: AsyncClient) -> None:
        """Test connection test for non-existent account returns 404."""
        account_id = uuid4()

        with patch("squant.api.v1.exchange_accounts.get_session"):
            with patch("squant.api.v1.exchange_accounts.ExchangeAccountService") as MockService:
                service = MockService.return_value
                service.test_connection = AsyncMock(side_effect=AccountNotFoundError(account_id))

                response = await client.post(f"/exchange-accounts/{account_id}/test")

                assert response.status_code == 404
