"""Unit tests for backtest metrics calculation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from squant.engine.backtest.metrics import (
    PerformanceMetrics,
    _calculate_max_drawdown,
    calculate_metrics,
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
        start_time = datetime(2024, 1, 1, tzinfo=UTC)

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

        metrics = calculate_metrics(curve, [], Decimal("10000"), total_fees=Decimal("100"))

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

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("0")
        assert max_dd_pct == Decimal("0")
        assert dd_hours == 0

    def test_simple_drawdown(self) -> None:
        """Test simple drawdown calculation."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak at hour 1
            Decimal("10000"),  # Drawdown of 2000 (16.67%) at hour 2
            Decimal("11000"),  # Not recovered (< 12000)
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("2000")
        # 2000 / 12000 * 100 = 16.666...%
        assert float(max_dd_pct) == pytest.approx(16.67, rel=0.01)
        # Duration: peak (h1) to end (h3) since equity never recovers to 12000
        assert dd_hours == 2

    def test_multiple_drawdowns(self) -> None:
        """Test with multiple drawdowns, takes the maximum."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak 1
            Decimal("11000"),  # Drawdown 1: 1000 (8.33%)
            Decimal("14000"),  # Peak 2 (new high)
            Decimal("10000"),  # Drawdown 2: 4000 (28.57%)
            Decimal("13000"),  # Not recovered (< 14000)
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("4000")
        # 4000 / 14000 * 100 = 28.57%
        assert float(max_dd_pct) == pytest.approx(28.57, rel=0.01)
        # Duration: peak 2 (h3) to end (h5) since equity never recovers to 14000
        assert dd_hours == 2


class TestTradeStatistics:
    """Tests for trade statistics calculation."""

    def test_trade_count(self) -> None:
        """Test trade counting."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
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
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 2, tzinfo=UTC),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 3, tzinfo=UTC),
                exit_price=Decimal("44000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("44000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
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
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("44000"),
                amount=Decimal("1"),
                pnl=Decimal("2000"),  # Win
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("44000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
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
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
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


class TestMetricsEdgeCases:
    """Tests for edge cases in metrics calculation."""

    def test_equity_curve_with_no_trades(self) -> None:
        """Test metrics with equity curve but zero trades (no division by zero)."""
        equities = [Decimal("10000"), Decimal("11000"), Decimal("12000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.total_trades == 0
        assert metrics.avg_trade_return == Decimal("0")
        assert metrics.win_rate == Decimal("0")
        assert metrics.profit_factor == Decimal("0")

    def test_zero_initial_capital(self) -> None:
        """Test metrics with zero initial capital doesn't crash."""
        equities = [Decimal("0"), Decimal("100")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, [], Decimal("0"))

        assert metrics.total_return == Decimal("100")
        assert metrics.total_return_pct == Decimal("0")  # Skips division by zero

    def test_single_equity_snapshot(self) -> None:
        """Test metrics with only one equity snapshot."""
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.total_return == Decimal("0")
        assert metrics.sharpe_ratio == Decimal("0")
        assert metrics.sortino_ratio == Decimal("0")

    def test_max_drawdown_single_snapshot(self) -> None:
        """Test max drawdown with only one equity snapshot returns zero."""
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("0")
        assert max_dd_pct == Decimal("0")
        assert dd_hours == 0

    def test_sharpe_ratio_zero_volatility(self) -> None:
        """Test Sharpe ratio with constant equity (zero std dev) returns zero."""
        equities = [Decimal("10000")] * 10
        curve = create_equity_curve(equities, interval_hours=24)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.sharpe_ratio == Decimal("0")

    def test_sortino_ratio_no_negative_returns(self) -> None:
        """Test Sortino ratio with only positive returns caps at 99.99."""
        equities = [Decimal("10000") + Decimal(str(i * 100)) for i in range(10)]
        curve = create_equity_curve(equities, interval_hours=24)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.sortino_ratio == Decimal("99.99")

    def test_all_losing_trades(self) -> None:
        """Test metrics with only losing trades."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("41000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("41000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
                exit_price=Decimal("40000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
        ]
        equities = [Decimal("10000"), Decimal("9000"), Decimal("8000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        assert metrics.win_rate == Decimal("0")
        assert metrics.winning_trades == 0
        assert metrics.losing_trades == 2
        assert metrics.profit_factor == Decimal("0")  # No gross profit

    def test_all_winning_trades_profit_factor_capped(self) -> None:
        """Test profit factor caps at 99.99 when there are no losses."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
        ]
        equities = [Decimal("10000"), Decimal("11000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        assert metrics.win_rate == Decimal("100")
        assert metrics.profit_factor == Decimal("99.99")


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
        assert "max_drawdown_duration_hours" in result
        assert "volatility" in result
        assert "max_consecutive_losses" in result
        assert result["total_trades"] == 5  # int, not string
        assert result["total_return"] == "1000"  # Decimal as string


class TestNewMetricsFields:
    """Tests for newly added metrics fields (TRD-009 compliance)."""

    def test_max_consecutive_losses(self) -> None:
        """Test max consecutive losses calculation."""
        trades = [
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 1, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 2, tzinfo=UTC),
                exit_price=Decimal("43000"),
                amount=Decimal("1"),
                pnl=Decimal("1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 3, tzinfo=UTC),
                entry_price=Decimal("43000"),
                exit_time=datetime(2024, 1, 4, tzinfo=UTC),
                exit_price=Decimal("42000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 5, tzinfo=UTC),
                entry_price=Decimal("42000"),
                exit_time=datetime(2024, 1, 6, tzinfo=UTC),
                exit_price=Decimal("41000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 7, tzinfo=UTC),
                entry_price=Decimal("41000"),
                exit_time=datetime(2024, 1, 8, tzinfo=UTC),
                exit_price=Decimal("40000"),
                amount=Decimal("1"),
                pnl=Decimal("-1000"),
            ),
            TradeRecord(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                entry_time=datetime(2024, 1, 9, tzinfo=UTC),
                entry_price=Decimal("40000"),
                exit_time=datetime(2024, 1, 10, tzinfo=UTC),
                exit_price=Decimal("42000"),
                amount=Decimal("1"),
                pnl=Decimal("2000"),
            ),
        ]
        equities = [Decimal("10000")]
        curve = create_equity_curve(equities)

        metrics = calculate_metrics(curve, trades, Decimal("10000"))

        assert metrics.max_consecutive_losses == 3

    def test_volatility_calculated(self) -> None:
        """Test annualized volatility is calculated."""
        equities = [
            Decimal("10000"),
            Decimal("10500"),
            Decimal("9800"),
            Decimal("10200"),
            Decimal("10100"),
        ]
        curve = create_equity_curve(equities, interval_hours=24)

        metrics = calculate_metrics(curve, [], Decimal("10000"), timeframe="1d")

        assert metrics.volatility > Decimal("0")

    def test_max_drawdown_duration_unrecovered(self) -> None:
        """Test max drawdown duration when equity never recovers to peak."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak at h1
            Decimal("11000"),  # h2
            Decimal("10000"),  # h3
            Decimal("9000"),  # h4 - max drawdown trough
            Decimal("11000"),  # h5 - not recovered (< 12000)
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("3000")
        # Duration: peak (h1) to end (h5) = 4 hours (not recovered)
        assert dd_hours == 4

    def test_calmar_ratio(self) -> None:
        """Test Calmar ratio calculation."""
        # Use a 10-day equity curve for annualized return to be nonzero
        equities = [Decimal("10000") + Decimal(str(i * 100)) for i in range(240)]
        curve = create_equity_curve(equities, interval_hours=1)

        metrics = calculate_metrics(curve, [], Decimal("10000"), timeframe="1h")

        # Should have both annualized return and max drawdown > 0 for a valid Calmar
        # With constantly increasing equity, max drawdown is 0, so Calmar is 0
        assert metrics.calmar_ratio == Decimal("0")

    def test_calmar_ratio_with_drawdown(self) -> None:
        """Test Calmar ratio is calculated when drawdown exists."""
        equities = [
            Decimal("10000"),
            Decimal("11000"),
            Decimal("10500"),
            Decimal("11500"),
            Decimal("11000"),
            Decimal("12000"),
            Decimal("11500"),
            Decimal("12500"),
            Decimal("12000"),
            Decimal("13000"),
        ]
        # Make it span 10 days for annualized return
        curve = create_equity_curve(equities, interval_hours=24)

        metrics = calculate_metrics(curve, [], Decimal("10000"), timeframe="1d")

        if metrics.annualized_return != Decimal("0") and metrics.max_drawdown_pct > 0:
            assert metrics.calmar_ratio != Decimal("0")

    def test_annualized_return_zero_for_short_backtest(self) -> None:
        """Test annualized return is zero for backtests < 7 days."""
        equities = [Decimal("10000"), Decimal("11000"), Decimal("12000")]
        # 2 hours total duration (< 7 days)
        curve = create_equity_curve(equities, interval_hours=1)

        metrics = calculate_metrics(curve, [], Decimal("10000"))

        assert metrics.annualized_return == Decimal("0")

    def test_timeframe_parameter_affects_sharpe(self) -> None:
        """Test that timeframe parameter affects ratio calculations."""
        equities = [
            Decimal("10000"),
            Decimal("10100"),
            Decimal("10050"),
            Decimal("10200"),
            Decimal("10150"),
        ]
        curve = create_equity_curve(equities, interval_hours=24)

        metrics_daily = calculate_metrics(curve, [], Decimal("10000"), timeframe="1d")
        metrics_hourly = calculate_metrics(curve, [], Decimal("10000"), timeframe="1h")

        # With different timeframes, the Sharpe ratios should differ
        # (hourly annualization amplifies more than daily)
        assert metrics_daily.sharpe_ratio != metrics_hourly.sharpe_ratio


class TestDrawdownDurationRecovery:
    """Tests for drawdown duration measured peak-to-recovery."""

    def test_recovery_shortens_duration(self) -> None:
        """When equity recovers to peak, duration ends at recovery point."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak at h1
            Decimal("9000"),  # Trough at h2
            Decimal("10000"),  # h3 — partial recovery
            Decimal("12000"),  # h4 — full recovery to peak
            Decimal("13000"),  # h5 — new high
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("3000")
        # Duration: peak (h1) to recovery (h4) = 3 hours
        assert dd_hours == 3

    def test_no_recovery_uses_end_time(self) -> None:
        """When equity never recovers, duration extends to end of curve."""
        equities = [
            Decimal("10000"),
            Decimal("15000"),  # Peak at h1
            Decimal("10000"),  # Trough at h2
            Decimal("12000"),  # h3 — partial recovery only
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("5000")
        # Duration: peak (h1) to end (h3) = 2 hours (not recovered)
        assert dd_hours == 2

    def test_immediate_recovery(self) -> None:
        """Drawdown that recovers on the very next bar."""
        equities = [
            Decimal("10000"),
            Decimal("12000"),  # Peak at h1
            Decimal("11000"),  # Trough at h2
            Decimal("12000"),  # Recovery at h3
        ]
        curve = create_equity_curve(equities)

        max_dd, max_dd_pct, dd_hours = _calculate_max_drawdown(curve)

        assert max_dd == Decimal("1000")
        # Duration: peak (h1) to recovery (h3) = 2 hours
        assert dd_hours == 2
