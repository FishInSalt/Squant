"""Order management API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.schemas.types import NumberDecimal


class CreateOrderRequest(BaseModel):
    """Request to create a new order."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    side: OrderSide = Field(..., description="Order side (BUY/SELL)")
    type: OrderType = Field(..., description="Order type (MARKET/LIMIT/STOP/STOP_LIMIT)")
    amount: Decimal = Field(..., gt=0, description="Order amount in base currency")
    price: Decimal | None = Field(None, description="Limit price (required for LIMIT/STOP_LIMIT)")
    stop_price: Decimal | None = Field(
        None, description="Stop trigger price (required for STOP/STOP_LIMIT)"
    )
    client_order_id: str | None = Field(None, max_length=32, description="Optional client order ID")
    run_id: UUID | None = Field(None, description="Strategy run ID (if from strategy)")

    @model_validator(mode="after")
    def validate_limit_price(self) -> "CreateOrderRequest":
        """Validate order type price constraints."""
        if self.type == OrderType.LIMIT and self.price is None:
            raise ValueError("price is required for LIMIT orders")
        if self.type == OrderType.STOP:
            if self.stop_price is None:
                raise ValueError("stop_price is required for STOP orders")
            if self.price is not None:
                raise ValueError("STOP orders must not have a limit price (use STOP_LIMIT)")
        if self.type == OrderType.STOP_LIMIT:
            if self.stop_price is None:
                raise ValueError("stop_price is required for STOP_LIMIT orders")
            if self.price is None:
                raise ValueError("price is required for STOP_LIMIT orders")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")
        if self.stop_price is not None and self.stop_price <= 0:
            raise ValueError("stop_price must be positive")
        return self


class OrderDetail(BaseModel):
    """Order detail response."""

    model_config = {"from_attributes": True}

    id: UUID = Field(..., description="Database order ID")
    account_id: UUID = Field(..., description="Account ID")
    account_name: str | None = Field(None, description="Exchange account name")
    run_id: UUID | None = Field(None, description="Strategy run ID")
    exchange: str = Field(..., description="Exchange name")
    exchange_oid: str | None = Field(None, description="Exchange order ID")
    symbol: str = Field(..., description="Trading pair")
    side: OrderSide = Field(..., description="Order side")
    type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(..., description="Order status")
    price: NumberDecimal | None = Field(None, description="Order price")
    stop_price: NumberDecimal | None = Field(None, description="Stop trigger price")
    amount: NumberDecimal = Field(..., description="Order amount")
    filled: NumberDecimal = Field(..., description="Filled amount")
    avg_price: NumberDecimal | None = Field(None, description="Average fill price")
    reject_reason: str | None = Field(None, description="Rejection reason if rejected")
    commission: NumberDecimal = Field(
        default=Decimal("0"), description="Total commission (sum of trade fees)"
    )
    commission_asset: str | None = Field(None, description="Commission currency (from trades)")
    remaining_amount: NumberDecimal = Field(
        default=Decimal("0"), description="Remaining unfilled amount (amount - filled)"
    )
    status_display: str = Field(default="", description="Frontend-friendly status (submitted→open)")
    strategy_name: str | None = Field(None, description="Strategy name (from run.strategy)")
    corrections: list | None = Field(None, description="Data correction audit log")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")


class TradeDetail(BaseModel):
    """Trade execution detail."""

    model_config = {"from_attributes": True}

    id: UUID = Field(..., description="Trade ID")
    order_id: UUID = Field(..., description="Order ID")
    exchange_tid: str | None = Field(None, description="Exchange trade ID")
    price: NumberDecimal = Field(..., description="Execution price")
    amount: NumberDecimal = Field(..., description="Execution amount")
    fee: NumberDecimal = Field(..., description="Trading fee")
    fee_currency: str | None = Field(None, description="Fee currency")
    timestamp: datetime = Field(..., description="Execution time")
    fill_source: str | None = Field(None, description="Fill source: ws, poll, or reconcile")
    taker_or_maker: str | None = Field(None, description="Maker or taker fill")


class OrderWithTrades(OrderDetail):
    """Order detail with trades."""

    trades: list[TradeDetail] = Field(default_factory=list, description="Trade executions")


class ListOrdersRequest(BaseModel):
    """Request to list orders."""

    status: list[OrderStatus] | None = Field(None, description="Filter by status")
    symbol: str | None = Field(None, description="Filter by trading pair")
    side: OrderSide | None = Field(None, description="Filter by side")
    start_time: datetime | None = Field(None, description="Filter by start time")
    end_time: datetime | None = Field(None, description="Filter by end time")
    page: int = Field(1, ge=1, description="Page number (starts from 1)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (max 100)")


class OrderListData(BaseModel):
    """Order list data container for paginated response."""

    items: list[OrderDetail] = Field(..., description="List of orders")
    total: int = Field(..., description="Total count (without pagination)")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")


class SyncOrdersResponse(BaseModel):
    """Response from syncing orders."""

    synced_count: int = Field(..., description="Number of orders synced")
    orders: list[OrderDetail] = Field(..., description="Synced orders")


class OrderStatsResponse(BaseModel):
    """Order statistics response."""

    total: int = Field(..., description="Total orders")
    open: int = Field(default=0, description="Open orders (pending + submitted)")
    pending: int = Field(..., description="Pending orders")
    submitted: int = Field(..., description="Submitted orders")
    partial: int = Field(..., description="Partially filled orders")
    filled: int = Field(..., description="Filled orders")
    cancelled: int = Field(..., description="Cancelled orders")
    rejected: int = Field(..., description="Rejected orders")
