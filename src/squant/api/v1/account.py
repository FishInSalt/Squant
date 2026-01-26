"""Account API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Path

from squant.api.deps import OKXExchange
from squant.api.utils import ApiResponse, handle_exchange_error
from squant.schemas.exchange import (
    BalanceItem,
    BalanceResponse,
)

router = APIRouter()


@router.get("/balance", response_model=ApiResponse[BalanceResponse])
async def get_balance(exchange: OKXExchange) -> ApiResponse[BalanceResponse]:
    """Get account balance for all currencies.

    Returns the available and frozen balance for each currency in the account.
    """
    try:
        account = await exchange.get_balance()
        data = BalanceResponse(
            exchange=account.exchange,
            balances=[
                BalanceItem(
                    currency=b.currency,
                    available=b.available,
                    frozen=b.frozen,
                    total=b.total,
                )
                for b in account.balances
            ],
            timestamp=account.timestamp,
        )
        return ApiResponse(data=data)
    except Exception as e:
        handle_exchange_error(e)


@router.get("/balance/{currency}", response_model=ApiResponse[BalanceItem | None])
async def get_balance_currency(
    exchange: OKXExchange,
    currency: Annotated[str, Path(description="Currency symbol (e.g., BTC, USDT)")],
) -> ApiResponse[BalanceItem | None]:
    """Get balance for a specific currency.

    Returns None if the currency is not found in the account.
    """
    try:
        balance = await exchange.get_balance_currency(currency)
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
