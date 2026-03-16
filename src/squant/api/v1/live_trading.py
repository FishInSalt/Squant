"""Live trading API endpoints."""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData
from squant.engine.risk import RiskConfig
from squant.infra.database import get_session
from squant.models.enums import RunStatus
from squant.schemas.backtest import EquityCurvePoint
from squant.schemas.live_trading import (
    EmergencyCloseResponse,
    LiveOrderInfo,
    LivePositionInfo,
    LiveSessionOrderResponse,
    LiveTradingListItem,
    LiveTradingRunResponse,
    LiveTradingStatusResponse,
    RemainingPosition,
    ResumeLiveTradingRequest,
    RiskStateResponse,
    StartLiveTradingRequest,
    StopLiveTradingRequest,
)
from squant.services.live_trading import (
    ExchangeAccountNotFoundError,
    LiveExchangeConnectionError,
    LiveTradingError,
    LiveTradingService,
    RiskConfigurationError,
    SessionNotFoundError,
    SessionNotResumableError,
    StrategyInstantiationError,
)
from squant.services.strategy import StrategyNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=ApiResponse[LiveTradingRunResponse], status_code=201)
async def start_live_trading(
    request: StartLiveTradingRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[LiveTradingRunResponse]:
    """Start a live trading session.

    Creates a new live trading run and starts real-time trading
    with actual exchange execution.

    **Risk Configuration Required**: Live trading requires explicit risk
    management configuration to protect against excessive losses.

    Args:
        request: Live trading configuration including risk settings.
        session: Database session.

    Returns:
        Live trading run record.

    Raises:
        HTTPException:
            - 400 if strategy instantiation fails or risk config invalid
            - 404 if strategy not found
            - 503 if exchange connection fails
    """
    service = LiveTradingService(session)

    # Convert request risk config to engine RiskConfig
    risk_config = RiskConfig(
        max_position_size=request.risk_config.max_position_size,
        max_order_size=request.risk_config.max_order_size,
        daily_trade_limit=request.risk_config.daily_trade_limit,
        daily_loss_limit=request.risk_config.daily_loss_limit,
        max_price_deviation=request.risk_config.price_deviation_limit,
        circuit_breaker_loss_count=request.risk_config.circuit_breaker_threshold,
        min_order_value=request.risk_config.min_order_value,
        order_poll_interval=request.risk_config.order_poll_interval,
        balance_check_interval=request.risk_config.balance_check_interval,
    )

    try:
        run = await service.start(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            exchange_account_id=request.exchange_account_id,
            timeframe=request.timeframe,
            risk_config=risk_config,
            initial_equity=request.initial_equity,
            params=request.params,
        )
        return ApiResponse(data=LiveTradingRunResponse.model_validate(run))
    except StrategyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExchangeAccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RiskConfigurationError as e:
        raise HTTPException(status_code=400, detail=f"Risk configuration error: {e}")
    except StrategyInstantiationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LiveExchangeConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/stop", response_model=ApiResponse[LiveTradingRunResponse])
async def stop_live_trading(
    run_id: UUID,
    request: StopLiveTradingRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[LiveTradingRunResponse]:
    """Stop a live trading session.

    Stops the real-time trading and optionally cancels all open orders.

    Args:
        run_id: Live trading run ID.
        request: Stop configuration (optional).
        session: Database session.

    Returns:
        Updated live trading run record.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = LiveTradingService(session)
    cancel_orders = request.cancel_orders if request else True

    try:
        run = await service.stop(run_id, cancel_orders=cancel_orders)
        return ApiResponse(data=LiveTradingRunResponse.model_validate(run))
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/resume", response_model=ApiResponse[LiveTradingRunResponse])
async def resume_live_trading(
    run_id: UUID,
    request: ResumeLiveTradingRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[LiveTradingRunResponse]:
    """Resume a stopped/errored/interrupted live trading session.

    Reconnects to the exchange, reconciles orders and positions,
    restores trading state, and resumes.

    Args:
        run_id: Live trading run ID.
        request: Resume configuration (optional).
        session: Database session.

    Returns:
        Updated live trading run record.
    """
    service = LiveTradingService(session)
    warmup_bars = request.warmup_bars if request else 200

    try:
        run, reconciliation = await service.resume(run_id, warmup_bars=warmup_bars)
        return ApiResponse(
            data=LiveTradingRunResponse.model_validate(run),
            message=(
                f"Session resumed. Orders reconciled: "
                f"{reconciliation.get('orders_reconciled', 0)}, "
                f"fills processed: {reconciliation.get('fills_processed', 0)}"
            ),
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionNotResumableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ExchangeAccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LiveExchangeConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{run_id}/emergency-close", response_model=ApiResponse[EmergencyCloseResponse])
async def emergency_close(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[EmergencyCloseResponse]:
    """Emergency close all positions and stop the session.

    This endpoint immediately:
    1. Cancels all open orders
    2. Closes all positions at market price
    3. Stops the trading session

    Use this in case of emergency situations or when you need to
    immediately exit all positions.

    Args:
        run_id: Live trading run ID.
        session: Database session.

    Returns:
        Emergency close operation results.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = LiveTradingService(session)

    try:
        result = await service.emergency_close(run_id)
        return ApiResponse(
            data=EmergencyCloseResponse(
                run_id=run_id,
                status=result["status"],
                message=result.get("message"),
                orders_cancelled=result.get("orders_cancelled"),
                positions_closed=result.get("positions_closed"),
                remaining_positions=[
                    RemainingPosition(**rp) for rp in (result.get("remaining_positions") or [])
                ]
                or None,
                errors=result.get("errors") or None,
            )
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Emergency close failed for {run_id}")
        raise HTTPException(status_code=500, detail=f"Emergency close failed: {e}")


@router.get("/{run_id}/status", response_model=ApiResponse[LiveTradingStatusResponse])
async def get_live_trading_status(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[LiveTradingStatusResponse]:
    """Get real-time status of a live trading session.

    Returns current positions, orders, equity, risk state, and other live metrics.

    Args:
        run_id: Live trading run ID.
        session: Database session.

    Returns:
        Real-time status information including risk management state.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = LiveTradingService(session)

    try:
        status = await service.get_status(run_id)

        # Convert positions to response model
        positions = {
            symbol: LivePositionInfo(
                amount=Decimal(str(pos.get("amount", 0))),
                avg_entry_price=Decimal(str(pos.get("avg_entry_price", 0))),
                current_price=(
                    Decimal(str(pos["current_price"])) if pos.get("current_price") else None
                ),
                unrealized_pnl=(
                    Decimal(str(pos["unrealized_pnl"])) if pos.get("unrealized_pnl") else None
                ),
            )
            for symbol, pos in status.get("positions", {}).items()
        }

        # Convert live orders to response model
        live_orders = []
        for order in status.get("live_orders", []):
            live_orders.append(
                LiveOrderInfo(
                    internal_id=order.get("internal_id", ""),
                    exchange_order_id=order.get("exchange_order_id"),
                    symbol=order.get("symbol", ""),
                    side=order.get("side", ""),
                    type=order.get("order_type", order.get("type", "")),
                    amount=Decimal(str(order.get("amount", 0))),
                    filled_amount=Decimal(str(order.get("filled_amount", 0))),
                    price=Decimal(str(order["price"])) if order.get("price") else None,
                    avg_fill_price=(
                        Decimal(str(order["avg_fill_price"]))
                        if order.get("avg_fill_price")
                        else None
                    ),
                    status=order.get("status", ""),
                    created_at=order.get("created_at"),
                    updated_at=order.get("updated_at"),
                )
            )

        # Convert risk state to response model
        risk_state = None
        if status.get("risk_state"):
            rs = status["risk_state"]
            risk_state = RiskStateResponse(
                daily_pnl=Decimal(str(rs.get("daily_pnl", 0))),
                daily_trade_count=rs.get("daily_trade_count", 0),
                consecutive_losses=rs.get("consecutive_losses", 0),
                circuit_breaker_active=rs.get("circuit_breaker_active", False),
                max_position_size=Decimal(str(rs.get("max_position_size", 0))),
                max_order_size=Decimal(str(rs.get("max_order_size", 0))),
                daily_trade_limit=rs.get("daily_trade_limit", 0),
                daily_loss_limit=Decimal(str(rs.get("daily_loss_limit", 0))),
            )

        response = LiveTradingStatusResponse(
            run_id=UUID(status["run_id"]),
            symbol=status["symbol"],
            timeframe=status["timeframe"],
            is_running=status["is_running"],
            started_at=status.get("started_at"),
            stopped_at=status.get("stopped_at"),
            error_message=status.get("error_message"),
            bar_count=status.get("bar_count", 0),
            cash=Decimal(str(status.get("cash", 0))),
            equity=Decimal(str(status.get("equity", 0))),
            initial_capital=Decimal(str(status.get("initial_capital", 0))),
            total_fees=Decimal(str(status.get("total_fees", 0))),
            unrealized_pnl=Decimal(str(status.get("unrealized_pnl", 0))),
            realized_pnl=Decimal(str(status.get("realized_pnl", 0))),
            positions=positions,
            pending_orders=status.get("pending_orders", []),
            live_orders=live_orders,
            completed_orders_count=status.get("completed_orders_count", 0),
            trades_count=status.get("trades_count", 0),
            risk_state=risk_state,
        )

        return ApiResponse(data=response)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=ApiResponse[list[LiveTradingListItem]])
async def list_active_sessions(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[LiveTradingListItem]]:
    """List all active live trading sessions.

    Returns currently running live trading sessions with their live status.

    Args:
        session: Database session.

    Returns:
        List of active live trading sessions.
    """
    service = LiveTradingService(session)

    sessions = service.list_active()

    # Batch-fetch all run records in one query (fix: N+1 query)
    run_ids = [UUID(sess["run_id"]) for sess in sessions]
    runs_by_id = await service.get_runs_by_ids(run_ids) if run_ids else {}

    items = []
    for sess in sessions:
        run_id_str = sess["run_id"]
        run = runs_by_id.get(run_id_str)
        if not run:
            continue

        items.append(
            LiveTradingListItem(
                id=UUID(run_id_str),
                strategy_id=UUID(run.strategy_id),
                strategy_name=run.strategy_name,
                account_id=run.account_id,
                symbol=sess["symbol"],
                exchange=run.exchange,
                timeframe=sess["timeframe"],
                status=run.status.value if hasattr(run.status, "value") else run.status,
                is_running=sess["is_running"],
                initial_capital=run.initial_capital,
                started_at=sess.get("started_at"),
                created_at=run.created_at,
                bar_count=sess.get("bar_count", 0),
                equity=Decimal(str(sess.get("equity", 0))),
                cash=Decimal(str(sess.get("cash", 0))),
            )
        )

    return ApiResponse(data=items)


@router.get("/runs", response_model=ApiResponse[PaginatedData[LiveTradingRunResponse]])
async def list_live_trading_runs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    status: str | None = Query(None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[LiveTradingRunResponse]]:
    """List live trading runs with pagination.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.
        status: Optional status filter (pending, running, stopped, error, interrupted).
        session: Database session.

    Returns:
        Paginated list of live trading runs.
    """
    service = LiveTradingService(session)

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

    items = [LiveTradingRunResponse.model_validate(r) for r in runs]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/{run_id}/orders",
    response_model=ApiResponse[PaginatedData[LiveSessionOrderResponse]],
)
async def get_session_orders(
    run_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[LiveSessionOrderResponse]]:
    """Get orders from the audit table for a live trading session.

    Returns orders placed by the strategy engine, with their trade fills.

    Args:
        run_id: Live trading run ID.
        page: Page number (1-indexed).
        page_size: Items per page.
        session: Database session.

    Returns:
        Paginated list of order records with trades.
    """
    from squant.services.order import OrderRepository

    order_repo = OrderRepository(session)
    offset = (page - 1) * page_size

    orders = await order_repo.list_by_run(run_id, offset=offset, limit=page_size)
    total = await order_repo.count_by_run(run_id)

    items = [LiveSessionOrderResponse.model_validate(o) for o in orders]

    return ApiResponse(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{run_id}", response_model=ApiResponse[LiveTradingRunResponse])
async def get_live_trading_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[LiveTradingRunResponse]:
    """Get a live trading run by ID.

    Args:
        run_id: Live trading run ID.
        session: Database session.

    Returns:
        Live trading run details.

    Raises:
        HTTPException: 404 if not found.
    """
    service = LiveTradingService(session)

    try:
        run = await service.get_run(run_id)
        return ApiResponse(data=LiveTradingRunResponse.model_validate(run))
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/equity-curve", response_model=ApiResponse[list[EquityCurvePoint]])
async def get_equity_curve(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    since: datetime | None = Query(
        None, description="Only return records after this time (ISO 8601)"
    ),
) -> ApiResponse[list[EquityCurvePoint]]:
    """Get equity curve for a live trading run.

    Args:
        run_id: Live trading run ID.
        session: Database session.
        since: Optional time filter for incremental loading.

    Returns:
        Equity curve data points.

    Raises:
        HTTPException: 404 if not found.
    """
    service = LiveTradingService(session)

    try:
        equity_curve = await service.get_equity_curve(run_id, since=since)
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
        run_id: Live trading run ID.
        session: Database session.

    Returns:
        Number of snapshots persisted.

    Raises:
        HTTPException: 404 if session not found.
    """
    service = LiveTradingService(session)

    try:
        count = await service.persist_snapshots(run_id)
        return ApiResponse(data={"persisted_count": count})
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
