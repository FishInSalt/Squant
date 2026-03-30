"""Exchange adapters for different cryptocurrency exchanges."""

from .base import ExchangeAdapter
from .exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
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
]
