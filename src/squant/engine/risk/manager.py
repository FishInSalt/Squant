"""Risk manager for live trading order validation.

Validates orders against configured risk rules before execution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from squant.engine.risk.models import (
    RiskCheckResult,
    RiskConfig,
    RiskRuleType,
    RiskState,
)
from squant.models.enums import OrderSide, OrderType

if TYPE_CHECKING:
    from squant.infra.exchange.types import OrderRequest

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages risk checks for live trading orders.

    Validates orders against configured risk limits and tracks
    risk state (daily statistics, circuit breaker, etc.).

    Attributes:
        config: Risk configuration settings.
        state: Current risk state tracking.
    """

    def __init__(
        self,
        config: RiskConfig,
        initial_equity: Decimal,
    ) -> None:
        """Initialize risk manager.

        Args:
            config: Risk configuration.
            initial_equity: Initial account equity for relative calculations.
        """
        self.config = config
        self.state = RiskState()
        self._initial_equity = initial_equity
        self._current_equity = initial_equity

        # Initialize daily stats
        self.state.reset_daily_stats(initial_equity)

        logger.info(
            f"RiskManager initialized with equity={initial_equity}, "
            f"max_position={config.max_position_size}, "
            f"max_order={config.max_order_size}, "
            f"daily_loss_limit={config.daily_loss_limit}, "
            f"total_loss_limit={config.total_loss_limit}"
        )

    def update_equity(self, equity: Decimal) -> None:
        """Update current equity value.

        Args:
            equity: Current account equity.
        """
        self._current_equity = equity

    def update_position_value(self, position_value: Decimal) -> None:
        """Update current position value.

        Args:
            position_value: Total value of current positions.
        """
        self.state.current_position_value = position_value

    def record_trade_result(self, pnl: Decimal) -> None:
        """Record the result of a completed trade.

        Args:
            pnl: Profit/loss from the trade.
        """
        self.state.record_trade(pnl)

        # Check if circuit breaker should trigger
        if (
            self.config.circuit_breaker_enabled
            and self.state.consecutive_losses >= self.config.circuit_breaker_loss_count
            and not self.state.circuit_breaker_triggered
        ):
            logger.warning(
                f"Circuit breaker triggered after {self.state.consecutive_losses} "
                f"consecutive losses. Cooldown: {self.config.circuit_breaker_cooldown_minutes} minutes."
            )
            self.state.trigger_circuit_breaker(self.config.circuit_breaker_cooldown_minutes)

    def check_daily_reset(self) -> None:
        """Check if daily stats should be reset (new trading day).

        Resets daily counters if we've moved to a new UTC day.
        """
        now = datetime.now(UTC)
        if self.state.daily_reset_time is None:
            self.state.reset_daily_stats(self._current_equity)
            return

        # Reset if new day
        reset_date = self.state.daily_reset_time.date()
        if now.date() > reset_date:
            logger.info("New trading day detected, resetting daily risk stats")
            self.state.reset_daily_stats(self._current_equity)

    def validate_order(
        self,
        order: OrderRequest,
        current_price: Decimal,
        current_position_amount: Decimal = Decimal("0"),
    ) -> RiskCheckResult:
        """Validate an order against all risk rules.

        Args:
            order: Order request to validate.
            current_price: Current market price.
            current_position_amount: Current position amount in the symbol.

        Returns:
            RiskCheckResult with validation outcome.
        """
        # Check daily reset first
        self.check_daily_reset()

        # Check circuit breaker (RSK-006)
        result = self._check_circuit_breaker()
        if not result.passed:
            return result

        # Check daily trade limit (RSK-003)
        result = self._check_daily_trade_limit()
        if not result.passed:
            return result

        # Check daily loss limit (RSK-003)
        result = self._check_daily_loss_limit()
        if not result.passed:
            return result

        # Check total/cumulative loss limit (RSK-004)
        result = self._check_total_loss_limit()
        if not result.passed:
            return result

        # Check order size limits (RSK-002)
        result = self._check_order_size(order, current_price)
        if not result.passed:
            return result

        # Check position size limits (RSK-001)
        result = self._check_position_size(order, current_price, current_position_amount)
        if not result.passed:
            return result

        # Check price deviation (RSK-005)
        if order.type == OrderType.LIMIT and order.price is not None:
            result = self._check_price_deviation(order.price, current_price, order.side)
            if not result.passed:
                return result

        logger.debug(
            f"Order passed all risk checks: {order.symbol} {order.side.value} {order.amount}"
        )
        return RiskCheckResult.ok()

    def _check_circuit_breaker(self) -> RiskCheckResult:
        """Check if circuit breaker is active.

        Returns:
            RiskCheckResult for circuit breaker check.
        """
        if not self.config.circuit_breaker_enabled:
            return RiskCheckResult.ok()

        if not self.state.check_circuit_breaker_expired():
            remaining = None
            if self.state.circuit_breaker_until:
                breaker_time = self.state.circuit_breaker_until
                if breaker_time.tzinfo is None:
                    breaker_time = breaker_time.replace(tzinfo=UTC)
                remaining = (breaker_time - datetime.now(UTC)).total_seconds() / 60

            return RiskCheckResult.reject(
                rule_type=RiskRuleType.CIRCUIT_BREAKER,
                reason=f"Circuit breaker active. Trading paused for "
                f"{remaining:.1f} minutes due to {self.state.consecutive_losses} consecutive losses.",
                consecutive_losses=self.state.consecutive_losses,
                cooldown_remaining_minutes=remaining,
            )

        return RiskCheckResult.ok()

    def _check_daily_trade_limit(self) -> RiskCheckResult:
        """Check daily trade count limit.

        Returns:
            RiskCheckResult for daily trade limit check.
        """
        if self.state.daily_trade_count >= self.config.daily_trade_limit:
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.DAILY_TRADE_LIMIT,
                reason=f"Daily trade limit reached: {self.state.daily_trade_count}/{self.config.daily_trade_limit}",
                current_count=self.state.daily_trade_count,
                limit=self.config.daily_trade_limit,
            )

        return RiskCheckResult.ok()

    def _check_daily_loss_limit(self) -> RiskCheckResult:
        """Check daily loss limit.

        Returns:
            RiskCheckResult for daily loss limit check.
        """
        # Check relative limit
        if self.state.daily_start_equity > 0:
            loss_pct = -self.state.daily_pnl / self.state.daily_start_equity
            if loss_pct >= self.config.daily_loss_limit:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.DAILY_LOSS_LIMIT,
                    reason=f"Daily loss limit reached: {loss_pct:.2%} "
                    f"(limit: {self.config.daily_loss_limit:.2%})",
                    current_loss_pct=float(loss_pct),
                    limit_pct=float(self.config.daily_loss_limit),
                    daily_pnl=float(self.state.daily_pnl),
                )

        # Check absolute limit if configured
        if self.config.daily_loss_limit_absolute is not None:
            if -self.state.daily_pnl >= self.config.daily_loss_limit_absolute:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.DAILY_LOSS_LIMIT,
                    reason=f"Daily loss limit reached: {-self.state.daily_pnl} "
                    f"(limit: {self.config.daily_loss_limit_absolute})",
                    current_loss=float(-self.state.daily_pnl),
                    limit=float(self.config.daily_loss_limit_absolute),
                )

        return RiskCheckResult.ok()

    def _check_total_loss_limit(self) -> RiskCheckResult:
        """Check total/cumulative loss limit (RSK-004).

        This check ensures the strategy stops when cumulative losses
        reach the configured threshold (e.g., 20% of initial equity).

        Returns:
            RiskCheckResult for total loss limit check.
        """
        # If already triggered, reject all orders
        if self.state.total_loss_limit_triggered:
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.TOTAL_LOSS_LIMIT,
                reason="Total loss limit already triggered. Strategy must be reset.",
                total_pnl=float(self.state.total_pnl),
            )

        # Check relative limit against initial equity
        if self._initial_equity > 0:
            loss_pct = -self.state.total_pnl / self._initial_equity
            if loss_pct >= self.config.total_loss_limit:
                self.state.total_loss_limit_triggered = True
                logger.critical(
                    f"TOTAL LOSS LIMIT TRIGGERED: {loss_pct:.2%} loss "
                    f"(limit: {self.config.total_loss_limit:.2%}). "
                    f"Strategy should be stopped."
                )
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.TOTAL_LOSS_LIMIT,
                    reason=f"Total loss limit reached: {loss_pct:.2%} "
                    f"(limit: {self.config.total_loss_limit:.2%}). Strategy stopped.",
                    current_loss_pct=float(loss_pct),
                    limit_pct=float(self.config.total_loss_limit),
                    total_pnl=float(self.state.total_pnl),
                    initial_equity=float(self._initial_equity),
                )

        # Check absolute limit if configured
        if self.config.total_loss_limit_absolute is not None:
            if -self.state.total_pnl >= self.config.total_loss_limit_absolute:
                self.state.total_loss_limit_triggered = True
                logger.critical(
                    f"TOTAL LOSS LIMIT TRIGGERED: {-self.state.total_pnl} loss "
                    f"(limit: {self.config.total_loss_limit_absolute}). "
                    f"Strategy should be stopped."
                )
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.TOTAL_LOSS_LIMIT,
                    reason=f"Total loss limit reached: {-self.state.total_pnl} "
                    f"(limit: {self.config.total_loss_limit_absolute}). Strategy stopped.",
                    current_loss=float(-self.state.total_pnl),
                    limit=float(self.config.total_loss_limit_absolute),
                    total_pnl=float(self.state.total_pnl),
                )

        return RiskCheckResult.ok()

    def _check_order_size(
        self,
        order: OrderRequest,
        current_price: Decimal,
    ) -> RiskCheckResult:
        """Check order size limits.

        Args:
            order: Order request.
            current_price: Current market price.

        Returns:
            RiskCheckResult for order size check.
        """
        # Calculate order value
        price = order.price if order.price else current_price
        order_value = order.amount * price

        # Check minimum order value
        if order_value < self.config.min_order_value:
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.MAX_ORDER_SIZE,
                reason=f"Order value too small: {order_value} "
                f"(minimum: {self.config.min_order_value})",
                order_value=float(order_value),
                min_value=float(self.config.min_order_value),
            )

        # Check absolute order value limit
        if self.config.max_order_value is not None:
            if order_value > self.config.max_order_value:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.MAX_ORDER_SIZE,
                    reason=f"Order value exceeds limit: {order_value} "
                    f"(max: {self.config.max_order_value})",
                    order_value=float(order_value),
                    max_value=float(self.config.max_order_value),
                )

        # Check relative order size (fraction of equity)
        if self._current_equity > 0:
            order_size_pct = order_value / self._current_equity
            if order_size_pct > self.config.max_order_size:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.MAX_ORDER_SIZE,
                    reason=f"Order size exceeds limit: {order_size_pct:.2%} of equity "
                    f"(max: {self.config.max_order_size:.2%})",
                    order_size_pct=float(order_size_pct),
                    max_size_pct=float(self.config.max_order_size),
                )

        return RiskCheckResult.ok()

    def _check_position_size(
        self,
        order: OrderRequest,
        current_price: Decimal,
        current_position_amount: Decimal,
    ) -> RiskCheckResult:
        """Check position size limits.

        Args:
            order: Order request.
            current_price: Current market price.
            current_position_amount: Current position amount.

        Returns:
            RiskCheckResult for position size check.
        """
        # Calculate new position after order
        price = order.price if order.price else current_price

        if order.side == OrderSide.BUY:
            new_position_amount = current_position_amount + order.amount
        else:
            new_position_amount = current_position_amount - order.amount

        new_position_value = abs(new_position_amount) * price

        # Check absolute position value limit
        if self.config.max_position_value is not None:
            if new_position_value > self.config.max_position_value:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.MAX_POSITION_SIZE,
                    reason=f"Position value would exceed limit: {new_position_value} "
                    f"(max: {self.config.max_position_value})",
                    new_position_value=float(new_position_value),
                    max_value=float(self.config.max_position_value),
                )

        # Check relative position size (fraction of equity)
        if self._current_equity > 0:
            position_size_pct = new_position_value / self._current_equity
            if position_size_pct > self.config.max_position_size:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.MAX_POSITION_SIZE,
                    reason=f"Position size would exceed limit: {position_size_pct:.2%} of equity "
                    f"(max: {self.config.max_position_size:.2%})",
                    position_size_pct=float(position_size_pct),
                    max_size_pct=float(self.config.max_position_size),
                )

        return RiskCheckResult.ok()

    def _check_price_deviation(
        self,
        order_price: Decimal,
        current_price: Decimal,
        side: OrderSide,
    ) -> RiskCheckResult:
        """Check price deviation from market price.

        Args:
            order_price: Limit order price.
            current_price: Current market price.
            side: Order side.

        Returns:
            RiskCheckResult for price deviation check.
        """
        if current_price <= 0:
            return RiskCheckResult.ok()

        deviation = abs(order_price - current_price) / current_price

        if deviation > self.config.max_price_deviation:
            # Determine if the deviation is in a "bad" direction
            # For buys: paying more than market is bad
            # For sells: selling less than market is bad
            is_adverse = (side == OrderSide.BUY and order_price > current_price) or (
                side == OrderSide.SELL and order_price < current_price
            )

            if is_adverse:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.PRICE_DEVIATION_LIMIT,
                    reason=f"Order price deviates {deviation:.2%} from market price "
                    f"(max: {self.config.max_price_deviation:.2%}). "
                    f"Order: {order_price}, Market: {current_price}",
                    deviation=float(deviation),
                    max_deviation=float(self.config.max_price_deviation),
                    order_price=float(order_price),
                    market_price=float(current_price),
                )

        return RiskCheckResult.ok()

    def get_state_summary(self) -> dict:
        """Get a summary of current risk state.

        Returns:
            Dictionary with risk state information.
        """
        return {
            "daily_trade_count": self.state.daily_trade_count,
            "daily_trade_limit": self.config.daily_trade_limit,
            "daily_pnl": float(self.state.daily_pnl),
            "daily_loss_limit_pct": float(self.config.daily_loss_limit),
            "total_pnl": float(self.state.total_pnl),
            "total_loss_limit_pct": float(self.config.total_loss_limit),
            "total_loss_limit_triggered": self.state.total_loss_limit_triggered,
            "current_equity": float(self._current_equity),
            "initial_equity": float(self._initial_equity),
            "consecutive_losses": self.state.consecutive_losses,
            "circuit_breaker_triggered": self.state.circuit_breaker_triggered,
            "circuit_breaker_until": (
                self.state.circuit_breaker_until.isoformat()
                if self.state.circuit_breaker_until
                else None
            ),
            "current_position_value": float(self.state.current_position_value),
            "max_position_size_pct": float(self.config.max_position_size),
            "max_order_size_pct": float(self.config.max_order_size),
        }
