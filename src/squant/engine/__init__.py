"""Strategy engine - execution and management."""

from squant.engine.sandbox import (
    CompiledStrategy,
    ValidationResult,
    compile_strategy,
    validate_strategy_code,
)
from squant.engine.backtest import (
    BacktestContext,
    BacktestError,
    BacktestResult,
    BacktestRunner,
    Bar,
    EquitySnapshot,
    Fill,
    MatchingEngine,
    OrderSide,
    OrderStatus,
    OrderType,
    PerformanceMetrics,
    Position,
    SimulatedOrder,
    Strategy,
    StrategyInstantiationError,
    TradeRecord,
    calculate_metrics,
    run_backtest,
)

__all__ = [
    # Sandbox
    "CompiledStrategy",
    "ValidationResult",
    "compile_strategy",
    "validate_strategy_code",
    # Backtest types
    "Bar",
    "Position",
    "SimulatedOrder",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "Fill",
    "TradeRecord",
    "EquitySnapshot",
    "BacktestResult",
    # Backtest components
    "Strategy",
    "BacktestContext",
    "MatchingEngine",
    "PerformanceMetrics",
    "calculate_metrics",
    "BacktestRunner",
    "BacktestError",
    "StrategyInstantiationError",
    "run_backtest",
]
