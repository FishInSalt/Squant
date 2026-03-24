# Batch B: Capital Awareness & Validation

**Date**: 2026-03-24
**Status**: Approved
**Depends on**: Batch A (PR #60, merged)

## Overview

Enhance live trading with capital visibility, pre-order balance validation, and crash recovery order reconciliation. All changes follow the established principle: exchange is source of truth for orders, local engine tracks cash/positions.

## Scope

| ID | Feature | Summary |
|----|---------|---------|
| B1 | Account balance display | Show available balance when creating live session |
| B1+ | Resume balance check | Validate sufficient balance before resuming a session |
| B2 | Insufficient balance handling | Detect and notify when order fails due to insufficient funds |
| B4 | Recovery order reconciliation | Full order reconciliation on session resume |

**Deferred**: B3 (cash drift handling) absorbed by B2 — the only harmful drift scenario (exchange balance < session cash) is caught at order time.

## B1: Account Balance Display

### Backend API

New endpoint: `GET /api/v1/live/account-balance/{account_id}`

**Response schema**:

```json
{
  "account_total_value": 5000.00,
  "running_sessions": [
    {
      "run_id": "uuid",
      "strategy_name": "MA Cross",
      "symbol": "BTC/USDT",
      "equity": 1200.50
    }
  ],
  "sessions_total_equity": 2400.00,
  "available": 2600.00
}
```

**Implementation** (`LiveTradingService.get_account_available_balance`):

1. Fetch exchange account → create adapter → `get_balance()` → compute `account_total_value` in quote currency
2. Query all RUNNING `StrategyRun` records for this account (new repo method: `list_running_by_account(account_id)`)
3. For each running session:
   - Try `session_manager.get(run_id)` → `engine.context.equity` (real-time from memory)
   - Fallback: read `StrategyRun.result` JSONB → `result["equity"]` (last saved snapshot)
4. `available = account_total_value - sum(session equities)`

**Computing `account_total_value`** (multi-currency conversion):

The exchange account may hold multiple currencies (e.g., USDT + BTC). Session equity is denominated in the quote currency (e.g., USDT), so `account_total_value` must be converted to quote currency for the formula to be consistent.

Strategy:
1. **Priority**: Check `fetchBalance()` raw response (`info` field) for exchange-native total equity (e.g., OKX `totalEq`) → use directly if available
2. **Fallback**: Manual conversion — for each non-zero, non-quote currency balance, call `get_ticker(CURRENCY/QUOTE)` to get price, then sum:
   ```
   account_total_value = quote_balance.total + Σ(other.total × ticker.last)
   ```

The quote currency is derived from the session's symbol (e.g., `BTC/USDT` → quote = `USDT`). This requires at most 1-2 ticker lookups (accounts rarely hold many different currencies), so latency is acceptable.

**Edge cases**:
- No running sessions → available = account_total_value
- Engine not in memory (recovering) → use DB snapshot equity
- Exchange API failure → return error, frontend shows warning but doesn't block form
- Ticker lookup fails for a currency → include only the raw balance amount with a warning, don't block the calculation

### Frontend

**Trigger**: `handleAccountChange()` in `LiveTrading.vue` — auto-query when user selects an account.

**Display**: Above the "投入资金" input field:

```
可用余额：2,600.00 USDT ＝ 5,000.00 − 2,400.00（运行中会话占用）
```

**Hover tooltip** on the calculation portion shows breakdown:

```
账户总值：5,000.00 USDT
━━━━━━━━━━━━━━━━━━━━━━
运行中会话占用：
  MA Cross (BTC/USDT)    1,200.50
  RSI Scalp (ETH/USDT)   1,199.50
━━━━━━━━━━━━━━━━━━━━━━
合计占用：2,400.00
可用余额：2,600.00
```

**States**:
- Loading: `el-skeleton` placeholder
- Error: `el-alert` warning, form still submittable
- No running sessions: show simplified "可用余额：5,000.00 USDT（无运行中会话）"

## B1+: Resume Balance Check

### Problem

When resuming a stopped/errored session, the account may no longer have sufficient funds (other sessions started, manual trades consumed balance, withdrawals, etc.).

### Implementation

**Location**: `LiveTradingService.resume()`, after engine creation but before registration with session manager. This minimizes the race window between balance check and session becoming RUNNING.

**Logic**:

```python
# Reuse B1's calculation
balance_info = await self.get_account_available_balance(account_id)
session_equity = saved_result["equity"]  # from StrategyRun.result snapshot

if session_equity > balance_info.available:
    raise ValueError(
        f"Insufficient balance to resume session. "
        f"Session equity: {session_equity}, "
        f"Available: {balance_info.available}"
    )
```

**Note**: This is a soft check — it uses the same formula as B1. The session being resumed is NOT yet in RUNNING state, so its equity is not included in `sessions_total_equity`. The check is: can the account absorb this session's equity on top of existing running sessions?

**Known limitation**: If two sessions for the same account are resumed simultaneously, both may pass the check before either is registered. This is inherent to soft allocation and acceptable for a personal trading system.

**Frontend**: The resume API already returns errors as `{"code": 400, "message": ...}`. The existing error toast in the frontend will display the insufficient balance message.

## B2: Insufficient Balance Handling

### Design Decision

**No pre-check**. Let the exchange reject the order, then handle the error. Rationale:
- Exchange is the source of truth for balance
- Avoids extra API call and race conditions
- CCXT already maps `InsufficientFunds` → `InvalidOrderError`

### Implementation

**Location**: `LiveTradingEngine._submit_order()` exception handler (line ~2629)

Current behavior: all non-timeout exceptions → `REJECTED` + log.
New behavior: additionally detect insufficient funds and push notification.

```python
from squant.infra.exchange.exceptions import InvalidOrderError

except Exception as e:
    err_msg = str(e).lower()
    if "timeout" in err_msg or "requesttimeout" in err_msg:
        # existing timeout handling...
    else:
        order.status = OrderStatus.REJECTED
        # NEW: detect insufficient funds via exception type (not string matching)
        is_insufficient = (
            isinstance(e, InvalidOrderError) and e.field == "amount"
        )
        if is_insufficient:
            _fire_notification(
                self._run_id,
                level="warning",
                event_type="insufficient_funds",
                title="余额不足",
                message=f"下单失败：{order.symbol} {order.side.value} {order.amount}，交易所余额不足",
            )
        # existing rejection logic...
```

**Why type checking over string matching**: The adapter already maps `ccxt.InsufficientFunds` to `InvalidOrderError(field="amount")`. Checking the exception type is robust against message format changes across exchanges and CCXT versions.

**Frontend**: Receives notification via existing WebSocket event channel → displays `ElNotification` warning. Reuses the existing `_fire_notification()` helper (fire-and-forget via `asyncio.create_task`).

### What This Does NOT Do

- Does not auto-adjust order size (YAGNI, may break strategy logic)
- Does not pre-fetch balance (race condition, extra latency)
- Does not pause/stop the session (one rejected order is not fatal)

## B4: Recovery Order Reconciliation

### Problem

If the engine crashes during `adapter.place_order()`, the order may exist on the exchange but have no record in our DB. The existing `_reconcile_stale_db_orders()` only handles orders that ARE in DB but have stale status.

### Solution

On session resume, fetch all orders from exchange within a targeted time range and compare against DB records. Supplement any missing orders.

### Time Range

```
since = last_bar_time - 1 × timeframe_duration
until = now
```

- `last_bar_time`: from saved `StrategyRun.result` JSONB snapshot
- Subtract 1 bar as safety margin for snapshot/order timing differences
- Fallback to `session.started_at` if `last_bar_time` is unavailable

**Why this is safe**: The query range is `since` → `now`. Since `last_bar_time` represents the last successfully saved state, any orders after that point might be missing. The -1 bar margin covers edge cases where snapshot save and order submission overlap.

### Reconciliation Flow

```
resume():
  1. Balance check (B1+)
  2. Restore engine state from snapshot (existing)
  3. NEW: full order reconciliation
     a. Fetch exchange orders: adapter.get_orders(symbol, since=computed_since)
     b. Fetch DB orders: order_repo.list(run_id=run_id)
     c. Match by exchange_order_id
     d. For each exchange order NOT in DB:
        - Fetch fills: adapter.get_order_trades(symbol, exchange_oid)
        - Create Order + Trade records in DB
        - Update engine context (cash, positions) if fills exist
        - Mark fill_source = "reconcile_missing" (distinguishes from existing "reconcile" used for stale-status orders)
     e. For each DB order with stale status:
        - Update from exchange data (existing _reconcile_stale_db_orders logic, fill_source = "reconcile")
  4. Subscribe to market data and start (existing)
```

### New Exchange Adapter Method

```python
async def get_orders(
    self, symbol: str, since: datetime | None = None
) -> list[OrderResponse]:
    """Fetch all orders (open + closed) for symbol since given time."""
```

Underlying CCXT: `fetchClosedOrders(symbol, since) + fetchOpenOrders(symbol, since)` combined.

### Relationship with Existing Reconciliation

The current resume flow has two reconciliation steps:
1. `_reconcile_orders()` — reconciles in-memory `_live_orders` against exchange **open** orders
2. `_reconcile_stale_db_orders()` — reconciles DB orders with non-terminal status

B4 **supplements** these (does not replace them). It covers the gap: orders that exist on the exchange but are **completely absent from DB** (crash during `place_order()`). B4 runs after engine state restore but before the existing reconciliation steps, so any orders it discovers and records in DB will be visible to subsequent steps.

**Pagination**: Some exchanges limit `fetchClosedOrders` results (e.g., OKX: 100 per call). The `get_orders()` implementation should handle pagination to ensure completeness within the time range.

### Risk Controls

- Reconciliation runs once on resume, not during normal operation
- Missing orders marked `fill_source = "reconcile_missing"` for audit trail (distinct from existing `"reconcile"` for stale-status orders)
- Errors during reconciliation logged as warning, do not block engine startup
- Engine context (cash/positions) updated for reconciled fills to maintain consistency

## Data Flow Summary

```
┌─────────────────────────────────────────────────┐
│              Session Creation (B1)               │
│                                                  │
│  User selects account                            │
│       ↓                                          │
│  GET /api/v1/live/account-balance/{id}           │
│       ↓                                          │
│  Display: available = total - Σ(session equity)  │
│  Tooltip: breakdown per running session          │
│       ↓                                          │
│  User enters 投入资金 → start session            │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│           Session Resume (B1+)                    │
│                                                  │
│  User clicks resume                              │
│       ↓                                          │
│  Check: session equity ≤ available balance?       │
│       ↓ (insufficient)                           │
│  Reject with error message                       │
│       ↓ (sufficient)                             │
│  Proceed to restore + reconcile (B4) + start     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│            Order Submission (B2)                  │
│                                                  │
│  Strategy signal → _submit_order()               │
│       ↓                                          │
│  adapter.place_order()                           │
│       ↓ (InsufficientFunds)                      │
│  REJECTED + notify user via WebSocket            │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│           Session Recovery (B4)                   │
│                                                  │
│  resume() → balance check (B1+)                  │
│       ↓                                          │
│  restore state from snapshot                     │
│       ↓                                          │
│  adapter.get_orders(since=last_bar - 1 bar)      │
│       ↓                                          │
│  Compare exchange orders vs DB orders            │
│       ↓ (missing in DB)                          │
│  Fetch fills → create Order+Trade → update ctx   │
│       ↓                                          │
│  Start receiving new bars                        │
└─────────────────────────────────────────────────┘
```

## Files to Modify

### Backend
- `src/squant/services/live_trading.py` — `get_account_available_balance()`, `list_running_by_account()` repo method, resume balance check, resume reconciliation
- `src/squant/api/v1/live_trading.py` — new balance endpoint
- `src/squant/schemas/live_trading.py` — balance response schema
- `src/squant/engine/live/engine.py` — insufficient funds notification in `_submit_order()` (type-based detection using `InvalidOrderError`)
- `src/squant/infra/exchange/ccxt/rest_adapter.py` — `get_orders()` method (with pagination), `get_account_total_value()` helper (multi-currency conversion)
- `src/squant/infra/exchange/base.py` — abstract `get_orders()` method
- `src/squant/infra/exchange/types.py` — `AccountTotalValue` response type (if needed)

### Frontend
- `frontend/src/views/trading/LiveTrading.vue` — balance display + tooltip
- `frontend/src/api/live.ts` — `getAccountBalance()` API call
- `frontend/src/types/` — balance response type (auto-generated)

### Tests
- Unit tests for `get_account_available_balance()` service method
- Unit tests for `get_orders()` adapter method
- Unit tests for recovery reconciliation logic
- Unit tests for insufficient funds notification path
- Unit tests for resume balance check

## Non-Goals

- Hard capital allocation at exchange level (soft allocation only)
- Auto-adjusting order size on insufficient balance
- Real-time balance push via WebSocket (polling on account select is sufficient)
- Cash drift auto-correction (B3 absorbed by B2)
- Order event WAL via Redis (simpler recovery reconciliation chosen instead)
