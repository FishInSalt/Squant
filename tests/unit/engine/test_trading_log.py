"""Tests for BacktestContext.log() refactor with level, category, and file logger."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from squant.engine.backtest.context import BacktestContext


@pytest.fixture
def ctx():
    return BacktestContext(initial_capital=Decimal("10000"))


@pytest.fixture
def ctx_with_file_logger(tmp_path):
    logger = logging.getLogger("test.trading.log")
    logger.handlers.clear()
    handler = logging.FileHandler(tmp_path / "test.log")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    ctx = BacktestContext(
        initial_capital=Decimal("10000"),
        file_logger=logger,
        use_real_time=True,
    )
    yield ctx, tmp_path / "test.log"
    handler.close()


class TestLogMethod:
    def test_default_level_and_category(self, ctx):
        ctx.log("test message")
        assert len(ctx._logs) == 1
        entry = ctx._logs[0]
        assert "[INFO]" in entry
        assert "[strategy]" in entry
        assert "test message" in entry

    def test_custom_level_and_category(self, ctx):
        ctx.log("order failed", level="error", category="order")
        entry = ctx._logs[0]
        assert "[ERROR]" in entry
        assert "[order]" in entry

    def test_warning_level(self, ctx):
        ctx.log("balance low", level="warning", category="system")
        entry = ctx._logs[0]
        assert "[WARNING]" in entry
        assert "[system]" in entry

    def test_total_logs_incremented(self, ctx):
        ctx.log("msg1")
        ctx.log("msg2")
        assert ctx._total_logs_added == 2

    def test_backtest_uses_bar_time(self, ctx):
        """Backtest (use_real_time=False) should use bar time."""
        from squant.engine.backtest.types import Bar
        bar = Bar(
            symbol="BTC/USDT",
            time=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
            open=Decimal("50000"), high=Decimal("50100"),
            low=Decimal("49900"), close=Decimal("50050"),
            volume=Decimal("100"),
        )
        ctx._set_current_bar(bar)
        ctx.log("test")
        assert "2026-01-15 12:00:00" in ctx._logs[0]

    def test_live_uses_real_time(self):
        """Paper/Live (use_real_time=True) should use datetime.now."""
        ctx = BacktestContext(
            initial_capital=Decimal("10000"), use_real_time=True
        )
        ctx.log("test")
        # Should be close to current time
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:")
        assert now_str in ctx._logs[0]

    def test_file_logger_receives_entry(self, ctx_with_file_logger):
        ctx, log_file = ctx_with_file_logger
        ctx.log("file test", level="error", category="order")
        # Flush
        for h in ctx._file_logger.handlers:
            h.flush()
        content = log_file.read_text()
        assert "[ERROR]" in content
        assert "[order]" in content
        assert "file test" in content

    def test_no_file_logger_still_works(self, ctx):
        """Without file_logger, log() should not raise."""
        ctx.log("safe message")
        assert len(ctx._logs) == 1


class TestResultSnapshotNoLogs:
    def test_logs_not_in_snapshot(self, ctx):
        ctx.log("msg1")
        ctx.log("msg2")
        snapshot = ctx.build_result_snapshot()
        assert "logs" not in snapshot

    def test_restore_state_ignores_logs(self, ctx):
        """restore_state should not crash when state has logs (old format)."""
        state = {"cash": "10000", "logs": ["[2026] old log"]}
        ctx.restore_state(state)
        # _logs should remain empty (not restored from state)
        assert len(ctx._logs) == 0
