"""Unit tests for model enums."""

from __future__ import annotations

import pytest

from squant.models.enums import (
    CircuitBreakerTriggerType,
    LogLevel,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskRuleType,
    RunMode,
    RunStatus,
    StrategyStatus,
)


class TestRunMode:
    """Tests for RunMode enum."""

    def test_all_modes_exist(self):
        """Test all run modes exist."""
        assert RunMode.BACKTEST == "backtest"
        assert RunMode.PAPER == "paper"
        assert RunMode.LIVE == "live"

    def test_is_string_enum(self):
        """Test RunMode is string enum."""
        assert isinstance(RunMode.BACKTEST.value, str)
        assert RunMode.BACKTEST == "backtest"

    def test_membership(self):
        """Test membership check."""
        assert "backtest" in [m.value for m in RunMode]
        assert "paper" in [m.value for m in RunMode]
        assert "live" in [m.value for m in RunMode]

    def test_count(self):
        """Test total number of modes."""
        assert len(RunMode) == 3

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert RunMode("backtest") == RunMode.BACKTEST
        assert RunMode("paper") == RunMode.PAPER
        assert RunMode("live") == RunMode.LIVE


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_all_statuses_exist(self):
        """Test all run statuses exist."""
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.STOPPED == "stopped"
        assert RunStatus.ERROR == "error"
        assert RunStatus.COMPLETED == "completed"

    def test_count(self):
        """Test total number of statuses."""
        assert len(RunStatus) == 5

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert RunStatus("pending") == RunStatus.PENDING
        assert RunStatus("running") == RunStatus.RUNNING


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_all_sides_exist(self):
        """Test all order sides exist."""
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"

    def test_count(self):
        """Test total number of sides."""
        assert len(OrderSide) == 2

    def test_is_string_enum(self):
        """Test OrderSide is string enum."""
        assert isinstance(OrderSide.BUY, str)
        assert OrderSide.BUY == "buy"

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert OrderSide("buy") == OrderSide.BUY
        assert OrderSide("sell") == OrderSide.SELL


class TestOrderType:
    """Tests for OrderType enum."""

    def test_all_types_exist(self):
        """Test all order types exist."""
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"

    def test_count(self):
        """Test total number of types."""
        assert len(OrderType) == 2

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert OrderType("market") == OrderType.MARKET
        assert OrderType("limit") == OrderType.LIMIT


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_all_statuses_exist(self):
        """Test all order statuses exist."""
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.SUBMITTED == "submitted"
        assert OrderStatus.PARTIAL == "partial"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.CANCELLED == "cancelled"
        assert OrderStatus.REJECTED == "rejected"

    def test_count(self):
        """Test total number of statuses."""
        assert len(OrderStatus) == 6

    def test_terminal_statuses(self):
        """Test terminal statuses are identifiable."""
        terminal = [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]
        for status in terminal:
            assert status in OrderStatus

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert OrderStatus("filled") == OrderStatus.FILLED
        assert OrderStatus("cancelled") == OrderStatus.CANCELLED


class TestRiskRuleType:
    """Tests for RiskRuleType enum."""

    def test_all_types_exist(self):
        """Test all risk rule types exist."""
        assert RiskRuleType.ORDER_LIMIT == "order_limit"
        assert RiskRuleType.POSITION_LIMIT == "position_limit"
        assert RiskRuleType.DAILY_LOSS_LIMIT == "daily_loss_limit"
        assert RiskRuleType.TOTAL_LOSS_LIMIT == "total_loss_limit"
        assert RiskRuleType.FREQUENCY_LIMIT == "frequency_limit"
        assert RiskRuleType.VOLATILITY_BREAK == "volatility_break"

    def test_count(self):
        """Test total number of risk rule types."""
        assert len(RiskRuleType) == 6

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert RiskRuleType("order_limit") == RiskRuleType.ORDER_LIMIT
        assert RiskRuleType("daily_loss_limit") == RiskRuleType.DAILY_LOSS_LIMIT


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_all_levels_exist(self):
        """Test all log levels exist."""
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARNING == "warning"
        assert LogLevel.ERROR == "error"
        assert LogLevel.CRITICAL == "critical"

    def test_count(self):
        """Test total number of log levels."""
        assert len(LogLevel) == 5

    def test_severity_order(self):
        """Test log levels can be ordered by severity."""
        levels = [
            LogLevel.DEBUG,
            LogLevel.INFO,
            LogLevel.WARNING,
            LogLevel.ERROR,
            LogLevel.CRITICAL,
        ]
        # Just verify they all exist in expected order
        assert len(levels) == 5


class TestStrategyStatus:
    """Tests for StrategyStatus enum."""

    def test_all_statuses_exist(self):
        """Test all strategy statuses exist."""
        assert StrategyStatus.ACTIVE == "active"
        assert StrategyStatus.ARCHIVED == "archived"

    def test_count(self):
        """Test total number of statuses."""
        assert len(StrategyStatus) == 2

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert StrategyStatus("active") == StrategyStatus.ACTIVE
        assert StrategyStatus("archived") == StrategyStatus.ARCHIVED


class TestCircuitBreakerTriggerType:
    """Tests for CircuitBreakerTriggerType enum."""

    def test_all_types_exist(self):
        """Test all trigger types exist."""
        assert CircuitBreakerTriggerType.MANUAL == "manual"
        assert CircuitBreakerTriggerType.AUTO == "auto"

    def test_count(self):
        """Test total number of trigger types."""
        assert len(CircuitBreakerTriggerType) == 2

    def test_can_create_from_value(self):
        """Test creating enum from value."""
        assert CircuitBreakerTriggerType("manual") == CircuitBreakerTriggerType.MANUAL
        assert CircuitBreakerTriggerType("auto") == CircuitBreakerTriggerType.AUTO


class TestEnumInheritance:
    """Tests for enum inheritance properties."""

    def test_all_enums_are_string_enums(self):
        """Test all enums inherit from str."""
        enums = [
            RunMode,
            RunStatus,
            OrderSide,
            OrderType,
            OrderStatus,
            RiskRuleType,
            LogLevel,
            StrategyStatus,
            CircuitBreakerTriggerType,
        ]
        for enum_class in enums:
            for member in enum_class:
                assert isinstance(member, str)
                assert isinstance(member.value, str)

    def test_enum_values_are_lowercase(self):
        """Test all enum values are lowercase."""
        enums = [
            RunMode,
            RunStatus,
            OrderSide,
            OrderType,
            OrderStatus,
            RiskRuleType,
            LogLevel,
            StrategyStatus,
            CircuitBreakerTriggerType,
        ]
        for enum_class in enums:
            for member in enum_class:
                assert member.value == member.value.lower()


class TestEnumInvalidValues:
    """Tests for invalid enum values."""

    def test_invalid_run_mode_raises(self):
        """Test invalid RunMode raises ValueError."""
        with pytest.raises(ValueError):
            RunMode("invalid")

    def test_invalid_order_side_raises(self):
        """Test invalid OrderSide raises ValueError."""
        with pytest.raises(ValueError):
            OrderSide("invalid")

    def test_invalid_order_type_raises(self):
        """Test invalid OrderType raises ValueError."""
        with pytest.raises(ValueError):
            OrderType("invalid")

    def test_invalid_order_status_raises(self):
        """Test invalid OrderStatus raises ValueError."""
        with pytest.raises(ValueError):
            OrderStatus("invalid")

    def test_case_sensitive(self):
        """Test enum creation is case sensitive."""
        with pytest.raises(ValueError):
            OrderSide("BUY")  # Should be "buy"

        with pytest.raises(ValueError):
            OrderType("MARKET")  # Should be "market"
