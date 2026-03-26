# Real-Time Event Push Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Achieve sub-second event push for all trading state changes by replacing the bar-loop-driven processing model with a unified event-driven architecture.

**Architecture:** Live engine gets a single `asyncio.Queue` consumer (`_event_loop`) that processes WS fills, WS order updates, and bar closes through one path. Paper engine replaces its event format to match (no event loop needed). Frontend handles `state_update` (instant) + `bar_close` (periodic) instead of the old `bar_update` + `fill`.

**Tech Stack:** Python 3.12 asyncio, Vue 3 + TypeScript, Redis pub/sub (unchanged passthrough)

**Spec:** `docs/superpowers/specs/2026-03-26-realtime-event-push-design.md`

---

## File Structure

### Backend (modify)
- `src/squant/engine/live/engine.py` — Event model, event loop, process_candle refactor, event builders, lifecycle
- `src/squant/engine/paper/engine.py` — Replace `_build_fill_event` + `_build_bar_update_event` with unified format

### Frontend (modify)
- `frontend/src/types/trading.ts` — New `TradingStateSnapshot`, `StateUpdateEvent`, `BarCloseEvent` types; delete `TradingBarUpdate`, `TradingFillEvent`
- `frontend/src/views/trading/SessionDetail.vue` — Rewrite `handleTradingEvent()` for `state_update` + `bar_close`

### Tests (create)
- `tests/unit/engine/test_event_loop.py` — Event loop unit tests (3 event types, emergency close, error recovery, lifecycle)
- `tests/unit/engine/test_event_builders.py` — `_build_state_update_event` + `_build_bar_close_event` output format
- `tests/unit/engine/test_paper_state_update.py` — Paper engine unified event format

### Unchanged (verified — spec listed services as "minor changes" but the event callback is opaque `dict → Redis pub/sub`)
- `src/squant/services/live_trading.py`, `paper_trading.py` — `_create_event_callback` wraps any dict in `{"type": "trading_status", ...}` and publishes. No dict key inspection, no changes needed.
- `src/squant/websocket/` — Transparent JSON passthrough
- Frontend WebSocket store — Transparent callback routing

---

## Task Dependency Graph

```
Task 1 (Event Model + Shared Builder)
  ↓
Task 2 (Event Loop + Lifecycle)
  ↓
Task 3 (process_candle Refactor)
  ↓
Task 4 (WS Callbacks + Delete Old Code)
  ↓
Task 5 (Live Engine Tests)
  ↓
Task 6 (Paper Engine)
  ↓
Task 7 (Frontend Types + Handler)
  ↓
Task 8 (Cross-cutting Tests + Lint)
```

---

### Task 1: Event Model + Shared State Builder

**Context:** Define the new event types and extract a shared `_build_state_snapshot()` method from the existing `_build_bar_update_event()`. This is the foundation all other tasks depend on.

**Files:**
- Modify: `src/squant/engine/live/engine.py`
- Test: `tests/unit/engine/test_event_builders.py`

**What to do:**

1. Add imports at top of `engine.py`: `from asyncio import Queue` (asyncio is already imported)

2. Add event model after existing imports (before `_WS_STATUS_MAP`):

```python
class EngineEventType(str, Enum):
    """Event types processed by the unified event loop."""
    WS_FILL = "ws_fill"
    WS_ORDER = "ws_order"
    BAR_CLOSE = "bar_close"

@dataclass(frozen=True)
class EngineEvent:
    """Immutable event wrapper for the engine queue."""
    type: EngineEventType
    data: Any  # WSTradeExecution | WSOrderUpdate | WSCandle
    received_at: datetime
```

3. Extract `_build_state_snapshot()` from existing `_build_bar_update_event()` (lines 2976-3032). The new method returns the `state` dict + incremental data (new_fills, new_trades, new_logs) as a tuple. The existing `_build_bar_update_event()` calls this method. This is a safe refactoring step — existing behavior is unchanged.

```python
def _build_state_snapshot(self) -> tuple[dict[str, Any], list, list, list]:
    """Build state snapshot + incremental data. Used by both state_update and bar_close builders.

    Returns:
        (state_dict, new_fills_serialized, new_trades_serialized, new_logs)
    """
    ctx = self._context

    fill_delta = ctx._total_fills_added - self._last_emitted_fill_total
    trade_delta = ctx._total_trades_added - self._last_emitted_trade_total
    log_delta = ctx._total_logs_added - self._last_emitted_log_total

    new_fills = list(ctx._fills)[-fill_delta:] if fill_delta > 0 else []
    new_trades = list(ctx._trades)[-trade_delta:] if trade_delta > 0 else []
    new_logs = list(ctx._logs)[-log_delta:] if log_delta > 0 else []

    self._last_emitted_fill_total = ctx._total_fills_added
    self._last_emitted_trade_total = ctx._total_trades_added
    self._last_emitted_log_total = ctx._total_logs_added

    usdt_equiv = ctx.get_fees_usdt_equivalent()
    state = {
        "cash": str(ctx._cash),
        "equity": str(ctx.equity),
        "unrealized_pnl": str(ctx._get_unrealized_pnl()),
        "realized_pnl": str(ctx._cumulative_realized_pnl),
        "total_fees": str(ctx._total_fees),
        "fees_by_currency": {k: str(v) for k, v in ctx._fees_by_currency.items()},
        "fees_usdt_equivalent": str(usdt_equiv) if usdt_equiv is not None else None,
        "positions": {
            sym: {
                "amount": str(pos.amount),
                "avg_entry_price": str(pos.avg_entry_price),
            }
            for sym, pos in ctx._positions.items()
            if pos.amount != 0
        },
        "pending_orders": [
            {
                "id": o.id,
                "symbol": o.symbol,
                "side": o.side.value,
                "type": o.type.value,
                "amount": str(o.amount),
                "price": str(o.price) if o.price else None,
                "status": o.status.value,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in ctx._pending_orders
        ],
        "open_trade": _serialize_open_trade(ctx._open_trade),
        "completed_orders_count": ctx._restored_completed_orders_count + len(ctx._completed_orders),
        "trades_count": len(ctx._trades),
        "risk_state": self._risk_manager.get_state_summary(),
    }

    return (
        state,
        [_serialize_fill(f) for f in new_fills],
        [_serialize_trade(t) for t in new_trades],
        new_logs,
    )
```

4. Refactor existing `_build_bar_update_event()` to call `_build_state_snapshot()`:

```python
def _build_bar_update_event(self) -> dict[str, Any]:
    """Build incremental bar update event for WebSocket push."""
    state, new_fills, new_trades, new_logs = self._build_state_snapshot()
    return {
        "event": "bar_update",
        "run_id": str(self._run_id),
        "bar_count": self._bar_count,
        **state,  # Flatten state into top-level (backward compat)
        "new_fills": new_fills,
        "new_trades": new_trades,
        "new_logs": new_logs,
    }
```

**Important:** The refactored `_build_bar_update_event()` must produce an identical output shape to the original. The existing method puts state fields at the top level (not nested under `"state"`), so we use `**state` spread. This preserves backward compatibility during the transition.

5. Write tests for `_build_state_snapshot()` output format.

- [ ] **Step 1:** Write test file `tests/unit/engine/test_event_builders.py` with tests for `_build_state_snapshot()` return structure: verify it returns a 4-tuple, state dict has all required keys (cash, equity, positions, pending_orders, open_trade, completed_orders_count, trades_count, risk_state, fees fields), new_fills/new_trades/new_logs are lists, delta counters update correctly.

- [ ] **Step 2:** Implement `EngineEventType`, `EngineEvent`, `_build_state_snapshot()` in `engine.py`.

- [ ] **Step 3:** Refactor `_build_bar_update_event()` to use `_build_state_snapshot()`.

- [ ] **Step 4:** Run tests: `uv run pytest tests/unit/engine/test_event_builders.py -v --no-cov`

- [ ] **Step 5:** Run existing tests to verify no regression: `uv run pytest tests/unit/engine/ -v --no-cov`

- [ ] **Step 6:** Commit: `git commit -m "refactor: extract _build_state_snapshot from _build_bar_update_event"`

---

### Task 2: Event Loop + Lifecycle

**Context:** Add the unified event loop and wire it into engine lifecycle (start/stop). The event loop is created but not yet connected to any event sources — that comes in Tasks 3 and 4.

**Files:**
- Modify: `src/squant/engine/live/engine.py` (add `_event_loop`, modify `__init__`, `start`, `stop`)
- Test: `tests/unit/engine/test_event_loop.py`

**What to do:**

1. In `__init__()`, add after existing deque initialization (~line 338):

```python
self._event_queue: Queue[EngineEvent] = Queue(maxsize=1000)
self._event_loop_task: asyncio.Task | None = None
```

2. Add `_event_loop()` method (see spec for full pseudocode). Key points:
   - `while self._is_running` outer loop
   - `asyncio.wait_for(self._event_queue.get(), timeout=1.0)` with TimeoutError → continue
   - Update `self._last_active_at` on every event
   - `push_event = None` before lock
   - `async with self._processing_lock:` — check `_is_running`, check `_emergency_close_in_progress` for WS events
   - `match event.type:` with 3 cases (WS_FILL calls `_process_trade_execution` + flush + build; WS_ORDER calls `_process_single_ws_update` + flush + build; BAR_CLOSE calls `_handle_bar_close`)
   - Exception handling: WS events → log + skip; BAR_CLOSE → `await self.stop(error=...)` + return
   - Fire-and-forget push OUTSIDE the lock

3. **For now, WS_FILL and WS_ORDER cases can just log a placeholder** (the actual processing methods aren't rewired yet). BAR_CLOSE will call `_handle_bar_close` which doesn't exist yet — we'll add a stub.

4. Add stub: `async def _handle_bar_close(self, candle: WSCandle) -> None: pass`

5. In `start()`, after line 606 (`self._strategy.on_init()`), add:
```python
self._event_loop_task = asyncio.create_task(self._event_loop())
self._event_loop_task.add_done_callback(self._on_event_loop_done)
```

6. Add callback:
```python
def _on_event_loop_done(self, task: asyncio.Task) -> None:
    """Detect unexpected event loop exit."""
    if not task.cancelled() and task.exception() and self._is_running:
        logger.error(f"Event loop crashed for {self._run_id}: {task.exception()}")
        asyncio.create_task(self.stop(error=f"Event loop crashed: {task.exception()}"))
```

7. In `stop()`, after setting `_is_running = False` (line 634), add event loop shutdown:
```python
if self._event_loop_task and not self._event_loop_task.done():
    if self._event_loop_task != asyncio.current_task():
        try:
            await asyncio.wait_for(self._event_loop_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._event_loop_task.cancel()
```

- [ ] **Step 1:** Write test file `tests/unit/engine/test_event_loop.py` with:
  - Test event loop processes WS_FILL, WS_ORDER, BAR_CLOSE events from queue
  - Test event loop skips WS events when `_emergency_close_in_progress` is True (Critical — P0-2 race condition)
  - Test event loop exits when `_is_running` becomes False
  - Test `_on_event_loop_done` callback triggers stop on unexpected crash
  - **Test stop() from _handle_bar_close — no deadlock** (Critical): simulate `_handle_bar_close` calling `self.stop()` (e.g., via risk limit), verify event loop exits cleanly without deadlock. The key assertion: `stop()` detects `_event_loop_task == asyncio.current_task()` and skips the await.

- [ ] **Step 2:** Implement `_event_loop()`, `_on_event_loop_done()`, stub `_handle_bar_close()`, and lifecycle changes in `__init__()`, `start()`, `stop()`.

- [ ] **Step 3:** Run tests: `uv run pytest tests/unit/engine/test_event_loop.py -v --no-cov`

- [ ] **Step 4:** Run full engine tests: `uv run pytest tests/unit/engine/ -v --no-cov`

- [ ] **Step 5:** Commit: `git commit -m "feat: add unified event loop with lifecycle management"`

---

### Task 3: process_candle Refactor

**Context:** Split `process_candle()` into a thin filter/router (guards + Queue.put) and `_handle_bar_close()` (the actual processing body). This is the highest-risk mechanical change.

**Files:**
- Modify: `src/squant/engine/live/engine.py` (lines 1049-1298)

**What to do:**

1. Create `_handle_bar_close(self, candle: WSCandle) -> None` by moving the body of `process_candle()` from inside `async with self._processing_lock:` (lines 1115-1297) into this new async method. Remove `_drain_ws_updates()` call (line 1131). Keep everything else unchanged.

2. Thin `process_candle()` to keep only the guards (lines 1063-1108: `_is_running`, `_emergency_close`, `_circuit_breaker`, `is_closed`, symbol check, dedup check), then:
```python
# Route to event loop — await guarantees delivery
await self._event_queue.put(
    EngineEvent(EngineEventType.BAR_CLOSE, candle, datetime.now(UTC))
)
```

3. Remove `async with self._processing_lock:` from `process_candle()` — the lock is now in the event loop.

4. In `_handle_bar_close()`, replace the bar_update emit block (existing lines 1278-1286) with bar_close emit. For now, keep calling `_build_bar_update_event()` — we'll replace it in Task 5.

**Critical:** This task does NOT connect WS callbacks to the Queue yet. The old `_drain_ws_updates()` is removed from the bar path, but WS events still go into deques. They will simply accumulate unused until Task 4 wires them to the Queue.

**Verification:** All existing tests should still pass because:
- `process_candle()` still routes to the same logic (via Queue → event loop → `_handle_bar_close`)
- WS events are still buffered in deques (not processed, but tests don't depend on WS event processing within `process_candle`)

- [ ] **Step 1:** Create `_handle_bar_close()` by moving the `process_candle` body.

- [ ] **Step 2:** Thin `process_candle()` to guards + `await self._event_queue.put()`.

- [ ] **Step 3:** Run tests: `uv run pytest tests/unit/engine/ -v --no-cov`

- [ ] **Step 4:** Commit: `git commit -m "refactor: split process_candle into guard + _handle_bar_close"`

---

### Task 4: WS Callbacks → Queue + Delete Old Code

**Context:** Wire WS callbacks to put events into the Queue instead of deques. Delete the now-unused deques and `_drain_ws_updates()`.

**Files:**
- Modify: `src/squant/engine/live/engine.py`

**What to do:**

1. Modify `on_order_update()` (line 1300): keep `_emergency_close_in_progress` guard, replace `self._pending_ws_updates.append(update)` with:
```python
try:
    self._event_queue.put_nowait(
        EngineEvent(EngineEventType.WS_ORDER, update, datetime.now(UTC))
    )
except asyncio.QueueFull:
    logger.warning(f"Event queue full, dropping WS_ORDER for {self._run_id}")
```

2. Modify `_handle_private_ws_message()` (line 749): replace `self._pending_ws_trade_executions.append(data)` with:
```python
try:
    self._event_queue.put_nowait(
        EngineEvent(EngineEventType.WS_FILL, data, datetime.now(UTC))
    )
except asyncio.QueueFull:
    logger.warning(f"Event queue full, dropping WS_FILL for {self._run_id}")
```

3. Delete `_drain_ws_updates()` method entirely.

4. Remove `_pending_ws_updates` and `_pending_ws_trade_executions` deque declarations from `__init__()`. Also remove the `_MAX_PENDING_WS_UPDATES` constant if only used for deque maxlen.

5. In the event loop's WS_FILL case, replace placeholder with actual processing:
```python
case EngineEventType.WS_FILL:
    self._process_trade_execution(event.data)
    await self._flush_order_events()
    push_event = self._build_state_update_event("fill", event.data)
```
Similarly for WS_ORDER case:
```python
case EngineEventType.WS_ORDER:
    self._process_single_ws_update(event.data)
    await self._flush_order_events()
    push_event = self._build_state_update_event("order_update", event.data)
```

Note: `_build_state_update_event()` doesn't exist yet — create a minimal stub that calls `_build_state_snapshot()` and returns a dict with `"event": "state_update"`. Full implementation in Task 5.

- [ ] **Step 1:** Wire WS callbacks to Queue with QueueFull handling.

- [ ] **Step 2:** Delete deques, `_drain_ws_updates()`, related constants.

- [ ] **Step 3:** Wire event loop WS cases to actual processing methods.

- [ ] **Step 4:** Add stub `_build_state_update_event()`.

- [ ] **Step 5:** Add **queue overflow test** to `test_event_loop.py`: fill queue to capacity (maxsize=1000), verify `put_nowait` for WS_FILL raises `QueueFull` and is caught (event dropped with log warning). Verify `await put()` for BAR_CLOSE blocks until space is available.

- [ ] **Step 6:** Run tests: `uv run pytest tests/unit/engine/ -v --no-cov`

- [ ] **Step 7:** Commit: `git commit -m "feat: wire WS callbacks to event queue, delete deque buffering"`

---

### Task 5: Event Builders (state_update + bar_close)

**Context:** Implement `_build_state_update_event()` and `_build_bar_close_event()` for the Live engine. Replace `_build_bar_update_event()` with `_build_bar_close_event()` in `_handle_bar_close()`.

**Files:**
- Modify: `src/squant/engine/live/engine.py`
- Modify: `tests/unit/engine/test_event_builders.py`

**What to do:**

1. Implement `_build_state_update_event(self, trigger: str, event_data: Any) -> dict[str, Any]`:

```python
def _build_state_update_event(self, trigger: str, event_data: Any) -> dict[str, Any]:
    """Build state_update event for immediate push after WS fill/order processing."""
    state, new_fills, new_trades, new_logs = self._build_state_snapshot()

    trigger_detail: dict[str, Any] = {}
    if trigger == "fill" and hasattr(event_data, "price"):
        trigger_detail = {
            "order_id": getattr(event_data, "order_id", ""),
            "side": getattr(event_data, "side", None) or "",
            "price": str(event_data.price),
            "amount": str(event_data.amount),
            "fee": str(getattr(event_data, "fee", "0")),
            "fee_currency": getattr(event_data, "fee_currency", ""),
        }
    elif trigger == "order_update" and hasattr(event_data, "order_id"):
        internal_id = self._exchange_order_map.get(event_data.order_id)
        live_order = self._live_orders.get(internal_id) if internal_id else None
        trigger_detail = {
            "order_id": event_data.order_id,
            "status": event_data.status,
            "side": live_order.side.value if live_order else "",
            "amount": str(live_order.amount) if live_order else "0",
            "filled_amount": str(event_data.filled_size),
        }

    return {
        "event": "state_update",
        "run_id": str(self._run_id),
        "trigger": trigger,
        "trigger_detail": trigger_detail,
        "state": state,
        "new_fills": new_fills,
        "new_trades": new_trades,
        "new_logs": new_logs,
    }
```

2. Implement `_build_bar_close_event(self, bar: Bar) -> dict[str, Any]`:

```python
def _build_bar_close_event(self, bar: Bar) -> dict[str, Any]:
    """Build bar_close event for periodic push at bar close."""
    state, new_fills, new_trades, new_logs = self._build_state_snapshot()

    equity_point = None
    if self._context.equity_curve:
        latest = self._context.equity_curve[-1]
        equity_point = {
            "time": latest.time.isoformat() if hasattr(latest, "time") else str(latest.get("time", "")),
            "equity": str(self._context.equity),
            "cash": str(self._context._cash),
            "position_value": str(self._context._get_position_value()),
            "unrealized_pnl": str(self._context._get_unrealized_pnl()),
        }

    return {
        "event": "bar_close",
        "run_id": str(self._run_id),
        "bar_count": self._bar_count,
        "bar": {
            "time": bar.time.isoformat(),
            "open": str(bar.open),
            "high": str(bar.high),
            "low": str(bar.low),
            "close": str(bar.close),
            "volume": str(bar.volume),
        },
        "equity_point": equity_point,
        "state": state,
        "new_fills": new_fills,
        "new_trades": new_trades,
        "new_logs": new_logs,
    }
```

3. In `_handle_bar_close()`, replace the bar_update emit block with bar_close:
```python
# Build bar_close event inside lock context (state is consistent)
bar_close_event = self._build_bar_close_event(bar)

# ... (after lock release, at end of _handle_bar_close) ...
# Fire-and-forget push
if self._on_event:
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._on_event(bar_close_event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
    except Exception as e:
        logger.debug(f"Bar close event push failed for {self._run_id}: {e}")
```

4. Delete `_build_bar_update_event()` — it's fully replaced.

5. Add tests for `_build_state_update_event()` output format (trigger, trigger_detail, state nested, new_fills) and `_build_bar_close_event()` output (bar, equity_point with full fields, state).

6. Add **delta tracking test**: Process 3 consecutive fills via event loop. Verify each resulting `state_update` has exactly 1 `new_fill` (not cumulative). Then verify `bar_close` after all 3 has 0 `new_fills` (all already emitted).

7. Add **fill-before-status ordering test**: Enqueue a WS_ORDER (status=filled) BEFORE a WS_FILL for the same order. Verify the event loop processes them in FIFO order, the fallback fill path in `_process_single_ws_update` produces correct state, and the subsequent WS_FILL deduplicates correctly (fill_delta = 0).

- [ ] **Step 1:** Add tests for both builder methods + delta tracking + fill-before-status ordering.

- [ ] **Step 2:** Implement `_build_state_update_event()` and `_build_bar_close_event()`.

- [ ] **Step 3:** Replace emit block in `_handle_bar_close()`. Delete `_build_bar_update_event()`.

- [ ] **Step 4:** **Fix breaking existing tests.** Deleting `_build_bar_update_event()` will break:
  - `tests/unit/engine/live/test_engine.py` — any test calling `engine._build_bar_update_event()` directly. Update to use `_build_bar_close_event(bar)` or `_build_state_update_event(...)`.
  - `tests/unit/services/test_reconcile_order_count.py:~169` — uses `inspect.getsource(LiveTradingEngine._build_bar_update_event)`. Update to reference `_build_state_snapshot` or `_build_bar_close_event`.
  - Search for any other references: `grep -r "bar_update_event\|bar_update" tests/unit/engine/live/`

- [ ] **Step 5:** Run tests: `uv run pytest tests/unit/engine/ tests/unit/services/ -v --no-cov`

- [ ] **Step 6:** Commit: `git commit -m "feat: implement state_update and bar_close event builders"`

---

### Task 6: Paper Engine Event Format Unification

**Context:** Replace Paper engine's `_build_fill_event()` and `_build_bar_update_event()` with the new `state_update` / `bar_close` format. Paper engine already pushes fills in real-time — this is a format change, not a behavior change.

**Files:**
- Modify: `src/squant/engine/paper/engine.py`
- Test: `tests/unit/engine/test_paper_state_update.py`

**What to do:**

1. Add a `_build_state_snapshot()` method to Paper engine (similar to Live, but uses `self._cached_realized_pnl` and `self._risk_manager` may be None).

2. Replace `_build_fill_event(self, fill)` with `_build_state_update_event(self, trigger: str, fill: Any = None)`:
   - Format: `{"event": "state_update", "run_id": ..., "trigger": "fill", "trigger_detail": {...}, "state": {...}, "new_fills": [...], "new_trades": [...], "new_logs": [...]}`
   - `trigger_detail` for fill: `{order_id, side, price, amount, fee, fee_currency}`

3. Replace `_build_bar_update_event()` with `_build_bar_close_event(self, bar: Bar)`:
   - Format: `{"event": "bar_close", "run_id": ..., "bar_count": ..., "bar": {...}, "equity_point": {...}, "state": {...}, "new_fills": [...], "new_trades": [...], "new_logs": [...]}`
   - `equity_point`: `{time, equity, cash, position_value, unrealized_pnl}` from latest equity snapshot

4. In `_process_fill_safe()` (line 930), change `self._build_fill_event(fill)` to `self._build_state_update_event("fill", fill)`.

5. In `process_candle()` emit section (line 607), change `self._build_bar_update_event()` to `self._build_bar_close_event(bar)` (pass the bar object).

6. Delete `_build_fill_event()` and `_build_bar_update_event()`.

- [ ] **Step 1:** Write tests for Paper's `_build_state_update_event()` and `_build_bar_close_event()` output format.

- [ ] **Step 2:** Implement `_build_state_snapshot()`, `_build_state_update_event()`, `_build_bar_close_event()` in Paper engine.

- [ ] **Step 3:** Wire new methods in `_process_fill_safe()` and `process_candle()`.

- [ ] **Step 4:** Delete old methods (`_build_fill_event`, `_build_bar_update_event`).

- [ ] **Step 5:** **Fix breaking existing tests.** Deleting old methods/event types will break:
  - `tests/unit/engine/paper/test_ws_events.py` — asserts on `event["event"] == "bar_update"` and `event["event"] == "fill"`. Update to `"bar_close"` and `"state_update"` respectively, and adjust field expectations (state is now nested under `"state"` key, not flat).
  - Search: `grep -r "bar_update\|\"fill\"" tests/unit/engine/paper/`

- [ ] **Step 6:** Run tests: `uv run pytest tests/unit/engine/ -v --no-cov`

- [ ] **Step 7:** Commit: `git commit -m "feat: unify paper engine event format to state_update + bar_close"`

---

### Task 7: Frontend Types + Event Handler

**Context:** Rewrite the frontend event handler to process `state_update` + `bar_close` instead of `bar_update` + `fill`. This simplifies the handler from ~130 lines of per-field parsing to ~40 lines of snapshot application.

**Files:**
- Modify: `frontend/src/types/trading.ts` (lines 310-357)
- Modify: `frontend/src/views/trading/SessionDetail.vue` (lines 979-1115)

**What to do:**

1. In `trading.ts`, replace `TradingBarUpdate` (lines 310-330) and `TradingFillEvent` (lines 339-357) with:

```typescript
export interface TradingStateSnapshot {
  cash: string
  equity: string
  unrealized_pnl: string
  realized_pnl: string
  total_fees: string
  fees_by_currency: Record<string, string>
  fees_usdt_equivalent: string | null
  positions: Record<string, { amount: string; avg_entry_price: string }>
  pending_orders: PendingOrderInfo[]
  open_trade?: OpenTrade
  completed_orders_count: number
  trades_count: number
  risk_state: Record<string, unknown>
}

export interface StateUpdateEvent {
  event: 'state_update'
  run_id: string
  trigger: 'fill' | 'order_update'
  trigger_detail: Record<string, string>
  state: TradingStateSnapshot
  new_fills: Fill[]
  new_trades: Trade[]
  new_logs: string[]
}

export interface BarCloseEvent {
  event: 'bar_close'
  run_id: string
  bar_count: number
  bar: {
    time: string
    open: string
    high: string
    low: string
    close: string
    volume: string
  }
  equity_point: {
    time: string
    equity: string
    cash: string
    position_value: string
    unrealized_pnl: string
  } | null
  state: TradingStateSnapshot
  new_fills: Fill[]
  new_trades: Trade[]
  new_logs: string[]
}
```

2. In `SessionDetail.vue`, rewrite `handleTradingEvent()`:

```typescript
function handleTradingEvent(data: Record<string, unknown>) {
  if (!status.value) return
  const eventType = data.event as string

  if (eventType === 'state_update' || eventType === 'bar_close') {
    const prevCompletedCount = status.value?.completed_orders_count ?? 0

    // Apply state snapshot (shallow merge)
    applyStateSnapshot(data.state as Record<string, unknown>)

    // Append incremental data
    appendIncrementalData(data)

    // Auto-refresh audit orders when completed_orders_count increases
    if (isLive.value && (status.value.completed_orders_count ?? 0) > prevCompletedCount) {
      loadLiveAuditOrders()
      loadAllLiveOrders()
    }

    // state_update: toast notification
    if (eventType === 'state_update' && data.trigger) {
      showTradeNotification(data.trigger as string, data.trigger_detail as Record<string, string>)
    }

    // bar_close: equity curve + bar count
    if (eventType === 'bar_close') {
      if (data.equity_point) {
        appendEquityPoint(data.equity_point as Record<string, string>)
      }
      status.value.bar_count = data.bar_count as number
    }
  } else if (eventType === 'engine_stopped') {
    // Unchanged
    status.value.is_running = false
    if (data.error_message) {
      status.value.error_message = data.error_message as string
    }
    loadSession()
    if (isLive.value) {
      loadLiveAuditOrders()
    }
    unsubscribeTradingChannel()
  }
}
```

3. Add helper functions:

```typescript
function applyStateSnapshot(state: Record<string, unknown>) {
  if (!state || !status.value) return
  status.value.cash = parseFloat(state.cash as string)
  status.value.equity = parseFloat(state.equity as string)
  status.value.unrealized_pnl = parseFloat(state.unrealized_pnl as string)
  status.value.realized_pnl = parseFloat(state.realized_pnl as string)
  status.value.total_fees = parseFloat(state.total_fees as string)
  ;(status.value as any).fees_by_currency = state.fees_by_currency
  ;(status.value as any).fees_usdt_equivalent = state.fees_usdt_equivalent != null
    ? parseFloat(state.fees_usdt_equivalent as string)
    : null
  status.value.completed_orders_count = state.completed_orders_count as number
  status.value.trades_count = state.trades_count as number

  // Positions: parse string → number
  const rawPositions = state.positions as Record<string, { amount: string; avg_entry_price: string }> | undefined
  if (rawPositions) {
    const parsed: Record<string, Position> = {}
    for (const [sym, pos] of Object.entries(rawPositions)) {
      parsed[sym] = { amount: parseFloat(pos.amount), avg_entry_price: parseFloat(pos.avg_entry_price) }
    }
    status.value.positions = parsed
  }

  status.value.pending_orders = (state.pending_orders as PendingOrderInfo[]) || []

  // Open trade
  if (isPaper.value) {
    ;(status.value as PaperTradingStatus).open_trade = state.open_trade as OpenTrade | undefined
  } else if (isLive.value) {
    const ot = state.open_trade as OpenTrade | undefined
    liveOpenTrade.value = ot ? { entry_time: ot.entry_time, entry_price: ot.entry_price, amount: ot.amount } : null
  }

  // Risk state
  if (state.risk_state) {
    ;(status.value as LiveTradingStatus).risk_state = state.risk_state as RiskState
  }
}

function appendIncrementalData(data: Record<string, unknown>) {
  // Fills
  const newFills = data.new_fills as Fill[] | undefined
  if (Array.isArray(newFills) && newFills.length) {
    if (isPaper.value) {
      const ps = status.value as PaperTradingStatus
      if (ps.fills) ps.fills.push(...newFills)
    } else if (isLive.value) {
      liveWsFills.value.push(...newFills)
      if (liveWsFills.value.length > 500) {
        liveWsFills.value = liveWsFills.value.slice(-500)
      }
    }
  }

  // Trades
  const newTrades = data.new_trades as Trade[] | undefined
  if (Array.isArray(newTrades) && newTrades.length && isPaper.value) {
    const ps = status.value as PaperTradingStatus
    if (ps.trades) ps.trades.push(...newTrades)
  }

  // Logs
  const newLogs = data.new_logs as string[] | undefined
  if (Array.isArray(newLogs) && newLogs.length) {
    tradingLogs.value.push(...newLogs)
    if (tradingLogs.value.length > 2000) {
      tradingLogs.value = tradingLogs.value.slice(-2000)
    }
  }
}

function appendEquityPoint(point: Record<string, string>) {
  equityCurve.value.push({
    time: point.time,
    equity: parseFloat(point.equity),
    cash: parseFloat(point.cash),
    position_value: parseFloat(point.position_value),
    unrealized_pnl: parseFloat(point.unrealized_pnl),
  } as EquityPoint)
}

function showTradeNotification(trigger: string, detail: Record<string, string>) {
  if (trigger === 'fill') {
    const side = detail.side === 'buy' ? '买入' : '卖出'
    ElMessage.success(`${side} ${detail.amount} 成交 @ ${detail.price}`)
  } else if (trigger === 'order_update' && detail.status === 'cancelled') {
    ElMessage.warning('订单已取消')
  } else if (trigger === 'order_update' && detail.status === 'rejected') {
    ElMessage.error('订单被拒绝')
  }
}
```

4. Remove `loadEquityCurve(true)` call from the event handler (equity points now come via WS push). Keep `loadEquityCurve()` (no args) for initial load.

5. In the polling fallback (`startPolling()`), keep `loadEquityCurve(true)` as a safety net — polling still runs every ~30s.

- [ ] **Step 1:** Update `trading.ts` types.

- [ ] **Step 2:** Add helper functions (`applyStateSnapshot`, `appendIncrementalData`, `appendEquityPoint`, `showTradeNotification`).

- [ ] **Step 3:** Rewrite `handleTradingEvent()`.

- [ ] **Step 4:** Remove `loadEquityCurve(true)` from event handler.

- [ ] **Step 5:** Run frontend tests: `cd frontend && pnpm test`

- [ ] **Step 6:** Run frontend build: `cd frontend && pnpm build`

- [ ] **Step 7:** Commit: `git commit -m "feat: frontend handles state_update + bar_close events"`

---

### Task 8: Cross-cutting Tests + Lint + Final Verification

**Context:** Run all tests, fix lint issues, verify the full stack works.

**Files:**
- All modified files from Tasks 1-7

**What to do:**

1. Run full backend test suite: `uv run pytest -v --no-cov`
2. Run lint: `./scripts/dev.sh lint`
3. Run format: `./scripts/dev.sh format`
4. Run frontend tests: `cd frontend && pnpm test`
5. Run frontend build: `cd frontend && pnpm build`
6. Fix any failures.
7. Verify no existing test references `bar_update` event type (search for `"bar_update"` or `bar_update` in test files).
8. Update frontend test mocks in `frontend/src/__tests__/` if they reference old event types.

- [ ] **Step 1:** Run `uv run pytest -v --no-cov` — fix any failures.

- [ ] **Step 2:** Run `./scripts/dev.sh lint` and `./scripts/dev.sh format` — fix issues.

- [ ] **Step 3:** Run `cd frontend && pnpm test && pnpm build` — fix any failures.

- [ ] **Step 4:** Search for stale `bar_update` / `fill` event references in tests and frontend mocks.

- [ ] **Step 5:** Commit: `git commit -m "chore: fix lint and update tests for new event types"`

---

## Key Risk Mitigation

1. **Task 1 is safe:** Extract-method refactoring, existing behavior unchanged.
2. **Task 3 is the riskiest:** Mechanical method split but touches 250 lines of critical code. Verify all engine tests pass after this step.
3. **Task 4 is the point of no return:** After wiring WS callbacks to Queue, the old deque path is dead. Run full test suite.
4. **Task 7 is frontend-only:** Can be tested independently with `pnpm test && pnpm build`.
5. **Emergency close safety:** Verified by unit tests in Task 2 (test_event_loop.py).
