"""Pydantic schemas for circuit breaker API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TriggerCircuitBreakerRequest(BaseModel):
    """Request to trigger the circuit breaker."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Reason for triggering the circuit breaker",
    )
    cooldown_minutes: int | None = Field(
        None,
        ge=1,
        le=1440,
        description="Optional cooldown period in minutes (1-1440, default from config)",
    )


class TriggerCircuitBreakerResponse(BaseModel):
    """Response after triggering the circuit breaker."""

    status: str = Field(..., description="Trigger status (triggered/already_active)")
    triggered_at: str = Field(..., description="ISO 8601 timestamp of trigger")
    live_sessions_stopped: int = Field(..., description="Number of live sessions stopped")
    paper_sessions_stopped: int = Field(..., description="Number of paper sessions stopped")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")


class CloseAllPositionsRequest(BaseModel):
    """Request to close all positions."""

    reason: str = Field(
        default="Manual close all positions",
        max_length=256,
        description="Reason for closing all positions",
    )


class CloseAllPositionsResponse(BaseModel):
    """Response after closing all positions."""

    live_positions_closed: int = Field(..., description="Number of live positions closed")
    paper_positions_reset: int = Field(..., description="Number of paper sessions reset")
    orders_cancelled: int = Field(..., description="Number of orders cancelled")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="Errors by session")


class CircuitBreakerStatusResponse(BaseModel):
    """Circuit breaker status response."""

    is_active: bool = Field(..., description="Whether circuit breaker is currently active")
    triggered_at: str | None = Field(None, description="ISO 8601 timestamp of last trigger")
    trigger_type: str | None = Field(None, description="Type of last trigger (manual/auto)")
    trigger_reason: str | None = Field(None, description="Reason for last trigger")
    cooldown_until: str | None = Field(None, description="ISO 8601 timestamp when cooldown ends")
    active_live_sessions: int = Field(..., description="Number of active live trading sessions")
    active_paper_sessions: int = Field(..., description="Number of active paper trading sessions")


class ResetCircuitBreakerResponse(BaseModel):
    """Response after resetting the circuit breaker."""

    status: str = Field(..., description="Reset status (reset/cooldown/not_active)")
    cooldown_remaining_minutes: float | None = Field(
        None, description="Minutes remaining in cooldown if applicable"
    )


# RSK-008: Risk trigger record schemas


class RiskTriggerResponse(BaseModel):
    """Risk trigger record response."""

    id: UUID
    time: datetime
    rule_id: UUID | None = None
    run_id: UUID | None = None
    trigger_type: str
    details: dict[str, Any]

    model_config = {"from_attributes": True}


class RiskTriggerListItem(BaseModel):
    """Risk trigger list item for paginated response."""

    id: UUID
    time: datetime
    rule_id: UUID | None = None
    run_id: UUID | None = None
    trigger_type: str
    details: dict[str, Any]
    # Joined fields
    rule_name: str | None = None
    rule_type: str | None = None
    strategy_name: str | None = None
    symbol: str | None = None
    message: str | None = None


class CircuitBreakerEventResponse(BaseModel):
    """Circuit breaker event response."""

    id: UUID
    time: datetime
    trigger_type: str
    trigger_source: str
    reason: str
    details: dict[str, Any]
    sessions_stopped: int
    positions_closed: int

    model_config = {"from_attributes": True}
