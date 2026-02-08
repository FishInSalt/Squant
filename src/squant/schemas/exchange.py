"""Exchange API schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.schemas.types import NumberDecimal


# Balance schemas
class BalanceItem(BaseModel):
    """Single currency balance."""

    currency: str = Field(..., description="Currency symbol")
    available: NumberDecimal = Field(..., description="Available balance")
    frozen: NumberDecimal = Field(..., description="Frozen balance")
    total: NumberDecimal = Field(..., description="Total balance")


class BalanceResponse(BaseModel):
    """Account balance response."""

    exchange: str = Field(..., description="Exchange name")
    balances: list[BalanceItem] = Field(..., description="Currency balances")
    timestamp: datetime = Field(..., description="Response timestamp")


# Ticker schemas
class TickerResponse(BaseModel):
    """Ticker response."""

    symbol: str = Field(..., description="Trading pair")
    last: NumberDecimal = Field(..., description="Last price")
    bid: NumberDecimal | None = Field(None, description="Best bid price")
    ask: NumberDecimal | None = Field(None, description="Best ask price")
    high_24h: NumberDecimal | None = Field(None, description="24h high")
    low_24h: NumberDecimal | None = Field(None, description="24h low")
    volume_24h: NumberDecimal | None = Field(None, description="24h volume in base currency")
    volume_quote_24h: NumberDecimal | None = Field(
        None, description="24h volume in quote currency (USDT)"
    )
    change_24h: NumberDecimal | None = Field(None, description="24h price change")
    change_pct_24h: NumberDecimal | None = Field(None, description="24h price change percentage")
    timestamp: datetime = Field(..., description="Response timestamp")


# Candlestick schemas
class CandlestickItem(BaseModel):
    """Single candlestick."""

    timestamp: datetime = Field(..., description="Candle open time")
    open: NumberDecimal = Field(..., description="Open price")
    high: NumberDecimal = Field(..., description="High price")
    low: NumberDecimal = Field(..., description="Low price")
    close: NumberDecimal = Field(..., description="Close price")
    volume: NumberDecimal = Field(..., description="Volume")


class CandlestickResponse(BaseModel):
    """Candlestick response."""

    symbol: str = Field(..., description="Trading pair")
    timeframe: str = Field(..., description="Time frame")
    candles: list[CandlestickItem] = Field(..., description="Candlestick data")


# Order schemas
class PlaceOrderRequest(BaseModel):
    """Place order request."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    side: OrderSide = Field(..., description="Order side")
    type: OrderType = Field(..., description="Order type")
    amount: Decimal = Field(..., gt=0, description="Order amount")
    price: Decimal | None = Field(None, description="Limit price")
    client_order_id: str | None = Field(None, max_length=32, description="Client order ID")


class OrderResponse(BaseModel):
    """Order response."""

    order_id: str = Field(..., description="Exchange order ID")
    client_order_id: str | None = Field(None, description="Client order ID")
    symbol: str = Field(..., description="Trading pair")
    side: OrderSide = Field(..., description="Order side")
    type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(..., description="Order status")
    price: NumberDecimal | None = Field(None, description="Order price")
    amount: NumberDecimal = Field(..., description="Order amount")
    filled: NumberDecimal = Field(..., description="Filled amount")
    avg_price: NumberDecimal | None = Field(None, description="Average fill price")
    created_at: datetime | None = Field(None, description="Creation time")


class CancelOrderRequest(BaseModel):
    """Cancel order request."""

    symbol: str = Field(..., description="Trading pair")
    order_id: str | None = Field(None, description="Exchange order ID")
    client_order_id: str | None = Field(None, description="Client order ID")


class OpenOrdersResponse(BaseModel):
    """Open orders response."""

    orders: list[OrderResponse] = Field(..., description="List of open orders")
    total: int = Field(..., description="Total count")
