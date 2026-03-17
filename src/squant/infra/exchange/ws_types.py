"""Shared WebSocket message types for all exchange adapters.

These types are exchange-agnostic and used across the system for
real-time market data, order updates, and account notifications
via Redis pub/sub.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from squant.infra.exchange.types import WSMessageType


class WSTicker(BaseModel):
    """Real-time ticker data from WebSocket."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    last: Decimal = Field(..., description="Last traded price")
    bid: Decimal | None = Field(default=None, description="Best bid price")
    ask: Decimal | None = Field(default=None, description="Best ask price")
    bid_size: Decimal | None = Field(default=None, description="Best bid size")
    ask_size: Decimal | None = Field(default=None, description="Best ask size")
    high_24h: Decimal | None = Field(default=None, description="24h high price")
    low_24h: Decimal | None = Field(default=None, description="24h low price")
    volume_24h: Decimal | None = Field(default=None, description="24h volume in base")
    volume_quote_24h: Decimal | None = Field(default=None, description="24h volume in quote")
    open_24h: Decimal | None = Field(default=None, description="24h open price")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WSCandle(BaseModel):
    """Real-time candlestick data from WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    timeframe: str = Field(..., description="Candle timeframe (e.g., 1m, 5m)")
    timestamp: datetime = Field(..., description="Candle open time")
    open: Decimal = Field(..., description="Open price")
    high: Decimal = Field(..., description="High price")
    low: Decimal = Field(..., description="Low price")
    close: Decimal = Field(..., description="Close price")
    volume: Decimal = Field(..., description="Volume in base currency")
    volume_quote: Decimal | None = Field(default=None, description="Volume in quote currency")
    is_closed: bool = Field(default=False, description="Whether the candle is closed")


class WSTrade(BaseModel):
    """Real-time trade data from WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    trade_id: str = Field(..., description="Trade ID")
    price: Decimal = Field(..., description="Trade price")
    size: Decimal = Field(..., description="Trade size")
    side: str = Field(..., description="Trade side (buy/sell)")
    timestamp: datetime = Field(..., description="Trade timestamp")


class WSOrderBookLevel(BaseModel):
    """Single level of order book."""

    price: Decimal = Field(..., description="Price level")
    size: Decimal = Field(..., description="Size at this price")
    num_orders: int | None = Field(default=None, description="Number of orders")


class WSOrderBook(BaseModel):
    """Real-time order book data from WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    bids: list[WSOrderBookLevel] = Field(default_factory=list, description="Bid levels")
    asks: list[WSOrderBookLevel] = Field(default_factory=list, description="Ask levels")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checksum: int | None = Field(default=None, description="OKX checksum for validation")


class WSOrderUpdate(BaseModel):
    """Real-time order status update from WebSocket."""

    order_id: str = Field(..., description="Exchange order ID")
    client_order_id: str | None = Field(default=None, description="Client order ID")
    symbol: str = Field(..., description="Trading pair")
    side: str = Field(..., description="Order side (buy/sell)")
    order_type: str = Field(..., description="Order type (market/limit)")
    status: str = Field(..., description="Order status")
    price: Decimal | None = Field(default=None, description="Order price")
    size: Decimal = Field(..., description="Order size")
    filled_size: Decimal = Field(default=Decimal("0"), description="Filled size")
    avg_price: Decimal | None = Field(default=None, description="Average fill price")
    fee: Decimal | None = Field(default=None, description="Trading fee")
    fee_currency: str | None = Field(default=None, description="Fee currency")
    created_at: datetime | None = Field(default=None, description="Order creation time")
    updated_at: datetime | None = Field(default=None, description="Order update time")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WSBalanceUpdate(BaseModel):
    """Single currency balance update."""

    currency: str = Field(..., description="Currency symbol")
    available: Decimal = Field(..., description="Available balance")
    frozen: Decimal = Field(default=Decimal("0"), description="Frozen balance")


class WSAccountUpdate(BaseModel):
    """Real-time account balance update from WebSocket."""

    balances: list[WSBalanceUpdate] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WSMessage(BaseModel):
    """Unified WebSocket message wrapper for Redis pub/sub."""

    type: WSMessageType = Field(..., description="Message type")
    channel: str = Field(..., description="Channel name (e.g., ticker:BTC-USDT)")
    data: dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Re-export WSMessageType for convenience
__all__ = [
    "WSMessageType",
    "WSTicker",
    "WSCandle",
    "WSTrade",
    "WSOrderBookLevel",
    "WSOrderBook",
    "WSOrderUpdate",
    "WSBalanceUpdate",
    "WSAccountUpdate",
    "WSMessage",
]
