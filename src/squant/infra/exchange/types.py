"""Exchange adapter shared types."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from squant.models.enums import OrderSide, OrderStatus, OrderType


class TimeFrame(str, Enum):
    """Candlestick time frame."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class WSMessageType(str, Enum):
    """WebSocket message types for internal pub/sub routing.

    Shared across all exchange implementations (OKX, Binance, etc.)
    to provide consistent message type identification for Redis pub/sub.
    """

    TICKER = "ticker"
    CANDLE = "candle"
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    ORDER_UPDATE = "order_update"
    ACCOUNT_UPDATE = "account_update"
    EXCHANGE_SWITCHING = "exchange_switching"  # Notify clients of exchange switch
    SERVICE_READY = "service_ready"  # Notify clients that stream manager is ready


class Balance(BaseModel):
    """Single currency balance."""

    currency: str = Field(..., description="Currency symbol (e.g., BTC, USDT)")
    available: Decimal = Field(..., description="Available balance for trading")
    frozen: Decimal = Field(default=Decimal("0"), description="Frozen/locked balance")

    @property
    def total(self) -> Decimal:
        """Total balance (available + frozen)."""
        return self.available + self.frozen


class AccountBalance(BaseModel):
    """Account balance containing multiple currencies."""

    exchange: str = Field(..., description="Exchange name")
    balances: list[Balance] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_balance(self, currency: str) -> Balance | None:
        """Get balance for specific currency."""
        for balance in self.balances:
            if balance.currency.upper() == currency.upper():
                return balance
        return None


class Ticker(BaseModel):
    """Market ticker data."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    last: Decimal = Field(..., description="Last traded price")
    bid: Decimal | None = Field(default=None, description="Best bid price")
    ask: Decimal | None = Field(default=None, description="Best ask price")
    high_24h: Decimal | None = Field(default=None, description="24h high price")
    low_24h: Decimal | None = Field(default=None, description="24h low price")
    volume_24h: Decimal | None = Field(default=None, description="24h volume")
    volume_quote_24h: Decimal | None = Field(default=None, description="24h quote volume")
    change_24h: Decimal | None = Field(default=None, description="24h price change")
    change_pct_24h: Decimal | None = Field(default=None, description="24h price change %")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Candlestick(BaseModel):
    """OHLCV candlestick data."""

    timestamp: datetime = Field(..., description="Candle open time")
    open: Decimal = Field(..., description="Open price")
    high: Decimal = Field(..., description="High price")
    low: Decimal = Field(..., description="Low price")
    close: Decimal = Field(..., description="Close price")
    volume: Decimal = Field(..., description="Volume in base currency")
    volume_quote: Decimal | None = Field(default=None, description="Volume in quote currency")


class OrderRequest(BaseModel):
    """Order placement request."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    side: OrderSide = Field(..., description="Order side (buy/sell)")
    type: OrderType = Field(..., description="Order type (market/limit)")
    amount: Decimal = Field(..., gt=0, description="Order amount in base currency")
    price: Decimal | None = Field(
        default=None, description="Limit price (required for limit orders)"
    )
    client_order_id: str | None = Field(default=None, description="Client-specified order ID")

    def model_post_init(self, __context: object) -> None:
        """Validate that limit orders have a price."""
        if self.type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit orders must have a price")


class OrderResponse(BaseModel):
    """Order response from exchange."""

    order_id: str = Field(..., description="Exchange order ID")
    client_order_id: str | None = Field(default=None, description="Client-specified order ID")
    symbol: str = Field(..., description="Trading pair")
    side: OrderSide = Field(..., description="Order side")
    type: OrderType = Field(..., description="Order type")
    status: OrderStatus = Field(..., description="Order status")
    price: Decimal | None = Field(default=None, description="Order price")
    amount: Decimal = Field(..., description="Order amount")
    filled: Decimal = Field(default=Decimal("0"), description="Filled amount")
    avg_price: Decimal | None = Field(default=None, description="Average fill price")
    fee: Decimal | None = Field(default=None, description="Trading fee")
    fee_currency: str | None = Field(default=None, description="Fee currency")
    created_at: datetime | None = Field(default=None, description="Order creation time")
    updated_at: datetime | None = Field(default=None, description="Order update time")


class CancelOrderRequest(BaseModel):
    """Cancel order request."""

    symbol: str = Field(..., description="Trading pair")
    order_id: str | None = Field(default=None, description="Exchange order ID")
    client_order_id: str | None = Field(default=None, description="Client order ID")

    def model_post_init(self, __context: object) -> None:
        """Validate that at least one ID is provided."""
        if not self.order_id and not self.client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")
