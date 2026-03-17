"""Order management API endpoints.

This module provides REST API endpoints for managing orders:
- Creating orders (persisted to DB + submitted to exchange)
- Canceling orders
- Querying order history
- Syncing order status from exchange

Security Note: Orders require a valid exchange account created through
the /api/v1/exchange-accounts endpoint with properly encrypted credentials.
"""

import logging
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from squant.api.deps import DbSession
from squant.api.utils import ApiResponse, handle_exchange_error, paginate_params
from squant.models.enums import OrderSide, OrderStatus
from squant.models.exchange import ExchangeAccount
from squant.schemas.order import (
    CreateOrderRequest,
    OrderDetail,
    OrderListData,
    OrderStatsResponse,
    OrderWithTrades,
    SyncOrdersResponse,
    TradeDetail,
)
from squant.services.order import (
    OrderNotFoundError,
    OrderService,
    OrderValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class NoActiveAccountError(Exception):
    """No active exchange account available."""

    def __init__(self, exchange: str = "okx"):
        super().__init__(
            f"No active exchange account found for '{exchange}'. "
            f"Please create an account via POST /api/v1/exchange-accounts first."
        )


async def _get_active_account(
    session: DbSession,
    exchange: str = "okx",
) -> ExchangeAccount:
    """Get an active exchange account for order operations.

    Security: Only returns accounts with properly encrypted credentials
    that were created through the official account creation flow.

    Args:
        session: Database session.
        exchange: Exchange name.

    Returns:
        Active ExchangeAccount with encrypted credentials.

    Raises:
        NoActiveAccountError: If no active account exists.
    """
    from sqlalchemy import select

    # Find first active account for this exchange
    stmt = (
        select(ExchangeAccount)
        .where(
            ExchangeAccount.exchange == exchange,
            ExchangeAccount.is_active == True,  # noqa: E712
        )
        .order_by(ExchangeAccount.created_at.asc())
        .limit(1)
    )

    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if account is None:
        logger.warning(f"No active exchange account found for {exchange}")
        raise NoActiveAccountError(exchange)

    # Security check: Ensure account has proper encrypted credentials
    # Placeholder credentials are exactly 11 bytes ("placeholder")
    if account.nonce == b"placeholder" or len(account.nonce) < 12:
        logger.error(
            f"Account {account.id} has invalid credentials - may be a legacy placeholder. "
            "Please recreate the account with proper API credentials."
        )
        raise NoActiveAccountError(exchange)

    return account


async def get_order_service(
    session: DbSession,
) -> AsyncGenerator[OrderService, None]:
    """Get OrderService instance.

    This dependency provides an OrderService configured with:
    - Database session for persistence
    - Exchange adapter created from the active account's credentials
    - Active account with encrypted credentials

    The adapter is properly closed after the request completes.

    Args:
        session: Database session.

    Yields:
        Configured OrderService.

    Raises:
        HTTPException: If no active exchange account is available.
    """
    from squant.infra.exchange.ccxt import CCXTRestAdapter, ExchangeCredentials
    from squant.services.account import ExchangeAccountService

    try:
        account = await _get_active_account(session)
    except NoActiveAccountError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e

    # Decrypt credentials and create an authenticated adapter
    try:
        credentials = ExchangeAccountService.get_decrypted_credentials(account)
    except Exception as e:
        logger.error(f"Failed to decrypt credentials for account {account.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to access account credentials.",
        ) from e

    exchange_id = account.exchange.lower()
    ccxt_credentials = ExchangeCredentials(
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        passphrase=credentials.get("passphrase"),
        sandbox=account.testnet,
    )
    adapter = CCXTRestAdapter(exchange_id, ccxt_credentials)
    await adapter.connect()
    try:
        yield OrderService(session, adapter, account)
    finally:
        await adapter.close()


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


def _handle_order_error(e: Exception) -> None:
    """Convert order service exceptions to HTTP exceptions."""
    if isinstance(e, OrderNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, OrderValidationError):
        raise HTTPException(status_code=400, detail=str(e))
    # Delegate to common exchange error handler
    handle_exchange_error(e)


def _status_display(status: OrderStatus | str) -> str:
    """Map order status to frontend-friendly display value (OD-004)."""
    status_str = status.value if isinstance(status, OrderStatus) else status
    if status_str in ("pending", "submitted"):
        return "open"
    return status_str


def _to_order_detail(order) -> OrderDetail:
    """Convert Order model to OrderDetail schema."""
    commission = sum((t.fee for t in order.trades), Decimal("0")) if order.trades else Decimal("0")
    commission_asset = None
    if order.trades:
        # Use fee_currency from the first trade (typically consistent across trades)
        commission_asset = next((t.fee_currency for t in order.trades if t.fee_currency), None)
    strategy_name = None
    if order.run and order.run.strategy:
        strategy_name = order.run.strategy.name
    return OrderDetail(
        id=UUID(order.id),
        account_id=UUID(order.account_id),
        run_id=UUID(order.run_id) if order.run_id else None,
        exchange=order.exchange,
        exchange_oid=order.exchange_oid,
        symbol=order.symbol,
        side=order.side,
        type=order.type,
        status=order.status,
        price=order.price,
        amount=order.amount,
        filled=order.filled,
        avg_price=order.avg_price,
        reject_reason=order.reject_reason,
        commission=commission,
        commission_asset=commission_asset,
        remaining_amount=order.amount - order.filled,
        status_display=_status_display(order.status),
        strategy_name=strategy_name,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _to_order_with_trades(order) -> OrderWithTrades:
    """Convert Order model to OrderWithTrades schema."""
    trades = [
        TradeDetail(
            id=UUID(t.id),
            order_id=UUID(t.order_id),
            exchange_tid=t.exchange_tid,
            price=t.price,
            amount=t.amount,
            fee=t.fee,
            fee_currency=t.fee_currency,
            timestamp=t.timestamp,
        )
        for t in order.trades
    ]
    commission = sum((t.fee for t in order.trades), Decimal("0")) if order.trades else Decimal("0")
    commission_asset = None
    if order.trades:
        commission_asset = next((t.fee_currency for t in order.trades if t.fee_currency), None)
    strategy_name = None
    if order.run and order.run.strategy:
        strategy_name = order.run.strategy.name
    return OrderWithTrades(
        id=UUID(order.id),
        account_id=UUID(order.account_id),
        run_id=UUID(order.run_id) if order.run_id else None,
        exchange=order.exchange,
        exchange_oid=order.exchange_oid,
        symbol=order.symbol,
        side=order.side,
        type=order.type,
        status=order.status,
        price=order.price,
        amount=order.amount,
        filled=order.filled,
        avg_price=order.avg_price,
        reject_reason=order.reject_reason,
        commission=commission,
        commission_asset=commission_asset,
        remaining_amount=order.amount - order.filled,
        status_display=_status_display(order.status),
        strategy_name=strategy_name,
        created_at=order.created_at,
        updated_at=order.updated_at,
        trades=trades,
    )


@router.post("", response_model=ApiResponse[OrderDetail], status_code=201)
async def create_order(
    service: OrderServiceDep,
    request: CreateOrderRequest,
) -> ApiResponse[OrderDetail]:
    """Create and submit a new order.

    The order is persisted to the database and submitted to the exchange.
    If the exchange submission fails, the order is marked as REJECTED.

    For limit orders, price is required.
    For market orders, price should be omitted.
    """
    try:
        order = await service.create_order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.type,
            amount=request.amount,
            price=request.price,
            client_order_id=request.client_order_id,
            run_id=request.run_id,
        )
        return ApiResponse(data=_to_order_detail(order))
    except (OrderValidationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _handle_order_error(e)


@router.get("", response_model=ApiResponse[OrderListData])
async def list_orders(
    service: OrderServiceDep,
    status: Annotated[list[OrderStatus] | None, Query(description="Filter by status")] = None,
    symbol: Annotated[str | None, Query(description="Filter by trading pair")] = None,
    side: Annotated[OrderSide | None, Query(description="Filter by side")] = None,
    page: Annotated[int, Query(ge=1, description="Page number (starts from 1)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> ApiResponse[OrderListData]:
    """List orders with optional filters.

    Returns paginated list of orders matching the specified criteria.
    """
    try:
        offset, limit = paginate_params(page, page_size)
        orders = await service.list_orders(
            status=status,
            symbol=symbol,
            side=side,
            offset=offset,
            limit=limit,
        )
        total = await service.count_orders(status=status, symbol=symbol, side=side)
        data = OrderListData(
            items=[_to_order_detail(o) for o in orders],
            total=total,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(data=data)
    except Exception as e:
        _handle_order_error(e)


@router.get("/open", response_model=ApiResponse[list[OrderDetail]])
async def get_open_orders(
    service: OrderServiceDep,
    symbol: Annotated[str | None, Query(description="Filter by trading pair")] = None,
) -> ApiResponse[list[OrderDetail]]:
    """Get all open (non-terminal) orders.

    Returns orders with status PENDING, SUBMITTED, or PARTIAL.
    """
    try:
        orders = await service.get_open_orders(symbol=symbol)
        return ApiResponse(data=[_to_order_detail(o) for o in orders])
    except Exception as e:
        _handle_order_error(e)


@router.get("/stats", response_model=ApiResponse[OrderStatsResponse])
async def get_order_stats(
    service: OrderServiceDep,
) -> ApiResponse[OrderStatsResponse]:
    """Get order statistics by status."""
    try:
        # Use single aggregated query instead of N+1 queries
        stats = await service.get_order_stats()
        data = OrderStatsResponse(
            total=stats["total"],
            open=stats["pending"] + stats["submitted"],
            pending=stats["pending"],
            submitted=stats["submitted"],
            partial=stats["partial"],
            filled=stats["filled"],
            cancelled=stats["cancelled"],
            rejected=stats["rejected"],
        )
        return ApiResponse(data=data)
    except Exception as e:
        _handle_order_error(e)


@router.get("/{order_id}", response_model=ApiResponse[OrderWithTrades])
async def get_order(
    service: OrderServiceDep,
    order_id: Annotated[UUID, Path(description="Order ID")],
) -> ApiResponse[OrderWithTrades]:
    """Get order details by ID.

    Returns the order with all associated trade executions.
    """
    try:
        order = await service.get_order(order_id)
        return ApiResponse(data=_to_order_with_trades(order))
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        _handle_order_error(e)


@router.post("/{order_id}/cancel", response_model=ApiResponse[OrderDetail])
async def cancel_order(
    service: OrderServiceDep,
    order_id: Annotated[UUID, Path(description="Order ID")],
) -> ApiResponse[OrderDetail]:
    """Cancel an order.

    Cancels the order on the exchange and updates the database record.
    """
    try:
        order = await service.cancel_order(order_id)
        return ApiResponse(data=_to_order_detail(order))
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OrderValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _handle_order_error(e)


@router.post("/{order_id}/sync", response_model=ApiResponse[OrderDetail])
async def sync_order(
    service: OrderServiceDep,
    order_id: Annotated[UUID, Path(description="Order ID")],
) -> ApiResponse[OrderDetail]:
    """Sync order status from exchange.

    Fetches the latest order status from the exchange and updates
    the database record.
    """
    try:
        order = await service.sync_order(order_id)
        return ApiResponse(data=_to_order_detail(order))
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        _handle_order_error(e)


@router.post("/sync", response_model=ApiResponse[SyncOrdersResponse])
async def sync_open_orders(
    service: OrderServiceDep,
    symbol: Annotated[str | None, Query(description="Filter by trading pair")] = None,
) -> ApiResponse[SyncOrdersResponse]:
    """Sync all open orders from exchange.

    Fetches all open orders from the exchange and updates the
    corresponding database records.
    """
    try:
        orders = await service.sync_open_orders(symbol=symbol)
        data = SyncOrdersResponse(
            synced_count=len(orders),
            orders=[_to_order_detail(o) for o in orders],
        )
        return ApiResponse(data=data)
    except Exception as e:
        _handle_order_error(e)
