"""Pydantic schemas for paper trading API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from squant.schemas.backtest import FillRecordResponse, TradeRecordResponse
from squant.schemas.live_trading import RiskConfigRequest
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
        default=Decimal("0.0005"),
        ge=0,
        le=1,
        description="Slippage rate for market orders (default 5bps covers typical spread)",
    )
    params: dict[str, Any] | None = Field(None, description="Strategy parameters")
    risk_config: RiskConfigRequest | None = Field(
        None, description="Optional risk management configuration"
    )


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
    # Extracted from result JSONB for list display (IMP-006)
    equity: NumberDecimal | None = None
    unrealized_pnl: NumberDecimal | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="wrap")
    @classmethod
    def _handle_orm_result_fields(cls, data: Any, handler: Any) -> "PaperTradingRunResponse":
        """Handle equity/unrealized_pnl which don't exist on StrategyRun ORM.

        These fields are populated from result JSONB in the API layer.
        When model_validate() with from_attributes=True reads an ORM object,
        getattr() may return invalid types. This validator catches the error,
        strips the problematic fields, and retries.
        """
        try:
            return handler(data)
        except Exception:
            if isinstance(data, dict):
                raise
            # ORM object: build dict manually, excluding result-only fields
            from pydantic.fields import FieldInfo

            result = {}
            for name, field_info in cls.model_fields.items():
                if name in ("equity", "unrealized_pnl"):
                    result[name] = None
                    continue
                val = getattr(data, name, field_info.default)
                result[name] = val
            return handler(result)


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


class OpenTradeInfo(BaseModel):
    """Currently open trade (position entry info for chart markers)."""

    symbol: str
    side: str
    entry_time: str
    entry_price: NumberDecimal
    amount: NumberDecimal
    fees: NumberDecimal


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
    fills: list[FillRecordResponse] = Field(default_factory=list)
    open_trade: OpenTradeInfo | None = None
    logs: list[str] = Field(default_factory=list)
    risk_state: dict[str, Any] | None = None


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
