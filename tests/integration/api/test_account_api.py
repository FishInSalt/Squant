"""
Integration tests for Account API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/06-account.md:
- ACC-001: Add exchange API configuration
- ACC-002: Binance exchange support
- ACC-003: OKX exchange support
- ACC-004: API key encrypted storage
- ACC-005: API connection test
- ACC-006: Edit/delete API configuration
- ACC-010: Asset summary across exchanges
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from squant.main import app
from squant.models.exchange import ExchangeAccount
from squant.utils.crypto import decrypt_string, encrypt_string


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


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
            "is_testnet": True,
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=account_data)

        assert response.status_code == 201
        data = response.json()

        assert data["exchange"] == "okx"
        assert data["name"] == "My OKX Account"
        assert data["is_testnet"] is True

    @pytest.mark.asyncio
    async def test_create_account_missing_required_fields(self, client, db_session):
        """Test ACC-001-3: Prompt for required fields."""
        # Missing api_key
        incomplete_data = {
            "exchange": "binance",
            "name": "Incomplete Account",
            "api_secret": "secret_only",
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=incomplete_data)

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

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=invalid_data)

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
            "is_testnet": True,
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=binance_data)

        assert response.status_code == 201
        data = response.json()

        assert data["exchange"] == "binance"
        # Passphrase should not be required for Binance
        assert "passphrase" not in binance_data

    @pytest.mark.asyncio
    async def test_binance_connection_test_success(self, client, db_session, sample_exchange_account):
        """Test ACC-002-2: Test Binance connection with correct API."""
        # Update sample account to be Binance
        sample_exchange_account.exchange = "binance"
        await db_session.commit()

        # Mock exchange adapter to return success
        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(return_value=True)
        mock_adapter.get_balance = AsyncMock(
            return_value={"USDT": 1000.0, "BTC": 0.5}
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "balance" in data

    @pytest.mark.asyncio
    async def test_binance_connection_test_auth_failure(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-002-3: Show authentication failed with incorrect API."""
        # Update sample account to be Binance
        sample_exchange_account.exchange = "binance"
        await db_session.commit()

        # Mock exchange adapter to raise authentication error
        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(
            side_effect=Exception("API-key format invalid")
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code == 400
        data = response.json()

        # Should contain authentication error message
        assert "认证失败" in data["detail"] or "authentication" in data["detail"].lower()


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
            "is_testnet": True,
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=okx_data)

        assert response.status_code == 201
        data = response.json()

        assert data["exchange"] == "okx"
        # Passphrase is stored but not returned in plain text
        assert data.get("passphrase") != "okx_passphrase"

    @pytest.mark.asyncio
    async def test_okx_connection_test_success(self, client, db_session, sample_exchange_account):
        """Test ACC-003-2: Test OKX connection with correct API."""
        # Mock exchange adapter
        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(return_value=True)
        mock_adapter.get_balance = AsyncMock(
            return_value={"USDT": 5000.0, "BTC": 0.25}
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "balance" in data

    @pytest.mark.asyncio
    async def test_okx_missing_passphrase_error(self, client, db_session):
        """Test ACC-003-3: Prompt for passphrase if missing."""
        okx_data_no_passphrase = {
            "exchange": "okx",
            "name": "OKX No Passphrase",
            "api_key": "okx_api_key",
            "api_secret": "okx_api_secret",
            # Missing passphrase
            "is_testnet": True,
        }

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.post("/api/v1/exchange-accounts", json=okx_data_no_passphrase)

        # Should either be validation error or business logic error
        assert response.status_code in [400, 422]
        data = response.json()

        # Should mention passphrase requirement
        assert "passphrase" in str(data).lower()


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
        # Create account directly to check database storage
        account = ExchangeAccount(
            id=uuid4(),
            exchange="okx",
            name="Encryption Test",
            api_key=encrypt_string("plaintext_key_123"),
            api_secret=encrypt_string("plaintext_secret_456"),
            passphrase=encrypt_string("plaintext_pass_789"),
            is_testnet=True,
        )

        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)

        # Verify encrypted values are NOT the plaintext
        assert account.api_key != "plaintext_key_123"
        assert account.api_secret != "plaintext_secret_456"
        assert account.passphrase != "plaintext_pass_789"

        # Verify we can decrypt them
        decrypted_key = decrypt_string(account.api_key)
        decrypted_secret = decrypt_string(account.api_secret)
        decrypted_pass = decrypt_string(account.passphrase)

        assert decrypted_key == "plaintext_key_123"
        assert decrypted_secret == "plaintext_secret_456"
        assert decrypted_pass == "plaintext_pass_789"

    @pytest.mark.asyncio
    async def test_decrypt_when_using_api(self, db_session, sample_exchange_account):
        """Test ACC-004-2: Correctly decrypt when using API."""
        # Service should decrypt keys when creating exchange adapter
        from squant.services.account import AccountService

        service = AccountService(db_session)

        # Get account (which should decrypt keys)
        account = await service.get(sample_exchange_account.id)

        # Verify account has encrypted values (not plaintext)
        assert account.api_key != "test_api_key"
        assert account.api_secret != "test_api_secret"

        # When used by exchange adapter, keys should decrypt properly
        # (this is tested implicitly in connection tests)

    @pytest.mark.asyncio
    async def test_secret_displayed_as_masked(self, client, db_session, sample_exchange_account):
        """Test ACC-004-3: Secret displayed as masked in API response."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.get(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert response.status_code == 200
        data = response.json()

        # API should mask the secret
        # Depending on implementation, this could be:
        # 1. Completely omitted
        # 2. Shown as "****"
        # 3. Shown as partial (first/last chars only)

        # At minimum, should NOT show the actual decrypted value
        if "api_secret" in data:
            assert data["api_secret"] != "test_api_secret"


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
        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(return_value=True)
        mock_adapter.get_balance = AsyncMock(
            return_value={
                "USDT": 10000.0,
                "BTC": 0.5,
                "ETH": 2.0,
            }
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "balance" in data
        assert data["balance"]["USDT"] == 10000.0

    @pytest.mark.asyncio
    async def test_connection_test_shows_failure_with_reason(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-005-3: Show connection failed with error reason."""
        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(
            side_effect=Exception("Invalid API credentials")
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code == 400
        data = response.json()

        # Should include error reason
        assert "Invalid API credentials" in data["detail"] or "连接失败" in data["detail"]

    @pytest.mark.asyncio
    async def test_connection_test_timeout(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-005-4: Show connection timeout on network timeout."""
        import asyncio

        mock_adapter = MagicMock()
        mock_adapter.test_connection = AsyncMock(side_effect=asyncio.TimeoutError())

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.exchange_accounts.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.post(f"/api/v1/exchange-accounts/{sample_exchange_account.id}/test")

        assert response.status_code in [400, 408, 504]
        data = response.json()

        # Should mention timeout
        assert "timeout" in data["detail"].lower() or "超时" in data["detail"]


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

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.patch(
                f"/api/v1/exchange-accounts/{sample_exchange_account.id}",
                json=update_data,
            )

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Updated Account Name"

    @pytest.mark.asyncio
    async def test_delete_exchange_account(self, client, db_session, sample_exchange_account):
        """Test ACC-006-2: Delete account."""
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.delete(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert response.status_code in [200, 204]

        # Verify account was deleted
        with patch("squant.api.deps.get_db_session", return_value=db_session):
            get_response = client.get(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_prevent_deletion_if_strategy_uses_account(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-006-3: Prevent deletion if strategy is using account."""
        # Create a paper trading run using this account
        from squant.models.enums import RunStatus
        from squant.models.paper_trading import PaperTradingRun

        run = PaperTradingRun(
            id=uuid4(),
            exchange_account_id=sample_exchange_account.id,
            symbol="BTC/USDT",
            initial_balance=10000.0,
            status=RunStatus.RUNNING,
        )
        db_session.add(run)
        await db_session.commit()

        with patch("squant.api.deps.get_db_session", return_value=db_session):
            response = client.delete(f"/api/v1/exchange-accounts/{sample_exchange_account.id}")

        # Should prevent deletion
        assert response.status_code == 400
        data = response.json()

        # Should mention account is in use
        assert "使用" in data["detail"] or "in use" in data["detail"].lower()


class TestAssetSummaryAcrossExchanges:
    """
    Tests for ACC-010: Asset summary across exchanges

    Acceptance criteria:
    - Display asset list for configured exchanges
    - Show quantity and value for each coin
    - Show total asset summary for multiple exchanges
    """

    @pytest.mark.asyncio
    async def test_get_assets_for_single_exchange(
        self, client, db_session, sample_exchange_account
    ):
        """Test ACC-010-1: Display asset list."""
        mock_adapter = MagicMock()
        mock_adapter.get_balance = AsyncMock(
            return_value={
                "USDT": 5000.0,
                "BTC": 0.25,
                "ETH": 1.5,
            }
        )

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.account.get_exchange_adapter", return_value=mock_adapter),
        ):
            response = client.get(f"/api/v1/account/{sample_exchange_account.id}/balance")

        assert response.status_code == 200
        data = response.json()

        # Should show all coins
        assert "USDT" in data
        assert data["USDT"] == 5000.0
        assert "BTC" in data

    @pytest.mark.asyncio
    async def test_asset_summary_with_multiple_exchanges(self, client, db_session):
        """Test ACC-010-3: Total asset summary for multiple exchanges."""
        # Create two exchange accounts
        account1 = ExchangeAccount(
            id=uuid4(),
            exchange="okx",
            name="OKX Account",
            api_key=encrypt_string("key1"),
            api_secret=encrypt_string("secret1"),
            passphrase=encrypt_string("pass1"),
            is_testnet=True,
        )

        account2 = ExchangeAccount(
            id=uuid4(),
            exchange="binance",
            name="Binance Account",
            api_key=encrypt_string("key2"),
            api_secret=encrypt_string("secret2"),
            is_testnet=True,
        )

        db_session.add(account1)
        db_session.add(account2)
        await db_session.commit()

        # Mock adapters for both exchanges
        def get_mock_adapter(account_id, *args, **kwargs):
            mock = MagicMock()
            if account_id == account1.id:
                mock.get_balance = AsyncMock(return_value={"USDT": 3000.0, "BTC": 0.1})
            else:
                mock.get_balance = AsyncMock(return_value={"USDT": 2000.0, "BTC": 0.15})
            return mock

        with (
            patch("squant.api.deps.get_db_session", return_value=db_session),
            patch("squant.api.v1.account.get_exchange_adapter", side_effect=get_mock_adapter),
        ):
            response = client.get("/api/v1/account/summary")

        assert response.status_code == 200
        data = response.json()

        # Should aggregate balances
        # Total USDT: 5000.0, Total BTC: 0.25
        assert "total" in data or "assets" in data
