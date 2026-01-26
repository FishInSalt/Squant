"""Backtest API endpoints."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.engine.backtest.runner import BacktestError
from squant.infra.database import get_session
from squant.schemas.backtest import (
    AvailableSymbolResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestRunResponse,
    CheckDataRequest,
    CreateBacktestRequest,
    DataAvailabilityResponse,
    EquityCurvePoint,
    RunBacktestRequest,
)
from squant.services.backtest import (
    BacktestNotFoundError,
    BacktestService,
    InsufficientDataError,
)
from squant.services.strategy import StrategyNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[BacktestRunResponse])
async def run_backtest(
    request: RunBacktestRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Create and run a backtest synchronously.

    This endpoint creates a backtest run and executes it immediately,
    returning when the backtest completes.

    Args:
        request: Backtest configuration.
        session: Database session.

    Returns:
        Backtest run with results.

    Raises:
        HTTPException: 400 if insufficient data, 404 if strategy not found.
    """
    service = BacktestService(session)

    try:
        run = await service.create_and_run(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            timeframe=request.timeframe,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission_rate=request.commission_rate,
            slippage=request.slippage,
            params=request.params,
        )
        return ApiResponse(data=BacktestRunResponse.model_validate(run))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BacktestError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/async", response_model=ApiResponse[BacktestRunResponse])
async def create_backtest(
    request: CreateBacktestRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Create a backtest run without executing it.

    Use this to create a backtest that can be executed later.
    Call POST /backtest/{run_id}/run to execute.

    Args:
        request: Backtest configuration.
        session: Database session.

    Returns:
        Created backtest run (status: pending).

    Raises:
        HTTPException: 404 if strategy not found.
    """
    service = BacktestService(session)

    try:
        run = await service.create(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            timeframe=request.timeframe,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission_rate=request.commission_rate,
            slippage=request.slippage,
            params=request.params,
        )
        return ApiResponse(data=BacktestRunResponse.model_validate(run))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/run", response_model=ApiResponse[BacktestRunResponse])
async def execute_backtest(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Execute a pending backtest.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Updated backtest run with results.

    Raises:
        HTTPException: 400 if execution fails, 404 if not found.
    """
    service = BacktestService(session)

    try:
        run = await service.run(run_id)
        return ApiResponse(data=BacktestRunResponse.model_validate(run))
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BacktestError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ApiResponse[PaginatedData[BacktestListItem]])
async def list_backtests(
    strategy_id: UUID = Query(..., description="Strategy ID (required)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[BacktestListItem]]:
    """List backtest runs for a strategy with pagination.

    Args:
        strategy_id: Strategy ID to filter by (required).
        page: Page number (1-indexed).
        page_size: Items per page.
        session: Database session.

    Returns:
        Paginated list of backtest runs.
    """
    service = BacktestService(session)

    runs, total = await service.list_by_strategy(
        strategy_id,
        page=page,
        page_size=page_size,
    )

    items = [BacktestListItem.model_validate(r) for r in runs]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{run_id}", response_model=ApiResponse[BacktestRunResponse])
async def get_backtest(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Get a backtest run by ID.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Backtest run details.

    Raises:
        HTTPException: 404 if not found.
    """
    service = BacktestService(session)

    try:
        run = await service.get(run_id)
        return ApiResponse(data=BacktestRunResponse.model_validate(run))
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/detail", response_model=ApiResponse[BacktestDetailResponse])
async def get_backtest_detail(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestDetailResponse]:
    """Get backtest details including equity curve.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Detailed backtest response with equity curve.

    Raises:
        HTTPException: 404 if not found.
    """
    service = BacktestService(session)

    try:
        run = await service.get(run_id)
        equity_curve = await service.get_equity_curve(run_id)

        return ApiResponse(
            data=BacktestDetailResponse(
                run=BacktestRunResponse.model_validate(run),
                equity_curve=[EquityCurvePoint.model_validate(e) for e in equity_curve],
                total_bars=len(equity_curve),
            )
        )
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/equity-curve", response_model=ApiResponse[list[EquityCurvePoint]])
async def get_equity_curve(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[EquityCurvePoint]]:
    """Get equity curve for a backtest.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Equity curve data points.

    Raises:
        HTTPException: 404 if not found.
    """
    service = BacktestService(session)

    try:
        equity_curve = await service.get_equity_curve(run_id)
        return ApiResponse(
            data=[EquityCurvePoint.model_validate(e) for e in equity_curve]
        )
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{run_id}", response_model=ApiResponse[None])
async def delete_backtest(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a backtest run.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Success response.

    Raises:
        HTTPException: 404 if not found.
    """
    service = BacktestService(session)

    try:
        await service.delete(run_id)
        return ApiResponse(data=None, message="Backtest deleted")
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/data/check", response_model=ApiResponse[DataAvailabilityResponse])
async def check_data_availability(
    request: CheckDataRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DataAvailabilityResponse]:
    """Check historical data availability for backtesting.

    Args:
        request: Data availability check request.
        session: Database session.

    Returns:
        Data availability information.
    """
    service = BacktestService(session)

    result = await service.check_data_availability(
        exchange=request.exchange,
        symbol=request.symbol,
        timeframe=request.timeframe,
        start=request.start_date,
        end=request.end_date,
    )

    return ApiResponse(data=DataAvailabilityResponse(**result))


@router.get("/data/symbols", response_model=ApiResponse[list[AvailableSymbolResponse]])
async def list_available_symbols(
    exchange: str | None = Query(None, description="Filter by exchange"),
    timeframe: str | None = Query(None, description="Filter by timeframe"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AvailableSymbolResponse]]:
    """List symbols with available historical data.

    Args:
        exchange: Optional exchange filter.
        timeframe: Optional timeframe filter.
        session: Database session.

    Returns:
        List of available symbols with data info.
    """
    from squant.services.data_loader import DataLoader

    loader = DataLoader(session)
    symbols = await loader.get_available_symbols(exchange=exchange, timeframe=timeframe)

    return ApiResponse(
        data=[AvailableSymbolResponse(**s) for s in symbols]
    )
