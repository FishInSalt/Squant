"""Health check endpoints."""

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.database import get_session
from squant.infra.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    version: str


class ComponentHealth(BaseModel):
    """Component health status."""

    status: str
    latency_ms: float | None = None
    message: str | None = None


class DetailedHealthStatus(BaseModel):
    """Detailed health check response with components."""

    status: str
    timestamp: datetime
    version: str
    components: dict[str, ComponentHealth]


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Basic health check endpoint."""
    return HealthStatus(
        status="healthy",
        timestamp=datetime.now(UTC),
        version="0.1.0",
    )


@router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_probe(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Kubernetes readiness probe.

    Checks database and Redis connections to ensure the service
    is ready to handle requests.
    """
    # Check database connection
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Check Redis connection
    try:
        redis = get_redis_client()
        if redis is not None:
            await redis.ping()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return {"status": "ready"}


@router.get("/health/detailed", response_model=DetailedHealthStatus)
async def detailed_health_check(
    session: AsyncSession = Depends(get_session),
) -> DetailedHealthStatus:
    """Detailed health check with component status and latency."""
    components: dict[str, ComponentHealth] = {}

    # Check database
    try:
        start = time.perf_counter()
        await session.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        components["database"] = ComponentHealth(
            status="healthy",
            latency_ms=round(latency_ms, 2),
        )
    except Exception as e:
        components["database"] = ComponentHealth(
            status="unhealthy",
            message=str(e),
        )

    # Check Redis
    try:
        redis = get_redis_client()
        if redis is not None:
            start = time.perf_counter()
            await redis.ping()
            latency_ms = (time.perf_counter() - start) * 1000
            components["redis"] = ComponentHealth(
                status="healthy",
                latency_ms=round(latency_ms, 2),
            )
        else:
            components["redis"] = ComponentHealth(
                status="not_configured",
                message="Redis client not initialized",
            )
    except Exception as e:
        components["redis"] = ComponentHealth(
            status="unhealthy",
            message=str(e),
        )

    # Determine overall status
    overall_status = "healthy"
    for component in components.values():
        if component.status == "unhealthy":
            overall_status = "unhealthy"
            break

    return DetailedHealthStatus(
        status=overall_status,
        timestamp=datetime.now(UTC),
        version="0.1.0",
        components=components,
    )
