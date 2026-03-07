"""Risk management models and configuration.

Defines risk rules, configurations, and check results for live trading.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RiskRuleType(str, Enum):
    """Types of risk rules."""

    MAX_POSITION_SIZE = "max_position_size"  # RSK-001
    MAX_ORDER_SIZE = "max_order_size"  # RSK-002
    DAILY_TRADE_LIMIT = "daily_trade_limit"  # RSK-003
    DAILY_LOSS_LIMIT = "daily_loss_limit"  # RSK-003 (daily)
    TOTAL_LOSS_LIMIT = "total_loss_limit"  # RSK-004 (cumulative)
    PRICE_DEVIATION_LIMIT = "price_deviation_limit"  # RSK-005
    CIRCUIT_BREAKER = "circuit_breaker"  # RSK-006


class RiskAction(str, Enum):
    """Actions to take when a risk rule is triggered."""

    REJECT = "reject"  # Reject the order
    WARN = "warn"  # Allow but log warning
    REDUCE = "reduce"  # Reduce order size to comply


class RiskRule(BaseModel):
    """A single risk management rule.

    Attributes:
        rule_type: Type of risk check.
        enabled: Whether the rule is active.
        action: Action to take when triggered.
        params: Rule-specific parameters.
    """

    rule_type: RiskRuleType
    enabled: bool = True
    action: RiskAction = RiskAction.REJECT
    params: dict[str, Any] = Field(default_factory=dict)


class RiskConfig(BaseModel):
    """Risk management configuration for live trading.

    Contains all risk limits and rules for a trading session.
    Sensible defaults are provided for safety.
    """

    # Position limits (RSK-001)
    max_position_size: Decimal = Field(
        default=Decimal("0.1"),
        description="Maximum position size as fraction of account equity (0.1 = 10%)",
    )
    max_position_value: Decimal | None = Field(
        default=None,
        description="Maximum position value in quote currency (absolute limit)",
    )

    # Order limits (RSK-002)
    max_order_size: Decimal = Field(
        default=Decimal("0.05"),
        description="Maximum single order size as fraction of account equity (0.05 = 5%)",
    )
    max_order_value: Decimal | None = Field(
        default=None,
        description="Maximum single order value in quote currency (absolute limit)",
    )
    min_order_value: Decimal = Field(
        default=Decimal("10"),
        description="Minimum order value in quote currency",
    )

    # Daily limits (RSK-003)
    daily_trade_limit: int = Field(
        default=100,
        description="Maximum number of trades per day",
    )
    daily_loss_limit: Decimal = Field(
        default=Decimal("0.05"),
        description="Maximum daily loss as fraction of initial equity (0.05 = 5%)",
    )
    daily_loss_limit_absolute: Decimal | None = Field(
        default=None,
        description="Maximum daily loss in quote currency (absolute limit)",
    )

    # Total/cumulative loss limits (RSK-004)
    total_loss_limit: Decimal = Field(
        default=Decimal("0.20"),
        description="Maximum total/cumulative loss as fraction of initial equity (0.20 = 20%)",
    )
    total_loss_limit_absolute: Decimal | None = Field(
        default=None,
        description="Maximum total loss in quote currency (absolute limit)",
    )

    # Price limits (RSK-005)
    max_price_deviation: Decimal = Field(
        default=Decimal("0.02"),
        description="Maximum allowed price deviation from last price (0.02 = 2%)",
    )

    # Circuit breaker (RSK-006)
    circuit_breaker_enabled: bool = Field(
        default=True,
        description="Enable circuit breaker on consecutive losses",
    )
    circuit_breaker_loss_count: int = Field(
        default=5,
        ge=1,
        description="Number of consecutive losses to trigger circuit breaker",
    )
    circuit_breaker_cooldown_minutes: int = Field(
        default=30,
        description="Cooldown period in minutes after circuit breaker triggers",
    )

    # General settings
    require_confirmation: bool = Field(
        default=False,
        description="Require manual confirmation for large orders",
    )
    confirmation_threshold: Decimal = Field(
        default=Decimal("0.03"),
        description="Order size threshold for confirmation (fraction of equity)",
    )


class RiskCheckResult(BaseModel):
    """Result of a risk check on an order.

    Attributes:
        passed: Whether the order passed all risk checks.
        action: Recommended action if check failed.
        rule_type: The rule that failed (if any).
        reason: Human-readable explanation.
        adjusted_amount: Adjusted order amount if action is REDUCE.
        metadata: Additional context for the check result.
    """

    passed: bool
    action: RiskAction | None = None
    rule_type: RiskRuleType | None = None
    reason: str | None = None
    adjusted_amount: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls) -> "RiskCheckResult":
        """Create a passing result."""
        return cls(passed=True)

    @classmethod
    def reject(
        cls,
        rule_type: RiskRuleType,
        reason: str,
        **metadata: Any,
    ) -> "RiskCheckResult":
        """Create a rejection result."""
        return cls(
            passed=False,
            action=RiskAction.REJECT,
            rule_type=rule_type,
            reason=reason,
            metadata=metadata,
        )

    @classmethod
    def warn(
        cls,
        rule_type: RiskRuleType,
        reason: str,
        **metadata: Any,
    ) -> "RiskCheckResult":
        """Create a warning result (order allowed)."""
        return cls(
            passed=True,
            action=RiskAction.WARN,
            rule_type=rule_type,
            reason=reason,
            metadata=metadata,
        )

    @classmethod
    def reduce(
        cls,
        rule_type: RiskRuleType,
        reason: str,
        adjusted_amount: Decimal,
        **metadata: Any,
    ) -> "RiskCheckResult":
        """Create a reduce result with adjusted amount."""
        return cls(
            passed=True,
            action=RiskAction.REDUCE,
            rule_type=rule_type,
            reason=reason,
            adjusted_amount=adjusted_amount,
            metadata=metadata,
        )


class RiskState(BaseModel):
    """Current risk state tracking for a trading session.

    Tracks daily statistics and state needed for risk checks.
    """

    # Daily tracking
    daily_trade_count: int = 0
    daily_pnl: Decimal = Decimal("0")
    daily_start_equity: Decimal = Decimal("0")
    daily_reset_time: datetime | None = None

    # Total/cumulative tracking (RSK-004)
    total_pnl: Decimal = Decimal("0")
    total_loss_limit_triggered: bool = False

    # Consecutive loss tracking (circuit breaker)
    consecutive_losses: int = 0
    circuit_breaker_triggered: bool = False
    circuit_breaker_until: datetime | None = None

    # Position tracking
    current_position_value: Decimal = Decimal("0")

    # Unrealized PnL tracking for daily loss calculation
    unrealized_pnl: Decimal = Decimal("0")
    daily_start_unrealized_pnl: Decimal = Decimal("0")

    def reset_daily_stats(self, equity: Decimal) -> None:
        """Reset daily statistics.

        Args:
            equity: Current equity to set as daily start.
        """
        if equity <= 0:
            logger.warning(
                f"reset_daily_stats called with non-positive equity={equity}. "
                f"Daily loss percentage checks will be disabled."
            )
        self.daily_trade_count = 0
        self.daily_pnl = Decimal("0")
        self.daily_start_equity = equity
        self.daily_start_unrealized_pnl = self.unrealized_pnl
        self.daily_reset_time = datetime.now(UTC)

    def record_trade(self, pnl: Decimal) -> None:
        """Record a completed trade (position fully closed).

        Note: daily_trade_count is NOT incremented here — it is incremented
        by RiskManager.record_order_fill() on each fill, not on position close.

        Args:
            pnl: Profit/loss from the trade.
        """
        self.daily_pnl += pnl
        self.total_pnl += pnl  # Track cumulative PnL (RSK-004)

        # Track consecutive losses
        # Zero PnL (break-even) should not affect the counter
        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0

    def trigger_circuit_breaker(self, cooldown_minutes: int) -> None:
        """Trigger the circuit breaker.

        Args:
            cooldown_minutes: Duration of cooldown period.
        """
        self.circuit_breaker_triggered = True
        self.circuit_breaker_until = datetime.now(UTC) + timedelta(minutes=cooldown_minutes)

    def check_circuit_breaker_expired(self) -> bool:
        """Check if circuit breaker cooldown has expired.

        Returns:
            True if expired, False otherwise.
        """
        if not self.circuit_breaker_triggered:
            return True
        if self.circuit_breaker_until is None:
            return True
        # Make comparison timezone-aware
        now = datetime.now(UTC)
        breaker_time = self.circuit_breaker_until
        if breaker_time.tzinfo is None:
            breaker_time = breaker_time.replace(tzinfo=UTC)
        if now >= breaker_time:
            self.circuit_breaker_triggered = False
            self.circuit_breaker_until = None
            self.consecutive_losses = 0
            return True
        return False
