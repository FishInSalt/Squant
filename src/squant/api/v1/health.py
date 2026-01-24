"""Health check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

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
        timestamp=datetime.now(timezone.utc),
        version="0.1.0",
    )


@router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness_probe() -> dict[str, str]:
    """Kubernetes readiness probe."""
    # TODO: Check database and Redis connections
    return {"status": "ready"}
