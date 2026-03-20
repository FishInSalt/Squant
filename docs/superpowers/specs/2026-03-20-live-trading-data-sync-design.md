# Live Trading Data Sync — Batch A: Order/Fill Data Alignment

## Goal

Make live trading order and fill data fully aligned with exchange real data, by leveraging WebSocket `watchMyTrades` for real-time per-fill data and REST `fetchOrderTrades` as reconciliation fallback.

## Background

The current live trading engine only uses `watchOrders` (WS) and `get_order` (REST polling) for order synchronization. Both return **order-level aggregate data** (total filled_amount, blended avg_price), not individual fill records. This causes:

1. **Partial fill status stuck** — Orders with split fills may never transition from PARTIAL to FILLED correctly
2. **Inaccurate fill prices** — System reverse-calculates incremental fill price from blended averages, introducing precision errors
3. **Inaccurate fill timestamps** — Uses `lastTradeTimestamp` from order object, not per-fill execution time
4. **Missing exchange trade IDs** — `Trade.exchange_tid` is never populated, making exchange reconciliation impossible
5. **No per-fill visibility** — Users cannot see individual fill details for split orders

## Key Constraints

- **Multiple sessions on same account and symbol** — Fill attribution must be by `order_id`, not by symbol
- **Order/fill data uses exchange as source of truth** — Auto-correct local data when discrepancy found
- **Cash and positions remain locally tracked** — Not auto-corrected (session-level accounting)
- **Mixed order types** — Both market and limit orders; partial fills are common
- **Supported exchanges** — OKX, Binance, Bybit (all support `watchMyTrades` and `fetchOrderTrades`)

## Architecture

Two WS private channels with clear separation of concerns, plus REST fallback:

```
watchMyTrades ──→ Per-fill data (price, amount, fee, timestamp, trade_id)
                  Source of truth for fill records

watchOrders   ──→ Order status changes (cancelled, rejected)
                  NO longer used for fill detection

fetchOrderTrades → REST fallback for reconciliation only
                   (WS reconnect, session recovery, fill mismatch)
```

## Design

### Component 1: WS Layer — watchMyTrades Channel

**Files**: `infra/exchange/ws_types.py`, `infra/exchange/ccxt/provider.py`, `infra/exchange/ccxt/transformer.py`

#### New WS Message Type

Follow existing pattern: all WS types in `ws_types.py` are Pydantic `BaseModel` classes.

```python
# ws_types.py
class WSTradeExecution(BaseModel):
    """Per-fill record from watchMyTrades (private channel)."""
    trade_id: str              # Exchange trade ID
    order_id: str              # Exchange order ID
    client_order_id: str | None = None
    symbol: str
    side: str                  # buy/sell
    price: Decimal             # Exact fill price
    amount: Decimal            # Exact fill amount (cost = price * amount, computed on read)
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    taker_or_maker: str | None = None  # taker/maker
    timestamp: datetime        # Exchange execution timestamp
```

Relationship with existing types:
- `WSOrderUpdate` — Order-level status machine (submitted/partial/filled/cancelled)
- `WSTradeExecution` — Individual fill fact record

**Note**: `_dispatch()` method's type union must be updated to include `WSTradeExecution`.

#### Provider Method

```python
# provider.py - CCXTStreamProvider
async def watch_my_trades(self, symbol: str) -> None:
    """Subscribe to user trade execution feed (private, requires credentials).

    Args:
        symbol: Trading symbol (required — Binance and Bybit require symbol;
                OKX supports None but we use symbol for consistency).
    """
```

- Internally starts `_my_trades_loop`, similar to existing `_orders_loop`
- Loop pattern: each iteration calls `self._exchange.watch_my_trades(symbol)`, same as `_orders_loop` calling `watch_orders()` — this ensures re-subscription on reconnect when the exchange instance is recreated by `reconnect()`
- Messages dispatched via existing handler mechanism with type `"trade_execution"`
- Reuses existing reconnection logic (exponential backoff with fast retry)

#### Reconnect Detection

Add a reconnect event mechanism to `CCXTStreamProvider`:

```python
# provider.py
async def add_reconnect_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
    """Register a callback invoked after successful WS reconnection."""
    self._reconnect_handlers.append(handler)
```

When `reconnect()` completes and subscriptions are restored, invoke all registered reconnect handlers. The engine registers `_on_ws_reconnect()` which triggers fill reconciliation for all active orders.

#### Transformer

```python
# transformer.py
@staticmethod
def trade_to_ws_trade_execution(trade: dict) -> WSTradeExecution:
    """Convert CCXT watchMyTrades trade dict to WSTradeExecution."""
```

### Component 2: Engine Layer — Fill Processing Refactor

**Files**: `engine/live/engine.py`

#### Current Flow (problematic)

```
watchOrders → detect filled_size delta → reverse-calculate incremental_price → _record_fill()
```

#### New Flow

```
watchMyTrades → exact per-fill data → _record_fill()
watchOrders   → status changes only (cancelled/rejected) → no fill processing
```

#### Key Changes

1. **New queue**: `_pending_ws_trade_executions: deque[WSTradeExecution]` (maxlen=1000). Uses same copy-and-clear pattern as existing `_pending_ws_updates`.

2. **`_handle_private_ws_message()`** — Add handling for `"trade_execution"` type, enqueue to `_pending_ws_trade_executions`

3. **`_start_private_ws()`** — After connecting, subscribe to both channels:
   - `self._provider.watch_orders(symbol)` (existing)
   - `self._provider.watch_my_trades(symbol)` (new)
   - Register `self._on_ws_reconnect` as reconnect handler

4. **`_drain_ws_updates()`** — Process in two steps:
   - First: drain `_pending_ws_trade_executions` (fill data) — copy-and-clear
   - Then: drain `_pending_ws_updates` (order status changes) — copy-and-clear
   - Order matters: record fills before evaluating terminal status

5. **New method `_process_trade_execution(exec: WSTradeExecution)`**:
   - Find corresponding `LiveOrder` via `exchange_order_id` → `_exchange_order_map`
   - **Skip unknown orders**: If `exchange_order_id` not in `_exchange_order_map`, log warning and skip (fill belongs to another session or manual trade on same account)
   - **Dedup**: Skip if `exec.trade_id` already in `_processed_trade_ids`
   - Update `LiveOrder.filled_amount`, `avg_fill_price`, `fee`
   - Call `_record_fill()` with exact data (price, amount, fee, timestamp)
   - Buffer `"fill"` audit event with `exchange_tid` populated
   - Add `exec.trade_id` to `_processed_trade_ids`

6. **`_handle_order_ws_update()` simplified**:
   - No longer detects fill_delta or calculates incremental_price
   - Only processes: CANCELLED, REJECTED status transitions
   - FILLED status: if local already FILLED (fills arrived first), ignore; if not, mark for reconciliation

7. **REST polling path (`_sync_pending_orders` / `_update_order_from_response()`) changes**:
   - Remove fill detection and `_record_fill()` calls from REST polling path
   - REST polling now only updates order **status** (CANCELLED, REJECTED, etc.)
   - Fill data comes exclusively from `watchMyTrades` (real-time) or `fetchOrderTrades` (reconciliation)
   - This eliminates the duplicate fill risk between WS fills and REST aggregate data

8. **Dedup protection `_processed_trade_ids: set[str]`**:
   - Prevents duplicate recording on WS reconnect
   - Cap at 10,000 entries; on overflow, evict oldest half (simple LRU: convert to `OrderedDict`, pop first 5,000)
   - DB `Trade.exchange_tid` unique index serves as second line of defense (see Schema Changes)

#### Status Transition Logic

```
Fill arrives (watchMyTrades):
  → Update LiveOrder.filled_amount
  → If filled_amount >= amount → mark FILLED
  → If 0 < filled_amount < amount → mark PARTIAL

Status change arrives (watchOrders):
  → CANCELLED/REJECTED → mark terminal status directly
  → FILLED → if local already FILLED (fills arrived first) → ignore
           → if local not FILLED (fills delayed) → queue for reconciliation
```

### Component 3: REST Reconciliation Fallback

**Files**: `engine/live/engine.py`, `infra/exchange/ccxt/rest_adapter.py`, `infra/exchange/base.py`

#### New REST Method

```python
# base.py - ExchangeAdapter (abstract)
async def get_order_trades(self, symbol: str, order_id: str) -> list[TradeInfo]:
    """Get all individual fills for a specific order."""

# types.py — Follow existing pattern: Pydantic BaseModel
class TradeInfo(BaseModel):
    """Individual fill record from exchange."""
    trade_id: str
    order_id: str
    symbol: str
    side: str
    price: Decimal
    amount: Decimal
    fee: Decimal
    fee_currency: str
    taker_or_maker: str | None = None
    timestamp: datetime

# rest_adapter.py - CCXTRestAdapter
async def get_order_trades(self, symbol: str, order_id: str) -> list[TradeInfo]:
    """Call CCXT fetchOrderTrades(order_id, symbol)."""
```

#### Reconciliation Triggers

| Scenario | Trigger |
|----------|---------|
| WS reconnect | Engine's `_on_ws_reconnect()` handler (registered via `provider.add_reconnect_handler()`) → reconcile all active orders |
| Session recovery | After `_reconcile_positions()` in `resume()` flow |
| Fill mismatch | `watchOrders` reports FILLED but local `filled_amount < amount` |

#### Reconciliation Flow

```python
async def _reconcile_order_fills(self, live_order: LiveOrder) -> None:
    # 1. Fetch all fills from exchange
    trades = await self._adapter.get_order_trades(symbol, exchange_order_id)

    # 2. Find fills missing locally (by trade_id)
    missing = [t for t in trades if t.trade_id not in self._processed_trade_ids]

    # 3. Record missing fills (same _record_fill path, source="reconcile")
    for trade in missing:
        self._record_fill(..., source="reconcile")
        self._processed_trade_ids.add(trade.trade_id)

    # 4. Compare final state, record corrections if any
    if local != exchange:
        self._pending_order_events.append({"type": "correction", ...})
```

#### Rate Limiting

- Sequential execution, configurable interval (default 200ms, via `RiskConfig.reconcile_interval_ms`)
- Max orders per reconciliation batch configurable (default 20, via `RiskConfig.reconcile_batch_size`), overflow deferred to next bar

### Component 4: Correction Audit Log

**Files**: `engine/live/engine.py`, `services/live_trading.py`, `models/order.py`

#### New Audit Event Type

```python
{
    "type": "correction",
    "internal_id": "...",
    "exchange_order_id": "...",
    "corrections": [
        {"field": "filled_amount", "before": "0.015", "after": "0.02"},
        {"field": "avg_fill_price", "before": "96500.00", "after": "96487.53"},
        {"field": "status", "before": "partial", "after": "filled"}
    ],
    "reason": "reconcile_after_ws_reconnect",
    "missing_trade_ids": ["t123", "t456"],
    "timestamp": "2026-03-20T10:30:00Z"
}
```

#### Storage

New JSONB field on Order model (requires Alembic migration):

```python
# models/order.py
corrections = Column(JSON, nullable=True, default=None)
# Format: [{"timestamp": "...", "reason": "...", "changes": [...]}]
```

#### Persistence

In `_persist_orders()` callback, handle `"correction"` events:
- Update Order record fields (filled, avg_price, status)
- Append correction record to `Order.corrections` JSONB

### Component 5: Frontend Per-Fill Display

**Files**: `frontend/src/views/trading/SessionDetail.vue`, `frontend/src/views/order/OrderHistory.vue`, `frontend/src/types/order.ts`

#### Data Source

Backend `OrderWithTrades` schema already includes `trades: list[TradeDetail]`. Audit endpoint `GET /api/v1/live/{run_id}/orders` already returns this data. Backend schema updates needed: add `taker_or_maker` to `TradeDetail`, add `corrections` to `OrderDetail`, then regenerate OpenAPI types.

#### Type Updates

```typescript
// types/order.ts
interface TradeDetail {
  id: string
  exchange_tid: string | null
  price: number
  amount: number
  fee: number
  fee_currency: string | null
  taker_or_maker: string | null   // new
  timestamp: string
  fill_source: string             // ws / poll / reconcile
}

interface OrderWithTrades extends Order {
  trades: TradeDetail[]
  corrections: CorrectionRecord[] | null  // new
}

interface CorrectionRecord {
  timestamp: string
  reason: string
  changes: Array<{field: string, before: string, after: string}>
  missing_trade_ids?: string[]
}
```

#### Session Detail — Expandable Order Rows

Each order row expands to show per-fill table:

```
Order #abc123  BTC/USDT  Buy  0.02  Avg 96487.53  Filled
  ├─ #t001  0.008 @ 96500.00  fee 0.077 USDT  taker  10:30:15
  ├─ #t002  0.005 @ 96480.00  fee 0.048 USDT  maker  10:30:17
  └─ #t003  0.007 @ 96475.00  fee 0.068 USDT  taker  10:30:22
```

#### Order History — Detail Dialog

Click order row → dialog showing:
- Order basic info
- Per-fill table (timestamp, price, amount, fee, maker/taker)
- Correction history (if any)

#### K-Line Chart Trade Markers (deferred)

Current: one marker per order at order avg_price. Future improvement: if fills span different candles, each fill gets its own marker at its exact price on the corresponding candle. **Deferred to follow-up** — requires significant KlineCharts API work with no backend dependency.

## Schema Changes

### New: `TradeInfo` (types.py) — Pydantic BaseModel

REST response type for `get_order_trades`.

### New: `WSTradeExecution` (ws_types.py) — Pydantic BaseModel

WS message type for `watchMyTrades` channel.

### Modified: Order model (models/order.py)

- Add `corrections: Column(JSON, nullable=True)` — Alembic migration required

### Modified: Trade model (models/order.py)

- `exchange_tid` — Now populated from `WSTradeExecution.trade_id` (was always NULL)
- Add `taker_or_maker: Column(String(8), nullable=True)` — Alembic migration required
- Widen `fill_source: Column(String(8))` → `Column(String(16))` — current max "reconcile" is 10 chars, exceeds `String(8)`. Alembic migration required.
- Add unique index on `exchange_tid` (filtered: `WHERE exchange_tid IS NOT NULL`) — prevents duplicate fill records as DB-level defense alongside in-memory `_processed_trade_ids`
- **Drop `cost` column**: `cost = price * amount` is trivially computed; storing it introduces consistency risk on corrections. Compute on read instead.

### Modified: TradeDetail schema (schemas/order.py)

- Add `taker_or_maker: str | None`
- Backend schema changes required: update `TradeDetail` and `OrderWithTrades` Pydantic schemas, then regenerate OpenAPI types via `./scripts/generate-api-types.sh`

### Modified: Provider `_dispatch()` type union (provider.py)

- Add `WSTradeExecution` to the data parameter type union

## Testing Strategy

### Unit Tests

- `WSTradeExecution` creation from CCXT trade dict (transformer)
- `_process_trade_execution()` dedup logic (same trade_id ignored)
- `_process_trade_execution()` skips unknown orders (fill for order not in `_exchange_order_map`)
- `_drain_ws_updates()` ordering (fills before status changes)
- `_reconcile_order_fills()` detects and fills gaps
- `_processed_trade_ids` LRU eviction when cap exceeded
- Correction audit event generation
- Status transition: PARTIAL → FILLED via fills (not via watchOrders)
- Race condition: `watchMyTrades` fill arrives during `_reconcile_order_fills()` execution (dedup prevents double recording)
- REST polling path no longer processes fills (only status changes)

### Integration Tests

- `watch_my_trades` subscription on OKX demo account
- `get_order_trades` REST call for a known filled order
- Place order → receive fills via `watchMyTrades` → verify Trade records in DB
- `Trade.exchange_tid` unique index prevents duplicate inserts

### Manual Verification

- Place a large limit order that fills in multiple tranches
- Verify each fill appears with correct price, amount, timestamp, trade_id
- Kill backend during active fills → restart → verify reconciliation fills gaps
- Check correction audit log after reconciliation

## Out of Scope (Batch B)

- Account balance display during session creation
- Pre-order exchange balance validation
- Cash drift auto-correction
- Real-time event persistence to Redis
- Soft capital allocation model with running session equity deduction
