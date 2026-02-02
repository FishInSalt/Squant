"""Watchlist API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse
from squant.infra.database import get_session
from squant.schemas.watchlist import (
    AddToWatchlistRequest,
    ReorderWatchlistRequest,
    WatchlistCheckResponse,
    WatchlistItemResponse,
)
from squant.services.watchlist import (
    WatchlistItemExistsError,
    WatchlistItemNotFoundError,
    WatchlistService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[WatchlistItemResponse], status_code=201)
async def add_to_watchlist(
    request: AddToWatchlistRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[WatchlistItemResponse]:
    """Add a trading pair to the watchlist.

    Args:
        request: Add to watchlist request with exchange and symbol.
        session: Database session.

    Returns:
        Created watchlist item.

    Raises:
        HTTPException: 409 if item already exists.
    """
    service = WatchlistService(session)

    try:
        item = await service.add(request)
        return ApiResponse(data=WatchlistItemResponse.model_validate(item))
    except WatchlistItemExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=ApiResponse[list[WatchlistItemResponse]])
async def list_watchlist(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[WatchlistItemResponse]]:
    """List all watchlist items ordered by sort_order.

    Args:
        session: Database session.

    Returns:
        List of watchlist items.
    """
    service = WatchlistService(session)
    items = await service.list()
    return ApiResponse(data=[WatchlistItemResponse.model_validate(item) for item in items])


@router.delete("/{item_id}", response_model=ApiResponse[None])
async def remove_from_watchlist(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Remove an item from the watchlist.

    Args:
        item_id: Watchlist item UUID.
        session: Database session.

    Returns:
        Success response.

    Raises:
        HTTPException: 404 if item not found.
    """
    service = WatchlistService(session)

    try:
        await service.remove(item_id)
        return ApiResponse(data=None, message="Item removed from watchlist")
    except WatchlistItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/check", response_model=ApiResponse[WatchlistCheckResponse])
async def check_watchlist(
    exchange: str = Query(..., description="Exchange identifier"),
    symbol: str = Query(..., description="Trading pair symbol"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[WatchlistCheckResponse]:
    """Check if a trading pair is in the watchlist.

    Args:
        exchange: Exchange identifier (e.g., 'okx').
        symbol: Trading pair symbol (e.g., 'BTC/USDT').
        session: Database session.

    Returns:
        Check response with in_watchlist status and item_id if exists.
    """
    service = WatchlistService(session)
    in_watchlist, item_id = await service.check(exchange, symbol)
    return ApiResponse(
        data=WatchlistCheckResponse(in_watchlist=in_watchlist, item_id=item_id)
    )


@router.put("/reorder", response_model=ApiResponse[list[WatchlistItemResponse]])
async def reorder_watchlist(
    request: ReorderWatchlistRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[WatchlistItemResponse]]:
    """Reorder watchlist items.

    Args:
        request: Reorder request with items and their new sort_order values.
        session: Database session.

    Returns:
        Updated list of watchlist items.
    """
    service = WatchlistService(session)
    items = await service.reorder(request.items)
    return ApiResponse(data=[WatchlistItemResponse.model_validate(item) for item in items])
