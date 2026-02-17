"""Backtest API endpoints."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.engine.backtest.runner import BacktestError
from squant.infra.database import get_session
from squant.models.enums import RunStatus
from squant.models.market import Kline
from squant.schemas.backtest import (
    AvailableSymbolResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestMetrics,
    BacktestRunResponse,
    CandlesPageResponse,
    CandlestickPoint,
    CheckDataRequest,
    CreateBacktestRequest,
    DataAvailabilityResponse,
    EquityCurvePoint,
    ExportFormat,
    RunBacktestRequest,
    TradeRecordResponse,
)
from squant.services.backtest import (
    BacktestNotFoundError,
    BacktestService,
    InvalidInitialCapitalError,
)
from squant.services.data_loader import DataLoader
from squant.services.strategy import StrategyNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[BacktestRunResponse], status_code=201)
async def run_backtest(
    request: RunBacktestRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Create a backtest and start execution in background.

    Returns immediately with a PENDING run record. The backtest executes
    asynchronously — poll GET /backtest/{run_id} for status updates.

    Args:
        request: Backtest configuration.
        session: Database session.

    Returns:
        Created backtest run (status: pending).

    Raises:
        HTTPException: 400 if invalid config, 404 if strategy not found.
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
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidInitialCapitalError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fire-and-forget: execution happens in background with independent DB session
    BacktestService.run_in_background(str(run.id))

    return ApiResponse(data=BacktestRunResponse.model_validate(run))


@router.post("/async", response_model=ApiResponse[BacktestRunResponse], status_code=201)
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
    except InvalidInitialCapitalError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/run", response_model=ApiResponse[BacktestRunResponse])
async def execute_backtest(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Start execution of a pending backtest in background.

    Returns immediately. Poll GET /backtest/{run_id} for status updates.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Current backtest run record.

    Raises:
        HTTPException: 404 if not found, 400 if not in pending state.
    """
    service = BacktestService(session)

    run = await service.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")
    if run.status != RunStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Backtest is not pending (status: {run.status.value})",
        )

    BacktestService.run_in_background(str(run_id))

    return ApiResponse(data=BacktestRunResponse.model_validate(run))


@router.post("/{run_id}/cancel", response_model=ApiResponse[BacktestRunResponse])
async def cancel_backtest(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BacktestRunResponse]:
    """Cancel a running backtest (TRD-008#3).

    This endpoint requests cancellation of a running backtest.
    The backtest will stop at the next bar iteration.

    Args:
        run_id: Backtest run ID.
        session: Database session.

    Returns:
        Current backtest run state.

    Raises:
        HTTPException: 400 if not cancellable, 404 if not found.
    """
    service = BacktestService(session)

    try:
        run = await service.cancel(run_id)
        return ApiResponse(
            data=BacktestRunResponse.model_validate(run),
            message="Backtest cancellation requested",
        )
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BacktestError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ApiResponse[PaginatedData[BacktestListItem]])
async def list_backtests(
    strategy_id: UUID | None = Query(None, description="Strategy ID (optional)"),
    status: str | None = Query(
        None, description="Status filter: pending, running, completed, error"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[BacktestListItem]]:
    """List backtest runs with optional filters and pagination.

    Args:
        strategy_id: Optional strategy ID to filter by.
        status: Optional status filter (pending, running, completed, error).
        page: Page number (1-indexed).
        page_size: Items per page.
        session: Database session.

    Returns:
        Paginated list of backtest runs.
    """
    # Parse status if provided
    run_status = None
    if status:
        try:
            run_status = RunStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: pending, running, completed, error",
            )

    service = BacktestService(session)

    runs, total = await service.list_runs(
        strategy_id=strategy_id,
        status=run_status,
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
    loader = DataLoader(session)
    symbols = await loader.get_available_symbols(exchange=exchange, timeframe=timeframe)

    return ApiResponse(data=[AvailableSymbolResponse(**s) for s in symbols])


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
        response = BacktestRunResponse.model_validate(run)
        # Inject real-time progress for running backtests
        if run.status == RunStatus.RUNNING:
            response.progress = BacktestService.get_progress(str(run_id))
        return ApiResponse(data=response)
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

        # Extract strongly-typed metrics from run.result dict (BT-004)
        metrics = None
        trades: list[TradeRecordResponse] = []
        if run.result:
            metrics = BacktestMetrics(
                **{k: v for k, v in run.result.items() if k in BacktestMetrics.model_fields}
            )
            # Extract trades if stored in result
            raw_trades = run.result.get("trades", [])
            if raw_trades and isinstance(raw_trades, list):
                for t in raw_trades:
                    if isinstance(t, dict):
                        trades.append(TradeRecordResponse(**t))

        return ApiResponse(
            data=BacktestDetailResponse(
                run=BacktestRunResponse.model_validate(run),
                metrics=metrics,
                equity_curve=[EquityCurvePoint.model_validate(e) for e in equity_curve],
                trades=trades,
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
        return ApiResponse(data=[EquityCurvePoint.model_validate(e) for e in equity_curve])
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


@router.get("/{run_id}/candles", response_model=ApiResponse[CandlesPageResponse])
async def get_backtest_candles(
    run_id: UUID,
    before: datetime | None = Query(None, description="Fetch candles before this time"),
    after: datetime | None = Query(None, description="Fetch candles after this time"),
    limit: int = Query(1000, ge=1, le=2000, description="Max candles to return"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[CandlesPageResponse]:
    """Get paginated candlestick data for a backtest run's period.

    Supports cursor-based pagination via `before` / `after` timestamps.
    Default (no cursor): returns the last `limit` candles of the backtest period.

    Args:
        run_id: Backtest run ID.
        before: Return candles with time < before (scroll left / older data).
        after: Return candles with time > after (scroll right / newer data).
        limit: Max number of candles to return (1-2000, default 1000).
        session: Database session.

    Returns:
        Paginated candles with total_count metadata.

    Raises:
        HTTPException: 404 if backtest not found, 400 if no data available.
    """
    service = BacktestService(session)

    try:
        run = await service.get(run_id)
    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not run.backtest_start or not run.backtest_end:
        raise HTTPException(status_code=400, detail="Backtest date range not set")

    # Base filter: always within backtest date range
    base_filters = [
        Kline.exchange == run.exchange,
        Kline.symbol == run.symbol,
        Kline.timeframe == run.timeframe,
        Kline.time >= run.backtest_start,
        Kline.time <= run.backtest_end,
    ]

    # Total count (full backtest range, no cursor filter)
    count_result = await session.execute(
        select(func.count()).select_from(Kline).where(and_(*base_filters))
    )
    total_count = count_result.scalar() or 0

    # Build paginated query with cursor
    filters = list(base_filters)
    if before:
        filters.append(Kline.time < before)
    if after:
        filters.append(Kline.time > after)

    if before:
        # Fetch N newest candles before cursor → reverse to chronological order
        stmt = (
            select(Kline.time, Kline.open, Kline.high, Kline.low, Kline.close, Kline.volume)
            .where(and_(*filters))
            .order_by(Kline.time.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(reversed(result.all()))
    else:
        if after:
            # Fetch N oldest candles after cursor
            stmt = (
                select(
                    Kline.time, Kline.open, Kline.high, Kline.low, Kline.close, Kline.volume,
                )
                .where(and_(*filters))
                .order_by(Kline.time.asc())
                .limit(limit)
            )
        else:
            # Default: last N candles of the backtest period
            stmt = (
                select(
                    Kline.time, Kline.open, Kline.high, Kline.low, Kline.close, Kline.volume,
                )
                .where(and_(*filters))
                .order_by(Kline.time.desc())
                .limit(limit)
            )
        result = await session.execute(stmt)
        rows = result.all()
        if not after:
            rows = list(reversed(rows))

    candles = [
        CandlestickPoint(
            timestamp=row[0], open=row[1], high=row[2],
            low=row[3], close=row[4], volume=row[5],
        )
        for row in rows
    ]

    return ApiResponse(data=CandlesPageResponse(candles=candles, total_count=total_count))


@router.get("/{run_id}/export", response_model=ApiResponse[dict])
async def export_backtest_report(
    run_id: UUID,
    format: ExportFormat = Query(ExportFormat.JSON, description="Export format: json or csv"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """Export backtest report (TRD-009#4).

    Exports a completed backtest as JSON or CSV format.

    Args:
        run_id: Backtest run ID.
        format: Export format ('json' or 'csv').
        session: Database session.

    Returns:
        Report data. For CSV format, returns {content: "...", filename: "..."}

    Raises:
        HTTPException: 400 if invalid format or not completed, 404 if not found.
    """
    service = BacktestService(session)

    try:
        report = await service.export_report(run_id, format=format)

        if format == ExportFormat.CSV:
            csv_content = service.generate_csv_report(report)
            return ApiResponse(
                data={
                    "content": csv_content,
                    "filename": f"backtest_{run_id}_{report['exported_at'][:10]}.csv",
                    "content_type": "text/csv",
                },
                message="Report exported as CSV",
            )

        return ApiResponse(data=report, message="Report exported as JSON")

    except BacktestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
