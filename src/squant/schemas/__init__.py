"""Pydantic schemas for request/response validation."""

from squant.schemas.exchange import (
    BalanceItem,
    BalanceResponse,
    CancelOrderRequest,
    CandlestickItem,
    CandlestickResponse,
    OpenOrdersResponse,
    OrderResponse,
    PlaceOrderRequest,
    TickerResponse,
)
from squant.schemas.order import (
    CreateOrderRequest,
    ListOrdersRequest,
    OrderDetail,
    OrderListData,
    OrderStatsResponse,
    OrderWithTrades,
    SyncOrdersResponse,
    TradeDetail,
)

__all__ = [
    # Exchange schemas
    "BalanceItem",
    "BalanceResponse",
    "CancelOrderRequest",
    "CandlestickItem",
    "CandlestickResponse",
    "OpenOrdersResponse",
    "OrderResponse",
    "PlaceOrderRequest",
    "TickerResponse",
    # Order management schemas
    "CreateOrderRequest",
    "ListOrdersRequest",
    "OrderDetail",
    "OrderListData",
    "OrderStatsResponse",
    "OrderWithTrades",
    "SyncOrdersResponse",
    "TradeDetail",
]
