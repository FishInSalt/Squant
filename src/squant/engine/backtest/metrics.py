"""Performance metrics calculation for backtests.

Calculates standard performance metrics including:
- Returns (total, annualized)
- Risk metrics (max drawdown, Sharpe ratio, Sortino ratio)
- Trade statistics (win rate, profit factor)
"""

import math
from dataclasses import dataclass
from decimal import Decimal

from squant.engine.backtest.types import EquitySnapshot, TradeRecord


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a backtest.

    All percentage values are expressed as decimals (e.g., 0.1 = 10%).
    """

    # Return metrics
    total_return: Decimal = Decimal("0")
    total_return_pct: Decimal = Decimal("0")
    annualized_return: Decimal = Decimal("0")

    # Risk metrics
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    sharpe_ratio: Decimal = Decimal("0")
    sortino_ratio: Decimal = Decimal("0")
    calmar_ratio: Decimal = Decimal("0")

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    avg_trade_return: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")

    # Duration metrics
    avg_trade_duration_hours: Decimal = Decimal("0")
    total_duration_days: int = 0

    # Fee metrics
    total_fees: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "total_return": str(self.total_return),
            "total_return_pct": str(self.total_return_pct),
            "annualized_return": str(self.annualized_return),
            "max_drawdown": str(self.max_drawdown),
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "sharpe_ratio": str(self.sharpe_ratio),
            "sortino_ratio": str(self.sortino_ratio),
            "calmar_ratio": str(self.calmar_ratio),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "avg_trade_return": str(self.avg_trade_return),
            "avg_win": str(self.avg_win),
            "avg_loss": str(self.avg_loss),
            "largest_win": str(self.largest_win),
            "largest_loss": str(self.largest_loss),
            "avg_trade_duration_hours": str(self.avg_trade_duration_hours),
            "total_duration_days": self.total_duration_days,
            "total_fees": str(self.total_fees),
        }


def calculate_metrics(
    equity_curve: list[EquitySnapshot],
    trades: list[TradeRecord],
    initial_capital: Decimal,
    total_fees: Decimal = Decimal("0"),
    risk_free_rate: Decimal = Decimal("0.02"),  # 2% annual risk-free rate
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics.

    Args:
        equity_curve: List of equity snapshots over time.
        trades: List of completed trades.
        initial_capital: Starting capital.
        total_fees: Total fees paid.
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino calculations.

    Returns:
        PerformanceMetrics with all calculated values.
    """
    metrics = PerformanceMetrics()
    metrics.total_fees = total_fees

    if not equity_curve:
        return metrics

    # Calculate returns
    final_equity = equity_curve[-1].equity
    metrics.total_return = final_equity - initial_capital
    if initial_capital > 0:
        metrics.total_return_pct = metrics.total_return / initial_capital * 100

    # Duration - use total_seconds for accurate sub-day calculation
    start_time = equity_curve[0].time
    end_time = equity_curve[-1].time
    duration = end_time - start_time
    duration_seconds = duration.total_seconds()
    # Convert to days with fractional precision
    duration_days = Decimal(str(duration_seconds)) / Decimal("86400")
    metrics.total_duration_days = max(1, duration.days)  # For display (integer days)

    # Annualized return - only calculate for backtests >= 1 day
    # For shorter periods, annualization produces meaningless extreme values
    if duration_days >= Decimal("1") and initial_capital > 0:
        years = duration_days / Decimal("365")
        total_return_factor = final_equity / initial_capital
        if total_return_factor > 0 and years > 0:
            try:
                # Annualized return = (1 + total_return)^(1/years) - 1
                annualized_factor = Decimal(
                    str(math.pow(float(total_return_factor), float(1 / years)))
                )
                metrics.annualized_return = (annualized_factor - 1) * 100
            except (OverflowError, ValueError):
                # Extreme values, cap at reasonable maximum
                metrics.annualized_return = (
                    Decimal("9999.99") if total_return_factor > 1 else Decimal("-99.99")
                )

    # Max drawdown
    metrics.max_drawdown, metrics.max_drawdown_pct = _calculate_max_drawdown(equity_curve)

    # Sharpe and Sortino ratios
    metrics.sharpe_ratio = _calculate_sharpe_ratio(equity_curve, risk_free_rate)
    metrics.sortino_ratio = _calculate_sortino_ratio(equity_curve, risk_free_rate)

    # Calmar ratio (annualized return / max drawdown)
    if metrics.max_drawdown_pct > 0:
        metrics.calmar_ratio = metrics.annualized_return / metrics.max_drawdown_pct

    # Trade statistics
    if trades:
        _calculate_trade_statistics(metrics, trades)

    return metrics


def _calculate_max_drawdown(equity_curve: list[EquitySnapshot]) -> tuple[Decimal, Decimal]:
    """Calculate maximum drawdown.

    Args:
        equity_curve: List of equity snapshots.

    Returns:
        Tuple of (max_drawdown_absolute, max_drawdown_percentage).
    """
    if len(equity_curve) < 2:
        return Decimal("0"), Decimal("0")

    max_equity = equity_curve[0].equity
    max_drawdown = Decimal("0")
    max_drawdown_pct = Decimal("0")

    for snapshot in equity_curve:
        if snapshot.equity > max_equity:
            max_equity = snapshot.equity

        drawdown = max_equity - snapshot.equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            if max_equity > 0:
                max_drawdown_pct = drawdown / max_equity * 100

    return max_drawdown, max_drawdown_pct


def _calculate_sharpe_ratio(
    equity_curve: list[EquitySnapshot],
    risk_free_rate: Decimal,
) -> Decimal:
    """Calculate Sharpe ratio.

    Sharpe = (portfolio_return - risk_free_rate) / portfolio_std_dev

    Args:
        equity_curve: List of equity snapshots.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Annualized Sharpe ratio.
    """
    if len(equity_curve) < 2:
        return Decimal("0")

    # Calculate periodic returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        if prev_equity > 0:
            returns.append(float((curr_equity - prev_equity) / prev_equity))

    if not returns or len(returns) < 2:
        return Decimal("0")

    # Calculate mean and standard deviation
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0

    if std_dev == 0:
        return Decimal("0")

    # Estimate periods per year (assume daily equity snapshots or infer from data)
    duration_days = (equity_curve[-1].time - equity_curve[0].time).days
    periods_per_day = len(equity_curve) / max(1, duration_days) if duration_days > 0 else 1
    periods_per_year = periods_per_day * 365

    # Annualize
    annualized_return = mean_return * periods_per_year
    annualized_std = std_dev * math.sqrt(periods_per_year)
    annual_risk_free = float(risk_free_rate)

    sharpe = (annualized_return - annual_risk_free) / annualized_std
    return Decimal(str(round(sharpe, 4)))


def _calculate_sortino_ratio(
    equity_curve: list[EquitySnapshot],
    risk_free_rate: Decimal,
) -> Decimal:
    """Calculate Sortino ratio.

    Similar to Sharpe but only uses downside deviation.

    Args:
        equity_curve: List of equity snapshots.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Annualized Sortino ratio.
    """
    if len(equity_curve) < 2:
        return Decimal("0")

    # Calculate periodic returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        if prev_equity > 0:
            returns.append(float((curr_equity - prev_equity) / prev_equity))

    if not returns or len(returns) < 2:
        return Decimal("0")

    # Calculate mean and downside deviation
    mean_return = sum(returns) / len(returns)
    negative_returns = [r for r in returns if r < 0]

    if not negative_returns:
        # No negative returns means infinite Sortino (cap at high value)
        return Decimal("99.99")

    downside_variance = sum(r**2 for r in negative_returns) / len(returns)
    downside_dev = math.sqrt(downside_variance) if downside_variance > 0 else 0

    if downside_dev == 0:
        return Decimal("0")

    # Estimate periods per year
    duration_days = (equity_curve[-1].time - equity_curve[0].time).days
    periods_per_day = len(equity_curve) / max(1, duration_days) if duration_days > 0 else 1
    periods_per_year = periods_per_day * 365

    # Annualize
    annualized_return = mean_return * periods_per_year
    annualized_downside = downside_dev * math.sqrt(periods_per_year)
    annual_risk_free = float(risk_free_rate)

    sortino = (annualized_return - annual_risk_free) / annualized_downside
    return Decimal(str(round(sortino, 4)))


def _calculate_trade_statistics(metrics: PerformanceMetrics, trades: list[TradeRecord]) -> None:
    """Calculate trade-based statistics.

    Args:
        metrics: Metrics object to update.
        trades: List of completed trades.
    """
    closed_trades = [t for t in trades if t.is_closed]
    metrics.total_trades = len(closed_trades)

    if not closed_trades:
        return

    # Win/loss counts
    wins = [t for t in closed_trades if t.pnl > 0]
    losses = [t for t in closed_trades if t.pnl < 0]
    metrics.winning_trades = len(wins)
    metrics.losing_trades = len(losses)

    # Win rate
    metrics.win_rate = Decimal(str(len(wins))) / Decimal(str(len(closed_trades))) * 100

    # Average returns
    total_pnl = sum(t.pnl for t in closed_trades)
    metrics.avg_trade_return = total_pnl / len(closed_trades)

    # Average win/loss
    if wins:
        metrics.avg_win = sum(t.pnl for t in wins) / len(wins)
        metrics.largest_win = max(t.pnl for t in wins)

    if losses:
        metrics.avg_loss = sum(t.pnl for t in losses) / len(losses)
        metrics.largest_loss = min(t.pnl for t in losses)

    # Profit factor (gross profit / gross loss)
    gross_profit = sum(t.pnl for t in wins) if wins else Decimal("0")
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else Decimal("0")

    if gross_loss > 0:
        metrics.profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        metrics.profit_factor = Decimal("99.99")  # Infinite profit factor capped

    # Average trade duration
    durations = []
    for t in closed_trades:
        if t.exit_time and t.entry_time:
            duration = (t.exit_time - t.entry_time).total_seconds() / 3600
            durations.append(duration)

    if durations:
        metrics.avg_trade_duration_hours = Decimal(str(round(sum(durations) / len(durations), 2)))
