"""Binance WebSocket message types and stream definitions."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from squant.infra.exchange.types import WSMessageType


class BinanceStreamType(str, Enum):
    """Binance WebSocket stream types."""

    # Market streams
    TICKER = "ticker"  # Individual symbol ticker: <symbol>@ticker
    ALL_TICKERS = "!ticker@arr"  # All market tickers
    MINI_TICKER = "miniTicker"  # Mini ticker: <symbol>@miniTicker
    KLINE = "kline"  # Kline/candlestick: <symbol>@kline_<interval>
    TRADE = "trade"  # Trade stream: <symbol>@trade
    AGG_TRADE = "aggTrade"  # Aggregate trade: <symbol>@aggTrade
    DEPTH = "depth"  # Partial book depth: <symbol>@depth<levels>@<speed>
    BOOK_TICKER = "bookTicker"  # Best bid/ask: <symbol>@bookTicker

    # User data streams (require listen key)
    ACCOUNT_UPDATE = "outboundAccountPosition"
    BALANCE_UPDATE = "balanceUpdate"
    ORDER_UPDATE = "executionReport"


# Kline interval mapping
KLINE_INTERVALS = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}

# Re-export WSMessageType for backwards compatibility
__all__ = ["WSMessageType"]


class BinanceTicker(BaseModel):
    """Real-time ticker data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USDT)")
    last: Decimal = Field(..., description="Last traded price")
    bid: Decimal | None = Field(default=None, description="Best bid price")
    ask: Decimal | None = Field(default=None, description="Best ask price")
    bid_size: Decimal | None = Field(default=None, description="Best bid quantity")
    ask_size: Decimal | None = Field(default=None, description="Best ask quantity")
    high_24h: Decimal | None = Field(default=None, description="24h high price")
    low_24h: Decimal | None = Field(default=None, description="24h low price")
    volume_24h: Decimal | None = Field(default=None, description="24h volume in base")
    volume_quote_24h: Decimal | None = Field(default=None, description="24h volume in quote")
    open_24h: Decimal | None = Field(default=None, description="24h open price")
    price_change: Decimal | None = Field(default=None, description="Price change")
    price_change_percent: Decimal | None = Field(default=None, description="Price change percent")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BinanceCandle(BaseModel):
    """Real-time candlestick data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    timeframe: str = Field(..., description="Candle timeframe (e.g., 1m, 5m)")
    timestamp: datetime = Field(..., description="Candle open time")
    open: Decimal = Field(..., description="Open price")
    high: Decimal = Field(..., description="High price")
    low: Decimal = Field(..., description="Low price")
    close: Decimal = Field(..., description="Close price")
    volume: Decimal = Field(..., description="Volume in base currency")
    volume_quote: Decimal | None = Field(default=None, description="Volume in quote currency")
    trades: int | None = Field(default=None, description="Number of trades")
    is_closed: bool = Field(default=False, description="Whether the candle is closed")


class BinanceTrade(BaseModel):
    """Real-time trade data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    trade_id: str = Field(..., description="Trade ID")
    price: Decimal = Field(..., description="Trade price")
    size: Decimal = Field(..., description="Trade quantity")
    side: str = Field(..., description="Trade side (buy/sell)")
    timestamp: datetime = Field(..., description="Trade timestamp")
    buyer_is_maker: bool = Field(default=False, description="Was buyer the maker")


class BinanceOrderBookLevel(BaseModel):
    """Single level of order book."""

    price: Decimal = Field(..., description="Price level")
    size: Decimal = Field(..., description="Quantity at this price")


class BinanceOrderBook(BaseModel):
    """Real-time order book data from Binance WebSocket."""

    symbol: str = Field(..., description="Trading pair")
    bids: list[BinanceOrderBookLevel] = Field(default_factory=list, description="Bid levels")
    asks: list[BinanceOrderBookLevel] = Field(default_factory=list, description="Ask levels")
    last_update_id: int | None = Field(default=None, description="Last update ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BinanceOrderUpdate(BaseModel):
    """Real-time order status update from Binance WebSocket."""

    event_type: str = Field(default="executionReport", description="Event type")
    order_id: str = Field(..., description="Exchange order ID")
    client_order_id: str | None = Field(default=None, description="Client order ID")
    symbol: str = Field(..., description="Trading pair")
    side: str = Field(..., description="Order side (BUY/SELL)")
    order_type: str = Field(..., description="Order type (MARKET/LIMIT)")
    time_in_force: str | None = Field(default=None, description="Time in force")
    status: str = Field(..., description="Order status")
    price: Decimal | None = Field(default=None, description="Order price")
    quantity: Decimal = Field(..., description="Order quantity")
    filled_quantity: Decimal = Field(default=Decimal("0"), description="Filled quantity")
    cumulative_quote_qty: Decimal | None = Field(default=None, description="Cumulative quote quantity")
    last_filled_price: Decimal | None = Field(default=None, description="Last fill price")
    last_filled_qty: Decimal | None = Field(default=None, description="Last fill quantity")
    commission: Decimal | None = Field(default=None, description="Commission amount")
    commission_asset: str | None = Field(default=None, description="Commission asset")
    trade_id: int | None = Field(default=None, description="Trade ID")
    created_at: datetime | None = Field(default=None, description="Order creation time")
    updated_at: datetime | None = Field(default=None, description="Order update time")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BinanceBalanceUpdate(BaseModel):
    """Single asset balance update."""

    asset: str = Field(..., description="Asset symbol")
    free: Decimal = Field(..., description="Available balance")
    locked: Decimal = Field(default=Decimal("0"), description="Locked balance")


class BinanceAccountUpdate(BaseModel):
    """Real-time account balance update from Binance WebSocket."""

    event_type: str = Field(default="outboundAccountPosition", description="Event type")
    balances: list[BinanceBalanceUpdate] = Field(default_factory=list)
    last_update_time: int | None = Field(default=None, description="Last account update time")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BinanceWSMessage(BaseModel):
    """Unified WebSocket message wrapper for Redis pub/sub."""

    type: WSMessageType = Field(..., description="Message type")
    channel: str = Field(..., description="Channel name (e.g., ticker:BTCUSDT)")
    exchange: str = Field(default="binance", description="Exchange name")
    data: dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
