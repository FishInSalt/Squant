"""
Integration tests for Account Service.

Tests account service functionality with real database integration:
- Exchange account creation and management
- API credential encryption/decryption
- Account validation and connection testing
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from squant.schemas.account import CreateExchangeAccountRequest, UpdateExchangeAccountRequest
from squant.services.account import (
    AccountInUseError,
    AccountNotFoundError,
    ExchangeAccountService,
)


@pytest_asyncio.fixture
async def account_service(db_session):
    """Create account service instance."""
    return ExchangeAccountService(db_session)


class TestExchangeAccountCreation:
    """Tests for exchange account creation."""

    @pytest.mark.asyncio
    async def test_create_okx_account(self, account_service):
        """Test creating OKX exchange account."""
        from pydantic import SecretStr

        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Test OKX Account",
            api_key=SecretStr("okx_test_key"),
            api_secret=SecretStr("okx_test_secret"),
            passphrase=SecretStr("okx_test_pass"),
            testnet=True,
        )

        account = await account_service.create(request)

        assert account.exchange == "okx"
        assert account.name == "Test OKX Account"
        assert account.testnet is True

        # Verify API keys are encrypted (should be bytes, not plaintext)
        assert isinstance(account.api_key_enc, bytes)
        assert isinstance(account.api_secret_enc, bytes)
        assert isinstance(account.passphrase_enc, bytes)

        # Verify we can decrypt them
        creds = account_service.get_decrypted_credentials(account)
        assert creds["api_key"] == "okx_test_key"
        assert creds["api_secret"] == "okx_test_secret"
        assert creds["passphrase"] == "okx_test_pass"

    @pytest.mark.asyncio
    async def test_create_binance_account(self, account_service):
        """Test creating Binance exchange account."""
        from pydantic import SecretStr

        request = CreateExchangeAccountRequest(
            exchange="binance",
            name="Test Binance Account",
            api_key=SecretStr("binance_test_key"),
            api_secret=SecretStr("binance_test_secret"),
            testnet=True,
        )

        account = await account_service.create(request)

        assert account.exchange == "binance"
        assert account.name == "Test Binance Account"

        # Binance doesn't require passphrase
        assert account.passphrase_enc is None

    @pytest.mark.asyncio
    async def test_create_account_encrypts_credentials(self, account_service):
        """Test that API credentials are encrypted on creation."""
        from pydantic import SecretStr

        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Encryption Test",
            api_key=SecretStr("plain_key_123"),
            api_secret=SecretStr("plain_secret_456"),
            passphrase=SecretStr("plain_pass_789"),
            testnet=True,
        )

        account = await account_service.create(request)

        # Stored values should be encrypted bytes
        assert isinstance(account.api_key_enc, bytes)
        assert isinstance(account.api_secret_enc, bytes)
        assert isinstance(account.passphrase_enc, bytes)
        assert isinstance(account.nonce, bytes)

        # But should decrypt to original values
        creds = account_service.get_decrypted_credentials(account)
        assert creds["api_key"] == "plain_key_123"
        assert creds["api_secret"] == "plain_secret_456"
        assert creds["passphrase"] == "plain_pass_789"

    @pytest.mark.asyncio
    async def test_create_account_persists_to_database(self, account_service, db_session):
        """Test that created account is persisted to database."""
        from pydantic import SecretStr

        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Persistence Test",
            api_key=SecretStr("persist_key"),
            api_secret=SecretStr("persist_secret"),
            passphrase=SecretStr("persist_pass"),
            testnet=True,
        )

        account = await account_service.create(request)

        # Refresh from database
        await db_session.refresh(account)

        # Verify it exists and has correct values
        assert account.name == "Persistence Test"
        creds = account_service.get_decrypted_credentials(account)
        assert creds["api_key"] == "persist_key"


class TestExchangeAccountRetrieval:
    """Tests for retrieving exchange accounts."""

    @pytest.mark.asyncio
    async def test_get_account_by_id(self, account_service, sample_exchange_account):
        """Test retrieving account by ID."""
        account = await account_service.get(sample_exchange_account.id)

        assert account is not None
        assert account.id == sample_exchange_account.id
        assert account.name == sample_exchange_account.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_account_raises_error(self, account_service):
        """Test that getting nonexistent account raises error."""
        with pytest.raises(AccountNotFoundError):
            await account_service.get(uuid4())

    @pytest.mark.asyncio
    async def test_list_all_accounts(self, account_service, db_session):
        """Test listing all exchange accounts."""
        from pydantic import SecretStr

        # Create multiple accounts using service
        for i in range(3):
            request = CreateExchangeAccountRequest(
                exchange="okx" if i % 2 == 0 else "binance",
                name=f"Account {i}",
                api_key=SecretStr(f"key_{i}"),
                api_secret=SecretStr(f"secret_{i}"),
                passphrase=SecretStr(f"pass_{i}") if i % 2 == 0 else None,
                testnet=True,
            )
            await account_service.create(request)

        accounts = await account_service.list()

        # Should have at least 3 accounts (plus sample_exchange_account if present)
        assert len(accounts) >= 3

    @pytest.mark.asyncio
    async def test_list_accounts_filter_by_exchange(self, account_service, db_session):
        """Test filtering accounts by exchange."""
        from pydantic import SecretStr

        # Create accounts for different exchanges using service
        await account_service.create(
            CreateExchangeAccountRequest(
                exchange="okx",
                name="OKX Account",
                api_key=SecretStr("okx_key"),
                api_secret=SecretStr("okx_secret"),
                passphrase=SecretStr("okx_pass"),
                testnet=True,
            )
        )

        await account_service.create(
            CreateExchangeAccountRequest(
                exchange="binance",
                name="Binance Account",
                api_key=SecretStr("binance_key"),
                api_secret=SecretStr("binance_secret"),
                testnet=True,
            )
        )

        # Filter by OKX
        accounts = await account_service.list(exchange="okx")

        assert all(account.exchange == "okx" for account in accounts)
        assert len(accounts) >= 1

    @pytest.mark.skip(reason="Pagination not implemented in service.list()")
    @pytest.mark.asyncio
    async def test_list_accounts_pagination(self, account_service, db_session):
        """Test account list pagination."""
        # This feature is not implemented in the current service
        pass


class TestExchangeAccountUpdate:
    """Tests for updating exchange accounts."""

    @pytest.mark.asyncio
    async def test_update_account_name(self, account_service, sample_exchange_account):
        """Test updating account name."""
        request = UpdateExchangeAccountRequest(name="Updated Name")

        updated = await account_service.update(sample_exchange_account.id, request)

        assert updated.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_account_api_key(self, account_service, sample_exchange_account):
        """Test updating API key."""
        from pydantic import SecretStr

        request = UpdateExchangeAccountRequest(api_key=SecretStr("new_api_key_123"))

        updated = await account_service.update(sample_exchange_account.id, request)

        # Should be encrypted
        assert isinstance(updated.api_key_enc, bytes)
        creds = account_service.get_decrypted_credentials(updated)
        assert creds["api_key"] == "new_api_key_123"

    @pytest.mark.asyncio
    async def test_update_account_multiple_fields(self, account_service, sample_exchange_account):
        """Test updating multiple fields at once."""
        from pydantic import SecretStr

        request = UpdateExchangeAccountRequest(
            name="Multi Update",
            api_key=SecretStr("multi_key"),
            api_secret=SecretStr("multi_secret"),
            testnet=False,
        )

        updated = await account_service.update(sample_exchange_account.id, request)

        assert updated.name == "Multi Update"
        creds = account_service.get_decrypted_credentials(updated)
        assert creds["api_key"] == "multi_key"
        assert creds["api_secret"] == "multi_secret"
        assert updated.testnet is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_account_raises_error(self, account_service):
        """Test updating nonexistent account raises error."""
        request = UpdateExchangeAccountRequest(name="Does Not Exist")

        with pytest.raises(AccountNotFoundError):
            await account_service.update(uuid4(), request)


class TestExchangeAccountDeletion:
    """Tests for deleting exchange accounts."""

    @pytest.mark.asyncio
    async def test_delete_account(self, account_service, db_session):
        """Test deleting an account."""
        from pydantic import SecretStr

        # Create account to delete
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="To Delete",
            api_key=SecretStr("delete_key"),
            api_secret=SecretStr("delete_secret"),
            passphrase=SecretStr("delete_pass"),
            testnet=True,
        )
        account = await account_service.create(request)
        account_id = account.id

        # Delete the account
        await account_service.delete(account_id)

        # Verify it's gone
        with pytest.raises(AccountNotFoundError):
            await account_service.get(account_id)

    @pytest.mark.asyncio
    async def test_delete_account_with_active_runs_raises_error(
        self, account_service, sample_exchange_account, sample_strategy, db_session
    ):
        """Test that deleting account with active runs raises error.

        This test verifies that the foreign key constraint prevents deletion
        of accounts that are referenced by strategy runs.
        """
        from uuid import uuid4

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

        # Ensure the run is persisted
        await db_session.refresh(run)

        # Attempt to delete the account - should fail with AccountInUseError
        with pytest.raises(AccountInUseError):
            await account_service.delete(sample_exchange_account.id)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_account_raises_error(self, account_service):
        """Test deleting nonexistent account raises error."""
        with pytest.raises(AccountNotFoundError):
            await account_service.delete(uuid4())


class TestAccountConnectionTesting:
    """Tests for testing account connections."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, account_service, sample_exchange_account):
        """Test successful connection test."""
        # Mock the adapter's get_balance method
        mock_balance = MagicMock()
        mock_balance.balances = {"USDT": 10000.0, "BTC": 0.5}

        with patch("squant.services.account.OKXAdapter") as MockAdapter:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get_balance = AsyncMock(return_value=mock_balance)
            MockAdapter.return_value = mock_instance

            result = await account_service.test_connection(sample_exchange_account.id)

        assert result["success"] is True
        assert result["balance_count"] == 2
        assert result["message"] is None

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, account_service, sample_exchange_account):
        """Test failed connection test."""
        from squant.infra.exchange.exceptions import ExchangeAuthenticationError

        with patch("squant.services.account.OKXAdapter") as MockAdapter:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(
                side_effect=ExchangeAuthenticationError("Invalid API key")
            )
            mock_instance.__aexit__ = AsyncMock()
            MockAdapter.return_value = mock_instance

            result = await account_service.test_connection(sample_exchange_account.id)

        assert result["success"] is False
        assert "Authentication failed" in result["message"]
        assert result["balance_count"] is None

    @pytest.mark.asyncio
    async def test_test_connection_with_balance_check(
        self, account_service, sample_exchange_account
    ):
        """Test connection with balance check."""
        mock_balance = MagicMock()
        mock_balance.balances = {"USDT": 5000.0, "BTC": 0.25}

        with patch("squant.services.account.OKXAdapter") as MockAdapter:
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_instance.get_balance = AsyncMock(return_value=mock_balance)
            MockAdapter.return_value = mock_instance

            result = await account_service.test_connection(sample_exchange_account.id)

            assert result["success"] is True
            assert result["balance_count"] == 2


class TestCredentialDecryption:
    """Tests for credential decryption when using accounts."""

    @pytest.mark.asyncio
    async def test_credentials_decrypted_for_exchange_adapter(
        self, account_service, db_session
    ):
        """Test that credentials are properly decrypted when accessing them."""
        from pydantic import SecretStr

        # Create account with known credentials
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Decryption Test",
            api_key=SecretStr("decrypt_key_123"),
            api_secret=SecretStr("decrypt_secret_456"),
            passphrase=SecretStr("decrypt_pass_789"),
            testnet=True,
        )
        account = await account_service.create(request)

        # Decrypt credentials
        creds = account_service.get_decrypted_credentials(account)

        # Verify decrypted credentials
        assert creds["api_key"] == "decrypt_key_123"
        assert creds["api_secret"] == "decrypt_secret_456"
        assert creds["passphrase"] == "decrypt_pass_789"
