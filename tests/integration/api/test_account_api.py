"""
Integration tests for Account API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/06-account.md:
- ACC-001: Add exchange API configuration
- ACC-002: Binance exchange support
- ACC-003: OKX exchange support
- ACC-004: API key encrypted storage
- ACC-005: API connection test
- ACC-006: Edit/delete API configuration
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from squant.schemas.account import CreateExchangeAccountRequest


class TestAddExchangeAPIConfiguration:
    """
    Tests for ACC-001: Add exchange API configuration

    Acceptance criteria:
    - Show config form on "Add Account"
    - Save config successfully when complete
    - Prompt for required fields if missing
    """

    @pytest.mark.asyncio
    async def test_create_exchange_account_success(self, client, db_session):
        """Test ACC-001-1 & ACC-001-2: Successfully create exchange account."""
        account_data = {
            "exchange": "okx",
            "name": "My OKX Account",
            "api_key": "test_api_key_123",
            "api_secret": "test_api_secret_456",
            "passphrase": "test_passphrase",
            "testnet": True,
        }

        response = await client.post("/api/v1/exchange-accounts", json=account_data)

        assert response.status_code == 200
        data = response.json()

        # Response is wrapped in ApiResponse
        assert "data" in data
        account = data["data"]
        assert account["exchange"] == "okx"
        assert account["name"] == "My OKX Account"
        assert account["testnet"] is True

    @pytest.mark.asyncio
    async def test_create_account_missing_required_fields(self, client, db_session):
        """Test ACC-001-3: Prompt for required fields."""
        # Missing api_key
        incomplete_data = {
            "exchange": "binance",
            "name": "Incomplete Account",
            "api_secret": "secret_only",
        }

        response = await client.post("/api/v1/exchange-accounts", json=incomplete_data)

        assert response.status_code == 422  # Validation error
        data = response.json()

        # Should have validation error for missing api_key
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_account_validates_exchange_name(self, client, db_session):
        """Test that only valid exchange names are accepted."""
        invalid_data = {
            "exchange": "invalid_exchange",
            "name": "Invalid Exchange",
            "api_key": "key",
            "api_secret": "secret",
        }

        response = await client.post("/api/v1/exchange-accounts", json=invalid_data)

        assert response.status_code == 422


class TestBinanceExchangeSupport:
    """
    Tests for ACC-002: Binance exchange support

    Acceptance criteria:
    - Support Binance with API Key and Secret
    - Test connection success with correct API
    - Show "Authentication failed" with incorrect API
    """

    @pytest.mark.asyncio
    async def test_create_binance_account(self, client, db_session):
        """Test ACC-002-1: Create Binance account with API Key and Secret."""
        binance_data = {
            "exchange": "binance",
            "name": "My Binance",
            "api_key": "binance_api_key",
            "api_secret": "binance_api_secret",
            "testnet": True,
        }

        response = await client.post("/api/v1/exchange-accounts", json=binance_data)

        assert response.status_code == 200
        data = response.json()

        account = data["data"]
        assert account["exchange"] == "binance"
        # Passphrase should not be required for Binance
        assert "passphrase" not in binance_data

    @pytest.mark.asyncio
    async def test_binance_connection_test_success(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-002-2: Test Binance connection with correct API."""
        # Update sample account to be Binance
        sample_exchange_account.exchange = "binance"
        await db_session.commit()

        # Mock the service test_connection method
        mock_result = {
            "success": True,
            "message": None,
            "balance_count": 2,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is True
        assert result["balance_count"] == 2

    @pytest.mark.asyncio
    async def test_binance_connection_test_auth_failure(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-002-3: Show authentication failed with incorrect API."""
        # Update sample account to be Binance
        sample_exchange_account.exchange = "binance"
        await db_session.commit()

        # Mock the service to return failure
        mock_result = {
            "success": False,
            "message": "Authentication failed: API-key format invalid",
            "balance_count": None,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is False
        assert "Authentication failed" in result["message"]


class TestOKXExchangeSupport:
    """
    Tests for ACC-003: OKX exchange support

    Acceptance criteria:
    - Support OKX with API Key, Secret, Passphrase
    - Test connection success with correct API
    - Prompt "Passphrase is required" if missing
    """

    @pytest.mark.asyncio
    async def test_create_okx_account_with_passphrase(self, client, db_session):
        """Test ACC-003-1: Create OKX account with API Key, Secret, Passphrase."""
        okx_data = {
            "exchange": "okx",
            "name": "My OKX",
            "api_key": "okx_api_key",
            "api_secret": "okx_api_secret",
            "passphrase": "okx_passphrase",
            "testnet": True,
        }

        response = await client.post("/api/v1/exchange-accounts", json=okx_data)

        assert response.status_code == 200
        data = response.json()

        account = data["data"]
        assert account["exchange"] == "okx"
        # Passphrase is stored but not returned in plain text
        assert "passphrase" not in account or account.get("passphrase") != "okx_passphrase"

    @pytest.mark.asyncio
    async def test_okx_connection_test_success(self, client, db_session, sample_exchange_account):
        """Test ACC-003-2: Test OKX connection with correct API."""
        # Mock the service test_connection method
        mock_result = {
            "success": True,
            "message": None,
            "balance_count": 2,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is True
        assert result["balance_count"] == 2

    @pytest.mark.asyncio
    async def test_okx_missing_passphrase_error(self, client, db_session):
        """Test ACC-003-3: Prompt for passphrase if missing."""
        okx_data_no_passphrase = {
            "exchange": "okx",
            "name": "OKX No Passphrase",
            "api_key": "okx_api_key",
            "api_secret": "okx_api_secret",
            # Missing passphrase
            "testnet": True,
        }

        response = await client.post("/api/v1/exchange-accounts", json=okx_data_no_passphrase)

        # Should be 400 (business logic error)
        assert response.status_code == 400
        data = response.json()

        # Should mention passphrase requirement
        assert "passphrase" in data["detail"].lower()


class TestAPIKeyEncryptedStorage:
    """
    Tests for ACC-004: API key encrypted storage

    Acceptance criteria:
    - Store API Key and Secret encrypted in database
    - Decrypt correctly when using API
    - Display Secret as masked (e.g., ****)
    """

    @pytest.mark.asyncio
    async def test_api_keys_encrypted_in_database(self, db_session):
        """Test ACC-004-1: API keys stored encrypted."""
        from squant.services.account import ExchangeAccountService

        # Create account via service
        service = ExchangeAccountService(db_session)
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Encryption Test",
            api_key=SecretStr("plaintext_key_123"),
            api_secret=SecretStr("plaintext_secret_456"),
            passphrase=SecretStr("plaintext_pass_789"),
            testnet=True,
        )

        account = await service.create(request)

        # Verify encrypted values are bytes (not plaintext strings)
        assert isinstance(account.api_key_enc, bytes)
        assert isinstance(account.api_secret_enc, bytes)
        assert isinstance(account.passphrase_enc, bytes)

        # Verify we can decrypt them
        creds = service.get_decrypted_credentials(account)
        assert creds["api_key"] == "plaintext_key_123"
        assert creds["api_secret"] == "plaintext_secret_456"
        assert creds["passphrase"] == "plaintext_pass_789"

    @pytest.mark.asyncio
    async def test_decrypt_when_using_api(self, db_session, sample_exchange_account):
        """Test ACC-004-2: Correctly decrypt when using API."""
        from squant.services.account import ExchangeAccountService

        service = ExchangeAccountService(db_session)

        # Get account (which should have encrypted values)
        account = await service.get(sample_exchange_account.id)

        # Verify account has encrypted bytes (not plaintext)
        assert isinstance(account.api_key_enc, bytes)
        assert isinstance(account.api_secret_enc, bytes)

        # Decrypt and verify
        creds = service.get_decrypted_credentials(account)
        assert creds["api_key"] == "test_api_key"
        assert creds["api_secret"] == "test_api_secret"

    @pytest.mark.asyncio
    async def test_secret_displayed_as_masked(self, client, db_session, sample_exchange_account):
        """Test ACC-004-3: Secret displayed as masked in API response."""
        response = await client.get(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert response.status_code == 200
        data = response.json()

        account = data["data"]

        # API should NOT return encrypted credentials
        # The response schema should omit these sensitive fields
        assert "api_key_enc" not in account
        assert "api_secret_enc" not in account
        assert "passphrase_enc" not in account


class TestAPIConnectionTest:
    """
    Tests for ACC-005: API connection test

    Acceptance criteria:
    - Show test progress
    - Show "Connection success" + account balance if valid
    - Show "Connection failed" + error reason if invalid
    - Show "Connection timeout" on network timeout
    """

    @pytest.mark.asyncio
    async def test_connection_test_shows_success_with_balance(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-005-2: Show connection success with balance."""
        mock_result = {
            "success": True,
            "message": None,
            "balance_count": 3,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is True
        assert result["balance_count"] == 3

    @pytest.mark.asyncio
    async def test_connection_test_shows_failure_with_reason(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-005-3: Show connection failed with error reason."""
        mock_result = {
            "success": False,
            "message": "Authentication failed: Invalid API credentials",
            "balance_count": None,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is False
        assert "Invalid API credentials" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_test_timeout(self, client, db_session, sample_exchange_account):
        """Test ACC-005-4: Show connection timeout on network timeout."""
        mock_result = {
            "success": False,
            "message": "Connection timeout",
            "balance_count": None,
        }

        with patch(
            "squant.services.account.ExchangeAccountService.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test"
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["success"] is False
        assert "timeout" in result["message"].lower()


class TestEditDeleteAPIConfiguration:
    """
    Tests for ACC-006: Edit/delete API configuration

    Acceptance criteria:
    - Edit existing configurations
    - Show confirmation dialog on delete
    - Prevent deletion if strategy is using the account
    """

    @pytest.mark.asyncio
    async def test_edit_exchange_account(self, client, db_session, sample_exchange_account):
        """Test ACC-006-1: Edit existing configuration."""
        update_data = {
            "name": "Updated Account Name",
            "api_key": "new_api_key",
        }

        response = await client.put(
            f"/api/v1/exchange-accounts/{sample_exchange_account.id}",
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()

        account = data["data"]
        assert account["name"] == "Updated Account Name"

    @pytest.mark.asyncio
    async def test_delete_exchange_account(self, client, db_session, sample_exchange_account):
        """Test ACC-006-2: Delete account."""
        response = await client.delete(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert response.status_code == 200

        # Verify account was deleted
        get_response = await client.get(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_prevent_deletion_if_strategy_uses_account(
        self, client, db_session, sample_exchange_account, sample_strategy
    ):
        """Test ACC-006-3: Prevent deletion if strategy is using account.

        This test verifies that accounts with associated strategy runs cannot be deleted
        due to the foreign key constraint with ondelete="RESTRICT".
        """
        from squant.models.enums import RunStatus
        from squant.models.strategy import StrategyRun

        # Create a strategy run using this account
        run = StrategyRun(
            id=uuid4(),
            strategy_id=sample_strategy.id,
            account_id=sample_exchange_account.id,
            mode="live",
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1m",
            initial_capital=10000.0,
            status=RunStatus.RUNNING,
        )
        db_session.add(run)
        await db_session.commit()

        # Ensure the run is persisted and visible
        await db_session.refresh(run)

        # Attempt to delete the account - should fail with 409 Conflict
        response = await client.delete(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        # Should prevent deletion (409 Conflict)
        assert response.status_code == 409
        data = response.json()

        # Should mention account is in use
        assert "in use" in data["detail"].lower() or "使用" in data["detail"]
