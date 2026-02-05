"""Unit tests for exchange account service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.exchange import ExchangeAccount
from squant.schemas.account import (
    CreateExchangeAccountRequest,
    UpdateExchangeAccountRequest,
)
from squant.services.account import (
    AccountInUseError,
    AccountNameExistsError,
    AccountNotFoundError,
    ExchangeAccountRepository,
    ExchangeAccountService,
)


class TestExchangeAccountRepository:
    """Tests for ExchangeAccountRepository."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> ExchangeAccountRepository:
        """Create a repository with mock session."""
        return ExchangeAccountRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_exchange_and_name_found(
        self, repository: ExchangeAccountRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting an account by exchange and name when it exists."""
        mock_account = MagicMock(spec=ExchangeAccount)
        mock_account.exchange = "okx"
        mock_account.name = "main-account"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_account
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_and_name("okx", "main-account")
        assert result == mock_account

    @pytest.mark.asyncio
    async def test_get_by_exchange_and_name_not_found(
        self, repository: ExchangeAccountRepository, mock_session: AsyncMock
    ) -> None:
        """Test getting an account when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_exchange_and_name("okx", "non-existent")
        assert result is None


class TestExchangeAccountService:
    """Tests for ExchangeAccountService."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> ExchangeAccountService:
        """Create a service with mock session."""
        return ExchangeAccountService(mock_session)

    @pytest.fixture
    def mock_crypto_manager(self):
        """Create a mock crypto manager."""
        with patch("squant.services.account.get_crypto_manager") as mock:
            crypto = MagicMock()
            crypto.NONCE_SIZE = 12
            crypto.encrypt_with_derived_nonce.return_value = b"encrypted_data"
            crypto.decrypt_with_derived_nonce.return_value = "decrypted_value"
            mock.return_value = crypto
            yield crypto

    @pytest.mark.asyncio
    async def test_create_success(
        self, service: ExchangeAccountService, mock_session: AsyncMock, mock_crypto_manager
    ) -> None:
        """Test successful account creation."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="test-account",
            api_key="api_key_123",
            api_secret="api_secret_456",
            passphrase="passphrase_789",
            testnet=True,
        )

        mock_account = MagicMock(spec=ExchangeAccount)
        mock_account.id = str(uuid4())
        mock_account.exchange = "okx"
        mock_account.name = "test-account"

        with patch.object(
            service.repository, "get_by_exchange_and_name", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            with patch.object(service.repository, "create", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_account

                result = await service.create(request)
                assert result == mock_account
                mock_session.commit.assert_called_once()

                # Verify crypto was called for each credential field
                assert mock_crypto_manager.encrypt_with_derived_nonce.call_count == 3

    @pytest.mark.asyncio
    async def test_create_name_exists(
        self, service: ExchangeAccountService, mock_crypto_manager
    ) -> None:
        """Test that duplicate name raises error."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="existing-account",
            api_key="key",
            api_secret="secret",
            passphrase="pass",
        )

        with patch.object(
            service.repository, "get_by_exchange_and_name", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = MagicMock(spec=ExchangeAccount)

            with pytest.raises(AccountNameExistsError) as exc_info:
                await service.create(request)

            assert "existing-account" in str(exc_info.value)
            assert "okx" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_found(self, service: ExchangeAccountService) -> None:
        """Test getting an account that exists."""
        account_id = uuid4()
        mock_account = MagicMock(spec=ExchangeAccount)
        mock_account.id = str(account_id)

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            result = await service.get(account_id)
            assert result == mock_account

    @pytest.mark.asyncio
    async def test_get_not_found(self, service: ExchangeAccountService) -> None:
        """Test getting an account that doesn't exist."""
        account_id = uuid4()

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(AccountNotFoundError) as exc_info:
                await service.get(account_id)

            assert str(account_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_success(
        self, service: ExchangeAccountService, mock_session: AsyncMock
    ) -> None:
        """Test successful account deletion."""
        account_id = uuid4()
        mock_account = MagicMock()
        mock_account.exchange = "okx"
        mock_account.name = "test_account"

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(service.repository, "delete", new_callable=AsyncMock) as mock_delete:
                mock_delete.return_value = True

                await service.delete(account_id)
                mock_get.assert_called_once_with(account_id)
                mock_delete.assert_called_once_with(account_id)
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service: ExchangeAccountService) -> None:
        """Test deleting an account that doesn't exist."""
        account_id = uuid4()

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(AccountNotFoundError):
                await service.delete(account_id)

    @pytest.mark.asyncio
    async def test_update_success(
        self, service: ExchangeAccountService, mock_session: AsyncMock
    ) -> None:
        """Test successful account update."""
        account_id = uuid4()
        mock_account = MagicMock(spec=ExchangeAccount)
        mock_account.id = str(account_id)
        mock_account.exchange = "okx"
        mock_account.name = "old-name"

        request = UpdateExchangeAccountRequest(name="new-name")

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(
                service.repository, "get_by_exchange_and_name", new_callable=AsyncMock
            ) as mock_get_by_name:
                mock_get_by_name.return_value = None

                with patch.object(
                    service.repository, "update", new_callable=AsyncMock
                ) as mock_update:
                    mock_update.return_value = mock_account

                    result = await service.update(account_id, request)
                    assert result == mock_account

    @pytest.mark.asyncio
    async def test_update_name_conflict(self, service: ExchangeAccountService) -> None:
        """Test that updating to existing name raises error."""
        account_id = uuid4()
        mock_account = MagicMock(spec=ExchangeAccount)
        mock_account.id = str(account_id)
        mock_account.exchange = "okx"
        mock_account.name = "old-name"

        request = UpdateExchangeAccountRequest(name="existing-name")

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(
                service.repository, "get_by_exchange_and_name", new_callable=AsyncMock
            ) as mock_get_by_name:
                mock_get_by_name.return_value = MagicMock(spec=ExchangeAccount)

                with pytest.raises(AccountNameExistsError):
                    await service.update(account_id, request)

    @pytest.mark.asyncio
    async def test_list_all(self, service: ExchangeAccountService) -> None:
        """Test listing all accounts."""
        mock_accounts = [
            MagicMock(spec=ExchangeAccount),
            MagicMock(spec=ExchangeAccount),
        ]

        with patch.object(service.repository, "list_all", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_accounts

            result = await service.list()
            assert result == mock_accounts
            mock_list.assert_called_once_with(exchange=None)

    @pytest.mark.asyncio
    async def test_list_by_exchange(self, service: ExchangeAccountService) -> None:
        """Test listing accounts filtered by exchange."""
        mock_accounts = [MagicMock(spec=ExchangeAccount)]

        with patch.object(service.repository, "list_all", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_accounts

            result = await service.list(exchange="okx")
            assert result == mock_accounts
            mock_list.assert_called_once_with(exchange="okx")


class TestAccountCredentialUpdate:
    """Tests for credential update flows in ExchangeAccountService.update()."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> ExchangeAccountService:
        """Create a service with mock session."""
        return ExchangeAccountService(mock_session)

    @pytest.fixture
    def mock_account(self) -> MagicMock:
        """Create a mock account for update tests."""
        account = MagicMock(spec=ExchangeAccount)
        account.id = str(uuid4())
        account.exchange = "okx"
        account.name = "test-account"
        return account

    @pytest.mark.asyncio
    async def test_update_api_key_preserves_existing_secret(
        self, service: ExchangeAccountService, mock_session: AsyncMock, mock_account
    ) -> None:
        """Test updating only api_key preserves existing api_secret."""
        from pydantic import SecretStr

        request = UpdateExchangeAccountRequest(api_key=SecretStr("new-key"))

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "old-key",
                    "api_secret": "existing-secret",
                    "passphrase": "existing-pass",
                }

                with patch("squant.services.account.get_crypto_manager") as mock_crypto:
                    crypto = MagicMock()
                    crypto.NONCE_SIZE = 12
                    crypto.encrypt_with_derived_nonce.return_value = b"encrypted"
                    mock_crypto.return_value = crypto

                    with patch.object(
                        service.repository, "update", new_callable=AsyncMock
                    ) as mock_update:
                        mock_update.return_value = mock_account
                        await service.update(uuid4(), request)

                    # api_key (index=0), api_secret (index=1), passphrase (index=2)
                    calls = crypto.encrypt_with_derived_nonce.call_args_list
                    assert calls[0][0][0] == "new-key"  # new api_key
                    assert calls[1][0][0] == "existing-secret"  # preserved api_secret
                    assert calls[2][0][0] == "existing-pass"  # preserved passphrase

    @pytest.mark.asyncio
    async def test_update_passphrase_to_empty_removes_it(
        self, service: ExchangeAccountService, mock_session: AsyncMock, mock_account
    ) -> None:
        """Test updating passphrase to empty string removes it."""
        from pydantic import SecretStr

        request = UpdateExchangeAccountRequest(
            api_key=SecretStr("key"), passphrase=SecretStr("")
        )

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "old-key",
                    "api_secret": "old-secret",
                    "passphrase": "old-pass",
                }

                with patch("squant.services.account.get_crypto_manager") as mock_crypto:
                    crypto = MagicMock()
                    crypto.NONCE_SIZE = 12
                    crypto.encrypt_with_derived_nonce.return_value = b"encrypted"
                    mock_crypto.return_value = crypto

                    with patch.object(
                        service.repository, "update", new_callable=AsyncMock
                    ) as mock_update:
                        mock_update.return_value = mock_account
                        await service.update(uuid4(), request)

                        # passphrase_enc should be set to None
                        update_kwargs = mock_update.call_args[1]
                        assert update_kwargs["passphrase_enc"] is None

    @pytest.mark.asyncio
    async def test_update_credentials_decryption_fails_raises_value_error(
        self, service: ExchangeAccountService, mock_account
    ) -> None:
        """Test that DecryptionError during update raises ValueError."""
        from pydantic import SecretStr

        from squant.utils.crypto import DecryptionError

        request = UpdateExchangeAccountRequest(api_key=SecretStr("new-key"))

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch("squant.services.account.get_crypto_manager") as mock_crypto:
                crypto = MagicMock()
                mock_crypto.return_value = crypto

                with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                    mock_decrypt.side_effect = DecryptionError("Corrupted data")

                    with pytest.raises(ValueError, match="corrupted"):
                        await service.update(uuid4(), request)

    @pytest.mark.asyncio
    async def test_update_new_passphrase_encrypts_it(
        self, service: ExchangeAccountService, mock_session: AsyncMock, mock_account
    ) -> None:
        """Test updating passphrase to new value encrypts and stores it."""
        from pydantic import SecretStr

        request = UpdateExchangeAccountRequest(
            api_key=SecretStr("key"), passphrase=SecretStr("new-pass")
        )

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "old-key",
                    "api_secret": "old-secret",
                }

                with patch("squant.services.account.get_crypto_manager") as mock_crypto:
                    crypto = MagicMock()
                    crypto.NONCE_SIZE = 12
                    crypto.encrypt_with_derived_nonce.return_value = b"encrypted"
                    mock_crypto.return_value = crypto

                    with patch.object(
                        service.repository, "update", new_callable=AsyncMock
                    ) as mock_update:
                        mock_update.return_value = mock_account
                        await service.update(uuid4(), request)

                    # Should encrypt: api_key(0), api_secret(1), passphrase(2)
                    assert crypto.encrypt_with_derived_nonce.call_count == 3
                    passphrase_call = crypto.encrypt_with_derived_nonce.call_args_list[2]
                    assert passphrase_call[0][0] == "new-pass"


class TestAccountErrors:
    """Tests for account error classes."""

    def test_account_not_found_error(self) -> None:
        """Test AccountNotFoundError message."""
        error = AccountNotFoundError("test-id")
        assert "test-id" in str(error)
        assert error.account_id == "test-id"

    def test_account_name_exists_error(self) -> None:
        """Test AccountNameExistsError message."""
        error = AccountNameExistsError("okx", "main-account")
        assert "main-account" in str(error)
        assert "okx" in str(error)
        assert error.exchange == "okx"
        assert error.name == "main-account"

    def test_account_in_use_error(self) -> None:
        """Test AccountInUseError message."""
        error = AccountInUseError("test-id", "has associated orders")
        assert "test-id" in str(error)
        assert "in use" in str(error)
        assert "orders" in str(error)
        assert error.account_id == "test-id"
        assert error.reason == "has associated orders"

    def test_account_in_use_error_no_reason(self) -> None:
        """Test AccountInUseError without reason."""
        error = AccountInUseError("test-id")
        assert "test-id" in str(error)
        assert "in use" in str(error)
        assert error.reason == ""


class TestConnectionTest:
    """Unit tests for ExchangeAccountService.test_connection (ACC-005).

    These tests verify the connection testing functionality which allows users
    to test their exchange credentials before using them for trading.
    """

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> ExchangeAccountService:
        """Create a service with mock session."""
        return ExchangeAccountService(mock_session)

    @pytest.fixture
    def sample_okx_account(self):
        """Create a sample OKX account with encrypted credentials."""
        account = MagicMock(spec=ExchangeAccount)
        account.id = uuid4()
        account.exchange = "okx"
        account.name = "test-account"
        account.testnet = True
        account.api_key_enc = b"encrypted_key"
        account.api_secret_enc = b"encrypted_secret"
        account.passphrase_enc = b"encrypted_pass"
        account.nonce = b"test_nonce_12"  # 12 bytes
        return account

    @pytest.fixture
    def sample_binance_account(self):
        """Create a sample Binance account (no passphrase)."""
        account = MagicMock(spec=ExchangeAccount)
        account.id = uuid4()
        account.exchange = "binance"
        account.name = "test-binance"
        account.testnet = False
        account.api_key_enc = b"encrypted_key"
        account.api_secret_enc = b"encrypted_secret"
        account.passphrase_enc = None
        account.nonce = b"test_nonce_12"
        return account

    @pytest.mark.asyncio
    async def test_connection_success_okx(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test successful OKX connection returns balance count."""
        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                    "passphrase": "test_pass",
                }

                with patch("squant.services.account.OKXAdapter") as MockAdapter:
                    mock_balance = MagicMock()
                    mock_balance.balances = [MagicMock(), MagicMock(), MagicMock()]

                    # Create proper async context manager mock
                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(return_value=mock_balance)
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is True
        assert result["balance_count"] == 3
        assert result["message"] is None

    @pytest.mark.asyncio
    async def test_connection_success_binance(
        self, service: ExchangeAccountService, sample_binance_account
    ) -> None:
        """Test successful Binance connection."""
        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_binance_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                }

                with patch("squant.services.account.BinanceAdapter") as MockAdapter:
                    mock_balance = MagicMock()
                    mock_balance.balances = [MagicMock()]

                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(return_value=mock_balance)
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_binance_account.id)

        assert result["success"] is True
        assert result["balance_count"] == 1

    @pytest.mark.asyncio
    async def test_connection_okx_missing_passphrase(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test OKX connection fails when passphrase is missing."""
        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                # Return credentials without passphrase
                mock_decrypt.return_value = {
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                }

                result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is False
        assert "passphrase" in result["message"].lower()
        assert result["balance_count"] is None

    @pytest.mark.asyncio
    async def test_connection_auth_failure(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test authentication failure returns proper error."""
        from squant.infra.exchange.exceptions import ExchangeAuthenticationError

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "invalid_key",
                    "api_secret": "invalid_secret",
                    "passphrase": "invalid_pass",
                }

                with patch("squant.services.account.OKXAdapter") as MockAdapter:
                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(
                        side_effect=ExchangeAuthenticationError("Invalid API key")
                    )
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is False
        assert "Authentication failed" in result["message"]
        assert result["balance_count"] is None

    @pytest.mark.asyncio
    async def test_connection_network_timeout(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test network timeout returns proper error."""
        from squant.infra.exchange.exceptions import ExchangeConnectionError

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "key",
                    "api_secret": "secret",
                    "passphrase": "pass",
                }

                with patch("squant.services.account.OKXAdapter") as MockAdapter:
                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(
                        side_effect=ExchangeConnectionError("Connection timed out")
                    )
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is False
        assert "Connection failed" in result["message"]
        assert result["balance_count"] is None

    @pytest.mark.asyncio
    async def test_connection_api_error(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test API error returns proper error."""
        from squant.infra.exchange.exceptions import ExchangeAPIError

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "key",
                    "api_secret": "secret",
                    "passphrase": "pass",
                }

                with patch("squant.services.account.OKXAdapter") as MockAdapter:
                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(
                        side_effect=ExchangeAPIError("Rate limit exceeded")
                    )
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is False
        assert "API error" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_unknown_exchange(self, service: ExchangeAccountService) -> None:
        """Test unknown exchange returns proper error.

        Note: ConnectionTestError is caught by the generic Exception handler
        in test_connection, so it returns an error result rather than raising.
        """
        unknown_account = MagicMock(spec=ExchangeAccount)
        unknown_account.id = uuid4()
        unknown_account.exchange = "unknown_exchange"
        unknown_account.api_key_enc = b"key"
        unknown_account.api_secret_enc = b"secret"
        unknown_account.passphrase_enc = None
        unknown_account.nonce = b"test_nonce_12"

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = unknown_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "key",
                    "api_secret": "secret",
                }

                result = await service.test_connection(unknown_account.id)

        # The ConnectionTestError is caught by generic Exception handler
        assert result["success"] is False
        assert "unknown_exchange" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_connection_account_not_found(self, service: ExchangeAccountService) -> None:
        """Test connection test with non-existent account."""
        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            with pytest.raises(AccountNotFoundError):
                await service.test_connection(uuid4())

    @pytest.mark.asyncio
    async def test_connection_decryption_failure(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test connection test when credential decryption fails.

        Security: Error message should be generic to avoid leaking implementation details.
        """
        from squant.services.account import ConnectionTestError
        from squant.utils.crypto import DecryptionError

        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.side_effect = DecryptionError("Invalid key")

                with pytest.raises(ConnectionTestError) as exc_info:
                    await service.test_connection(sample_okx_account.id)

        # Error message should be generic (not expose "decryption" implementation details)
        error_msg = str(exc_info.value).lower()
        assert "credentials" in error_msg
        assert "corrupted" in error_msg or "recreate" in error_msg

    @pytest.mark.asyncio
    async def test_connection_unexpected_error(
        self, service: ExchangeAccountService, sample_okx_account
    ) -> None:
        """Test connection test handles unexpected errors gracefully."""
        with patch.object(service.repository, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_okx_account

            with patch.object(service, "get_decrypted_credentials") as mock_decrypt:
                mock_decrypt.return_value = {
                    "api_key": "key",
                    "api_secret": "secret",
                    "passphrase": "pass",
                }

                with patch("squant.services.account.OKXAdapter") as MockAdapter:
                    mock_adapter_instance = MagicMock()
                    mock_adapter_instance.get_balance = AsyncMock(
                        side_effect=RuntimeError("Unexpected internal error")
                    )
                    mock_adapter_instance.__aenter__ = AsyncMock(return_value=mock_adapter_instance)
                    mock_adapter_instance.__aexit__ = AsyncMock(return_value=None)
                    MockAdapter.return_value = mock_adapter_instance

                    result = await service.test_connection(sample_okx_account.id)

        assert result["success"] is False
        assert "Unexpected error" in result["message"]


class TestGetDecryptedCredentials:
    """Unit tests for get_decrypted_credentials method."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session: AsyncMock) -> ExchangeAccountService:
        """Create a service with mock session."""
        return ExchangeAccountService(mock_session)

    def test_decrypt_all_credentials(self, service: ExchangeAccountService) -> None:
        """Test all credentials are decrypted correctly."""
        account = MagicMock(spec=ExchangeAccount)
        account.api_key_enc = b"encrypted_key"
        account.api_secret_enc = b"encrypted_secret"
        account.passphrase_enc = b"encrypted_pass"
        account.nonce = b"test_nonce_12"

        with patch("squant.services.account.get_crypto_manager") as mock_crypto:
            mock_manager = MagicMock()
            mock_manager.decrypt_with_derived_nonce.side_effect = [
                "decrypted_key",
                "decrypted_secret",
                "decrypted_pass",
            ]
            mock_crypto.return_value = mock_manager

            result = service.get_decrypted_credentials(account)

        assert result["api_key"] == "decrypted_key"
        assert result["api_secret"] == "decrypted_secret"
        assert result["passphrase"] == "decrypted_pass"

        # Verify correct nonce indices were used
        calls = mock_manager.decrypt_with_derived_nonce.call_args_list
        assert calls[0][1]["index"] == 0  # api_key
        assert calls[1][1]["index"] == 1  # api_secret
        assert calls[2][1]["index"] == 2  # passphrase

    def test_decrypt_without_passphrase(self, service: ExchangeAccountService) -> None:
        """Test decryption works when passphrase is not set."""
        account = MagicMock(spec=ExchangeAccount)
        account.api_key_enc = b"encrypted_key"
        account.api_secret_enc = b"encrypted_secret"
        account.passphrase_enc = None  # No passphrase
        account.nonce = b"test_nonce_12"

        with patch("squant.services.account.get_crypto_manager") as mock_crypto:
            mock_manager = MagicMock()
            mock_manager.decrypt_with_derived_nonce.side_effect = [
                "decrypted_key",
                "decrypted_secret",
            ]
            mock_crypto.return_value = mock_manager

            result = service.get_decrypted_credentials(account)

        assert result["api_key"] == "decrypted_key"
        assert result["api_secret"] == "decrypted_secret"
        assert "passphrase" not in result

        # Only two decryption calls should be made
        assert mock_manager.decrypt_with_derived_nonce.call_count == 2

    def test_decrypt_raises_on_failure(self, service: ExchangeAccountService) -> None:
        """Test that decryption error is propagated."""
        from squant.utils.crypto import DecryptionError

        account = MagicMock(spec=ExchangeAccount)
        account.api_key_enc = b"corrupted_data"
        account.api_secret_enc = b"encrypted_secret"
        account.passphrase_enc = None
        account.nonce = b"test_nonce_12"

        with patch("squant.services.account.get_crypto_manager") as mock_crypto:
            mock_manager = MagicMock()
            mock_manager.decrypt_with_derived_nonce.side_effect = DecryptionError(
                "Decryption failed"
            )
            mock_crypto.return_value = mock_manager

            with pytest.raises(DecryptionError):
                service.get_decrypted_credentials(account)
