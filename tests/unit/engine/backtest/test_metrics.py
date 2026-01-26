"""Unit tests for backtest metrics calculation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from squant.engine.backtest.metrics import (
    PerformanceMetrics,
    calculate_metrics,
    _calculate_max_drawdown,
)
from squant.engine.backtest.types import (
    EquitySnapshot,
    OrderSide,
    TradeRecord,
)


def create_equity_curve(
    equities: list[Decimal],
    start_time: datetime | None = None,
    interval_hours: int = 1,
) -> list[EquitySnapshot]:
    """Helper to create equity curve from list of equity values."""
    if start_time is None:
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    curve = []
    for i, equity in enumerate(equities):
        time = start_time + timedelta(hours=i * interval_hours)
        # Assume 80% cash, 20% position for simplicity
        cash = equity * Decimal("0.8")
        position_value = equity * Decimal("0.2")
        curve.append(
            EquitySnapshot(
                time=time,
                equity=equity,
                cash=cash,
                position_value=position_value,
                unrealized_pnl=Decimal("0"),
            )
        )
    return curve


class TestCalculateMetrics:
    """Tests for calculate_metrics function."""

    def test_empty_equity_curve(self) -> None:
        """Test with empty equity curve."""
        metrics = calculate_metrics([], [], Decimal("10000"))

        assert metrics.total_return == Decimal("0")
        assert metrics.total_trades == 0

    def test_total_return_calculation(self) -> None:
        """Test total return calculation."""
        equities = [Decimal("10000"), Decimal("11000"), Decimal("12000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.total_return == Decimal("2000")
        assert metrics.total_return_pct == Decimal("20")

    def test_negative_return(self) -> None:
        """Test negative return calculation."""
        equities = [Decimal("10000"), Decimal("9000"), Decimal("8000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.total_return == Decimal("-2000")
        assert metrics.total_return_pct == Decimal("-20")

    def test_fees_tracked(self) -> None:
        """Test that fees are tracked."""
        equities = [Decimal("10000"), Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(
            curve, [], Decimal("10000"), total_fees=Decimal("100")
        )

        assert metrics.total_fees == Decimal("100")


class TestMaxDrawdown:
    """Tests for max drawdown calculation."""

    def test_no_drawdown(self) -> None:
        """Test with constantly increasing equity."""
        equities = [
            Decimal("10000"),
            Decimal("11000"),
            Decimal("12000"),
            Decimal("13000"),
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("0")
        assert max_dd_pct == Decimal("0")

    def test_simple_drawdown(self) -> None:
        """Test simple drawdown calculation."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak
            Decimal("10000"),  # Drawdown of 2000 (16.67%)
            Decimal("11000"),
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("2000")
        # 2000 / 12000 * 100 = 16.666...%
        assert float(max_dd_pct) == pytest.approx(16.67, rel=0.01)

    def test_multiple_drawdowns(self) -> None:
        """Test with multiple drawdowns, takes the maximum."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak 1
            Decimal("11000"),  # Drawdown 1: 1000 (8.33%)
            Decimal("14000"),  # Peak 2 (new high)
            Decimal("10000"),  # Drawdown 2: 4000 (28.57%)
            Decimal("13000"),
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("4000")
        # 4000 / 14000 * 100 = 28.57%
        assert float(max_dd_pct) == pytest.approx(28.57, rel=0.01)


class TestTradeStatistics:
    """Tests for trade statistics calculation."""

    def test_trade_count(self) -> None:
        """Test trade counting."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
                exit_price=Decimal("42000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
        ]
        equities = [Decimal("10000"), Decimal("11000"), Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1

    def test_win_rate(self) -> None:
        """Test win rate calculation."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                exit_price=Decimal("44000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                entry_price=Decimal("44000"),
                exit_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
        ]
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        # 2 wins out of 3 = 66.67%
        assert float(metrics.win_rate) == pytest.approx(66.67, rel=0.01)

    def test_profit_factor(self) -> None:
        """Test profit factor calculation."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_price=Decimal("44000"),
                amount=Decimal("1"),
                pnl=Decimal("2000"),  # Win
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                entry_price=Decimal("44000"),
                exit_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),  # Loss
            ),
        ]
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        # Profit factor = 2000 / 1000 = 2.0
        assert metrics.profit_factor == Decimal("2")

    def test_average_trade_return(self) -> None:
        """Test average trade return calculation."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 4, tzinfo=timezone.utc),
                exit_price=Decimal("42500"),
                amount=Decimal("1"),
                pnl=Decimal("-500"),
            ),
        ]
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        # Average = (1000 + (-500)) / 2 = 250
        assert metrics.avg_trade_return == Decimal("250")


class TestPerformanceMetricsToDict:
    """Tests for PerformanceMetrics.to_dict()."""

    def test_to_dict_returns_all_fields(self) -> None:
        """Test that to_dict includes all fields."""
        metrics = PerformanceMetrics(
            total_return=Decimal("1000"),
            total_return_pct=Decimal("10"),
            max_drawdown=Decimal("500"),
            total_trades=5,
            win_rate=Decimal("60"),
        )

        result = metrics.to_dict()

        assert "total_return" in result
        assert "total_return_pct" in result
        assert "max_drawdown" in result
        assert "total_trades" in result
        assert "win_rate" in result
        assert result["total_trades"] == 5  # int, not string
        assert result["total_return"] == "1000"  # Decimal as string
