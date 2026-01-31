"""Exchange API schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from squant.models.enums import OrderSide, OrderStatus, OrderType


# Balance schemas
class BalanceItem(BaseModel):
    """Single currency balance."""

    currency: str = Field(..., description="Currency symbol")
    available: Decimal = Field(..., description="Available balance")
    frozen: Decimal = Field(..., description="Frozen balance")
    total: Decimal = Field(..., description="Total balance")


class BalanceResponse(BaseModel):
    """Account balance response."""

    exchange: str = Field(..., description="Exchange name")
    balances: list[BalanceItem] = Field(..., description="Currency balances")
    timestamp: datetime = Field(..., description="Response timestamp")


# Ticker schemas
class TickerResponse(BaseModel):
    """Ticker response."""

    symbol: str = Field(..., description="Trading pair")
    last: Decimal = Field(..., description="Last price")
    bid: Decimal | None = Field(None, description="Best bid price")
    ask: Decimal | None = Field(None, description="Best ask price")
    high_24h: Decimal | None = Field(None, description="24h high")
    low_24h: Decimal | None = Field(None, description="24h low")
    volume_24h: Decimal | None = Field(None, description="24h volume in base currency")
    volume_quote_24h: Decimal | None = Field(
        None, description="24h volume in quote currency (USDT)"
    )
    change_24h: Decimal | None = Field(None, description="24h price change")
    change_pct_24h: Decimal | None = Field(None, description="24h price change percentage")
    timestamp: datetime = Field(..., description="Response timestamp")


# Candlestick schemas
class CandlestickItem(BaseModel):
    """Single candlestick."""

    timestamp: datetime = Field(..., description="Candle open time")
    open: Decimal = Field(..., description="Open price")
    high: Decimal = Field(..., description="High price")
    low: Decimal = Field(..., description="Low price")
    close: Decimal = Field(..., description="Close price")
    volume: Decimal = Field(..., description="Volume")


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
    price: Decimal | None = Field(None, description="Order price")
    amount: Decimal = Field(..., description="Order amount")
    filled: Decimal = Field(..., description="Filled amount")
    avg_price: Decimal | None = Field(None, description="Average fill price")
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
