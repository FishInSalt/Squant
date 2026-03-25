# Trading Log Feature Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured, file-persisted runtime logs for Live and Paper trading sessions, making strategy decisions, order events, risk actions, and system events visible to users in real time.

**Motivation:** During live trading, critical events (exchange errors, risk rejections, order failures) are only visible in backend log files. Users have no way to know why an order wasn't placed or why a session stopped. This feature surfaces runtime events directly in the session UI.

---

## 1. Log Infrastructure

### 1.1 `context.log()` Refactor

Current signature:
```python
def log(self, message: str) -> None
```

New signature:
```python
def log(self, message: str, level: str = "info", category: str = "strategy") -> None
```

- `level`: `"info"` | `"warning"` | `"error"`
- `category`: `"strategy"` | `"order"` | `"fill"` | `"risk"` | `"system"`
- Default values ensure backward compatibility with existing `context.log("msg")` calls.

Log entry format (plain text with tags):
```
[2026-03-25 16:49:04] [INFO] [strategy] 提交买入 BTC/USDT 0.01 市价 #926c5fa2
[2026-03-25 16:49:04] [ERROR] [order] 下单失败: OKX 50001 Service temporarily unavailable
[2026-03-25 16:49:18] [WARNING] [system] Dead Man's Switch 续期失败
```

Implementation:
```python
def log(self, message: str, level: str = "info", category: str = "strategy") -> None:
    timestamp = datetime.now(UTC)
    entry = f"[{timestamp:%Y-%m-%d %H:%M:%S}] [{level.upper()}] [{category}] {message}"
    self._logs.append(entry)
    self._total_logs_added += 1
    if self._file_logger:
        self._file_logger.info(entry)
```

`BacktestContext.__init__` accepts an optional `file_logger: logging.Logger | None = None`. File content and `_logs` deque content are identical strings.

Timestamp always uses `datetime.now(UTC)` (real event time), replacing the previous `self._current_bar.time` which was bar time.

### 1.2 Per-Session Log File

**Directory structure:**
```
logs/trading/{run_id}/
  ├── trading.log                        # current log file
  ├── trading.log.2026-03-25_163000      # rotated file (timestamp suffix)
  └── trading.log.2026-03-26_120000
```

**File handler setup (Live/Paper engine):**
- Python `logging.Logger` with custom `RotatingFileHandler`
- `maxBytes=10MB`, rotate with timestamp suffix (e.g., `trading.log.2026-03-25_163000`)
- `backupCount` effectively unlimited (no automatic deletion of rotated files)
- Formatter: `logging.Formatter("%(message)s")` — writes entry text only, no extra metadata
- Backtest does NOT create file logger (results are transient)

**Lifecycle:**
- Engine start: create logger + file handler, pass to BacktestContext
- Engine stop: close and remove file handler
- Session delete: `shutil.rmtree(f"logs/trading/{run_id}")` removes directory and all log files

### 1.3 Remove Logs from Result JSONB

- `build_result_snapshot()`: remove `"logs": list(self._logs)` field
- `restore_state()`: remove logs restoration logic
- `_logs` deque starts empty on resume; historical logs are in the file
- Reduces result JSONB size; separates concerns (result = trading state, file = runtime logs)

---

## 2. Engine Log Events

### 2.1 Log Categories and Events

**`order` — Order lifecycle (Live engine):**
- `[INFO]` Order submitted successfully (with exchange order ID)
- `[ERROR]` Order submission failed (with exchange error message)
- `[WARNING]` Insufficient funds (buy: 余额不足, sell: 持仓不足)
- `[INFO]` Order cancelled
- `[WARNING]` Order timed out and cancelled

**`fill` — Trade execution:**
- `[INFO]` Fill received (price, amount, fee, fee_currency)
- Existing trade tracking logs (open/close/increase position) — add level=info, category=fill

**`risk` — Risk management:**
- `[WARNING]` Order rejected by risk manager (with reason)
- `[ERROR]` Circuit breaker triggered / total loss limit
- Existing `context.log("Order rejected (risk): ...")` calls — add level/category params

**`system` — Infrastructure events (Live engine):**
- `[WARNING]` Dead Man's Switch renewal failed
- `[WARNING]` Private WebSocket disconnected
- `[INFO]` Private WebSocket reconnected
- `[INFO]` Reconciliation completed (with summary)
- `[WARNING]` Cash/position discrepancy detected

**`strategy` — Strategy events (existing, add level/category):**
- `[INFO]` 提交买入/卖出 (existing calls in context.buy/sell)
- `[ERROR]` Strategy on_bar/on_fill/on_order_done error

### 2.2 Paper Engine

Same categories but fewer events (no exchange interaction):
- `strategy`: buy/sell submissions, strategy errors
- `fill`: simulated fill notifications, trade tracking
- `risk`: risk rejections
- `system`: not applicable (no WS, no DMS)
- `order`: not applicable (no exchange orders)

---

## 3. Frontend

### 3.1 Log Tab

- Remove `v-if="isPaper"` guard — show log tab for both Paper and Live sessions
- On page load: call `GET /api/v1/{mode}/{run_id}/logs?tail=500` to load historical logs from file
- On WS `new_logs`: append incrementally (existing mechanism, unchanged)
- Color coding by keyword matching:
  - `[ERROR]` → red text
  - `[WARNING]` → yellow/orange text
  - `[INFO]` → default text
- Existing auto-scroll toggle preserved

### 3.2 API Endpoint

**`GET /api/v1/paper/{run_id}/logs?tail=500`**
**`GET /api/v1/live/{run_id}/logs?tail=500`**

- Reads log file(s) from `logs/trading/{run_id}/trading.log`
- `tail` parameter: return last N lines (default 500)
- Returns `{"code": 0, "data": {"logs": ["[2026-03-25 ...] ...", ...]}}`
- No log file → return empty array
- For rotated files: only reads current `trading.log` (rotated files are for user's manual inspection)

---

## 4. Bug Fixes Included

### 4.1 Issue #10: Exchange Temporary Unavailability

`_submit_order` failure now logs via `context.log(msg, level="error", category="order")`. Users can see the exact exchange error in the log tab. No change to existing REJECT behavior (retry mechanism is a separate feature).

### 4.2 Issue #11: Duplicate Error Toast on Session Create

Remove `toastError` in `LiveTrading.vue` `handleSubmit` catch block — Axios interceptor already displays the error.

---

## 5. Data Flow Summary

**Running session:**
```
Engine event → context.log(msg, level, category)
                 ├─ _logs deque (in-memory)
                 │    └─ bar_update WS → new_logs → frontend append
                 └─ file_logger → logs/trading/{run_id}/trading.log
```

**Page load (running or stopped session):**
```
Frontend → GET /api/v1/{mode}/{run_id}/logs?tail=500
              └─ reads logs/trading/{run_id}/trading.log → response
```

**Resume:**
```
_logs deque starts empty (no restore from result JSONB)
Historical logs available via file API
New logs accumulate in deque + file from resume point
```

---

## 6. Files Changed (Estimated)

| File | Change |
|------|--------|
| `engine/backtest/context.py` | Refactor `log()`, add `file_logger` param, remove logs from snapshot/restore |
| `engine/backtest/types.py` | No change |
| `engine/live/engine.py` | Add ~15 `context.log()` calls at key events |
| `engine/paper/engine.py` | Add level/category to existing log calls, create file logger |
| `engine/backtest/runner.py` | Add level/category to existing log calls |
| `services/live_trading.py` | Create/cleanup file logger in start/stop/resume |
| `services/paper_trading.py` | Create/cleanup file logger in start/stop/resume |
| `api/v1/live_trading.py` | Add `GET /{run_id}/logs` endpoint |
| `api/v1/paper_trading.py` | Add `GET /{run_id}/logs` endpoint |
| `frontend/SessionDetail.vue` | Remove isPaper guard on log tab, add color coding, load from API |
| `frontend/LiveTrading.vue` | Fix #11: remove duplicate toastError |
| `infra/trading_logger.py` (new) | Per-session logger factory with custom RotatingFileHandler |
