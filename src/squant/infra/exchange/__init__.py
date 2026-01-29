"""Exchange adapters for different cryptocurrency exchanges."""

from .base import ExchangeAdapter
from .binance import BinanceAdapter
from .exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from .okx import OKXAdapter
from .types import (
    AccountBalance,
    Balance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
)

__all__ = [
    # Base
    "ExchangeAdapter",
    # Exceptions
    "ExchangeError",
    "ExchangeConnectionError",
    "ExchangeAuthenticationError",
    "ExchangeRateLimitError",
    "ExchangeAPIError",
    "OrderNotFoundError",
    "InvalidOrderError",
    # Types
    "Balance",
    "AccountBalance",
    "Ticker",
    "Candlestick",
    "OrderRequest",
    "OrderResponse",
    "CancelOrderRequest",
    "TimeFrame",
    # Adapters
    "BinanceAdapter",
    "OKXAdapter",
]
