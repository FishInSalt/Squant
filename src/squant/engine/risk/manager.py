"""Risk manager for live trading order validation.

Validates orders against configured risk rules before execution.
"""

from __future__ import annotations

import logging
import threading
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
        if initial_equity <= 0:
            raise ValueError(
                f"initial_equity must be positive, got {initial_equity}. "
                f"Risk percentage calculations require positive equity."
            )

        self.config = config
        self.state = RiskState()
        self._initial_equity = initial_equity
        self._current_equity = initial_equity
        self._lock = threading.RLock()

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
        with self._lock:
            self._current_equity = equity

    def check_total_loss_limit(self) -> bool:
        """Check if total loss limit has been breached (IMP-005).

        Called by the engine after updating equity and unrealized PnL on each bar.
        Unlike validate_order() which only runs on order submission, this runs
        every bar to detect when cumulative losses cross the threshold even without
        new orders.

        Returns:
            True if total loss limit is triggered (engine should stop).
        """
        with self._lock:
            if self.state.total_loss_limit_triggered:
                return True

            effective_total_pnl = self.state.total_pnl + self.state.unrealized_pnl

            if self._initial_equity > 0:
                loss_pct = -effective_total_pnl / self._initial_equity
                if loss_pct >= self.config.total_loss_limit:
                    self.state.total_loss_limit_triggered = True
                    logger.critical(
                        f"TOTAL LOSS LIMIT TRIGGERED: {loss_pct:.2%} loss "
                        f"(limit: {self.config.total_loss_limit:.2%})"
                    )
                    return True

            if self.config.total_loss_limit_absolute is not None:
                if -effective_total_pnl >= self.config.total_loss_limit_absolute:
                    self.state.total_loss_limit_triggered = True
                    logger.critical(
                        f"TOTAL LOSS LIMIT TRIGGERED: {-effective_total_pnl} loss "
                        f"(limit: {self.config.total_loss_limit_absolute})"
                    )
                    return True

            return False

    def update_position_value(self, position_value: Decimal) -> None:
        """Update current position value.

        Args:
            position_value: Total value of current positions.
        """
        with self._lock:
            self.state.current_position_value = position_value

    def update_unrealized_pnl(self, unrealized_pnl: Decimal) -> None:
        """Update current unrealized PnL for daily loss calculation.

        The daily loss check uses the *change* in unrealized PnL since the
        day started, not the absolute value.  This way, a position that was
        already underwater at day-open doesn't double-count.

        Args:
            unrealized_pnl: Total unrealized PnL across all positions.
        """
        with self._lock:
            self.state.unrealized_pnl = unrealized_pnl

    def record_order_fill(self) -> None:
        """Record that an order was filled (increments daily trade count).

        Called on every fill (market or limit, partial or full) to track
        order execution frequency. This is separate from record_trade_result()
        which tracks round-trip PnL on position close.
        """
        with self._lock:
            self.state.daily_trade_count += 1

    def record_trade_result(self, pnl: Decimal) -> None:
        """Record the result of a completed trade (position fully closed).

        Args:
            pnl: Profit/loss from the trade.
        """
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            return self._validate_order_unlocked(order, current_price, current_position_amount)

    def _validate_order_unlocked(
        self,
        order: OrderRequest,
        current_price: Decimal,
        current_position_amount: Decimal = Decimal("0"),
    ) -> RiskCheckResult:
        """Internal order validation (caller must hold self._lock)."""
        # Reject all orders if equity is zero or negative (safety check)
        if self._current_equity <= 0:
            logger.warning(
                f"Order rejected: current equity is {self._current_equity} "
                f"(zero or negative). All trading blocked."
            )
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.TOTAL_LOSS_LIMIT,
                reason=f"Cannot trade with zero or negative equity: {self._current_equity}",
                current_equity=float(self._current_equity),
            )

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
        if order.type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and order.price is not None:
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
        """Check daily loss limit including unrealized PnL.

        Effective daily PnL = realized daily PnL + change in unrealized PnL
        since day start. This prevents strategies from holding large underwater
        positions without triggering the daily loss limit.

        Returns:
            RiskCheckResult for daily loss limit check.
        """
        # Compute effective daily PnL: realized + unrealized change since day start
        unrealized_change = self.state.unrealized_pnl - self.state.daily_start_unrealized_pnl
        effective_daily_pnl = self.state.daily_pnl + unrealized_change

        # Check relative limit
        if self.state.daily_start_equity > 0:
            loss_pct = -effective_daily_pnl / self.state.daily_start_equity
            if loss_pct >= self.config.daily_loss_limit:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.DAILY_LOSS_LIMIT,
                    reason=f"Daily loss limit reached: {loss_pct:.2%} "
                    f"(limit: {self.config.daily_loss_limit:.2%})",
                    current_loss_pct=float(loss_pct),
                    limit_pct=float(self.config.daily_loss_limit),
                    daily_pnl=float(self.state.daily_pnl),
                    unrealized_change=float(unrealized_change),
                    effective_daily_pnl=float(effective_daily_pnl),
                )
        elif effective_daily_pnl < 0:
            # daily_start_equity is 0 but we have losses — block trading (RSK-1)
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.DAILY_LOSS_LIMIT,
                reason="Daily loss detected but daily_start_equity is 0 "
                "(cannot calculate loss percentage)",
                daily_pnl=float(self.state.daily_pnl),
                unrealized_change=float(unrealized_change),
            )

        # Check absolute limit if configured
        if self.config.daily_loss_limit_absolute is not None:
            if -effective_daily_pnl >= self.config.daily_loss_limit_absolute:
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.DAILY_LOSS_LIMIT,
                    reason=f"Daily loss limit reached: {-effective_daily_pnl} "
                    f"(limit: {self.config.daily_loss_limit_absolute})",
                    current_loss=float(-effective_daily_pnl),
                    limit=float(self.config.daily_loss_limit_absolute),
                )

        return RiskCheckResult.ok()

    def _check_total_loss_limit(self) -> RiskCheckResult:
        """Check total/cumulative loss limit (RSK-004).

        This check ensures the strategy stops when cumulative losses
        reach the configured threshold (e.g., 20% of initial equity).
        Includes unrealized PnL (mark-to-market) so holding a losing
        position without closing it cannot bypass the total loss limit.

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

        # Effective PnL = realized + unrealized (mark-to-market)
        effective_total_pnl = self.state.total_pnl + self.state.unrealized_pnl

        # Check relative limit against initial equity
        if self._initial_equity > 0:
            loss_pct = -effective_total_pnl / self._initial_equity
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
                    unrealized_pnl=float(self.state.unrealized_pnl),
                    initial_equity=float(self._initial_equity),
                )

        # Check absolute limit if configured
        if self.config.total_loss_limit_absolute is not None:
            if -effective_total_pnl >= self.config.total_loss_limit_absolute:
                self.state.total_loss_limit_triggered = True
                logger.critical(
                    f"TOTAL LOSS LIMIT TRIGGERED: {-effective_total_pnl} loss "
                    f"(limit: {self.config.total_loss_limit_absolute}). "
                    f"Strategy should be stopped."
                )
                return RiskCheckResult.reject(
                    rule_type=RiskRuleType.TOTAL_LOSS_LIMIT,
                    reason=f"Total loss limit reached: {-effective_total_pnl} "
                    f"(limit: {self.config.total_loss_limit_absolute}). Strategy stopped.",
                    current_loss=float(-effective_total_pnl),
                    limit=float(self.config.total_loss_limit_absolute),
                    total_pnl=float(self.state.total_pnl),
                    unrealized_pnl=float(self.state.unrealized_pnl),
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
        # Calculate order value: prefer limit price, then stop price, then market price
        price = order.price or getattr(order, "stop_price", None) or current_price
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
            if order_value >= self.config.max_order_value:
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
            if order_size_pct >= self.config.max_order_size:
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
        if order.side == OrderSide.BUY:
            new_position_amount = current_position_amount + order.amount
        else:
            new_position_amount = current_position_amount - order.amount

        # Check for negative position (spot trading - no short selling)
        if new_position_amount < 0:
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.MAX_POSITION_SIZE,
                reason=f"Sell order would result in negative position: {new_position_amount} "
                f"(current: {current_position_amount}, selling: {order.amount})",
                new_position_amount=float(new_position_amount),
                current_position=float(current_position_amount),
                sell_amount=float(order.amount),
            )

        # Sell orders only reduce exposure, so skip position limit checks.
        # The negative-position check above is the only constraint for sells.
        if order.side == OrderSide.SELL:
            return RiskCheckResult.ok()

        # Always use current_price for position value — reflects actual market
        # exposure, not order cost. A BUY LIMIT at $40k when market is $50k
        # produces a position worth $50k, not $40k.
        new_position_value = new_position_amount * current_price

        # Check absolute position value limit
        if self.config.max_position_value is not None:
            if new_position_value >= self.config.max_position_value:
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
            if position_size_pct >= self.config.max_position_size:
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
            return RiskCheckResult.reject(
                rule_type=RiskRuleType.PRICE_DEVIATION_LIMIT,
                reason="Cannot validate price deviation: current market price is zero or negative "
                "(possible data feed failure)",
                market_price=float(current_price),
            )

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

    def restore_state(self, state_dict: dict) -> None:
        """Restore risk state from a persisted summary dict.

        Restores cumulative fields (total_pnl, circuit breaker, etc.) so that
        risk limits survive session resume. Daily stats are restored if the
        persisted snapshot is from the same UTC day; otherwise they are reset.

        Args:
            state_dict: Dictionary from get_state_summary() (persisted in DB).
        """
        with self._lock:
            # Cumulative fields — always restore
            self.state.total_pnl = Decimal(str(state_dict.get("total_pnl", 0)))
            self.state.total_loss_limit_triggered = state_dict.get(
                "total_loss_limit_triggered", False
            )
            self.state.consecutive_losses = state_dict.get("consecutive_losses", 0)
            self.state.circuit_breaker_triggered = state_dict.get(
                "circuit_breaker_triggered", False
            )
            if state_dict.get("circuit_breaker_until"):
                self.state.circuit_breaker_until = datetime.fromisoformat(
                    state_dict["circuit_breaker_until"]
                )

            # Equity (use 'in' check — get() is falsy when equity is 0)
            if "current_equity" in state_dict and state_dict["current_equity"] is not None:
                self._current_equity = Decimal(str(state_dict["current_equity"]))

            # Unrealized PnL
            self.state.unrealized_pnl = Decimal(str(state_dict.get("unrealized_pnl", 0)))

            # Daily stats — restore if same UTC day, otherwise reset
            daily_reset_str = state_dict.get("daily_reset_time")
            same_day = False
            if daily_reset_str:
                saved_date = datetime.fromisoformat(daily_reset_str).date()
                if saved_date == datetime.now(UTC).date():
                    same_day = True

            if same_day:
                self.state.daily_trade_count = state_dict.get("daily_trade_count", 0)
                self.state.daily_pnl = Decimal(str(state_dict.get("daily_pnl", 0)))
                self.state.daily_start_equity = Decimal(
                    str(state_dict.get("daily_start_equity", self._current_equity))
                )
                self.state.daily_start_unrealized_pnl = Decimal(
                    str(state_dict.get("daily_start_unrealized_pnl", 0))
                )
                if daily_reset_str:
                    self.state.daily_reset_time = datetime.fromisoformat(daily_reset_str)
            else:
                self.state.reset_daily_stats(self._current_equity)

            logger.info(
                f"RiskManager state restored: total_pnl={self.state.total_pnl}, "
                f"circuit_breaker={self.state.circuit_breaker_triggered}, "
                f"same_day={same_day}"
            )

    def get_state_summary(self) -> dict:
        """Get a summary of current risk state.

        Returns:
            Dictionary with risk state information.
        """
        with self._lock:
            return self._get_state_summary_unlocked()

    def _get_state_summary_unlocked(self) -> dict:
        """Internal state summary (caller must hold self._lock)."""
        return {
            "daily_trade_count": self.state.daily_trade_count,
            "daily_trade_limit": self.config.daily_trade_limit,
            "daily_pnl": float(self.state.daily_pnl),
            "daily_loss_limit_pct": float(self.config.daily_loss_limit),
            "unrealized_pnl": float(self.state.unrealized_pnl),
            "daily_start_unrealized_pnl": float(self.state.daily_start_unrealized_pnl),
            "daily_start_equity": float(self.state.daily_start_equity),
            "daily_reset_time": (
                self.state.daily_reset_time.isoformat() if self.state.daily_reset_time else None
            ),
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
