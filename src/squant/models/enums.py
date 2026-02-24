"""Database enum types."""

import enum


class RunMode(str, enum.Enum):
    """Strategy run mode."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class RunStatus(str, enum.Enum):
    """Strategy run status."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    CANCELLED = "cancelled"  # TRD-008#3: User cancelled the run
    ERROR = "error"
    INTERRUPTED = "interrupted"  # Infrastructure interruption (restart, health timeout)
    COMPLETED = "completed"


class OrderSide(str, enum.Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, enum.Enum):
    """Order status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class RiskRuleType(str, enum.Enum):
    """Risk rule type."""

    ORDER_LIMIT = "order_limit"
    POSITION_LIMIT = "position_limit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    TOTAL_LOSS_LIMIT = "total_loss_limit"
    FREQUENCY_LIMIT = "frequency_limit"
    VOLATILITY_BREAK = "volatility_break"


class LogLevel(str, enum.Enum):
    """Log level."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StrategyStatus(str, enum.Enum):
    """Strategy status."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class CircuitBreakerTriggerType(str, enum.Enum):
    """Circuit breaker trigger type."""

    MANUAL = "manual"  # Manual trigger via API
    AUTO = "auto"  # Automatic trigger by risk rules
