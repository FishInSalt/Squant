"""Tests for benchmark initial price persistence in BacktestContext."""

from datetime import UTC, datetime
from decimal import Decimal

from squant.engine.backtest.context import BacktestContext
from squant.engine.backtest.types import Bar


def _make_bar(close: str, time: datetime | None = None) -> Bar:
    close_d = Decimal(close)
    return Bar(
        time=time or datetime(2024, 1, 1, tzinfo=UTC),
        symbol="BTC/USDT",
        open=close_d,
        high=close_d + Decimal("100"),
        low=close_d - Decimal("100"),
        close=close_d,
        volume=Decimal("10"),
    )


class TestBenchmarkPersistence:
    """Tests for benchmark_initial_price serialization and restoration."""

    def test_benchmark_initial_price_persisted(self):
        """build_result_snapshot includes benchmark_initial_price after recording equity."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))

        # Set up a bar and record equity to initialize benchmark
        bar = _make_bar("50000")
        ctx._set_current_bar(bar)
        ctx._add_bar_to_history(bar)
        ctx._record_equity_snapshot(bar.time)

        result = ctx.build_result_snapshot()
        assert "benchmark_initial_price" in result
        assert result["benchmark_initial_price"] == "50000"

    def test_benchmark_initial_price_restored(self):
        """restore_state recovers _benchmark_initial_price from snapshot."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))

        state = {
            "cash": "100000",
            "total_fees": "0",
            "positions": {},
            "trades": [],
            "logs": [],
            "benchmark_initial_price": "45000",
        }
        ctx.restore_state(state)

        assert ctx._benchmark_initial_price == Decimal("45000")

    def test_benchmark_none_when_not_set(self):
        """benchmark_initial_price is None when no equity snapshot has been recorded."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))
        result = ctx.build_result_snapshot()

        assert result["benchmark_initial_price"] is None

    def test_benchmark_none_in_state_does_not_set(self):
        """restore_state with benchmark_initial_price=None leaves it unset."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))

        state = {
            "cash": "100000",
            "total_fees": "0",
            "positions": {},
            "trades": [],
            "logs": [],
            "benchmark_initial_price": None,
        }
        ctx.restore_state(state)

        assert ctx._benchmark_initial_price is None

    def test_benchmark_missing_from_state_preserves_default(self):
        """restore_state without benchmark_initial_price key leaves it unchanged."""
        ctx = BacktestContext(initial_capital=Decimal("100000"))

        state = {
            "cash": "100000",
            "total_fees": "0",
            "positions": {},
            "trades": [],
            "logs": [],
        }
        ctx.restore_state(state)

        # Should remain None (default)
        assert ctx._benchmark_initial_price is None

    def test_benchmark_round_trip(self):
        """Full round trip: record → snapshot → restore → verify correct benchmark."""
        ctx1 = BacktestContext(initial_capital=Decimal("100000"))

        # Record equity at initial price
        bar1 = _make_bar("50000", datetime(2024, 1, 1, tzinfo=UTC))
        ctx1._set_current_bar(bar1)
        ctx1._add_bar_to_history(bar1)
        ctx1._record_equity_snapshot(bar1.time)

        # Snapshot
        snapshot = ctx1.build_result_snapshot()

        # Restore into new context
        ctx2 = BacktestContext(initial_capital=Decimal("100000"))
        ctx2.restore_state(snapshot)

        assert ctx2._benchmark_initial_price == Decimal("50000")

        # Now record another equity snapshot at different price
        bar2 = _make_bar("60000", datetime(2024, 1, 2, tzinfo=UTC))
        ctx2._set_current_bar(bar2)
        ctx2._add_bar_to_history(bar2)
        ctx2._record_equity_snapshot(bar2.time)

        # Benchmark should use restored initial price, not re-initialize
        assert ctx2._benchmark_initial_price == Decimal("50000")
        # Benchmark equity = 100000 * 60000 / 50000 = 120000
        latest_snapshot = ctx2.equity_curve[-1]
        assert latest_snapshot.benchmark_equity == Decimal("120000")
