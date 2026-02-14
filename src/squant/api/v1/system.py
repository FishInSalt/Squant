"""System management API endpoints.

Provides data download management and historical data listing.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.deps import get_session, get_session_readonly
from squant.api.utils import ApiResponse
from squant.infra.exchange.ccxt.types import SUPPORTED_EXCHANGES
from squant.models.market import Kline
from squant.schemas.system import (
    DownloadDataRequest,
    DownloadTaskResponse,
    HistoricalDataItem,
)
from squant.services.data_download import get_download_service
from squant.services.data_loader import DataLoader

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Data Download Endpoints ====================


@router.post(
    "/data/download",
    response_model=ApiResponse[DownloadTaskResponse],
    status_code=201,
)
async def start_download(
    request: DownloadDataRequest,
) -> ApiResponse[DownloadTaskResponse]:
    """Start a historical data download task."""
    if request.exchange.lower() not in SUPPORTED_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {request.exchange}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXCHANGES))}",
        )

    service = get_download_service()

    try:
        task_info = service.start_download(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApiResponse(data=DownloadTaskResponse(**task_info.to_dict()))


@router.get(
    "/data/download/tasks",
    response_model=ApiResponse[list[DownloadTaskResponse]],
)
async def list_download_tasks() -> ApiResponse[list[DownloadTaskResponse]]:
    """List all download tasks (most recent first)."""
    service = get_download_service()
    tasks = service.list_tasks()
    return ApiResponse(data=[DownloadTaskResponse(**t.to_dict()) for t in tasks])


@router.get(
    "/data/download/{task_id}",
    response_model=ApiResponse[DownloadTaskResponse],
)
async def get_download_task(task_id: str) -> ApiResponse[DownloadTaskResponse]:
    """Get download task status by ID."""
    service = get_download_service()
    task_info = service.get_task(task_id)
    if task_info is None:
        raise HTTPException(status_code=404, detail=f"Download task not found: {task_id}")
    return ApiResponse(data=DownloadTaskResponse(**task_info.to_dict()))


@router.post(
    "/data/download/{task_id}/cancel",
    response_model=ApiResponse[DownloadTaskResponse],
)
async def cancel_download_task(task_id: str) -> ApiResponse[DownloadTaskResponse]:
    """Cancel a running download task."""
    service = get_download_service()
    task_info = service.cancel_task(task_id)
    if task_info is None:
        raise HTTPException(status_code=404, detail=f"Download task not found: {task_id}")
    return ApiResponse(data=DownloadTaskResponse(**task_info.to_dict()))


@router.delete(
    "/data/download/{task_id}",
    response_model=ApiResponse[None],
)
async def remove_download_task(task_id: str) -> ApiResponse[None]:
    """Remove a completed or failed download task from the list."""
    service = get_download_service()
    task_info = service.remove_task(task_id)
    if task_info is None:
        raise HTTPException(status_code=404, detail=f"Task not found or still active: {task_id}")
    return ApiResponse(data=None)  # type: ignore[arg-type]


# ==================== Historical Data Management Endpoints ====================


@router.get(
    "/data/list",
    response_model=ApiResponse[list[HistoricalDataItem]],
)
async def list_historical_data(
    exchange: str | None = Query(None, description="Filter by exchange"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    timeframe: str | None = Query(None, description="Filter by timeframe"),
    session: AsyncSession = Depends(get_session_readonly),
) -> ApiResponse[list[HistoricalDataItem]]:
    """List available historical data in the database."""
    loader = DataLoader(session)
    symbols = await loader.get_available_symbols(
        exchange=exchange,
        timeframe=timeframe,
    )

    # Apply symbol filter (DataLoader doesn't support it natively)
    if symbol:
        symbols = [s for s in symbols if s["symbol"] == symbol]

    items = [
        HistoricalDataItem(
            id=f"{s['exchange']}:{s['symbol']}:{s['timeframe']}",
            exchange=s["exchange"],
            symbol=s["symbol"],
            timeframe=s["timeframe"],
            start_date=s["first_bar"],
            end_date=s["last_bar"],
            candle_count=s["bar_count"],
        )
        for s in symbols
    ]

    return ApiResponse(data=items)


@router.delete(
    "/data/{data_id:path}",
    response_model=ApiResponse[None],
)
async def delete_historical_data(
    data_id: str,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete historical data for a specific exchange/symbol/timeframe.

    The data_id format is "exchange:symbol:timeframe" (e.g., "okx:BTC/USDT:1h").
    """
    # Parse composite ID: first colon = exchange, last colon = timeframe, middle = symbol
    first_colon = data_id.find(":")
    last_colon = data_id.rfind(":")
    if first_colon == -1 or last_colon == -1 or first_colon == last_colon:
        raise HTTPException(
            status_code=400,
            detail="Invalid data ID format. Expected 'exchange:symbol:timeframe'",
        )

    exchange = data_id[:first_colon]
    symbol = data_id[first_colon + 1 : last_colon]
    timeframe = data_id[last_colon + 1 :]

    result = await session.execute(
        delete(Kline).where(
            and_(
                Kline.exchange == exchange,
                Kline.symbol == symbol,
                Kline.timeframe == timeframe,
            )
        )
    )
    await session.commit()

    if result.rowcount == 0:  # type: ignore[union-attr]
        raise HTTPException(status_code=404, detail="No data found for the specified parameters")

    logger.info("Deleted %d klines for %s:%s:%s", result.rowcount, exchange, symbol, timeframe)

    return ApiResponse(data=None, message=f"Deleted {result.rowcount} candles")  # type: ignore[arg-type]


# ==================== Symbol Listing Endpoint ====================


@router.get(
    "/symbols/{exchange_id}",
    response_model=ApiResponse[list[str]],
)
async def list_exchange_symbols(exchange_id: str) -> ApiResponse[list[str]]:
    """List available trading symbols for an exchange via CCXT."""
    from squant.api.deps import _get_or_create_exchange_adapter

    if exchange_id.lower() not in SUPPORTED_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange_id}",
        )

    try:
        adapter = await _get_or_create_exchange_adapter(exchange_id.lower())
        symbols = adapter.get_symbols()
        return ApiResponse(data=symbols)
    except Exception as e:
        logger.warning("Failed to load symbols for %s: %s", exchange_id, e)
        raise HTTPException(status_code=502, detail=f"Failed to load symbols: {e}")
