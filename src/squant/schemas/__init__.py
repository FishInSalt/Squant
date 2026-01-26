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
from squant.schemas.risk import (
    CreateRiskRuleRequest,
    RiskRuleListItem,
    RiskRuleResponse,
    ToggleRiskRuleRequest,
    UpdateRiskRuleRequest,
)
from squant.schemas.strategy import (
    CreateStrategyRequest,
    StrategyListItem,
    StrategyResponse,
    UpdateStrategyRequest,
    ValidateCodeRequest,
    ValidationResultResponse,
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
    # Strategy schemas
    "CreateStrategyRequest",
    "UpdateStrategyRequest",
    "ValidateCodeRequest",
    "ValidationResultResponse",
    "StrategyResponse",
    "StrategyListItem",
    # Risk schemas
    "CreateRiskRuleRequest",
    "UpdateRiskRuleRequest",
    "ToggleRiskRuleRequest",
    "RiskRuleResponse",
    "RiskRuleListItem",
]
