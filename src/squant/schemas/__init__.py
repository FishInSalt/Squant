"""Pydantic schemas for request/response validation."""

from squant.schemas.account import (
    ConnectionTestResponse,
    CreateExchangeAccountRequest,
    ExchangeAccountListItem,
    ExchangeAccountResponse,
    UpdateExchangeAccountRequest,
)
from squant.schemas.backtest import (
    AvailableSymbolResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestMetrics,
    BacktestRunResponse,
    CheckDataRequest,
    CreateBacktestRequest,
    DataAvailabilityResponse,
    EquityCurvePoint,
    RunBacktestRequest,
    TradeRecordResponse,
)
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
    # Exchange account schemas
    "CreateExchangeAccountRequest",
    "UpdateExchangeAccountRequest",
    "ExchangeAccountResponse",
    "ExchangeAccountListItem",
    "ConnectionTestResponse",
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
    # Backtest schemas
    "RunBacktestRequest",
    "CreateBacktestRequest",
    "CheckDataRequest",
    "BacktestRunResponse",
    "BacktestListItem",
    "BacktestDetailResponse",
    "BacktestMetrics",
    "EquityCurvePoint",
    "TradeRecordResponse",
    "DataAvailabilityResponse",
    "AvailableSymbolResponse",
]
