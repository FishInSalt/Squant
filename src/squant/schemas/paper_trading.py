"""Pydantic schemas for paper trading API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from squant.schemas.backtest import TradeRecordResponse
from squant.schemas.types import NumberDecimal


class StartPaperTradingRequest(BaseModel):
    """Request to start a paper trading session."""

    strategy_id: UUID = Field(..., description="Strategy ID to run")
    symbol: str = Field(
        ..., min_length=1, max_length=32, description="Trading symbol (e.g., BTC/USDT)"
    )
    exchange: str = Field(..., min_length=1, max_length=32, description="Exchange name (e.g., okx)")
    timeframe: str = Field(
        ..., min_length=1, max_length=8, description="Candle timeframe (e.g., 1m)"
    )
    initial_capital: Decimal = Field(..., gt=0, description="Starting capital")
    commission_rate: Decimal = Field(
        default=Decimal("0.001"),
        ge=0,
        le=1,
        description="Commission rate (e.g., 0.001 = 0.1%)",
    )
    slippage: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=1,
        description="Slippage rate for market orders",
    )
    params: dict[str, Any] | None = Field(None, description="Strategy parameters")


class ResumePaperTradingRequest(BaseModel):
    """Request to resume a stopped/errored paper trading session."""

    warmup_bars: int = Field(
        default=200,
        ge=0,
        le=5000,
        description="Number of historical bars to replay for strategy warmup",
    )


class PaperTradingRunResponse(BaseModel):
    """Paper trading run response."""

    id: UUID
    strategy_id: UUID
    strategy_name: str | None = None
    mode: str
    symbol: str
    exchange: str
    timeframe: str
    status: str
    initial_capital: NumberDecimal | None
    commission_rate: NumberDecimal
    slippage: NumberDecimal | None
    params: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PositionInfo(BaseModel):
    """Position information."""

    amount: NumberDecimal
    avg_entry_price: NumberDecimal
    current_price: NumberDecimal | None = None
    unrealized_pnl: NumberDecimal | None = None


class PendingOrderInfo(BaseModel):
    """Pending order information."""

    id: str
    symbol: str
    side: str
    type: str
    amount: NumberDecimal
    price: NumberDecimal | None
    status: str
    created_at: datetime | None


class PaperTradingStatusResponse(BaseModel):
    """Paper trading status response."""

    run_id: UUID
    symbol: str
    timeframe: str
    is_running: bool
    started_at: datetime | None
    stopped_at: datetime | None
    error_message: str | None
    bar_count: int
    cash: NumberDecimal
    equity: NumberDecimal
    initial_capital: NumberDecimal
    total_fees: NumberDecimal
    unrealized_pnl: NumberDecimal = Field(default=Decimal("0"))
    realized_pnl: NumberDecimal = Field(default=Decimal("0"))
    positions: dict[str, PositionInfo]
    pending_orders: list[PendingOrderInfo]
    completed_orders_count: int
    trades_count: int
    trades: list[TradeRecordResponse] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


class PaperTradingListItem(BaseModel):
    """Paper trading list item (active session summary)."""

    id: UUID
    strategy_id: UUID
    strategy_name: str | None = None
    symbol: str
    exchange: str
    timeframe: str
    status: str
    is_running: bool
    initial_capital: NumberDecimal | None
    started_at: datetime | None
    created_at: datetime
    bar_count: int
    equity: NumberDecimal
    cash: NumberDecimal
