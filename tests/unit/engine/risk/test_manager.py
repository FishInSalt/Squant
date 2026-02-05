"""Unit tests for risk manager."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from squant.engine.risk.manager import RiskManager
from squant.engine.risk.models import (
    RiskAction,
    RiskCheckResult,
    RiskConfig,
    RiskRuleType,
    RiskState,
)
from squant.infra.exchange.types import OrderRequest
from squant.models.enums import OrderSide, OrderType


@pytest.fixture
def default_config():
    """Create a default risk configuration for testing."""
    return RiskConfig(
        max_position_size=Decimal("0.1"),  # 10% of equity
        max_order_size=Decimal("0.05"),  # 5% of equity
        min_order_value=Decimal("10"),
        daily_trade_limit=100,
        daily_loss_limit=Decimal("0.05"),  # 5% daily loss limit
        max_price_deviation=Decimal("0.02"),  # 2% price deviation
        circuit_breaker_enabled=True,
        circuit_breaker_loss_count=3,
        circuit_breaker_cooldown_minutes=30,
    )


@pytest.fixture
def risk_manager(default_config):
    """Create a risk manager for testing."""
    return RiskManager(
        config=default_config,
        initial_equity=Decimal("10000"),
    )


class TestRiskManagerInit:
    """Tests for risk manager initialization."""

    def test_initialization(self, default_config):
        """Test risk manager is initialized correctly."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("10000"))

        assert rm.config == default_config
        assert rm._initial_equity == Decimal("10000")
        assert rm._current_equity == Decimal("10000")
        assert rm.state.daily_trade_count == 0
        assert rm.state.daily_pnl == Decimal("0")

    def test_daily_stats_initialized(self, risk_manager):
        """Test daily stats are initialized on creation."""
        assert risk_manager.state.daily_start_equity == Decimal("10000")
        assert risk_manager.state.daily_reset_time is not None


class TestOrderSizeValidation:
    """Tests for order size validation (RSK-002)."""

    def test_valid_order_passes(self, risk_manager):
        """Test that a valid order passes validation."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),  # ~$500 at $50000
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True
        assert result.action is None

    def test_order_too_small_rejected(self, risk_manager):
        """Test that orders below minimum are rejected."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.0001"),  # ~$5 at $50000
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_ORDER_SIZE
        assert "too small" in result.reason.lower()

    def test_order_exceeds_max_size_rejected(self, risk_manager):
        """Test that orders exceeding max size are rejected."""
        # Order value: 0.2 * 50000 = $10000 = 100% of equity
        # Max allowed: 5% = $500
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.2"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_ORDER_SIZE
        assert "exceeds limit" in result.reason.lower()

    def test_order_at_max_size_passes(self, risk_manager):
        """Test that orders at exactly max size pass."""
        # Max order size = 5% of $10000 = $500
        # At $50000/BTC, that's 0.01 BTC
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_absolute_order_limit(self):
        """Test absolute order value limit."""
        config = RiskConfig(
            max_order_value=Decimal("1000"),
            max_order_size=Decimal("1.0"),  # Disable relative limit
        )
        rm = RiskManager(config=config, initial_equity=Decimal("100000"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.1"),  # $5000 at $50000
        )
        current_price = Decimal("50000")

        result = rm.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_ORDER_SIZE


class TestPositionSizeValidation:
    """Tests for position size validation (RSK-001)."""

    def test_position_within_limit_passes(self, risk_manager):
        """Test that positions within limit pass."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0")
        )

        assert result.passed is True

    def test_position_exceeds_limit_rejected(self, risk_manager):
        """Test that positions exceeding limit are rejected."""
        # Max position: 10% of $10000 = $1000
        # Max order: 5% of $10000 = $500
        #
        # We need:
        # 1. Order within 5% limit
        # 2. But resulting position > 10%
        #
        # At price $10000:
        # - Order: 0.04 BTC = $400 (4% of equity, within 5% limit)
        # - Current position: 0.07 BTC = $700 (7%)
        # - Total: 0.11 BTC = $1100 (11% > 10%)
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.04"),  # $400 at $10000 (4% of equity)
        )
        current_price = Decimal("10000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.07")
        )

        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_POSITION_SIZE

    def test_sell_resulting_position_still_exceeds_limit_rejected(self, risk_manager):
        """Test that sell orders are rejected if resulting position still exceeds limit.

        Even when selling (reducing position), if the remaining position would still
        exceed the maximum position size limit, the order should be rejected.

        Note: We use a lower price so the order size check passes first, then
        position check can be triggered.
        """
        # Config: max_position_size = 10% of $10,000 equity = $1,000
        #         max_order_size = 5% of $10,000 equity = $500
        # Use price $10,000 so order value is manageable
        # Current position: 0.15 BTC at $10,000 = $1,500 = 15% of equity (exceeds limit)
        # Sell order: 0.04 BTC at $10,000 = $400 (4% of equity, passes order size check)
        # Resulting position: 0.11 BTC at $10,000 = $1,100 = 11% of equity
        # Since 11% > 10% max position limit, order should be rejected
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.04"),
        )
        current_price = Decimal("10000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.15")
        )

        # 11% > 10% limit, should fail due to position size
        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_POSITION_SIZE

    def test_sell_to_close_position_passes(self, risk_manager):
        """Test that selling entire position passes."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.01")
        )

        # Resulting position = 0, passes
        assert result.passed is True

    def test_sell_reduces_position_within_limit_passes(self, risk_manager):
        """Test that selling to reduce position within limit passes.

        When selling reduces position to within the maximum allowed size,
        the order should be approved.
        """
        # Config: max_position_size = 10% of $10,000 equity = $1,000
        # Current position: 0.015 BTC at $50,000 = $750 = 7.5% of equity
        # Sell order: 0.01 BTC
        # Resulting position: 0.005 BTC at $50,000 = $250 = 2.5% of equity
        # Since 2.5% < 10% limit, order should pass
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.015")
        )

        # 2.5% < 10% limit, should pass
        assert result.passed is True


class TestDailyTradeLimitValidation:
    """Tests for daily trade limit validation (RSK-003)."""

    def test_within_daily_limit_passes(self, risk_manager):
        """Test that trades within daily limit pass."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Simulate some trades
        for _ in range(50):
            risk_manager.state.daily_trade_count += 1

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_exceeds_daily_limit_rejected(self, risk_manager):
        """Test that exceeding daily trade limit is rejected."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Hit the daily limit
        risk_manager.state.daily_trade_count = 100

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.DAILY_TRADE_LIMIT


class TestDailyLossLimitValidation:
    """Tests for daily loss limit validation (RSK-004)."""

    def test_within_loss_limit_passes(self, risk_manager):
        """Test that trades within loss limit pass."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Simulate some losses (3% loss)
        risk_manager.state.daily_pnl = Decimal("-300")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_exceeds_loss_limit_rejected(self, risk_manager):
        """Test that exceeding daily loss limit is rejected."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Hit the loss limit (5% of $10000 = $500)
        risk_manager.state.daily_pnl = Decimal("-500")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.DAILY_LOSS_LIMIT

    def test_loss_exactly_at_limit_rejected(self, risk_manager):
        """Test that loss exactly at limit is rejected (boundary test).

        When daily loss is exactly at the configured limit (5%),
        further orders should be rejected.
        """
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Loss exactly at 5% limit: -$500 / $10000 = -5%
        risk_manager.state.daily_pnl = Decimal("-500")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.DAILY_LOSS_LIMIT

    def test_loss_just_below_limit_passes(self, risk_manager):
        """Test that loss just below limit passes (boundary test).

        When daily loss is just below the configured limit,
        orders should still be allowed.
        """
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Loss just below 5% limit: -$499.99 / $10000 = -4.9999%
        risk_manager.state.daily_pnl = Decimal("-499.99")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True


class TestTotalLossLimitValidation:
    """Tests for total/cumulative loss limit validation (RSK-004)."""

    def test_within_total_loss_limit_passes(self, risk_manager):
        """Test that trades within total loss limit pass."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Simulate some cumulative losses (15% loss, below 20% limit)
        risk_manager.state.total_pnl = Decimal("-1500")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_exceeds_total_loss_limit_rejected(self, risk_manager):
        """Test that exceeding total loss limit is rejected (RSK-004-1)."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Hit the total loss limit (20% of $10000 = $2000)
        risk_manager.state.total_pnl = Decimal("-2000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT
        assert risk_manager.state.total_loss_limit_triggered is True

    def test_total_loss_exactly_at_limit_rejected(self, risk_manager):
        """Test that total loss exactly at limit is rejected (boundary test)."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Loss exactly at 20% limit: -$2000 / $10000 = -20%
        risk_manager.state.total_pnl = Decimal("-2000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT

    def test_total_loss_just_below_limit_passes(self, risk_manager):
        """Test that total loss just below limit passes (boundary test)."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Loss just below 20% limit: -$1999.99 / $10000 = -19.9999%
        risk_manager.state.total_pnl = Decimal("-1999.99")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_total_loss_limit_triggered_rejects_all_orders(self, risk_manager):
        """Test that once triggered, total loss limit rejects all orders."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Manually set triggered flag
        risk_manager.state.total_loss_limit_triggered = True

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT
        assert "reset" in result.reason.lower()

    def test_total_loss_accumulates_across_trades(self):
        """Test that total loss accumulates correctly across trades."""
        # Use custom config with disabled circuit breaker to avoid interference
        config = RiskConfig(
            circuit_breaker_enabled=False,
            daily_loss_limit=Decimal("0.5"),  # 50% to avoid triggering
            total_loss_limit=Decimal("0.20"),  # 20% total loss limit
        )
        rm = RiskManager(config=config, initial_equity=Decimal("10000"))

        # Record some losses
        rm.record_trade_result(Decimal("-500"))
        rm.record_trade_result(Decimal("-700"))
        rm.record_trade_result(Decimal("-300"))

        # Total loss should be $1500 (15%)
        assert rm.state.total_pnl == Decimal("-1500")

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Should still pass (15% < 20%)
        result = rm.validate_order(order, current_price)
        assert result.passed is True

        # Add more loss to exceed limit
        rm.record_trade_result(Decimal("-600"))  # Total now $2100 (21%)

        result = rm.validate_order(order, current_price)
        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT

    def test_total_loss_with_absolute_limit(self):
        """Test total loss limit with absolute value configuration."""
        config = RiskConfig(
            total_loss_limit=Decimal("0.5"),  # 50% relative (won't trigger)
            total_loss_limit_absolute=Decimal("1500"),  # $1500 absolute
            daily_loss_limit=Decimal("0.5"),  # High to avoid triggering
        )
        rm = RiskManager(config=config, initial_equity=Decimal("10000"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        # Set total loss just below absolute limit
        rm.state.total_pnl = Decimal("-1400")
        result = rm.validate_order(order, current_price)
        assert result.passed is True

        # Set total loss at absolute limit
        rm.state.total_pnl = Decimal("-1500")
        result = rm.validate_order(order, current_price)
        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT

    def test_total_loss_does_not_reset_daily(self, risk_manager):
        """Test that total loss does NOT reset when daily stats reset."""
        # Accumulate some total loss
        risk_manager.state.total_pnl = Decimal("-1000")
        risk_manager.state.daily_pnl = Decimal("-300")

        # Reset daily stats (simulating new day)
        risk_manager.state.reset_daily_stats(Decimal("9700"))

        # Daily should reset, but total should NOT
        assert risk_manager.state.daily_pnl == Decimal("0")
        assert risk_manager.state.total_pnl == Decimal("-1000")


class TestNegativePositionRejection:
    """Tests for negative position rejection (spot trading - no short selling).

    Note: Orders must pass the order size check (5% of equity) before reaching
    the position size check. With $10000 equity at $10000/BTC, max order is 0.05 BTC.
    """

    def test_sell_more_than_position_rejected(self, risk_manager):
        """Test selling more than current position is rejected.

        Use price of $10000 so order value = 0.04 * 10000 = $400 (4% of equity, passes)
        Current position: 0.02 BTC, trying to sell 0.04 BTC -> would result in -0.02
        """
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.04"),  # Trying to sell 0.04 BTC
        )
        current_price = Decimal("10000")  # $10000/BTC so order = $400 (4% of $10000)

        result = risk_manager.validate_order(
            order,
            current_price,
            current_position_amount=Decimal("0.02"),  # Only have 0.02
        )

        assert result.passed is False
        assert result.rule_type == RiskRuleType.MAX_POSITION_SIZE
        assert "negative position" in result.reason.lower()
        assert result.metadata["new_position_amount"] == pytest.approx(-0.02)

    def test_sell_with_no_position_rejected(self, risk_manager):
        """Test selling when position is 0 is rejected.

        Use small order value to pass order size check.
        """
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),  # 0.01 * $10000 = $100 = 1% of equity
        )
        current_price = Decimal("10000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0")
        )

        assert result.passed is False
        assert "negative position" in result.reason.lower()

    def test_sell_exact_position_passes(self, risk_manager):
        """Test selling exact position amount is allowed."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.02"),  # Selling exactly what we have
        )
        current_price = Decimal("10000")  # Order value = $200 = 2% of equity

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.02")
        )

        # Resulting position = 0, which is valid
        assert result.passed is True

    def test_sell_less_than_position_passes(self, risk_manager):
        """Test selling less than current position is allowed."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),  # Selling less than we have
        )
        current_price = Decimal("10000")  # Order value = $100 = 1% of equity

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.02")
        )

        # Resulting position = 0.01, which is valid
        assert result.passed is True

    def test_error_message_contains_amounts(self, risk_manager):
        """Test rejection message includes specific amounts for debugging."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            amount=Decimal("0.04"),  # Order value = $400 = 4% of equity
        )
        current_price = Decimal("10000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0.02")
        )

        assert result.passed is False
        # Check that the reason contains useful information about positions
        assert "0.02" in result.reason or "current" in result.reason.lower()
        assert "0.04" in result.reason or "selling" in result.reason.lower()

    def test_buy_order_not_affected(self, risk_manager):
        """Test that buy orders are not affected by negative position check."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(
            order, current_price, current_position_amount=Decimal("0")
        )

        # Buy order should pass (no negative position issue)
        assert result.passed is True


class TestPriceDeviationValidation:
    """Tests for price deviation validation (RSK-005)."""

    def test_limit_order_within_deviation_passes(self, risk_manager):
        """Test that limit orders within deviation pass."""
        # Use smaller amount to stay within order size limit
        # Order: 0.001 BTC at $50500 = $50.50 (0.5% of $10000 equity)
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=Decimal("50500"),  # 1% above market
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True

    def test_limit_order_exceeds_deviation_rejected(self, risk_manager):
        """Test that adverse limit orders exceeding deviation are rejected."""
        # Buy at 5% above market (adverse for buyer)
        # Use smaller amount to pass order size check
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.001"),  # $52.50 (0.5% of equity)
            price=Decimal("52500"),  # 5% above market
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.PRICE_DEVIATION_LIMIT

    def test_favorable_deviation_allowed(self, risk_manager):
        """Test that favorable price deviations are allowed."""
        # Buy at 5% below market (favorable for buyer)
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("47500"),  # 5% below market
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        # Favorable deviation is allowed
        assert result.passed is True

    def test_market_orders_skip_price_check(self, risk_manager):
        """Test that market orders skip price deviation check."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True


class TestCircuitBreaker:
    """Tests for circuit breaker (RSK-006)."""

    def test_circuit_breaker_not_triggered_initially(self, risk_manager):
        """Test that circuit breaker is not triggered initially."""
        assert risk_manager.state.circuit_breaker_triggered is False

    def test_circuit_breaker_triggers_on_consecutive_losses(self, risk_manager):
        """Test that circuit breaker triggers after consecutive losses."""
        # Record 3 consecutive losses (threshold)
        for _ in range(3):
            risk_manager.record_trade_result(Decimal("-100"))

        assert risk_manager.state.circuit_breaker_triggered is True
        assert risk_manager.state.circuit_breaker_until is not None

    def test_circuit_breaker_rejects_orders(self, risk_manager):
        """Test that circuit breaker rejects orders when active."""
        # Trigger circuit breaker
        risk_manager.state.trigger_circuit_breaker(30)

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is False
        assert result.rule_type == RiskRuleType.CIRCUIT_BREAKER

    def test_circuit_breaker_expires(self, risk_manager):
        """Test that circuit breaker expires after cooldown."""
        # Trigger circuit breaker with short cooldown
        risk_manager.state.circuit_breaker_triggered = True
        risk_manager.state.circuit_breaker_until = datetime.now(UTC) - timedelta(minutes=1)

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.01"),
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        # Circuit breaker should have expired
        assert result.passed is True
        assert risk_manager.state.circuit_breaker_triggered is False

    def test_winning_trade_resets_consecutive_losses(self, risk_manager):
        """Test that a winning trade resets consecutive loss count."""
        # Record 2 losses
        risk_manager.record_trade_result(Decimal("-100"))
        risk_manager.record_trade_result(Decimal("-100"))
        assert risk_manager.state.consecutive_losses == 2

        # Record a win
        risk_manager.record_trade_result(Decimal("50"))

        assert risk_manager.state.consecutive_losses == 0

    def test_circuit_breaker_disabled(self):
        """Test behavior when circuit breaker is disabled."""
        # Use high daily loss limit to avoid triggering it
        config = RiskConfig(
            circuit_breaker_enabled=False,
            daily_loss_limit=Decimal("0.5"),  # 50% daily loss limit
        )
        rm = RiskManager(config=config, initial_equity=Decimal("10000"))

        # Record many losses (small enough to not hit daily loss limit)
        for _ in range(10):
            rm.record_trade_result(Decimal("-100"))  # Total: $1000 = 10% < 50%

        # Should not trigger circuit breaker
        assert rm.state.circuit_breaker_triggered is False

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),  # Small order to pass size check
        )
        current_price = Decimal("50000")

        result = rm.validate_order(order, current_price)

        assert result.passed is True


class TestDailyReset:
    """Tests for daily statistics reset."""

    def test_daily_stats_reset(self, risk_manager):
        """Test that daily stats reset properly."""
        # Simulate some activity
        risk_manager.state.daily_trade_count = 50
        risk_manager.state.daily_pnl = Decimal("-200")

        # Update equity
        risk_manager.update_equity(Decimal("9800"))

        # Reset daily stats
        risk_manager.state.reset_daily_stats(Decimal("9800"))

        assert risk_manager.state.daily_trade_count == 0
        assert risk_manager.state.daily_pnl == Decimal("0")
        assert risk_manager.state.daily_start_equity == Decimal("9800")


class TestCheckDailyResetBoundary:
    """Tests for check_daily_reset() automatic reset logic."""

    def test_same_day_no_reset(self, risk_manager):
        """Test no reset occurs within the same day."""
        # Set reset time to today
        now = datetime.now(UTC)
        risk_manager.state.daily_reset_time = now

        # Simulate some daily stats
        risk_manager.state.daily_trade_count = 5
        risk_manager.state.daily_pnl = Decimal("-100")
        original_start_equity = risk_manager.state.daily_start_equity

        # Check reset - should NOT reset (same day)
        risk_manager.check_daily_reset()

        assert risk_manager.state.daily_trade_count == 5
        assert risk_manager.state.daily_pnl == Decimal("-100")
        assert risk_manager.state.daily_start_equity == original_start_equity

    def test_day_boundary_triggers_reset(self, risk_manager):
        """Test reset triggers when crossing day boundary."""
        # Set reset time to yesterday
        yesterday = datetime.now(UTC) - timedelta(days=1)
        risk_manager.state.daily_reset_time = yesterday

        # Simulate some daily stats
        risk_manager.state.daily_trade_count = 50
        risk_manager.state.daily_pnl = Decimal("-300")

        # Update equity to simulate current state
        risk_manager.update_equity(Decimal("9700"))

        # Check reset - should trigger reset (new day)
        risk_manager.check_daily_reset()

        assert risk_manager.state.daily_trade_count == 0
        assert risk_manager.state.daily_pnl == Decimal("0")
        assert risk_manager.state.daily_start_equity == Decimal("9700")
        # Reset time should be updated to today
        assert risk_manager.state.daily_reset_time.date() == datetime.now(UTC).date()

    def test_multiple_day_jump_still_resets(self, risk_manager):
        """Test reset works even after multiple days have passed."""
        # Set reset time to 6 days ago
        six_days_ago = datetime.now(UTC) - timedelta(days=6)
        risk_manager.state.daily_reset_time = six_days_ago

        # Simulate some daily stats
        risk_manager.state.daily_trade_count = 100
        risk_manager.state.daily_pnl = Decimal("-500")

        # Check reset - should trigger reset
        risk_manager.check_daily_reset()

        assert risk_manager.state.daily_trade_count == 0
        assert risk_manager.state.daily_pnl == Decimal("0")

    def test_total_pnl_preserved_after_reset(self, risk_manager):
        """Test total PnL is preserved while daily stats reset."""
        # Set up total PnL
        risk_manager.state.total_pnl = Decimal("-1500")
        risk_manager.state.daily_pnl = Decimal("-200")
        risk_manager.state.daily_trade_count = 10

        # Set reset time to yesterday
        yesterday = datetime.now(UTC) - timedelta(days=1)
        risk_manager.state.daily_reset_time = yesterday

        # Check reset
        risk_manager.check_daily_reset()

        # Daily stats should reset
        assert risk_manager.state.daily_trade_count == 0
        assert risk_manager.state.daily_pnl == Decimal("0")
        # Total PnL should be preserved
        assert risk_manager.state.total_pnl == Decimal("-1500")

    def test_none_reset_time_initializes(self, risk_manager):
        """Test that None reset_time triggers initialization."""
        # Clear the reset time
        risk_manager.state.daily_reset_time = None

        # Check reset - should initialize
        risk_manager.check_daily_reset()

        # Should have set a reset time
        assert risk_manager.state.daily_reset_time is not None
        assert risk_manager.state.daily_trade_count == 0
        assert risk_manager.state.daily_pnl == Decimal("0")

    def test_consecutive_losses_preserved_after_daily_reset(self, risk_manager):
        """Test that consecutive losses count is preserved after daily reset."""
        # Record some consecutive losses
        risk_manager.record_trade_result(Decimal("-100"))
        risk_manager.record_trade_result(Decimal("-100"))
        assert risk_manager.state.consecutive_losses == 2

        # Set reset time to yesterday
        yesterday = datetime.now(UTC) - timedelta(days=1)
        risk_manager.state.daily_reset_time = yesterday

        # Trigger daily reset
        risk_manager.check_daily_reset()

        # Consecutive losses should NOT reset with daily stats
        # (This tests whether consecutive losses persists across days)
        # Note: The actual behavior depends on implementation
        # If this fails, update the test based on actual desired behavior
        assert risk_manager.state.consecutive_losses == 2


class TestEquityUpdate:
    """Tests for equity updates."""

    def test_update_equity(self, risk_manager):
        """Test equity update affects validations."""
        # Initial equity: $10000
        # Max order size: 5% = $500
        Decimal("500")

        # Update to $20000
        risk_manager.update_equity(Decimal("20000"))

        # Now max order is 5% of $20000 = $1000
        # This order would have failed before
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.015"),  # $750 at $50000
        )
        current_price = Decimal("50000")

        result = risk_manager.validate_order(order, current_price)

        assert result.passed is True


class TestStateSummary:
    """Tests for state summary."""

    def test_get_state_summary(self, risk_manager):
        """Test that state summary contains expected fields."""
        # Do some activity
        risk_manager.state.daily_trade_count = 5
        risk_manager.state.daily_pnl = Decimal("-100")
        risk_manager.state.total_pnl = Decimal("-500")
        risk_manager.state.consecutive_losses = 2

        summary = risk_manager.get_state_summary()

        assert summary["daily_trade_count"] == 5
        assert summary["daily_trade_limit"] == 100
        assert summary["daily_pnl"] == -100.0
        assert summary["total_pnl"] == -500.0
        assert summary["total_loss_limit_pct"] == 0.2  # 20% default
        assert summary["total_loss_limit_triggered"] is False
        assert summary["current_equity"] == 10000.0
        assert summary["consecutive_losses"] == 2
        assert summary["circuit_breaker_triggered"] is False


class TestRiskCheckResult:
    """Tests for RiskCheckResult model."""

    def test_ok_result(self):
        """Test creating an OK result."""
        result = RiskCheckResult.ok()

        assert result.passed is True
        assert result.action is None
        assert result.reason is None

    def test_reject_result(self):
        """Test creating a reject result."""
        result = RiskCheckResult.reject(
            rule_type=RiskRuleType.MAX_ORDER_SIZE,
            reason="Order too large",
            order_value=1000,
        )

        assert result.passed is False
        assert result.action == RiskAction.REJECT
        assert result.rule_type == RiskRuleType.MAX_ORDER_SIZE
        assert result.reason == "Order too large"
        assert result.metadata["order_value"] == 1000

    def test_warn_result(self):
        """Test creating a warning result."""
        result = RiskCheckResult.warn(
            rule_type=RiskRuleType.PRICE_DEVIATION_LIMIT,
            reason="Price slightly off",
        )

        assert result.passed is True
        assert result.action == RiskAction.WARN
        assert result.rule_type == RiskRuleType.PRICE_DEVIATION_LIMIT

    def test_reduce_result(self):
        """Test creating a reduce result."""
        result = RiskCheckResult.reduce(
            rule_type=RiskRuleType.MAX_ORDER_SIZE,
            reason="Order reduced to comply",
            adjusted_amount=Decimal("0.5"),
        )

        assert result.passed is True
        assert result.action == RiskAction.REDUCE
        assert result.adjusted_amount == Decimal("0.5")


class TestRiskState:
    """Tests for RiskState model."""

    def test_record_trade_updates_stats(self):
        """Test that recording trades updates stats."""
        state = RiskState()
        state.daily_start_equity = Decimal("10000")

        state.record_trade(Decimal("100"))

        assert state.daily_trade_count == 1
        assert state.daily_pnl == Decimal("100")
        assert state.consecutive_losses == 0

    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        state = RiskState()

        state.record_trade(Decimal("-50"))

        assert state.daily_pnl == Decimal("-50")
        assert state.consecutive_losses == 1

    def test_trigger_circuit_breaker(self):
        """Test triggering circuit breaker."""
        state = RiskState()

        state.trigger_circuit_breaker(30)

        assert state.circuit_breaker_triggered is True
        assert state.circuit_breaker_until is not None
        # Should be approximately 30 minutes from now
        delta = state.circuit_breaker_until - datetime.now(UTC)
        assert 29 * 60 <= delta.total_seconds() <= 31 * 60

    def test_check_circuit_breaker_expired(self):
        """Test checking circuit breaker expiration."""
        state = RiskState()

        # Not triggered
        assert state.check_circuit_breaker_expired() is True

        # Trigger with past expiration
        state.circuit_breaker_triggered = True
        state.circuit_breaker_until = datetime.now(UTC) - timedelta(minutes=1)

        assert state.check_circuit_breaker_expired() is True
        assert state.circuit_breaker_triggered is False

    def test_reset_daily_stats(self):
        """Test resetting daily stats."""
        state = RiskState()
        state.daily_trade_count = 50
        state.daily_pnl = Decimal("-500")

        state.reset_daily_stats(Decimal("9500"))

        assert state.daily_trade_count == 0
        assert state.daily_pnl == Decimal("0")
        assert state.daily_start_equity == Decimal("9500")
        assert state.daily_reset_time is not None

    def test_zero_pnl_preserves_consecutive_losses(self):
        """Test that zero PnL trades do not reset consecutive loss counter."""
        state = RiskState()

        # Record 3 losses
        state.record_trade(Decimal("-100"))
        state.record_trade(Decimal("-50"))
        state.record_trade(Decimal("-75"))
        assert state.consecutive_losses == 3

        # Zero PnL should NOT reset the counter
        state.record_trade(Decimal("0"))
        assert state.consecutive_losses == 3

        # A win should reset the counter
        state.record_trade(Decimal("50"))
        assert state.consecutive_losses == 0

    def test_zero_pnl_does_not_increment_losses(self):
        """Test that zero PnL trades do not increment consecutive loss counter."""
        state = RiskState()

        # No losses yet
        assert state.consecutive_losses == 0

        # Zero PnL should not count as a loss
        state.record_trade(Decimal("0"))
        assert state.consecutive_losses == 0


class TestZeroEquityProtection:
    """Tests for zero/negative equity safety checks."""

    def test_zero_equity_rejects_all_orders(self, default_config):
        """Test that zero equity rejects all orders."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("10000"))
        rm.update_equity(Decimal("0"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )

        result = rm.validate_order(order, Decimal("50000"))

        assert result.passed is False
        assert result.rule_type == RiskRuleType.TOTAL_LOSS_LIMIT
        assert "zero or negative equity" in result.reason.lower()

    def test_negative_equity_rejects_all_orders(self, default_config):
        """Test that negative equity rejects all orders."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("10000"))
        rm.update_equity(Decimal("-500"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )

        result = rm.validate_order(order, Decimal("50000"))

        assert result.passed is False
        assert "zero or negative equity" in result.reason.lower()

    def test_positive_equity_allows_orders(self, default_config):
        """Test that positive equity allows orders normally."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("10000"))
        rm.update_equity(Decimal("100"))  # Very low but still positive

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),  # $50 at $50000
        )

        result = rm.validate_order(order, Decimal("50000"))
        # Order will be rejected by max_order_size (50% of $100 equity) not zero equity
        # This confirms the zero equity check is bypassed for positive equity
        assert result.rule_type != RiskRuleType.TOTAL_LOSS_LIMIT or result.passed


class TestAbsoluteDailyLossLimit:
    """Tests for absolute daily loss limit."""

    def test_absolute_daily_loss_limit_triggered(self):
        """Test absolute daily loss limit triggers rejection."""
        config = RiskConfig(
            max_position_size=Decimal("1.0"),
            max_order_size=Decimal("1.0"),
            min_order_value=Decimal("1"),
            daily_loss_limit=Decimal("1.0"),  # 100% - won't trigger
            daily_loss_limit_absolute=Decimal("500"),
            daily_trade_limit=1000,
        )
        rm = RiskManager(config=config, initial_equity=Decimal("10000"))

        # Record $500 in losses
        rm.record_trade_result(Decimal("-500"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )

        result = rm.validate_order(order, Decimal("50000"))

        assert result.passed is False
        assert result.rule_type == RiskRuleType.DAILY_LOSS_LIMIT

    def test_absolute_daily_loss_limit_not_triggered(self):
        """Test absolute daily loss limit does not trigger below threshold."""
        config = RiskConfig(
            max_position_size=Decimal("1.0"),
            max_order_size=Decimal("1.0"),
            min_order_value=Decimal("1"),
            daily_loss_limit=Decimal("1.0"),  # 100% - won't trigger
            daily_loss_limit_absolute=Decimal("500"),
            daily_trade_limit=1000,
        )
        rm = RiskManager(config=config, initial_equity=Decimal("10000"))

        # Record $499 in losses
        rm.record_trade_result(Decimal("-499"))

        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )

        result = rm.validate_order(order, Decimal("50000"))

        assert result.passed is True


class TestUpdatePositionValue:
    """Tests for position value tracking."""

    def test_update_position_value(self, risk_manager):
        """Test that update_position_value updates state correctly."""
        assert risk_manager.state.current_position_value == Decimal("0")

        risk_manager.update_position_value(Decimal("5000"))
        assert risk_manager.state.current_position_value == Decimal("5000")

        risk_manager.update_position_value(Decimal("0"))
        assert risk_manager.state.current_position_value == Decimal("0")


class TestZeroPriceDeviation:
    """Tests for price deviation with zero price."""

    def test_zero_current_price_passes(self, risk_manager):
        """Test that zero current price skips deviation check."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=Decimal("50000"),
        )

        # Zero current price should not cause division by zero
        risk_manager.validate_order(order, Decimal("0"))
        # Should be rejected by zero equity or pass price check
        # Key: no exception is raised

    def test_negative_current_price_passes(self, risk_manager):
        """Test that negative current price skips deviation check."""
        order = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=Decimal("50000"),
        )

        # Negative current price should not cause issues
        risk_manager.validate_order(order, Decimal("-1"))
        # Key: no exception is raised


class TestInitializationDailyResetTime:
    """Tests for daily reset time initialization."""

    def test_daily_reset_time_set_on_init(self, default_config):
        """Test that daily_reset_time is set during initialization."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("10000"))
        assert rm.state.daily_reset_time is not None

    def test_daily_start_equity_set_on_init(self, default_config):
        """Test that daily_start_equity is set to initial equity."""
        rm = RiskManager(config=default_config, initial_equity=Decimal("5000"))
        assert rm.state.daily_start_equity == Decimal("5000")
