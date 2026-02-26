"""Paper trading API endpoints."""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.deps import RedisClient
from squant.api.utils import ApiResponse, PaginatedData
from squant.infra.database import get_session
from squant.models.enums import RunStatus
from squant.schemas.backtest import EquityCurvePoint, TradeRecordResponse
from squant.schemas.paper_trading import (
    OpenTradeInfo,
    PaperTradingListItem,
    PaperTradingRunResponse,
    PaperTradingStatusResponse,
    PendingOrderInfo,
    PositionInfo,
    ResumePaperTradingRequest,
    StartPaperTradingRequest,
)
from squant.services.paper_trading import (
    PaperTradingError,
    PaperTradingService,
    SessionNotFoundError,
    SessionNotResumableError,
    StrategyInstantiationError,
)
from squant.services.strategy import StrategyNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[PaperTradingRunResponse], status_code=201)
async def start_paper_trading(
    request: StartPaperTradingRequest,
    redis: RedisClient,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaperTradingRunResponse]:
    """Start a paper trading session.

    Creates a new paper trading run and starts the real-time simulation
    using WebSocket market data.

    Args:
        request: Paper trading configuration.
        session: Database session.
        redis: Redis client for circuit breaker check.

    Returns:
        Paper trading run record.

    Raises:
        HTTPException: 400 if strategy instantiation fails, 404 if strategy not found.
    """
    service = PaperTradingService(session)

    try:
        run = await service.start(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange=request.exchange,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            commission_rate=request.commission_rate,
            slippage=request.slippage,
            params=request.params,
            redis=redis,
        )
        return ApiResponse(data=PaperTradingRunResponse.model_validate(run))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StrategyInstantiationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PaperTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/stop", response_model=ApiResponse[PaperTradingRunResponse])
async def stop_paper_trading(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaperTradingRunResponse]:
    """Stop a paper trading session.

    Stops the real-time simulation and persists final state.

    Args:
        run_id: Paper trading run ID.
        session: Database session.

    Returns:
        Updated paper trading run record.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = PaperTradingService(session)

    try:
        run = await service.stop(run_id)
        return ApiResponse(data=PaperTradingRunResponse.model_validate(run))
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/resume", response_model=ApiResponse[PaperTradingRunResponse])
async def resume_paper_trading(
    run_id: UUID,
    redis: RedisClient,
    request: ResumePaperTradingRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaperTradingRunResponse]:
    """Resume a stopped or errored paper trading session.

    Restores trading state from the saved result snapshot and replays
    historical bars to rebuild strategy internal state.

    Args:
        run_id: Paper trading run ID.
        request: Optional resume configuration.
        redis: Redis client for circuit breaker check.
        session: Database session.

    Returns:
        Updated paper trading run record.
    """
    service = PaperTradingService(session)
    warmup_bars = request.warmup_bars if request else 200

    try:
        run = await service.resume(run_id, warmup_bars=warmup_bars, redis=redis)
        return ApiResponse(data=PaperTradingRunResponse.model_validate(run))
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionNotResumableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PaperTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{run_id}/status", response_model=ApiResponse[PaperTradingStatusResponse])
async def get_paper_trading_status(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaperTradingStatusResponse]:
    """Get real-time status of a paper trading session.

    Returns current positions, orders, equity, and other live metrics.

    Args:
        run_id: Paper trading run ID.
        session: Database session.

    Returns:
        Real-time status information.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = PaperTradingService(session)

    try:
        status = await service.get_status(run_id)

        # Convert to response model
        positions = {
            symbol: PositionInfo(
                amount=Decimal(pos["amount"]),
                avg_entry_price=Decimal(pos["avg_entry_price"]),
                current_price=Decimal(pos["current_price"]) if pos.get("current_price") else None,
                unrealized_pnl=(
                    Decimal(pos["unrealized_pnl"]) if pos.get("unrealized_pnl") else None
                ),
            )
            for symbol, pos in status.get("positions", {}).items()
        }

        pending_orders = [
            PendingOrderInfo(
                id=order["id"],
                symbol=order["symbol"],
                side=order["side"],
                type=order["type"],
                amount=Decimal(order["amount"]),
                price=Decimal(order["price"]) if order.get("price") else None,
                status=order["status"],
                created_at=order.get("created_at"),
            )
            for order in status.get("pending_orders", [])
        ]

        trades = [
            TradeRecordResponse(
                symbol=t["symbol"],
                side=t["side"],
                entry_time=t["entry_time"],
                entry_price=Decimal(t["entry_price"]),
                exit_time=t.get("exit_time"),
                exit_price=Decimal(t["exit_price"]) if t.get("exit_price") else None,
                amount=Decimal(t["amount"]),
                pnl=Decimal(t["pnl"]),
                pnl_pct=Decimal(t["pnl_pct"]),
                fees=Decimal(t["fees"]),
            )
            for t in status.get("trades", [])
        ]

        open_trade_data = status.get("open_trade")
        open_trade = (
            OpenTradeInfo(
                symbol=open_trade_data["symbol"],
                side=open_trade_data["side"],
                entry_time=open_trade_data["entry_time"],
                entry_price=Decimal(open_trade_data["entry_price"]),
                amount=Decimal(open_trade_data["amount"]),
                fees=Decimal(open_trade_data["fees"]),
            )
            if open_trade_data
            else None
        )

        response = PaperTradingStatusResponse(
            run_id=UUID(status["run_id"]),
            symbol=status["symbol"],
            timeframe=status["timeframe"],
            is_running=status["is_running"],
            started_at=status.get("started_at"),
            stopped_at=status.get("stopped_at"),
            error_message=status.get("error_message"),
            bar_count=status["bar_count"],
            cash=Decimal(status["cash"]),
            equity=Decimal(status["equity"]),
            initial_capital=Decimal(status["initial_capital"]),
            total_fees=Decimal(status["total_fees"]),
            unrealized_pnl=Decimal(status["unrealized_pnl"]),
            realized_pnl=Decimal(status["realized_pnl"]),
            positions=positions,
            pending_orders=pending_orders,
            completed_orders_count=status["completed_orders_count"],
            trades_count=status["trades_count"],
            trades=trades,
            open_trade=open_trade,
            logs=status.get("logs", []),
        )

        return ApiResponse(data=response)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=ApiResponse[list[PaperTradingListItem]])
async def list_active_sessions(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[PaperTradingListItem]]:
    """List all active paper trading sessions.

    Returns currently running paper trading sessions with their live status.

    Args:
        session: Database session.

    Returns:
        List of active paper trading sessions.
    """
    service = PaperTradingService(session)

    sessions = service.list_active()

    items = []
    for sess in sessions:
        # Get strategy_id from database
        try:
            run = await service.get_run(UUID(sess["run_id"]))
            strategy_id = UUID(run.strategy_id)
        except SessionNotFoundError:
            continue

        items.append(
            PaperTradingListItem(
                id=UUID(sess["run_id"]),
                strategy_id=strategy_id,
                strategy_name=run.strategy_name,
                symbol=sess["symbol"],
                exchange=run.exchange,
                timeframe=sess["timeframe"],
                status=run.status.value if hasattr(run.status, "value") else run.status,
                is_running=sess["is_running"],
                initial_capital=run.initial_capital,
                started_at=sess.get("started_at"),
                created_at=run.created_at,
                bar_count=sess["bar_count"],
                equity=Decimal(sess["equity"]),
                cash=Decimal(sess["cash"]),
            )
        )

    return ApiResponse(data=items)


@router.post("/stop-all", response_model=ApiResponse[dict])
async def stop_all_paper_trading(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """Stop all active paper trading sessions.

    Returns:
        Number of sessions stopped.
    """
    service = PaperTradingService(session)
    stopped = await service.stop_all()
    return ApiResponse(data={"stopped_count": stopped})


@router.get("/runs", response_model=ApiResponse[PaginatedData[PaperTradingRunResponse]])
async def list_paper_trading_runs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    status: str | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[PaperTradingRunResponse]]:
    """List paper trading runs with pagination.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.
        status: Optional status filter (pending, running, stopped, error, interrupted).
        session: Database session.

    Returns:
        Paginated list of paper trading runs.
    """
    service = PaperTradingService(session)

    # Parse status filter
    run_status = None
    if status:
        try:
            run_status = RunStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in RunStatus]}",
            )

    runs, total = await service.list_runs(
        page=page,
        page_size=page_size,
        status=run_status,
    )

    items = [PaperTradingRunResponse.model_validate(r) for r in runs]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{run_id}", response_model=ApiResponse[PaperTradingRunResponse])
async def get_paper_trading_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaperTradingRunResponse]:
    """Get a paper trading run by ID.

    Args:
        run_id: Paper trading run ID.
        session: Database session.

    Returns:
        Paper trading run details.

    Raises:
        HTTPException: 404 if not found.
    """
    service = PaperTradingService(session)

    try:
        run = await service.get_run(run_id)
        return ApiResponse(data=PaperTradingRunResponse.model_validate(run))
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/equity-curve", response_model=ApiResponse[list[EquityCurvePoint]])
async def get_equity_curve(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[EquityCurvePoint]]:
    """Get equity curve for a paper trading run.

    Args:
        run_id: Paper trading run ID.
        session: Database session.

    Returns:
        Equity curve data points.

    Raises:
        HTTPException: 404 if not found.
    """
    service = PaperTradingService(session)

    try:
        equity_curve = await service.get_equity_curve(run_id)
        return ApiResponse(data=[EquityCurvePoint.model_validate(e) for e in equity_curve])
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/persist", response_model=ApiResponse[dict])
async def persist_equity_snapshots(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """Manually persist pending equity snapshots.

    This endpoint is useful for forcing persistence of equity curve data
    without waiting for the automatic batch persistence.

    Args:
        run_id: Paper trading run ID.
        session: Database session.

    Returns:
        Number of snapshots persisted.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = PaperTradingService(session)

    try:
        count = await service.persist_snapshots(run_id)
        return ApiResponse(data={"persisted_count": count})
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
