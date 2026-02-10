"""Exchange account API endpoints."""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse
from squant.infra.database import get_session
from squant.schemas.account import (
    ConnectionTestResponse,
    CreateExchangeAccountRequest,
    ExchangeAccountListItem,
    ExchangeAccountResponse,
    UpdateExchangeAccountRequest,
)
from squant.services.account import (
    AccountInUseError,
    AccountNameExistsError,
    AccountNotFoundError,
    ExchangeAccountService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[ExchangeAccountResponse], status_code=201)
async def create_exchange_account(
    request: CreateExchangeAccountRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ExchangeAccountResponse]:
    """Create a new exchange account configuration.

    Store API credentials securely with AES-256-GCM encryption.

    Args:
        request: Account creation request with credentials.
        session: Database session.

    Returns:
        Created account (credentials not returned).

    Raises:
        HTTPException: 400 if OKX without passphrase, 409 if name exists.
    """
    # Validate OKX requires passphrase
    if request.exchange == "okx" and not request.passphrase:
        raise HTTPException(
            status_code=400,
            detail="OKX exchange requires passphrase",
        )

    service = ExchangeAccountService(session)

    try:
        account = await service.create(request)
        return ApiResponse(data=ExchangeAccountResponse.model_validate(account))
    except AccountNameExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=ApiResponse[list[ExchangeAccountListItem]])
async def list_exchange_accounts(
    exchange: Literal["okx", "binance"] | None = Query(None, description="Filter by exchange"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ExchangeAccountListItem]]:
    """List all exchange account configurations.

    Args:
        exchange: Optional exchange filter.
        session: Database session.

    Returns:
        List of accounts (credentials not returned).
    """
    service = ExchangeAccountService(session)
    accounts = await service.list(exchange=exchange)
    items = [ExchangeAccountListItem.model_validate(a) for a in accounts]
    return ApiResponse(data=items)


@router.get("/{account_id}", response_model=ApiResponse[ExchangeAccountResponse])
async def get_exchange_account(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ExchangeAccountResponse]:
    """Get exchange account details by ID.

    Args:
        account_id: Account UUID.
        session: Database session.

    Returns:
        Account details (credentials not returned).

    Raises:
        HTTPException: 404 if not found.
    """
    service = ExchangeAccountService(session)

    try:
        account = await service.get(account_id)
        return ApiResponse(data=ExchangeAccountResponse.model_validate(account))
    except AccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{account_id}", response_model=ApiResponse[ExchangeAccountResponse])
async def update_exchange_account(
    account_id: UUID,
    request: UpdateExchangeAccountRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ExchangeAccountResponse]:
    """Update an exchange account configuration.

    Args:
        account_id: Account UUID.
        request: Update request.
        session: Database session.

    Returns:
        Updated account (credentials not returned).

    Raises:
        HTTPException: 404 if not found, 409 if name exists.
    """
    service = ExchangeAccountService(session)

    try:
        account = await service.update(account_id, request)
        return ApiResponse(data=ExchangeAccountResponse.model_validate(account))
    except AccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AccountNameExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{account_id}", response_model=ApiResponse[None])
async def delete_exchange_account(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete an exchange account configuration.

    Args:
        account_id: Account UUID.
        session: Database session.

    Returns:
        Success response.

    Raises:
        HTTPException: 404 if not found, 409 if account is in use.
    """
    service = ExchangeAccountService(session)

    try:
        await service.delete(account_id)
        return ApiResponse(data=None, message="Account deleted")
    except AccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AccountInUseError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{account_id}/test", response_model=ApiResponse[ConnectionTestResponse])
async def test_exchange_connection(
    account_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ConnectionTestResponse]:
    """Test connection to exchange using stored credentials.

    Attempts to fetch account balance to verify API credentials are valid.

    Args:
        account_id: Account UUID.
        session: Database session.

    Returns:
        Connection test result with success status and balance count.

    Raises:
        HTTPException: 404 if account not found.
    """
    service = ExchangeAccountService(session)

    try:
        result = await service.test_connection(account_id)
        return ApiResponse(
            data=ConnectionTestResponse(
                success=result["success"],
                message=result["message"],
                balance_count=result["balance_count"],
            )
        )
    except AccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
