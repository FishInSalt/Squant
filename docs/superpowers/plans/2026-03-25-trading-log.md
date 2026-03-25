# Trading Log Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured, file-persisted runtime logs for Live and Paper trading sessions with frontend display.

**Architecture:** Dual-write logging — `context.log()` writes to both in-memory deque (for WS push) and per-session log file (for persistence). Frontend loads historical logs from file API, receives new logs via existing WS push. Custom RotatingFileHandler with timestamp-suffixed rotation. Logs removed from result JSONB.

**Tech Stack:** Python logging module, FastAPI, Vue 3, Element Plus

**Spec:** `docs/superpowers/specs/2026-03-25-trading-log-design.md`

---

### Task 1: Trading Logger Utility

Create the per-session logger factory with custom rotation.

**Files:**
- Create: `src/squant/infra/trading_logger.py`
- Test: `tests/unit/infra/test_trading_logger.py`

- [ ] **Step 1: Write tests for trading logger**

```python
"""Tests for per-session trading logger with timestamp-suffixed rotation."""
import logging
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from squant.infra.trading_logger import create_trading_logger, cleanup_trading_logs


@pytest.fixture
def log_dir(tmp_path):
    """Temporary log directory."""
    d = tmp_path / "logs" / "trading" / "test-run-id"
    d.mkdir(parents=True)
    return d


class TestCreateTradingLogger:
    def test_creates_logger_and_file(self, tmp_path):
        run_id = "test-run-001"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        logger.info("test message")
        log_file = tmp_path / "logs" / "trading" / run_id / "trading.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "test message" in content

    def test_message_only_format(self, tmp_path):
        """Logger should write only the message, no extra metadata."""
        run_id = "test-run-002"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        logger.info("[2026-03-25 16:49:04] [INFO] [order] test order")
        log_file = tmp_path / "logs" / "trading" / run_id / "trading.log"
        content = log_file.read_text().strip()
        assert content == "[2026-03-25 16:49:04] [INFO] [order] test order"

    def test_rotation_with_timestamp_suffix(self, tmp_path):
        """When file exceeds maxBytes, rotated file gets timestamp suffix."""
        run_id = "test-run-003"
        logger = create_trading_logger(
            run_id, base_dir=str(tmp_path / "logs" / "trading"), max_bytes=100
        )
        # Write enough to trigger rotation
        for i in range(20):
            logger.info(f"[2026-03-25 16:49:{i:02d}] [INFO] [test] message number {i} padding")
        log_dir = tmp_path / "logs" / "trading" / run_id
        files = list(log_dir.iterdir())
        assert len(files) > 1  # At least one rotated file
        rotated = [f for f in files if f.name != "trading.log"]
        # Rotated files should have timestamp suffix
        for f in rotated:
            assert f.name.startswith("trading.log.")
            # Format: trading.log.YYYY-MM-DD_HHMMSS
            suffix = f.name.replace("trading.log.", "")
            assert len(suffix) == 17  # 2026-03-25_164900

    def test_close_trading_logger(self, tmp_path):
        """close_trading_logger removes handlers."""
        run_id = "test-run-004"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        from squant.infra.trading_logger import close_trading_logger
        close_trading_logger(logger)
        assert len(logger.handlers) == 0


class TestCleanupTradingLogs:
    def test_removes_log_directory(self, tmp_path):
        run_id = "test-run-005"
        log_dir = tmp_path / "logs" / "trading" / run_id
        log_dir.mkdir(parents=True)
        (log_dir / "trading.log").write_text("some logs")
        (log_dir / "trading.log.2026-03-25_120000").write_text("old logs")
        cleanup_trading_logs(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        assert not log_dir.exists()

    def test_no_error_if_dir_missing(self, tmp_path):
        """Cleanup should not raise if directory doesn't exist."""
        cleanup_trading_logs("nonexistent", base_dir=str(tmp_path / "logs" / "trading"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/infra/test_trading_logger.py -v --no-cov`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement trading logger**

```python
"""Per-session trading logger with timestamp-suffixed rotation.

Each trading session (paper/live) gets its own log directory and file.
Log entries are written as-is (message only, no extra metadata from logging module).
When the log file exceeds max_bytes, it is rotated with a timestamp suffix.
"""

import logging
import os
import shutil
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_BASE = "logs/trading"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB


class TimestampRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that renames rotated files with timestamp suffix.

    Instead of .1, .2, ... suffixes, uses .YYYY-MM-DD_HHMMSS format.
    Does not delete old rotated files (backupCount is ignored).
    """

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        # Rename current file with timestamp suffix
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        rotated_name = f"{self.baseFilename}.{timestamp}"
        if os.path.exists(self.baseFilename):
            os.rename(self.baseFilename, rotated_name)
        # Open new file
        if not self.delay:
            self.stream = self._open()


def create_trading_logger(
    run_id: str,
    base_dir: str = DEFAULT_LOG_BASE,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> logging.Logger:
    """Create a per-session file logger.

    Args:
        run_id: Session run ID (used as directory name).
        base_dir: Base directory for trading logs.
        max_bytes: Max file size before rotation.

    Returns:
        Logger instance with file handler configured.
    """
    log_dir = Path(base_dir) / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "trading.log"

    logger = logging.getLogger(f"squant.trading.{run_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Don't propagate to root logger

    handler = TimestampRotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=999,  # Effectively unlimited (doRollover ignores this)
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    return logger


def close_trading_logger(logger: logging.Logger) -> None:
    """Close and remove all handlers from a trading logger."""
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def cleanup_trading_logs(run_id: str, base_dir: str = DEFAULT_LOG_BASE) -> None:
    """Remove all log files for a session.

    Args:
        run_id: Session run ID.
        base_dir: Base directory for trading logs.
    """
    log_dir = Path(base_dir) / run_id
    if log_dir.exists():
        shutil.rmtree(log_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/infra/test_trading_logger.py -v --no-cov`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squant/infra/trading_logger.py tests/unit/infra/test_trading_logger.py
git commit -m "feat: add per-session trading logger with timestamp rotation"
```

---

### Task 2: Refactor BacktestContext.log()

Add `level`, `category`, `file_logger`, `use_real_time` parameters. Remove logs from result JSONB.

**Files:**
- Modify: `src/squant/engine/backtest/context.py`
  - `__init__` (line 42): add `file_logger` and `use_real_time` params
  - `log()` (line 717): add `level`, `category` params, dual-write
  - `build_result_snapshot()` (line 1138): remove `"logs"` field
  - `restore_state()` (lines 1226-1230): remove logs restoration
- Test: `tests/unit/engine/test_trading_log.py`

- [ ] **Step 1: Write tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/engine/test_trading_log.py -v --no-cov`
Expected: FAIL

- [ ] **Step 3: Implement changes to BacktestContext**

In `context.py`:

1. Add params to `__init__` (after line 53 `max_logs`):
   - `file_logger: logging.Logger | None = None`
   - `use_real_time: bool = False`
   - Store as `self._file_logger = file_logger` and `self._use_real_time = use_real_time`
   - Add `import logging` at top

2. Refactor `log()` method (line 717):
```python
def log(self, message: str, level: str = "info", category: str = "strategy") -> None:
    if self._use_real_time:
        timestamp = datetime.now(UTC)
    else:
        timestamp = self._current_bar.time if self._current_bar else datetime.now(UTC)
    entry = f"[{timestamp:%Y-%m-%d %H:%M:%S}] [{level.upper()}] [{category}] {message}"
    self._logs.append(entry)
    self._total_logs_added += 1
    if self._file_logger:
        self._file_logger.info(entry)
```

3. Remove `"logs"` from `build_result_snapshot()` (line 1138): delete the `"logs": list(self._logs),` line.

4. Remove logs restoration from `restore_state()` (lines 1226-1230): delete the entire `if state.get("logs")` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/engine/test_trading_log.py -v --no-cov`
Expected: ALL PASS

- [ ] **Step 5: Run existing engine tests for regressions**

Run: `uv run pytest tests/unit/engine/ -v --no-cov -n auto`
Expected: ALL PASS (existing `context.log("msg")` calls still work due to defaults)

- [ ] **Step 6: Commit**

```bash
git add src/squant/engine/backtest/context.py tests/unit/engine/test_trading_log.py
git commit -m "refactor: add level/category/file_logger to context.log(), remove logs from result JSONB"
```

---

### Task 3: Update Existing Log Calls

Add `level` and `category` parameters to all existing `context.log()` calls across engines.

**Files:**
- Modify: `src/squant/engine/backtest/runner.py` (lines 292, 326, 333, 349, 353, 383-386)
- Modify: `src/squant/engine/paper/engine.py` (lines 521, 557, 570, 594, 724-730, 753, 839, 868-871, 897)
- Modify: `src/squant/engine/backtest/context.py` (lines 387, 483 — buy/sell log calls)

- [ ] **Step 1: Update backtest runner log calls**

All calls in `runner.py`:
- Line 292: `self._context.log(f"Order {fill.order_id} rejected at fill: {e}", level="warning", category="fill")`
- Line 326: `self._context.log(f"ERROR in on_fill: {e}", level="error", category="strategy")`
- Line 333: `self._context.log(f"ERROR in on_order_done: {e}", level="error", category="strategy")`
- Line 349: `self._context.log(f"RESOURCE LIMIT EXCEEDED: {e}", level="error", category="strategy")`
- Line 353: `self._context.log(f"ERROR in on_bar: {e}", level="error", category="strategy")`
- Lines 383-386: order expiry log — add `level="info", category="order"`

- [ ] **Step 2: Update paper engine log calls**

All calls in `paper/engine.py`:
- Line 521: risk rejection → `level="warning", category="risk"`
- Line 557: on_fill error → `level="error", category="strategy"`
- Line 570: on_order_done error → `level="error", category="strategy"`
- Line 594: on_bar error → `level="error", category="strategy"`
- Lines 724-730: risk stop/cancel → `level="warning", category="risk"` / stop trigger → `level="info", category="order"`
- Line 753: stop-limit trigger → `level="info", category="order"`
- Line 839: risk rejection → `level="warning", category="risk"`
- Lines 868-871: order expiry → `level="info", category="order"`
- Line 897: fill rejected → `level="warning", category="fill"`

- [ ] **Step 3: Update context buy/sell log calls**

In `context.py`:
- Line 387 (buy): `self.log(f"提交买入 ...")` → `self.log(f"提交买入 ...", category="order")`
- Line 483 (sell): `self.log(f"提交卖出 ...")` → `self.log(f"提交卖出 ...", category="order")`

- [ ] **Step 4: Update live engine existing log calls**

In `live/engine.py`:
- Line 1156: total loss limit → `level="error", category="risk"`
- Line 1202: on_fill error → `level="error", category="strategy"`
- Line 1215: on_order_done error → `level="error", category="strategy"`
- Line 1249: on_bar error → `level="error", category="strategy"`

- [ ] **Step 5: Run all engine tests**

Run: `uv run pytest tests/unit/engine/ tests/unit/services/ -v --no-cov -n auto`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/engine/
git commit -m "refactor: add level/category to all existing context.log() calls"
```

---

### Task 4: Add New Log Events in Live Engine

Add `context.log()` calls at key live trading events that are currently not logged.

**Files:**
- Modify: `src/squant/engine/live/engine.py`

- [ ] **Step 1: Add order lifecycle logs**

In `_submit_order()` (around line 2598 — success path):
```python
self._context.log(
    f"订单已提交 {order.symbol} {order.side.value} {order.amount} "
    f"{order.type.value} → exchange:{response.order_id}",
    category="order",
)
```

In `_submit_order()` error path (around line 2652 — before `logger.exception`):
```python
self._context.log(
    f"下单失败: {e}",
    level="error",
    category="order",
)
```

In `_submit_order()` insufficient funds path (around line 2634):
```python
# The notification already fires, but log it too
self._context.log(msg, level="warning", category="order")
```

In `_submit_order()` timeout path (around line 2624):
```python
self._context.log(
    f"订单提交超时 {order.symbol} {order.side.value} {order.amount}，将在下次同步时对账",
    level="warning",
    category="order",
)
```

- [ ] **Step 2: Add fill logs**

In `_record_fill()` (around line 2366, after fill creation):
```python
side_cn = "买入" if live_order.side == OrderSide.BUY else "卖出"
fee_info = f" fee={fill_fee}"
if live_order.fee_currency:
    fee_info += f" {live_order.fee_currency}"
self._context.log(
    f"{side_cn}成交 {live_order.symbol} {fill_amount} @{fill_price}{fee_info} ({source})",
    category="fill",
)
```

- [ ] **Step 3: Add system event logs**

DMS failure — in `_activate_dead_man_switch()` or wherever DMS errors are caught (search for "dead man" in engine):
```python
self._context.log(
    f"Dead Man's Switch 续期失败: {e}",
    level="warning",
    category="system",
)
```

Order cancellation — in `_cancel_all_orders()` success path:
```python
self._context.log(
    f"订单已取消 #{internal_id[:8]}",
    category="order",
)
```

Order timeout — in `_expire_ttl_orders()`:
```python
self._context.log(
    f"订单超时已取消 #{internal_id[:8]}",
    level="warning",
    category="order",
)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/engine/live/ -v --no-cov`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/squant/engine/live/engine.py
git commit -m "feat: add context.log() calls for order/fill/system events in live engine"
```

---

### Task 5: Wire File Logger in Paper/Live Services

Create and manage per-session file loggers in service lifecycle methods.

**Files:**
- Modify: `src/squant/services/paper_trading.py` (start ~line 255, stop ~line 609, resume ~line 871)
- Modify: `src/squant/services/live_trading.py` (start ~line 320, stop ~line 992, resume ~line 1736)
- Modify: `src/squant/engine/paper/engine.py` — pass file_logger to context creation
- Modify: `src/squant/engine/live/engine.py` — pass file_logger to context creation

- [ ] **Step 1: Wire file logger in paper trading**

In `PaperTradingService.start()`: after creating the engine, before starting it:
```python
from squant.infra.trading_logger import create_trading_logger
file_logger = create_trading_logger(str(run.id))
```
Pass `file_logger` and `use_real_time=True` to BacktestContext construction (in paper engine constructor).

In `PaperTradingService.stop()`: after stopping engine:
```python
from squant.infra.trading_logger import close_trading_logger
if engine and hasattr(engine, '_file_logger') and engine._file_logger:
    close_trading_logger(engine._file_logger)
```

Same for `resume()`.

The paper engine (`PaperTradingEngine.__init__`) creates BacktestContext at line 152. Add `file_logger` and `use_real_time=True` params. Store `self._file_logger` reference for cleanup.

- [ ] **Step 2: Wire file logger in live trading**

Same pattern in `LiveTradingService.start()`, `stop()`, `resume()`.

The live engine (`LiveTradingEngine.__init__`) creates BacktestContext at line 269. Add `file_logger` and `use_real_time=True` params. Store `self._file_logger` reference.

- [ ] **Step 3: Add cleanup on session delete**

If there are delete endpoints, add `cleanup_trading_logs(run_id)` call. If not, note this for when delete is implemented.

- [ ] **Step 4: Run service tests**

Run: `uv run pytest tests/unit/services/ -v --no-cov -n auto`
Expected: ALL PASS (may need to update mocks/fixtures)

- [ ] **Step 5: Commit**

```bash
git add src/squant/services/ src/squant/engine/paper/engine.py src/squant/engine/live/engine.py
git commit -m "feat: wire per-session file logger in paper/live service lifecycle"
```

---

### Task 6: Add Log API Endpoints

Add `GET /{run_id}/logs` endpoints for paper and live.

**Files:**
- Modify: `src/squant/api/v1/paper_trading.py`
- Modify: `src/squant/api/v1/live_trading.py`
- Test: `tests/unit/api/v1/test_trading_logs_api.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for trading log API endpoints."""
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from squant.main import create_app


@pytest.fixture
def app():
    return create_app()


class TestLiveLogsEndpoint:
    async def test_returns_logs_from_file(self, app, tmp_path):
        run_id = "3f8e3b5b-423e-4d13-9bcd-630b2f2ea447"
        log_dir = tmp_path / run_id
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trading.log"
        log_file.write_text(
            "[2026-03-25 16:49:04] [INFO] [order] test line 1\n"
            "[2026-03-25 16:49:05] [ERROR] [order] test line 2\n"
        )
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["logs"]) == 2

    async def test_tail_parameter(self, app, tmp_path):
        run_id = "3f8e3b5b-423e-4d13-9bcd-630b2f2ea447"
        log_dir = tmp_path / run_id
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trading.log"
        lines = [f"[2026-03-25 16:49:{i:02d}] [INFO] [test] line {i}\n" for i in range(10)]
        log_file.write_text("".join(lines))
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs?tail=3")
        data = resp.json()["data"]
        assert len(data["logs"]) == 3
        assert "line 9" in data["logs"][-1]

    async def test_no_log_file_returns_empty(self, app, tmp_path):
        run_id = "00000000-0000-0000-0000-000000000000"
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs")
        data = resp.json()["data"]
        assert data["logs"] == []
```

- [ ] **Step 2: Implement endpoint**

In `live_trading.py`, add:
```python
from squant.infra.trading_logger import DEFAULT_LOG_BASE

TRADING_LOG_BASE = DEFAULT_LOG_BASE

@router.get("/{run_id}/logs")
async def get_trading_logs(
    run_id: UUID,
    tail: int = Query(default=500, ge=1, le=5000),
) -> ApiResponse:
    log_file = Path(TRADING_LOG_BASE) / str(run_id) / "trading.log"
    if not log_file.exists():
        return ApiResponse(code=0, data={"logs": []})
    with open(log_file, encoding="utf-8") as f:
        lines = f.readlines()
    logs = [line.rstrip("\n") for line in lines[-tail:]]
    return ApiResponse(code=0, data={"logs": logs})
```

Add the same endpoint to `paper_trading.py`.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/api/v1/test_trading_logs_api.py -v --no-cov`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/squant/api/v1/ tests/unit/api/v1/test_trading_logs_api.py
git commit -m "feat: add GET /{run_id}/logs endpoint for paper and live"
```

---

### Task 7: Clean Up Schemas and Status Responses

Remove `logs` field from status response schemas and service methods.

**Files:**
- Modify: `src/squant/schemas/paper_trading.py` (line 165: remove `logs` field)
- Modify: `src/squant/api/v1/paper_trading.py` (line 265: remove `logs=status.get(...)`)
- Modify: `src/squant/services/paper_trading.py` (`get_status()` around line 690: remove logs from fallback dict)

- [ ] **Step 1: Remove logs from PaperTradingStatusResponse**

In `schemas/paper_trading.py` line 165: delete `logs: list[str] = Field(default_factory=list)`

- [ ] **Step 2: Remove logs from paper API response construction**

In `api/v1/paper_trading.py` line 265: delete `logs=status.get("logs", []),`

- [ ] **Step 3: Remove logs from paper service get_status fallback**

In `services/paper_trading.py` `get_status()`: remove any `"logs"` key from the fallback status dict (for stopped sessions).

- [ ] **Step 4: Regenerate OpenAPI types**

```bash
./scripts/generate-api-types.sh
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/ -v --no-cov -n auto`
Expected: ALL PASS (some paper tests may need `logs` removed from expected responses)

- [ ] **Step 6: Commit**

```bash
git add src/squant/schemas/ src/squant/api/ src/squant/services/ frontend/src/types/
git commit -m "refactor: remove logs field from status response schemas"
```

---

### Task 8: Frontend — Log Tab for Live + Color Coding

Extend the log tab to both Paper and Live, add API-based loading, fix live WS handler, add color coding.

**Files:**
- Modify: `frontend/src/views/trading/SessionDetail.vue`
- Modify: `frontend/src/api/paper.ts` (add getLogs API call)
- Modify: `frontend/src/api/live.ts` (add getLogs API call)

- [ ] **Step 1: Add API functions**

In `frontend/src/api/paper.ts`:
```typescript
export function getPaperLogs(runId: string, tail = 500) {
  return get<{ logs: string[] }>(`/paper/${runId}/logs`, { tail })
}
```

In `frontend/src/api/live.ts`:
```typescript
export function getLiveLogs(runId: string, tail = 500) {
  return get<{ logs: string[] }>(`/live/${runId}/logs`, { tail })
}
```

- [ ] **Step 2: Modify SessionDetail.vue — log tab**

1. Change `v-if="isPaper"` (line 442) to remove the guard — show for both modes.

2. Replace `paperLogs` computed with a reactive ref that works for both modes:
```typescript
const tradingLogs = ref<string[]>([])
```

3. On mount / `loadStatus`, call the logs API:
```typescript
async function loadTradingLogs() {
  try {
    const resp = isPaper.value
      ? await getPaperLogs(props.id)
      : await getLiveLogs(props.id)
    tradingLogs.value = resp.logs || []
  } catch { /* ignore */ }
}
```

4. In the WS handler, add `new_logs` processing for BOTH paper and live:
```typescript
const newLogs = data.new_logs as string[] | undefined
if (Array.isArray(newLogs) && newLogs.length) {
  tradingLogs.value.push(...newLogs)
}
```

5. Remove `paperLogs` from status parsing (paper no longer sends logs in status).

- [ ] **Step 3: Add color coding**

Replace the plain text display with color-coded entries:
```vue
<div v-for="(log, index) in tradingLogs" :key="index"
     :class="['log-entry', logLevelClass(log)]">
  {{ log }}
</div>
```

```typescript
function logLevelClass(entry: string): string {
  if (entry.includes('[ERROR]')) return 'log-error'
  if (entry.includes('[WARNING]')) return 'log-warning'
  return 'log-info'
}
```

```scss
.log-error { color: #f56c6c; }
.log-warning { color: #e6a23c; }
.log-info { color: inherit; }
```

- [ ] **Step 4: Update auto-scroll watcher**

Change the watcher from `paperLogs` to `tradingLogs`:
```typescript
watch(() => tradingLogs.value.length, () => { ... })
```

- [ ] **Step 5: Test manually**

1. Start paper session → verify log tab shows with color coding
2. Start live session → verify log tab shows, WS pushes work
3. Stop and reopen session → verify historical logs load from API

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: extend log tab to live sessions with color coding and API loading"
```

---

### Task 9: Fix #11 — Duplicate Error Toast

**Files:**
- Modify: `frontend/src/views/trading/LiveTrading.vue` (line 602)

- [ ] **Step 1: Verify Axios interceptor shows error**

Check `frontend/src/api/index.ts` — confirm the response interceptor calls `ElMessage.error()` on HTTP errors.

- [ ] **Step 2: Remove duplicate toastError**

In `LiveTrading.vue` line 602, the catch block:
```typescript
} catch {
  toastError('启动失败')
}
```
Change to:
```typescript
} catch {
  // Error already shown by Axios response interceptor
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/trading/LiveTrading.vue
git commit -m "fix: remove duplicate error toast on session create (issue #11)"
```

---

### Task 10: Integration Test & Lint

**Files:** All modified files

- [ ] **Step 1: Run full unit test suite**

```bash
uv run pytest tests/unit -v --no-cov -n auto
```
Expected: ALL PASS

- [ ] **Step 2: Run lint**

```bash
./scripts/dev.sh lint
```
Fix any issues in modified files.

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && pnpm test
```

- [ ] **Step 4: Run frontend lint**

```bash
cd frontend && pnpm lint
```

- [ ] **Step 5: Final commit (if lint fixes needed)**

```bash
git add -A
git commit -m "style: fix lint issues"
```
