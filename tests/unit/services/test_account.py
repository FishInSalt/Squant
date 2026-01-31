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

        with patch.object(service.repository, "exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = True

            with patch.object(service.repository, "delete", new_callable=AsyncMock) as mock_delete:
                mock_delete.return_value = True

                await service.delete(account_id)
                mock_delete.assert_called_once_with(account_id)
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service: ExchangeAccountService) -> None:
        """Test deleting an account that doesn't exist."""
        account_id = uuid4()

        with patch.object(service.repository, "exists", new_callable=AsyncMock) as mock_exists:
            mock_exists.return_value = False

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
