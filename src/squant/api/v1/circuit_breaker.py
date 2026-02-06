"""Circuit breaker API endpoints.

Provides emergency trading halt functionality (RSK-010, RSK-011).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse
from squant.infra.database import get_session
from squant.infra.redis import get_redis
from squant.schemas.circuit_breaker import (
    CircuitBreakerStatusResponse,
    CloseAllPositionsRequest,
    CloseAllPositionsResponse,
    ResetCircuitBreakerResponse,
    TriggerCircuitBreakerRequest,
    TriggerCircuitBreakerResponse,
)
from squant.services.circuit_breaker import (
    CircuitBreakerAlreadyActiveError,
    CircuitBreakerCooldownError,
    CircuitBreakerOperationInProgressError,
    CircuitBreakerService,
    get_circuit_breaker_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/trigger", response_model=ApiResponse[TriggerCircuitBreakerResponse])
async def trigger_circuit_breaker(
    request: TriggerCircuitBreakerRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ApiResponse[TriggerCircuitBreakerResponse]:
    """Trigger the circuit breaker to stop all trading (RSK-010).

    This is the emergency stop function that will:
    1. Stop all live trading sessions
    2. Stop all paper trading sessions
    3. Set cooldown period

    Note: This does NOT automatically close positions. Use
    /close-all-positions endpoint for that.

    Args:
        request: Trigger request with reason and optional cooldown.
        session: Database session.
        redis: Redis client.

    Returns:
        Trigger result with session counts.

    Raises:
        HTTPException: 409 if circuit breaker is already active.
    """
    service = CircuitBreakerService(session, redis)

    try:
        result = await service.trigger(
            reason=request.reason,
            cooldown_minutes=request.cooldown_minutes,
        )
        return ApiResponse(data=TriggerCircuitBreakerResponse(**result))
    except CircuitBreakerAlreadyActiveError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except CircuitBreakerOperationInProgressError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/close-all-positions", response_model=ApiResponse[CloseAllPositionsResponse])
async def close_all_positions(
    request: CloseAllPositionsRequest | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ApiResponse[CloseAllPositionsResponse]:
    """Close all open positions across all sessions (RSK-011).

    This will:
    1. Cancel all open orders in live sessions
    2. Place market orders to close all positions in live sessions
    3. Stop all paper trading sessions

    WARNING: This is an emergency action and cannot be undone.

    Args:
        request: Optional request with reason.
        session: Database session.
        redis: Redis client.

    Returns:
        Close operation results.
    """
    service = CircuitBreakerService(session, redis)

    reason = request.reason if request else "Manual close all positions"
    result = await service.close_all_positions(reason=reason)

    return ApiResponse(data=CloseAllPositionsResponse(**result))


@router.get("/status", response_model=ApiResponse[CircuitBreakerStatusResponse])
async def get_status(
    redis: Redis = Depends(get_redis),
) -> ApiResponse[CircuitBreakerStatusResponse]:
    """Get current circuit breaker status.

    Returns:
        Current status including active state, cooldown, and session counts.
    """
    status = await get_circuit_breaker_status(redis)

    return ApiResponse(data=CircuitBreakerStatusResponse(**status))


@router.post("/reset", response_model=ApiResponse[ResetCircuitBreakerResponse])
async def reset_circuit_breaker(
    force: bool = False,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ApiResponse[ResetCircuitBreakerResponse]:
    """Reset the circuit breaker.

    Allows trading to resume after the circuit breaker was triggered.
    By default, respects the cooldown period. Use force=true to
    bypass cooldown (use with caution).

    Args:
        force: If true, bypass cooldown period.
        session: Database session.
        redis: Redis client.

    Returns:
        Reset status.

    Raises:
        HTTPException: 409 if in cooldown and force is false.
    """
    service = CircuitBreakerService(session, redis)

    try:
        result = await service.reset(force=force)
        return ApiResponse(data=ResetCircuitBreakerResponse(**result))
    except CircuitBreakerCooldownError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": 409,
                "message": str(e),
                "data": {"cooldown_remaining_minutes": e.remaining_minutes},
            },
        ) from None
