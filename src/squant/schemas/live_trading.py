"""Pydantic schemas for live trading API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RiskConfigRequest(BaseModel):
    """Risk configuration for live trading."""

    max_position_size: Decimal = Field(
        ...,
        gt=0,
        le=1,
        description="Maximum position size as fraction of equity (0-1)",
    )
    max_order_size: Decimal = Field(
        ...,
        gt=0,
        le=1,
        description="Maximum single order size as fraction of equity (0-1)",
    )
    daily_trade_limit: int = Field(
        ..., gt=0, le=1000, description="Maximum trades per day"
    )
    daily_loss_limit: Decimal = Field(
        ...,
        gt=0,
        le=1,
        description="Maximum daily loss as fraction of equity (0-1)",
    )
    price_deviation_limit: Decimal = Field(
        default=Decimal("0.02"),
        ge=0,
        le=1,
        description="Maximum price deviation from last price (0-1)",
    )
    circuit_breaker_threshold: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Consecutive losses to trigger circuit breaker",
    )


class StartLiveTradingRequest(BaseModel):
    """Request to start a live trading session."""

    strategy_id: UUID = Field(..., description="Strategy ID to run")
    symbol: str = Field(
        ..., min_length=1, max_length=32, description="Trading symbol (e.g., BTC/USDT)"
    )
    exchange: str = Field(
        ..., min_length=1, max_length=32, description="Exchange name (e.g., okx)"
    )
    timeframe: str = Field(
        ..., min_length=1, max_length=8, description="Candle timeframe (e.g., 1m)"
    )
    risk_config: RiskConfigRequest = Field(
        ..., description="Risk management configuration"
    )
    initial_equity: Decimal | None = Field(
        None,
        gt=0,
        description="Initial equity for risk calculations (fetched from exchange if not provided)",
    )
    params: dict[str, Any] | None = Field(None, description="Strategy parameters")


class LiveTradingRunResponse(BaseModel):
    """Live trading run response."""

    id: UUID
    strategy_id: UUID
    mode: str
    symbol: str
    exchange: str
    timeframe: str
    status: str
    initial_capital: Decimal | None
    commission_rate: Decimal
    slippage: Decimal | None
    params: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LivePositionInfo(BaseModel):
    """Position information for live trading."""

    amount: Decimal
    avg_entry_price: Decimal


class LiveOrderInfo(BaseModel):
    """Live order information."""

    internal_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    type: str
    amount: Decimal
    filled_amount: Decimal
    price: Decimal | None
    avg_fill_price: Decimal | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None


class RiskStateResponse(BaseModel):
    """Risk management state response."""

    daily_pnl: Decimal
    daily_trade_count: int
    consecutive_losses: int
    circuit_breaker_active: bool
    max_position_size: Decimal
    max_order_size: Decimal
    daily_trade_limit: int
    daily_loss_limit: Decimal


class LiveTradingStatusResponse(BaseModel):
    """Live trading status response."""

    run_id: UUID
    symbol: str
    timeframe: str
    is_running: bool
    started_at: datetime | None
    stopped_at: datetime | None
    error_message: str | None
    bar_count: int
    cash: Decimal
    equity: Decimal
    initial_capital: Decimal
    total_fees: Decimal
    positions: dict[str, LivePositionInfo]
    pending_orders: list[dict[str, Any]]
    live_orders: list[LiveOrderInfo]
    completed_orders_count: int
    trades_count: int
    risk_state: RiskStateResponse | None


class LiveTradingListItem(BaseModel):
    """Live trading list item (active session summary)."""

    run_id: UUID
    strategy_id: UUID
    symbol: str
    timeframe: str
    is_running: bool
    started_at: datetime | None
    bar_count: int
    equity: Decimal
    cash: Decimal


class StopLiveTradingRequest(BaseModel):
    """Request to stop live trading session."""

    cancel_orders: bool = Field(
        default=True, description="Whether to cancel all open orders on stop"
    )


class EmergencyCloseResponse(BaseModel):
    """Response from emergency close operation."""

    run_id: UUID
    status: str
    message: str | None = None
    orders_cancelled: int | None = None
    positions_closed: int | None = None
