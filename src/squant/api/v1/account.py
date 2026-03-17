"""Account API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from squant.api.deps import DbSession
from squant.api.utils import ApiResponse, handle_exchange_error
from squant.infra.exchange.ccxt import CCXTRestAdapter, ExchangeCredentials
from squant.models.exchange import ExchangeAccount
from squant.schemas.exchange import (
    BalanceItem,
    BalanceResponse,
)
from squant.services.account import ExchangeAccountService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_active_account(session) -> ExchangeAccount:
    """Get an active exchange account for balance queries.

    Returns:
        Active ExchangeAccount with encrypted credentials.

    Raises:
        HTTPException: If no active account exists.
    """
    from sqlalchemy import select

    stmt = (
        select(ExchangeAccount)
        .where(ExchangeAccount.is_active == True)  # noqa: E712
        .order_by(ExchangeAccount.created_at.asc())
        .limit(1)
    )

    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if account is None:
        raise HTTPException(
            status_code=400,
            detail="No active exchange account found. "
            "Please create an account via POST /api/v1/exchange-accounts first.",
        )

    # Security check: Ensure account has proper encrypted credentials
    if account.nonce == b"placeholder" or len(account.nonce) < 12:
        raise HTTPException(
            status_code=400,
            detail="Account has invalid credentials. "
            "Please recreate the account with proper API credentials.",
        )

    return account


async def _create_adapter_from_account(account: ExchangeAccount) -> CCXTRestAdapter:
    """Create an authenticated CCXTRestAdapter from an exchange account.

    Args:
        account: Exchange account with encrypted credentials.

    Returns:
        Connected CCXTRestAdapter instance.

    Raises:
        HTTPException: If credentials cannot be decrypted.
    """
    service = ExchangeAccountService.__new__(ExchangeAccountService)
    try:
        credentials = service.get_decrypted_credentials(account)
    except Exception as e:
        logger.error(f"Failed to decrypt credentials for account {account.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access account credentials. "
            "The stored credentials may be corrupted.",
        ) from e

    exchange_id = account.exchange.lower()
    ccxt_credentials = ExchangeCredentials(
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        passphrase=credentials.get("passphrase"),
        sandbox=account.testnet,
    )
    adapter = CCXTRestAdapter(exchange_id, ccxt_credentials)
    return adapter


@router.get("/balance", response_model=ApiResponse[BalanceResponse])
async def get_balance(session: DbSession) -> ApiResponse[BalanceResponse]:
    """Get account balance for all currencies.

    Returns the available and frozen balance for each currency
    using the first active exchange account.
    """
    account = await _get_active_account(session)
    adapter = await _create_adapter_from_account(account)

    try:
        async with adapter:
            account_balance = await adapter.get_balance()
            data = BalanceResponse(
                exchange=account_balance.exchange,
                balances=[
                    BalanceItem(
                        currency=b.currency,
                        available=b.available,
                        frozen=b.frozen,
                        total=b.total,
                    )
                    for b in account_balance.balances
                ],
                timestamp=account_balance.timestamp,
            )
            return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/balance/{currency}", response_model=ApiResponse[BalanceItem | None])
async def get_balance_currency(
    session: DbSession,
    currency: Annotated[str, Path(description="Currency symbol (e.g., BTC, USDT)")],
) -> ApiResponse[BalanceItem | None]:
    """Get balance for a specific currency.

    Returns None if the currency is not found in the account.
    """
    account = await _get_active_account(session)
    adapter = await _create_adapter_from_account(account)

    try:
        async with adapter:
            balance = await adapter.get_balance_currency(currency)
            if balance is None:
                return ApiResponse(data=None)
            data = BalanceItem(
                currency=balance.currency,
                available=balance.available,
                frozen=balance.frozen,
                total=balance.total,
            )
            return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)
