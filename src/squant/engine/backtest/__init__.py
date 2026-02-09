"""Backtest engine module.

Provides components for running strategy backtests on historical data.
"""

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.matching import MatchingEngine
from squant.engine.backtest.metrics import PerformanceMetrics, calculate_metrics
from squant.engine.backtest.runner import (
    BacktestError,
    BacktestRunner,
    StrategyInstantiationError,
    run_backtest,
)
from squant.engine.backtest.strategy_base import Strategy
from squant.engine.backtest.types import (
    BacktestResult,
    Bar,
    EquitySnapshot,
    Fill,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    SimulatedOrder,
    TradeRecord,
)

__all__ = [
    # Types
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
    # Strategy
    "Strategy",
    # Context
    "BacktestContext",
    # Matching
    "MatchingEngine",
    # Metrics
    "PerformanceMetrics",
    "calculate_metrics",
    # Runner
    "BacktestRunner",
    "BacktestError",
    "StrategyInstantiationError",
    "run_backtest",
]
