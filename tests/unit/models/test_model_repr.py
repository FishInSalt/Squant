"""Unit tests for model __repr__ methods."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from squant.models.enums import (
    LogLevel,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskRuleType,
    RunMode,
    RunStatus,
    StrategyStatus,
)
from squant.models.exchange import ExchangeAccount
from squant.models.log import SystemLog
from squant.models.market import Kline, Watchlist
from squant.models.metrics import BalanceSnapshot, EquityCurve
from squant.models.order import Order, Trade
from squant.models.risk import CircuitBreakerEvent, RiskRule, RiskTrigger
from squant.models.strategy import Strategy, StrategyRun


class TestSystemLogRepr:
    """Tests for SystemLog.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, level, and module."""
        log = SystemLog(
            id=123, level=LogLevel.INFO, module="test_module", message="Test message"
        )

        repr_str = repr(log)

        assert "SystemLog" in repr_str
        assert "id=123" in repr_str
        assert "level=LogLevel.INFO" in repr_str
        assert "module=test_module" in repr_str


class TestExchangeAccountRepr:
    """Tests for ExchangeAccount.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, exchange, and name."""
        account_id = uuid4()
        account = ExchangeAccount(
            id=account_id,
            exchange="binance",
            name="main_account",
            api_key_enc=b"encrypted_key",
            api_secret_enc=b"encrypted_secret",
            nonce=b"nonce123",
        )

        repr_str = repr(account)

        assert "ExchangeAccount" in repr_str
        assert f"id={account_id}" in repr_str
        assert "exchange=binance" in repr_str
        assert "name=main_account" in repr_str


class TestWatchlistRepr:
    """Tests for Watchlist.__repr__."""

    def test_repr_includes_exchange_and_symbol(self) -> None:
        """Test that __repr__ includes exchange and symbol."""
        watchlist = Watchlist(exchange="okx", symbol="BTC/USDT")

        repr_str = repr(watchlist)

        assert "Watchlist" in repr_str
        assert "exchange=okx" in repr_str
        assert "symbol=BTC/USDT" in repr_str


class TestKlineRepr:
    """Tests for Kline.__repr__."""

    def test_repr_includes_exchange_symbol_timeframe_time(self) -> None:
        """Test that __repr__ includes exchange, symbol, timeframe, and time."""
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        kline = Kline(
            time=timestamp,
            exchange="binance",
            symbol="ETH/USDT",
            timeframe="1h",
            open=Decimal("2000.00"),
            high=Decimal("2100.00"),
            low=Decimal("1950.00"),
            close=Decimal("2050.00"),
            volume=Decimal("1000.00"),
        )

        repr_str = repr(kline)

        assert "Kline" in repr_str
        assert "binance" in repr_str
        assert "ETH/USDT" in repr_str
        assert "1h" in repr_str
        assert str(timestamp) in repr_str


class TestEquityCurveRepr:
    """Tests for EquityCurve.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes run_id, time, and equity."""
        run_id = uuid4()
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        curve = EquityCurve(
            run_id=str(run_id),
            time=timestamp,
            equity=Decimal("10000.00"),
            cash=Decimal("5000.00"),
            position_value=Decimal("5000.00"),
        )

        repr_str = repr(curve)

        assert "EquityCurve" in repr_str
        assert f"run_id={run_id}" in repr_str
        assert "equity=10000.00" in repr_str


class TestBalanceSnapshotRepr:
    """Tests for BalanceSnapshot.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes account_id, currency, and time."""
        account_id = uuid4()
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        snapshot = BalanceSnapshot(
            account_id=str(account_id),
            currency="USDT",
            time=timestamp,
            free=Decimal("1000.00"),
            locked=Decimal("0.00"),
        )

        repr_str = repr(snapshot)

        assert "BalanceSnapshot" in repr_str
        assert f"account_id={account_id}" in repr_str
        assert "currency=USDT" in repr_str


class TestOrderRepr:
    """Tests for Order.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, symbol, side, and status."""
        order_id = uuid4()
        account_id = uuid4()
        order = Order(
            id=order_id,
            account_id=str(account_id),
            exchange="okx",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("1.0"),
            price=Decimal("50000.00"),
            status=OrderStatus.FILLED,
        )

        repr_str = repr(order)

        assert "Order" in repr_str
        assert f"id={order_id}" in repr_str
        assert "BTC/USDT" in repr_str
        assert "BUY" in repr_str or "buy" in repr_str
        assert "FILLED" in repr_str or "filled" in repr_str


class TestTradeRepr:
    """Tests for Trade.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, price, and amount."""
        trade_id = uuid4()
        order_id = uuid4()
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        trade = Trade(
            id=trade_id,
            order_id=str(order_id),
            price=Decimal("50000.00"),
            amount=Decimal("1.0"),
            timestamp=timestamp,
        )

        repr_str = repr(trade)

        assert "Trade" in repr_str
        assert f"id={trade_id}" in repr_str
        assert "price=50000.00" in repr_str
        assert "amount=1.0" in repr_str


class TestRiskRuleRepr:
    """Tests for RiskRule.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, name, and type."""
        rule_id = uuid4()
        rule = RiskRule(
            id=rule_id,
            name="max_position_size",
            type=RiskRuleType.POSITION_LIMIT,
            params={"max_size": 100.0},
        )

        repr_str = repr(rule)

        assert "RiskRule" in repr_str
        assert f"id={rule_id}" in repr_str
        assert "name=max_position_size" in repr_str
        assert "POSITION_LIMIT" in repr_str


class TestRiskTriggerRepr:
    """Tests for RiskTrigger.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, rule_id, and type."""
        trigger_id = uuid4()
        rule_id = uuid4()
        trigger = RiskTrigger(
            id=trigger_id,
            time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            rule_id=str(rule_id),
            trigger_type="position_limit",
            details={"current": 150, "limit": 100},
        )

        repr_str = repr(trigger)

        assert "RiskTrigger" in repr_str
        assert f"id={trigger_id}" in repr_str
        assert f"rule_id={rule_id}" in repr_str
        assert "position_limit" in repr_str


class TestCircuitBreakerEventRepr:
    """Tests for CircuitBreakerEvent.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, time, and trigger_type."""
        event_id = uuid4()
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        event = CircuitBreakerEvent(
            id=event_id,
            time=timestamp,
            trigger_type="manual",
            trigger_source="api",
            reason="Emergency stop",
            details={},
        )

        repr_str = repr(event)

        assert "CircuitBreakerEvent" in repr_str
        assert f"id={event_id}" in repr_str
        assert "manual" in repr_str


class TestStrategyRepr:
    """Tests for Strategy.__repr__."""

    def test_repr_includes_id_name_and_version(self) -> None:
        """Test that __repr__ includes id, name, and version."""
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="momentum_strategy",
            version="1.0.0",
            code="# strategy code",
            status=StrategyStatus.ACTIVE,
        )

        repr_str = repr(strategy)

        assert "Strategy" in repr_str
        assert f"id={strategy_id}" in repr_str
        assert "name=momentum_strategy" in repr_str
        assert "version=1.0.0" in repr_str


class TestStrategyRunRepr:
    """Tests for StrategyRun.__repr__."""

    def test_repr_includes_key_fields(self) -> None:
        """Test that __repr__ includes id, mode, and status."""
        run_id = uuid4()
        strategy_id = uuid4()
        run = StrategyRun(
            id=run_id,
            strategy_id=str(strategy_id),
            exchange="okx",
            symbol="BTC/USDT",
            timeframe="1h",
            mode=RunMode.PAPER,
            status=RunStatus.RUNNING,
        )

        repr_str = repr(run)

        assert "StrategyRun" in repr_str
        assert f"id={run_id}" in repr_str
        assert "PAPER" in repr_str or "paper" in repr_str
        assert "RUNNING" in repr_str or "running" in repr_str
