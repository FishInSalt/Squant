"""Pydantic schemas for backtest API requests and responses."""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RunBacktestRequest(BaseModel):
    """Request to create and run a backtest."""

    strategy_id: UUID = Field(..., description="Strategy ID to backtest")
    symbol: str = Field(
        ..., min_length=1, max_length=32, description="Trading symbol (e.g., BTC/USDT)"
    )
    exchange: str = Field(..., min_length=1, max_length=32, description="Exchange name (e.g., okx)")
    timeframe: str = Field(
        ..., min_length=1, max_length=8, description="Candle timeframe (e.g., 1h)"
    )
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
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

    @model_validator(mode="after")
    def validate_date_range(self) -> "RunBacktestRequest":
        """Validate that end_date is after start_date."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class CreateBacktestRequest(BaseModel):
    """Request to create a backtest without immediately running it."""

    strategy_id: UUID = Field(..., description="Strategy ID to backtest")
    symbol: str = Field(..., min_length=1, max_length=32, description="Trading symbol")
    exchange: str = Field(..., min_length=1, max_length=32, description="Exchange name")
    timeframe: str = Field(..., min_length=1, max_length=8, description="Candle timeframe")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: Decimal = Field(..., gt=0, description="Starting capital")
    commission_rate: Decimal = Field(default=Decimal("0.001"), ge=0, le=1)
    slippage: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    params: dict[str, Any] | None = Field(None, description="Strategy parameters")

    @model_validator(mode="after")
    def validate_date_range(self) -> "CreateBacktestRequest":
        """Validate that end_date is after start_date."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class CheckDataRequest(BaseModel):
    """Request to check data availability."""

    exchange: str = Field(..., min_length=1, max_length=32)
    symbol: str = Field(..., min_length=1, max_length=32)
    timeframe: str = Field(..., min_length=1, max_length=8)
    start_date: datetime
    end_date: datetime

    @model_validator(mode="after")
    def validate_date_range(self) -> "CheckDataRequest":
        """Validate that end_date is after start_date."""
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class BacktestRunResponse(BaseModel):
    """Backtest run response."""

    id: UUID
    strategy_id: UUID
    mode: str
    symbol: str
    exchange: str
    timeframe: str
    status: str
    backtest_start: datetime | None
    backtest_end: datetime | None
    initial_capital: Decimal | None
    commission_rate: Decimal
    slippage: Decimal | None
    params: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BacktestListItem(BaseModel):
    """Backtest list item (summary)."""

    id: UUID
    strategy_id: UUID
    symbol: str
    exchange: str
    timeframe: str
    status: str
    backtest_start: datetime | None
    backtest_end: datetime | None
    initial_capital: Decimal | None
    result: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EquityCurvePoint(BaseModel):
    """Single point in equity curve."""

    time: datetime
    equity: Decimal
    cash: Decimal
    position_value: Decimal
    unrealized_pnl: Decimal

    model_config = {"from_attributes": True}


class TradeRecordResponse(BaseModel):
    """Trade record response."""

    symbol: str
    side: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime | None
    exit_price: Decimal | None
    amount: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    fees: Decimal


class BacktestDetailResponse(BaseModel):
    """Detailed backtest response including equity curve and trades."""

    run: BacktestRunResponse
    equity_curve: list[EquityCurvePoint]
    total_bars: int | None = None


class DataAvailabilityResponse(BaseModel):
    """Data availability check response."""

    exchange: str
    symbol: str
    timeframe: str
    first_bar: datetime | None
    last_bar: datetime | None
    total_bars: int
    requested_start: datetime
    requested_end: datetime
    has_data: bool
    is_complete: bool


class AvailableSymbolResponse(BaseModel):
    """Available symbol info."""

    exchange: str
    symbol: str
    timeframe: str
    bar_count: int
    first_bar: datetime | None
    last_bar: datetime | None


class ExportFormat(str, enum.Enum):
    """Export format enum (TRD-009#4)."""

    JSON = "json"
    CSV = "csv"


class BacktestReportExport(BaseModel):
    """Backtest report export data (TRD-009#4)."""

    # Run metadata
    run_id: str
    strategy_id: str
    strategy_name: str | None
    symbol: str
    exchange: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    final_equity: Decimal
    commission_rate: Decimal
    slippage: Decimal

    # Performance metrics
    metrics: dict[str, Any]

    # Equity curve
    equity_curve: list[EquityCurvePoint]

    # Trades
    trades: list[TradeRecordResponse]

    # Export metadata
    exported_at: datetime
    export_format: str
