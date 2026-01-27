"""Service layer - business logic."""

from squant.services.order import (
    OrderNotFoundError,
    OrderRepository,
    OrderService,
    OrderValidationError,
    TradeRepository,
)
from squant.services.risk import (
    RiskRuleNotFoundError,
    RiskRuleRepository,
    RiskRuleService,
)
from squant.services.strategy import (
    StrategyNameExistsError,
    StrategyNotFoundError,
    StrategyRepository,
    StrategyService,
    StrategyValidationError,
)
from squant.services.backtest import (
    BacktestNotFoundError,
    BacktestService,
    InsufficientDataError,
    StrategyRunRepository,
)
from squant.services.data_loader import (
    DataAvailability,
    DataLoader,
)
from squant.services.live_trading import (
    ExchangeConnectionError,
    LiveTradingError,
    LiveTradingService,
    RiskConfigurationError,
    SessionAlreadyRunningError,
    SessionNotFoundError as LiveSessionNotFoundError,
    StrategyInstantiationError as LiveStrategyInstantiationError,
)

__all__ = [
    # Order services
    "OrderService",
    "OrderRepository",
    "TradeRepository",
    "OrderNotFoundError",
    "OrderValidationError",
    # Strategy services
    "StrategyService",
    "StrategyRepository",
    "StrategyNotFoundError",
    "StrategyNameExistsError",
    "StrategyValidationError",
    # Backtest services
    "BacktestService",
    "StrategyRunRepository",
    "BacktestNotFoundError",
    "InsufficientDataError",
    # Data loader
    "DataLoader",
    "DataAvailability",
    # Risk services
    "RiskRuleService",
    "RiskRuleRepository",
    "RiskRuleNotFoundError",
    # Live trading services
    "LiveTradingService",
    "LiveTradingError",
    "ExchangeConnectionError",
    "RiskConfigurationError",
    "SessionAlreadyRunningError",
    "LiveSessionNotFoundError",
    "LiveStrategyInstantiationError",
]
