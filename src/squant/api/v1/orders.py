"""Order management API endpoints.

This module provides REST API endpoints for managing orders:
- Creating orders (persisted to DB + submitted to exchange)
- Canceling orders
- Querying order history
- Syncing order status from exchange
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from squant.api.deps import DbSession, OKXExchange
from squant.api.utils import ApiResponse, handle_exchange_error, paginate_params
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError as ExchangeOrderNotFound,
)
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


async def _get_or_create_default_account(
    session: DbSession,
    exchange: str = "okx",
) -> ExchangeAccount:
    """Get or create a default exchange account for order tracking.

    This is a simplified implementation that creates a placeholder account
    for tracking orders. In a full implementation, this would use encrypted
    credentials stored in the database.

    Args:
        session: Database session.
        exchange: Exchange name.

    Returns:
        ExchangeAccount record.
    """
    from sqlalchemy import select

    # Check for existing default account
    stmt = select(ExchangeAccount).where(
        ExchangeAccount.exchange == exchange,
        ExchangeAccount.name == "default",
    )
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if account is None:
        # Create placeholder account
        # Note: In production, credentials would be properly encrypted
        account = ExchangeAccount(
            exchange=exchange,
            name="default",
            api_key_enc=b"placeholder",  # Not used - credentials from settings
            api_secret_enc=b"placeholder",
            passphrase_enc=b"placeholder",
            nonce=b"placeholder",
            testnet=True,  # Default to testnet for safety
            is_active=True,
        )
        session.add(account)
        await session.flush()
        await session.refresh(account)

    return account


async def get_order_service(
    session: DbSession,
    exchange: OKXExchange,
) -> OrderService:
    """Get OrderService instance.

    This dependency provides an OrderService configured with:
    - Database session for persistence
    - Exchange adapter for trading operations
    - Default account for order tracking

    Args:
        session: Database session.
        exchange: Exchange adapter.

    Returns:
        Configured OrderService.
    """
    account = await _get_or_create_default_account(session)
    return OrderService(session, exchange, account)


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


def _handle_order_error(e: Exception) -> None:
    """Convert order service exceptions to HTTP exceptions."""
    if isinstance(e, OrderNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, OrderValidationError):
        raise HTTPException(status_code=400, detail=str(e))
    # Delegate to common exchange error handler
    handle_exchange_error(e)


def _to_order_detail(order) -> OrderDetail:
    """Convert Order model to OrderDetail schema."""
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
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _to_order_with_trades(order) -> OrderWithTrades:
    """Convert Order model to OrderWithTrades schema."""
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
        created_at=order.created_at,
        updated_at=order.updated_at,
        trades=[
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
        ],
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
        total = await service.count_orders(status=status)
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
