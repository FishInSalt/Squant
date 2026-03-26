# Real-Time Event Push Architecture Design

## Problem Statement

Current architecture processes all WS events (fills, order status changes, logs) inside `process_candle()`, which only runs on bar close. For 1-minute bars, this means up to 60 seconds delay before users see order fills, status changes, and trading logs in the frontend.

Industry standard: all trading state changes should be pushed to the client immediately (<1s), with only K-line and equity curve sampling being inherently periodic.

## Goal

Achieve sub-second event push for all trading state changes (fills, orders, positions, cash, PnL, logs, risk) by decoupling WS event processing from the bar loop.

## Architecture: Unified Event-Driven (Approach C)

Replace the dual-path processing model (WS events buffered in deques + drained in `process_candle`) with a single event loop that processes all events — WS fills, WS order updates, and bar closes — through one `asyncio.Queue` consumer.

### Why Approach C over simpler alternatives

- **vs. Dual-Loop (Approach A):** Only ~50 lines more code, but eliminates lock contention (single consumer vs two consumers competing), guarantees FIFO ordering, simplifies debugging (single entry point), and makes adding new event types zero-cost.
- **vs. Callback-based (Approach B):** Backpressure via Queue, no task explosion under high load, deterministic FIFO processing order.
- **A is a subset of C:** The refactor from A to C is a mechanical split of `process_candle()` into guard + body. Cost is minimal, benefit is significant.

## Scope

- **Live engine:** Full event-driven refactor with unified event loop.
- **Paper engine:** Lightweight optimization — push `state_update` immediately after fills, no event loop refactor (local matching has no async WS events).
- **Frontend:** Handle new event types (`state_update` + `bar_close`; existing `engine_stopped` unchanged), simplified state management via full snapshots.

---

## Event Model

### Event Types

```python
class EngineEventType(str, Enum):
    WS_FILL = "ws_fill"            # watchMyTrades per-fill data
    WS_ORDER = "ws_order"          # watchOrders status change
    BAR_CLOSE = "bar_close"        # K-line closed candle
```

### Event Wrapper

```python
@dataclass(frozen=True)
class EngineEvent:
    type: EngineEventType
    data: WSTradeExecution | WSOrderUpdate | WSCandle
    received_at: datetime          # For latency monitoring
```

- Defined at top of `engine/live/engine.py` alongside existing types.
- `frozen=True` prevents mutation in queue.
- Only 3 event types for now. Future extensions (PRICE_UPDATE, RISK_ALERT) add enum values.

---

## Live Engine Event Loop

### New Flow

```
WS callback → asyncio.Queue → _event_loop() → acquire lock → process → push state_update
Candle close → asyncio.Queue → _event_loop() → acquire lock → bar logic → push bar_close
```

### Event Loop

```python
async def _event_loop(self) -> None:
    """Unified event processor. Single consumer, single lock."""
    while self._is_running:
        try:
            event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        # Update activity timestamp on every event (for health check)
        self._last_active_at = datetime.now(UTC)

        push_event = None  # Built inside lock, pushed outside (fire-and-forget)
        async with self._processing_lock:
            if not self._is_running:
                break
            try:
                match event.type:
                    case EngineEventType.WS_FILL:
                        self._process_trade_execution(event.data)
                        await self._flush_order_events()
                        push_event = self._build_state_update_event("fill", event.data)

                    case EngineEventType.WS_ORDER:
                        self._process_single_ws_update(event.data)
                        await self._flush_order_events()
                        push_event = self._build_state_update_event("order_update", event.data)

                    case EngineEventType.BAR_CLOSE:
                        await self._handle_bar_close(event.data)
                        # _handle_bar_close builds and fires its own bar_close event
            except Exception as e:
                logger.exception(f"Event loop error for {self._run_id}: {e}")
                if event.type == EngineEventType.BAR_CLOSE:
                    await self.stop(error=f"Bar processing error: {e}")
                    return

        # Fire-and-forget push OUTSIDE the lock (non-blocking)
        if push_event and self._on_event:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._on_event(push_event))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            except Exception as e:
                logger.debug(f"State update push failed: {e}")
```

**Key design: build inside lock, push outside.** The event dict is constructed while the lock is held (state is consistent), but the Redis publish happens after releasing the lock. This matches the existing fire-and-forget pattern and prevents push I/O from blocking subsequent event processing.

### WS Callback Changes

```python
# Before: append to deque
self._pending_ws_updates.append(update)

# After: put to Queue (with existing guards preserved)
# on_order_update(): keep _emergency_close_in_progress check before enqueue
# _handle_private_ws_message(): keep existing routing logic
if self._emergency_close_in_progress:
    return
self._event_queue.put_nowait(
    EngineEvent(EngineEventType.WS_ORDER, update, datetime.now(UTC))
)
```

**Guards preserved at enqueue site:**
- `_emergency_close_in_progress` check in `on_order_update()` — prevents fill processing from modifying positions/cash during emergency close.
- `_handle_private_ws_message()` type routing — unchanged, just replaces deque append with Queue put.

### process_candle() Thinning

`process_candle()` becomes a filter + router (~30 lines of guards), ending with:
```python
# BAR_CLOSE uses await put() to guarantee delivery (not put_nowait)
await self._event_queue.put(
    EngineEvent(EngineEventType.BAR_CLOSE, candle, datetime.now(UTC))
)
```

The processing body moves to `_handle_bar_close(candle)` — same logic, minus the deleted `_drain_ws_updates()` call. All bar-interval operations remain inside `_handle_bar_close`:

- `_reconcile_pending_orders()` — fill recovery after WS reconnect
- `_sync_balance()`, `_sync_pending_orders()` — exchange REST polling
- `_expire_ttl_orders()` — order TTL expiry
- Risk manager updates (`update_equity`, `update_unrealized_pnl`, `update_position_value`, `check_total_loss_limit`, `check_daily_reset`)
- Equity snapshot recording + persistence
- Strategy callbacks (`on_fill`, `on_order_done`) + `strategy.on_bar()` with resource limits
- Order request processing (`_process_order_requests`)
- Result state persistence for crash recovery
- Dead Man's Switch refresh (`_refresh_dead_man_switch`)
- `bar_close` event build + fire-and-forget push

These are bar-level operations that should not run on every WS event.

**Strategy notification timing:** `on_fill()` and `on_order_done()` callbacks remain in `_handle_bar_close` at bar boundary, not in the event loop's WS handlers. Rationale: strategies expect fills to be notified in the context of a bar (with current bar data set), and moving them to event loop would change the strategy execution contract. Fills are processed immediately for state correctness (positions, cash), but strategy is notified at the next bar close.

### Lifecycle

- `start()`: `self._event_loop_task = asyncio.create_task(self._event_loop())`
- `stop()`: set `_is_running = False`, `await asyncio.wait_for(self._event_loop_task, timeout=5.0)`, cancel on timeout.

### Deleted Code

- `_drain_ws_updates()` method
- `_pending_ws_updates` deque
- `_pending_ws_trade_executions` deque
- `_build_bar_update_event()` (replaced by `_build_state_update_event` + `_build_bar_close_event`)
- Lock acquisition in `process_candle()` (moved to event loop)

### Unchanged Internal State

- `_processed_trade_ids` OrderedDict (trade execution dedup) — internal to `_process_trade_execution()`, unaffected by Queue refactor.
- `_exchange_order_map`, `_live_orders`, `_orders_needing_reconciliation` — unchanged.
- `_background_tasks` set — continues to track fire-and-forget push tasks.

---

## Push Protocol

### Data Classification

| Push Type | Data | Trigger |
|-----------|------|---------|
| Instant (`state_update`) | Orders, fills, trades, positions, cash, equity, fees, PnL, logs, risk | WS fill / WS order event |
| Periodic (`bar_close`) | K-line, equity curve sample point, + full state snapshot as sync point | Bar close |

### `state_update` Event Format

```json
{
  "event": "state_update",
  "run_id": "uuid",
  "trigger": "fill",
  "trigger_detail": {
    "order_id": "abc123",
    "side": "buy",
    "price": "50000",
    "amount": "0.001",
    "fee": "0.05",
    "fee_currency": "USDT"
  },
  "state": {
    "cash": "99500.00",
    "equity": "99550.00",
    "unrealized_pnl": "50.00",
    "realized_pnl": "0",
    "total_fees": "0.05",
    "fees_by_currency": {"USDT": "0.05"},
    "fees_usdt_equivalent": "0.05",
    "positions": {"BTC/USDT": {"amount": "0.001", "avg_entry_price": "50000"}},
    "pending_orders": [],
    "open_trade": null,
    "completed_orders_count": 0,
    "trades_count": 0,
    "risk_state": {}
  },
  "new_fills": [],
  "new_trades": [],
  "new_logs": []
}
```

- `state`: Partial snapshot of **execution state** — fields that change during trading (cash, equity, positions, pending_orders, open_trade, fees, PnL, risk_state). Frontend applies via shallow merge (`Object.assign`), not full replacement.
- **Fields NOT in `state`** (remain sourced from REST initial load): `live_orders` (full order history), `initial_capital`, `is_running`, `started_at`, `stopped_at`, `error_message`, `symbol`, `strategy_name`. These are session-level metadata that don't change on fills/orders.
- `trigger` + `trigger_detail`: For toast notifications.
- `new_fills`/`new_trades`/`new_logs`: Incremental append data.
- **All numeric values are serialized as strings** (Decimal → str), consistent with existing `bar_update` serialization. `trigger_detail` follows the same convention.

### `bar_close` Event Format

```json
{
  "event": "bar_close",
  "run_id": "uuid",
  "bar_count": 42,
  "bar": {
    "time": "2026-03-26T10:05:00Z",
    "open": "50000",
    "high": "50100",
    "low": "49900",
    "close": "50050",
    "volume": "123.45"
  },
  "equity_point": {
    "time": "2026-03-26T10:05:00Z",
    "equity": "99550.00",
    "cash": "99500.00",
    "position_value": "50.00",
    "unrealized_pnl": "50.00"
  },
  "state": { "..." },
  "new_fills": [],
  "new_trades": [],
  "new_logs": []
}
```

- `bar`: K-line data. Note: K-line data is also pushed via the market data WS channel independently. The `bar` field here is intentionally redundant — it allows the trading session view to be self-contained without subscribing to the market data channel, and provides a consistent timestamp anchor for the equity curve point.
- `equity_point`: Equity curve sample point. Matches backend `EquityCurvePoint` schema: `{time, equity, cash, position_value, unrealized_pnl}`. This replaces the `loadEquityCurve(true)` REST call — all fields the frontend chart needs are included.
- `state`: Same structure as `state_update`'s `state` field — identical fields, same shallow merge semantics. The `bar_close` state serves as a periodic sync point: if a `state_update` push was lost, the next `bar_close` corrects the drift. "Sync point" means "same data, guaranteed delivery", not a different field set.

### Design Rationale

- **State = partial snapshot via shallow merge**: Only execution-state fields are pushed. Session metadata (initial_capital, live_orders, etc.) remains from REST. This avoids the need to include large, rarely-changing data in every push while ensuring all trading-relevant state is current.
- **Fills/trades/logs = incremental**: These are append-only lists. Full snapshot would grow unboundedly. Initial load via REST, then incremental via WS.
- **`bar_close` includes state**: Bar processing runs strategy (may place orders), syncs balance, expires orders — all change state. Also serves as periodic correction.

### Fill-Before-Status Ordering

The current `_drain_ws_updates()` enforces fills-first ordering by processing all `watchMyTrades` events before `watchOrders` events. In the new event loop, WS_FILL and WS_ORDER events are enqueued independently and processed in FIFO (arrival) order.

This is a relaxation of the strict ordering guarantee, but is **safe** because:

1. `_process_single_ws_update()` already has a fallback fill path (the `fill_delta > 0` branch within the method): when it sees new fills in the aggregated data, it computes incremental fill from blended averages. This handles the case where `WS_ORDER` (status=filled) arrives before `WS_FILL`.
2. If `WS_FILL` arrives later, it finds `old_filled` already reflects the fill from fallback, so `fill_delta = 0` — no duplicate.
3. The fallback path uses blended avg prices (less precise than per-fill prices), but subsequent REST enrichment recovers exact per-fill data.

This is the same safety mechanism that handles OKX demo environments where `watchMyTrades` is unavailable.

---

## Paper Engine (Lightweight)

No event loop refactor. This is a **replacement** of the existing immediate `fill` event with `state_update`, and the existing `bar_update` with `bar_close`.

The paper engine already pushes a `fill` event immediately from `_process_fill_safe()` via `_build_fill_event()` (fire-and-forget `create_task`). This existing event contains scalar state (cash, equity, positions, pending_orders, open_trade) but uses the `"fill"` event type with a different format than the new `state_update`.

Changes:

1. **Replace `_build_fill_event()`** with `_build_state_update_event()` — same trigger point (`_process_fill_safe`), but uses the new unified `state_update` format (adds `trigger`, `trigger_detail`, `state` snapshot with all fields, `new_fills`/`new_trades`/`new_logs` incremental data).
2. **Replace `_build_bar_update_event()`** with `_build_bar_close_event()` — bar-end event uses new format with `equity_point` and `bar` fields.
3. Delete: `_build_fill_event()`, `_build_bar_update_event()`.

Effect: Fill visibility latency drops from up to 60s (waiting for bar close to emit event) to the WS candle update interval (typically ~1s, varies by exchange). Paper engine calls `_fill_new_orders()` on every WS candle tick (both closed and unclosed). The `state_update` push happens immediately after the fill logic within any candle tick, not at the next bar close.

---

## Frontend Changes

### Event Handler

```typescript
function handleTradingEvent(data: Record<string, unknown>) {
  const eventType = data.event as string

  if (eventType === 'state_update' || eventType === 'bar_close') {
    const prevCompletedCount = status.value?.completed_orders_count ?? 0
    applyStateSnapshot(data.state)
    appendIncrementalData(data)

    // Auto-refresh audit orders when completed_orders_count increases (existing behavior)
    if (isLive.value && status.value.completed_orders_count > prevCompletedCount) {
      loadLiveAuditOrders()
      loadAllLiveOrders()
    }

    if (eventType === 'state_update' && data.trigger) {
      showTradeNotification(data.trigger, data.trigger_detail)
    }

    if (eventType === 'bar_close') {
      appendEquityPoint(data.equity_point)
      status.value.bar_count = data.bar_count
    }
  }
}
```

### State Application

`applyStateSnapshot()` replaces ~50 lines of per-field parsing with ~15 lines of direct assignment. No Paper/Live branching — unified handler.

### TypeScript Types

New interfaces: `TradingStateSnapshot`, `StateUpdateEvent`, `BarCloseEvent`.

### Deleted Code

- Per-field parsing in `handleTradingEvent` (~50 lines)
- Paper/Live branching for fills accumulation
- `loadEquityCurve(true)` REST call on each bar (replaced by WS-pushed `equity_point`)

### Unchanged

- WebSocket store, Redis pub/sub, WS handlers — all transparent passthrough.
- REST APIs (`/logs`, `/status`) — unaffected.
- `engine_stopped` event — continues to exist as-is, emitted by `stop()` in both live and paper engines. Not affected by this refactor.

---

## Error Handling

### Event Loop Errors

- **WS event failure**: Log + skip, loop continues. Single fill/order error doesn't stop engine.
- **BAR_CLOSE failure**: Stop engine (matches existing `process_candle` behavior).
- **Event loop task crash**: `add_done_callback` in `start()` detects abnormal exit, calls `stop()`.

### Queue Overflow

- `asyncio.Queue(maxsize=1000)`: Sufficient for normal load.
- **WS events** (WS_FILL, WS_ORDER): `put_nowait` raises `QueueFull` → log warning, drop event. Recoverable — next REST sync or next event's full snapshot corrects state.
- **BAR_CLOSE events**: Use `await queue.put()` (blocking) to guarantee delivery. Dropping a bar close would skip strategy execution and equity snapshot — unacceptable data loss. If the queue is full when a bar close arrives, the candle callback blocks until space is available (this implies the event loop is stuck, which will eventually trigger timeout/stop).

**Queue vs Deque overflow behavior change:** The old `deque(maxlen=N)` silently evicts the oldest event on overflow, preserving the newest. The new `Queue(maxsize=N)` with `put_nowait` drops the newest event. This is a behavioral difference, but the practical impact is minimal: the old deques were only consumed at bar close (up to 60s accumulation), while the new Queue has a continuously running consumer draining events in <1ms. Queue overflow would only occur if the event loop is stuck (e.g., awaiting a hung REST call inside `_handle_bar_close`), which is a pathological case regardless of the eviction strategy.

### Push Failure

- Silent skip. Full snapshot on next push auto-corrects.
- No cascading failure — engine state is always correct regardless of push success.

### Session Recovery

- Existing mechanism unchanged: `build_result_for_persistence()` saves state per bar, `restore_state()` recovers.
- Event loop restarts on recovery. Frontend re-subscribes and gets initial state via REST.

### WS Reconnection

- Existing `_on_ws_reconnect()` unchanged — marks orders for REST reconciliation.
- New WS events flow into Queue naturally after reconnection.

### Graceful Shutdown

- `stop()` sets `_is_running = False`.
- Event loop's `wait_for(..., timeout=1.0)` detects `_is_running == False` on next timeout cycle and exits.
- `stop()` then `await asyncio.wait_for(self._event_loop_task, timeout=5.0)` to wait for the loop to finish its current event.
- Fallback: cancel task after 5s timeout.
- **stop() from within event loop:** When `_handle_bar_close` calls `self.stop()` (e.g., on risk limit trigger), `stop()` does NOT acquire `_processing_lock` (consistent with current design — `stop()` may be called from within locked context). It only sets `_is_running = False`; the event loop checks this flag at the top of each iteration and exits. The event loop task await in `stop()` is skipped when called from within the loop itself (detected via `self._event_loop_task == asyncio.current_task()`).

---

## Migration

**One-time cutover.** No transition period (single-user system, frontend and backend deploy together).

### Backend Steps

1. Live engine: Add `EngineEvent`, `_event_loop()`, `_handle_bar_close()`, `_build_state_update_event()`, `_build_bar_close_event()`.
2. Live engine: Delete `_drain_ws_updates()`, two deques, `_build_bar_update_event()`.
3. Live engine: Thin `process_candle()` to guard + Queue.put.
4. Live engine: WS callbacks → Queue.put.
5. Paper engine: Add `state_update` push after fills, bar-end → `bar_close`.
6. Schema/types: Regenerate OpenAPI types.

### Frontend Steps

1. `SessionDetail.vue`: Rewrite `handleTradingEvent()` for dual event types.
2. `trading.ts`: New type interfaces.
3. Delete: per-field parsing, Paper/Live branching, REST equity curve polling.

### Unchanged Layers

- Redis pub/sub channels and WS handlers (transparent JSON passthrough).
- WebSocket store (forwards data to callbacks, doesn't parse).
- REST APIs.

---

## Testing Strategy

| Level | Test |
|-------|------|
| Unit | Event loop processes 3 event types correctly |
| Unit | Queue overflow handling (drop + log) |
| Unit | Event loop error recovery (WS event skip, BAR_CLOSE stop) |
| Unit | `_build_state_update_event()` output format |
| Unit | `_build_bar_close_event()` output format |
| Unit | `process_candle()` routes to Queue correctly |
| Unit | Paper engine pushes `state_update` after fill |
| Frontend | `applyStateSnapshot()` overwrites state correctly |
| Frontend | `bar_close` appends equity point |
| E2E | Live session: order → <1s state_update visible in frontend |
| E2E | Paper session: candle → fill + state_update pushed together |

---

## Files Affected

### Backend (modify)

- `src/squant/engine/live/engine.py` — Event loop, process_candle refactor, new builders
- `src/squant/engine/paper/engine.py` — state_update push after fill, bar_close builder
- `src/squant/services/live_trading.py` — Minor: status fallback dict updates
- `src/squant/services/paper_trading.py` — Minor: status fallback dict updates
- `src/squant/schemas/paper_trading.py` — Event type updates if needed
- `src/squant/schemas/live_trading.py` — Event type updates if needed

### Frontend (modify)

- `frontend/src/views/trading/SessionDetail.vue` — Event handler rewrite
- `frontend/src/types/trading.ts` — New event type interfaces

### Tests (create)

- `tests/unit/engine/test_event_loop.py` — Event loop unit tests
- `tests/unit/engine/test_event_builders.py` — Event builder output tests
- `tests/unit/engine/test_paper_state_update.py` — Paper instant push tests
