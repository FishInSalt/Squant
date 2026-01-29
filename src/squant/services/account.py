"""Exchange account service for account management."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.exchange import BinanceAdapter, OKXAdapter
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
)
from squant.infra.repository import BaseRepository
from squant.models.exchange import ExchangeAccount
from squant.schemas.account import (
    CreateExchangeAccountRequest,
    UpdateExchangeAccountRequest,
)
from squant.utils.crypto import DecryptionError, get_crypto_manager

logger = logging.getLogger(__name__)


class AccountNotFoundError(Exception):
    """Exchange account not found in database."""

    def __init__(self, account_id: str | UUID):
        self.account_id = str(account_id)
        super().__init__(f"Exchange account not found: {account_id}")


class AccountNameExistsError(Exception):
    """Exchange account name already exists for this exchange."""

    def __init__(self, exchange: str, name: str):
        self.exchange = exchange
        self.name = name
        super().__init__(f"Account name '{name}' already exists for exchange '{exchange}'")


class ConnectionTestError(Exception):
    """Connection test failed."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AccountInUseError(Exception):
    """Exchange account is in use and cannot be deleted."""

    def __init__(self, account_id: str | UUID, reason: str = ""):
        self.account_id = str(account_id)
        self.reason = reason
        msg = f"Exchange account {account_id} is in use"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class ExchangeAccountRepository(BaseRepository[ExchangeAccount]):
    """Repository for ExchangeAccount model with specialized queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(ExchangeAccount, session)

    async def get_by_exchange_and_name(
        self, exchange: str, name: str
    ) -> ExchangeAccount | None:
        """Get account by exchange and name combination.

        Args:
            exchange: Exchange identifier (e.g., 'okx', 'binance').
            name: Account name.

        Returns:
            ExchangeAccount if found, None otherwise.
        """
        stmt = select(ExchangeAccount).where(
            and_(ExchangeAccount.exchange == exchange, ExchangeAccount.name == name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_exchange(self, exchange: str) -> list[ExchangeAccount]:
        """List all accounts for a specific exchange.

        Args:
            exchange: Exchange identifier.

        Returns:
            List of accounts for the exchange.
        """
        stmt = (
            select(ExchangeAccount)
            .where(ExchangeAccount.exchange == exchange)
            .order_by(ExchangeAccount.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[ExchangeAccount]:
        """List all active accounts.

        Returns:
            List of active accounts.
        """
        stmt = (
            select(ExchangeAccount)
            .where(ExchangeAccount.is_active == True)  # noqa: E712
            .order_by(ExchangeAccount.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self, exchange: str | None = None
    ) -> list[ExchangeAccount]:
        """List all accounts with optional exchange filter.

        Args:
            exchange: Optional exchange filter.

        Returns:
            List of accounts.
        """
        stmt = select(ExchangeAccount)

        if exchange is not None:
            stmt = stmt.where(ExchangeAccount.exchange == exchange)

        stmt = stmt.order_by(ExchangeAccount.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ExchangeAccountService:
    """Service for exchange account business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ExchangeAccountRepository(session)

    async def create(self, request: CreateExchangeAccountRequest) -> ExchangeAccount:
        """Create a new exchange account.

        Args:
            request: Account creation request.

        Returns:
            Created account.

        Raises:
            AccountNameExistsError: If name already exists for this exchange.
        """
        # Check name uniqueness for this exchange
        existing = await self.repository.get_by_exchange_and_name(
            request.exchange, request.name
        )
        if existing:
            raise AccountNameExistsError(request.exchange, request.name)

        # Encrypt credentials using derived nonces
        # Each field uses a unique nonce derived from the base nonce
        # Index: 0=api_key, 1=api_secret, 2=passphrase
        import os

        crypto = get_crypto_manager()
        nonce = os.urandom(crypto.NONCE_SIZE)

        api_key_enc = crypto.encrypt_with_derived_nonce(
            request.api_key.get_secret_value(), nonce, index=0
        )
        api_secret_enc = crypto.encrypt_with_derived_nonce(
            request.api_secret.get_secret_value(), nonce, index=1
        )

        passphrase_enc = None
        if request.passphrase:
            passphrase_enc = crypto.encrypt_with_derived_nonce(
                request.passphrase.get_secret_value(), nonce, index=2
            )

        # Create account
        account = await self.repository.create(
            exchange=request.exchange,
            name=request.name,
            api_key_enc=api_key_enc,
            api_secret_enc=api_secret_enc,
            passphrase_enc=passphrase_enc,
            nonce=nonce,
            testnet=request.testnet,
        )

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            # Handle unique constraint violation (race condition)
            if "uq_exchange_account_name" in str(e).lower():
                raise AccountNameExistsError(request.exchange, request.name) from e
            raise

        return account

    async def update(
        self, account_id: UUID, request: UpdateExchangeAccountRequest
    ) -> ExchangeAccount:
        """Update an existing exchange account.

        Args:
            account_id: Account ID.
            request: Update request.

        Returns:
            Updated account.

        Raises:
            AccountNotFoundError: If account not found.
            AccountNameExistsError: If new name already exists.
        """
        account = await self.repository.get(account_id)
        if not account:
            raise AccountNotFoundError(account_id)

        # Check name uniqueness if name is being changed
        if request.name and request.name != account.name:
            existing = await self.repository.get_by_exchange_and_name(
                account.exchange, request.name
            )
            if existing:
                raise AccountNameExistsError(account.exchange, request.name)

        # Build update data
        update_data: dict[str, Any] = {}

        if request.name is not None:
            update_data["name"] = request.name
        if request.testnet is not None:
            update_data["testnet"] = request.testnet
        if request.is_active is not None:
            update_data["is_active"] = request.is_active

        # Handle credential updates (requires re-encryption with new nonce)
        if (
            request.api_key is not None
            or request.api_secret is not None
            or request.passphrase is not None
        ):
            import os

            crypto = get_crypto_manager()

            # Decrypt existing credentials if not being updated
            existing_creds = self.get_decrypted_credentials(account)

            api_key = (
                request.api_key.get_secret_value()
                if request.api_key
                else existing_creds["api_key"]
            )
            api_secret = (
                request.api_secret.get_secret_value()
                if request.api_secret
                else existing_creds["api_secret"]
            )

            # Generate new nonce and re-encrypt all credentials with derived nonces
            nonce = os.urandom(crypto.NONCE_SIZE)
            api_key_enc = crypto.encrypt_with_derived_nonce(api_key, nonce, index=0)
            api_secret_enc = crypto.encrypt_with_derived_nonce(api_secret, nonce, index=1)

            update_data["api_key_enc"] = api_key_enc
            update_data["api_secret_enc"] = api_secret_enc
            update_data["nonce"] = nonce

            # Handle passphrase
            if request.passphrase is not None:
                passphrase_enc = crypto.encrypt_with_derived_nonce(
                    request.passphrase.get_secret_value(), nonce, index=2
                )
                update_data["passphrase_enc"] = passphrase_enc
            elif existing_creds.get("passphrase"):
                passphrase_enc = crypto.encrypt_with_derived_nonce(
                    existing_creds["passphrase"], nonce, index=2
                )
                update_data["passphrase_enc"] = passphrase_enc

        if update_data:
            await self.repository.update(account_id, **update_data)

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            # Handle unique constraint violation (race condition)
            if "uq_exchange_account_name" in str(e).lower():
                raise AccountNameExistsError(
                    account.exchange, request.name or account.name
                ) from e
            raise

        # Refresh to get updated data
        await self.session.refresh(account)
        return account

    async def delete(self, account_id: UUID) -> None:
        """Delete an exchange account.

        Args:
            account_id: Account ID.

        Raises:
            AccountNotFoundError: If account not found.
            AccountInUseError: If account has associated orders or strategy runs.
        """
        exists = await self.repository.exists(account_id)
        if not exists:
            raise AccountNotFoundError(account_id)

        await self.repository.delete(account_id)

        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            error_str = str(e).lower()
            # Handle foreign key constraint violations
            if "foreign key" in error_str or "restrict" in error_str:
                reason = ""
                if "orders" in error_str:
                    reason = "has associated orders"
                elif "strategy_runs" in error_str:
                    reason = "has associated strategy runs"
                raise AccountInUseError(account_id, reason) from e
            raise

    async def get(self, account_id: UUID) -> ExchangeAccount:
        """Get an exchange account by ID.

        Args:
            account_id: Account ID.

        Returns:
            Exchange account.

        Raises:
            AccountNotFoundError: If not found.
        """
        account = await self.repository.get(account_id)
        if not account:
            raise AccountNotFoundError(account_id)
        return account

    async def list(self, exchange: str | None = None) -> list[ExchangeAccount]:
        """List exchange accounts with optional filter.

        Args:
            exchange: Optional exchange filter.

        Returns:
            List of accounts.
        """
        return await self.repository.list_all(exchange=exchange)

    async def test_connection(self, account_id: UUID) -> dict[str, Any]:
        """Test connection to exchange using stored credentials.

        Args:
            account_id: Account ID.

        Returns:
            Dict with success status and balance count.

        Raises:
            AccountNotFoundError: If account not found.
            ConnectionTestError: If connection test fails.
        """
        account = await self.repository.get(account_id)
        if not account:
            raise AccountNotFoundError(account_id)

        # Decrypt credentials
        try:
            credentials = self.get_decrypted_credentials(account)
        except DecryptionError as e:
            raise ConnectionTestError(f"Failed to decrypt credentials: {e}") from e

        # Create adapter and test connection
        try:
            if account.exchange == "okx":
                passphrase = credentials.get("passphrase")
                if not passphrase:
                    return {
                        "success": False,
                        "message": "OKX account missing passphrase",
                        "balance_count": None,
                    }
                adapter = OKXAdapter(
                    api_key=credentials["api_key"],
                    api_secret=credentials["api_secret"],
                    passphrase=passphrase,
                    testnet=account.testnet,
                )
            elif account.exchange == "binance":
                adapter = BinanceAdapter(
                    api_key=credentials["api_key"],
                    api_secret=credentials["api_secret"],
                    testnet=account.testnet,
                )
            else:
                raise ConnectionTestError(f"Unknown exchange: {account.exchange}")

            async with adapter:
                balance = await adapter.get_balance()
                return {
                    "success": True,
                    "message": None,
                    "balance_count": len(balance.balances),
                }

        except ExchangeAuthenticationError as e:
            logger.warning(f"Authentication failed for account {account_id}: {e}")
            return {
                "success": False,
                "message": f"Authentication failed: {e}",
                "balance_count": None,
            }
        except ExchangeConnectionError as e:
            logger.warning(f"Connection failed for account {account_id}: {e}")
            return {
                "success": False,
                "message": f"Connection failed: {e}",
                "balance_count": None,
            }
        except ExchangeAPIError as e:
            logger.warning(f"API error for account {account_id}: {e}")
            return {
                "success": False,
                "message": f"API error: {e}",
                "balance_count": None,
            }
        except Exception as e:
            logger.exception(f"Unexpected error testing account {account_id}")
            return {
                "success": False,
                "message": f"Unexpected error: {e}",
                "balance_count": None,
            }

    def get_decrypted_credentials(self, account: ExchangeAccount) -> dict[str, str]:
        """Decrypt and return account credentials.

        Uses derived nonces for each field:
        - Index 0: api_key
        - Index 1: api_secret
        - Index 2: passphrase

        Args:
            account: Exchange account with encrypted credentials.

        Returns:
            Dict with decrypted api_key, api_secret, and optionally passphrase.

        Raises:
            DecryptionError: If decryption fails.
        """
        crypto = get_crypto_manager()

        result = {
            "api_key": crypto.decrypt_with_derived_nonce(
                account.api_key_enc, account.nonce, index=0
            ),
            "api_secret": crypto.decrypt_with_derived_nonce(
                account.api_secret_enc, account.nonce, index=1
            ),
        }

        if account.passphrase_enc:
            result["passphrase"] = crypto.decrypt_with_derived_nonce(
                account.passphrase_enc, account.nonce, index=2
            )

        return result
