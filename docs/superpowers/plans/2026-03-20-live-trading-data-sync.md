# Live Trading Data Sync Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align live trading order/fill data with exchange real data by leveraging `watchMyTrades` WebSocket channel for real-time per-fill data and `fetchOrderTrades` as reconciliation fallback.

**Architecture:** Two WS private channels (`watchMyTrades` for per-fill data, `watchOrders` for status changes) with REST `fetchOrderTrades` as reconciliation fallback. Fill processing removed from REST polling path. In-memory `_processed_trade_ids` with LRU eviction + DB unique index for dedup.

**Tech Stack:** Python 3.12, CCXT (REST + WebSocket), SQLAlchemy async, Alembic, Pydantic, Vue 3 + TypeScript

**Spec:** `docs/superpowers/specs/2026-03-20-live-trading-data-sync-design.md`

---

## File Structure

### New Files
- `tests/unit/infra/exchange/test_ws_trade_execution.py` — WSTradeExecution transformer tests
- `tests/unit/infra/exchange/test_get_order_trades.py` — REST get_order_trades tests
- `tests/unit/infra/exchange/test_provider_my_trades.py` — Provider watchMyTrades tests
- `tests/unit/engine/live/test_fill_sync.py` — Engine fill processing + reconciliation tests
- `alembic/versions/xxxx_add_trade_sync_fields.py` — DB migration (auto-generated)

### Modified Files
- `src/squant/infra/exchange/ws_types.py` — Add `WSTradeExecution` model
- `src/squant/infra/exchange/types.py` — Add `TradeInfo` model, `WSMessageType.TRADE_EXECUTION`
- `src/squant/infra/exchange/base.py` — Add abstract `get_order_trades()` method
- `src/squant/infra/exchange/ccxt/transformer.py` — Add `trade_to_ws_trade_execution()` static method
- `src/squant/infra/exchange/ccxt/rest_adapter.py` — Implement `get_order_trades()`
- `src/squant/infra/exchange/ccxt/provider.py` — Add `watch_my_trades()`, `_my_trades_loop()`, reconnect handlers, update `_dispatch()` type union
- `src/squant/engine/live/engine.py` — Refactor fill processing, add reconciliation, subscribe to `watch_my_trades`
- `src/squant/engine/risk/models.py` — Add `reconcile_interval_ms`, `reconcile_batch_size` to `RiskConfig`
- `src/squant/models/order.py` — Add `corrections`, `taker_or_maker` columns, widen `fill_source`
- `src/squant/schemas/order.py` — Add `taker_or_maker`, `fill_source`, `corrections` to schemas
- `src/squant/services/live_trading.py` — Handle `"correction"` events in persist callback
- `frontend/src/types/order.ts` — Add `TradeDetail`, `CorrectionRecord` types
- `frontend/src/views/trading/SessionDetail.vue` — Expandable order rows with per-fill details
- `frontend/src/views/order/OrderHistory.vue` — Order detail dialog with fills

---

## Chunk 1: Foundation Types

### Task 1: WSTradeExecution Type

**Files:**
- Modify: `src/squant/infra/exchange/ws_types.py`
- Modify: `src/squant/infra/exchange/types.py`
- Test: `tests/unit/infra/exchange/test_ws_trade_execution.py`

**Context:** All WS types in `ws_types.py` are Pydantic `BaseModel` classes. `WSMessageType` enum in `types.py` defines message type strings.

- [ ] **Step 1: Write test for WSTradeExecution construction**

```python
# tests/unit/infra/exchange/test_ws_trade_execution.py
from datetime import datetime, UTC
from decimal import Decimal

from squant.infra.exchange.ws_types import WSTradeExecution


class TestWSTradeExecution:
    def test_create_from_fields(self):
        trade = WSTradeExecution(
            trade_id="t123456",
            order_id="o789",
            client_order_id="cli001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500.00"),
            amount=Decimal("0.008"),
            fee=Decimal("0.077"),
            fee_currency="USDT",
            taker_or_maker="taker",
            timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
        )
        assert trade.trade_id == "t123456"
        assert trade.order_id == "o789"
        assert trade.price == Decimal("96500.00")
        assert trade.amount == Decimal("0.008")
        assert trade.taker_or_maker == "taker"

    def test_defaults(self):
        trade = WSTradeExecution(
            trade_id="t1",
            order_id="o1",
            symbol="ETH/USDT",
            side="sell",
            price=Decimal("3000"),
            amount=Decimal("1"),
            timestamp=datetime.now(UTC),
        )
        assert trade.client_order_id is None
        assert trade.fee == Decimal("0")
        assert trade.fee_currency == ""
        assert trade.taker_or_maker is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infra/exchange/test_ws_trade_execution.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'WSTradeExecution'`

- [ ] **Step 3: Add WSTradeExecution to ws_types.py**

Add after `WSAccountUpdate` class (after line 110 in `ws_types.py`):

```python
class WSTradeExecution(BaseModel):
    """Per-fill record from watchMyTrades (private channel).

    Unlike WSOrderUpdate which gives order-level aggregates (total filled_size,
    blended avg_price), this type represents a single fill with exact price,
    amount, fee, and exchange timestamp.
    """

    trade_id: str
    order_id: str
    client_order_id: str | None = None
    symbol: str
    side: str
    price: Decimal
    amount: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    taker_or_maker: str | None = None
    timestamp: datetime
```

Also add `TRADE_EXECUTION = "trade_execution"` to `WSMessageType` enum in `types.py` (after `ORDER_UPDATE` line 36).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/infra/exchange/test_ws_trade_execution.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/squant/infra/exchange/ws_types.py src/squant/infra/exchange/types.py tests/unit/infra/exchange/test_ws_trade_execution.py
git commit -m "feat: add WSTradeExecution type for per-fill WS data"
```

---

### Task 2: TradeInfo Type + REST Adapter

**Files:**
- Modify: `src/squant/infra/exchange/types.py`
- Modify: `src/squant/infra/exchange/base.py`
- Modify: `src/squant/infra/exchange/ccxt/rest_adapter.py`
- Test: `tests/unit/infra/exchange/test_get_order_trades.py`

**Context:** `ExchangeAdapter` at `base.py` defines abstract methods. `CCXTRestAdapter` implements them. All types in `types.py` are Pydantic `BaseModel`.

- [ ] **Step 1: Write test for get_order_trades**

```python
# tests/unit/infra/exchange/test_get_order_trades.py
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.types import TradeInfo


class TestGetOrderTrades:
    @pytest.fixture
    def adapter(self):
        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)
        adapter._exchange = MagicMock()
        adapter._exchange.fetch_order_trades = AsyncMock()
        adapter._connected = True
        return adapter

    async def test_returns_trade_info_list(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = [
            {
                "id": "t001",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96500.0,
                "amount": 0.008,
                "fee": {"cost": 0.077, "currency": "USDT"},
                "takerOrMaker": "taker",
                "timestamp": 1711000215000,
            },
            {
                "id": "t002",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96480.0,
                "amount": 0.005,
                "fee": {"cost": 0.048, "currency": "USDT"},
                "takerOrMaker": "maker",
                "timestamp": 1711000217000,
            },
        ]

        result = await adapter.get_order_trades("BTC/USDT", "o123")

        assert len(result) == 2
        assert isinstance(result[0], TradeInfo)
        assert result[0].trade_id == "t001"
        assert result[0].price == Decimal("96500.0")
        assert result[0].fee == Decimal("0.077")
        assert result[0].taker_or_maker == "taker"
        assert result[1].trade_id == "t002"

    async def test_empty_result(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = []
        result = await adapter.get_order_trades("BTC/USDT", "o123")
        assert result == []

    async def test_handles_missing_fee(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = [
            {
                "id": "t001",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96500.0,
                "amount": 0.008,
                "fee": None,
                "takerOrMaker": None,
                "timestamp": 1711000215000,
            }
        ]
        result = await adapter.get_order_trades("BTC/USDT", "o123")
        assert result[0].fee == Decimal("0")
        assert result[0].fee_currency == ""
        assert result[0].taker_or_maker is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infra/exchange/test_get_order_trades.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'TradeInfo'`

- [ ] **Step 3: Add TradeInfo to types.py**

Add after `OrderResponse` class in `types.py`:

```python
class TradeInfo(BaseModel):
    """Individual fill record from exchange (REST fetchOrderTrades)."""

    trade_id: str
    order_id: str
    symbol: str
    side: str
    price: Decimal
    amount: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str = ""
    taker_or_maker: str | None = None
    timestamp: datetime
```

- [ ] **Step 4: Add abstract method to base.py**

Add to `ExchangeAdapter` class after `get_open_orders()` (after line 215):

```python
@abstractmethod
async def get_order_trades(self, symbol: str, order_id: str) -> list[TradeInfo]:
    """Get all individual fills for a specific order.

    Args:
        symbol: Trading symbol (e.g., "BTC/USDT").
        order_id: Exchange order ID.

    Returns:
        List of TradeInfo records sorted by timestamp ascending.
    """
```

Add `TradeInfo` to the imports from `types.py`.

- [ ] **Step 5: Implement in rest_adapter.py**

Add to `CCXTRestAdapter` class:

```python
async def get_order_trades(self, symbol: str, order_id: str) -> list[TradeInfo]:
    """Get all individual fills for a specific order via CCXT fetchOrderTrades."""

    async def _impl() -> list[TradeInfo]:
        raw_trades = await self._exchange.fetch_order_trades(order_id, symbol)
        result = []
        for t in raw_trades:
            fee_info = t.get("fee") or {}
            ts = t.get("timestamp")
            timestamp = (
                datetime.fromtimestamp(ts / 1000, tz=UTC)
                if ts is not None
                else datetime.now(UTC)
            )
            result.append(
                TradeInfo(
                    trade_id=str(t.get("id", "")),
                    order_id=str(t.get("order", "")),
                    symbol=t.get("symbol", symbol),
                    side=t.get("side", ""),
                    price=Decimal(str(t.get("price") or 0)),
                    amount=Decimal(str(t.get("amount") or 0)),
                    fee=Decimal(str(fee_info.get("cost") or 0)),
                    fee_currency=fee_info.get("currency") or "",
                    taker_or_maker=t.get("takerOrMaker"),
                    timestamp=timestamp,
                )
            )
        result.sort(key=lambda x: x.timestamp)
        return result

    return await with_retry(_impl, config=_READ_RETRY, operation_name="get_order_trades")
```

Follow existing adapter pattern: wrap implementation in inner function, call `with_retry()`. Import `TradeInfo` from types. Timestamp conversion is inlined (not via `_transformer` which belongs to the provider, not the adapter).

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/infra/exchange/test_get_order_trades.py -v --no-cov`
Expected: PASS

- [ ] **Step 7: Run existing adapter tests to verify no regressions**

Run: `uv run pytest tests/unit/infra/exchange/ -v --no-cov`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/squant/infra/exchange/types.py src/squant/infra/exchange/base.py src/squant/infra/exchange/ccxt/rest_adapter.py tests/unit/infra/exchange/test_get_order_trades.py
git commit -m "feat: add TradeInfo type and get_order_trades REST adapter method"
```

---

### Task 3: Transformer — trade_to_ws_trade_execution

**Files:**
- Modify: `src/squant/infra/exchange/ccxt/transformer.py`
- Test: `tests/unit/infra/exchange/test_ws_trade_execution.py` (extend)

**Context:** All transformer methods are `@staticmethod` on `CCXTDataTransformer`. They convert CCXT dicts to internal types. `_parse_timestamp()` at line 301 converts ms to datetime.

- [ ] **Step 1: Write test for transformer**

Append to `tests/unit/infra/exchange/test_ws_trade_execution.py`:

```python
from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer


class TestTradeToWSTradeExecution:
    def test_transforms_ccxt_trade(self):
        ccxt_trade = {
            "id": "t001",
            "order": "o123",
            "clientOrderId": "cli001",
            "symbol": "BTC/USDT",
            "side": "buy",
            "price": 96500.0,
            "amount": 0.008,
            "fee": {"cost": 0.077, "currency": "USDT"},
            "takerOrMaker": "taker",
            "timestamp": 1711000215000,
        }
        result = CCXTDataTransformer.trade_to_ws_trade_execution(ccxt_trade)
        assert isinstance(result, WSTradeExecution)
        assert result.trade_id == "t001"
        assert result.order_id == "o123"
        assert result.client_order_id == "cli001"
        assert result.price == Decimal("96500.0")
        assert result.amount == Decimal("0.008")
        assert result.fee == Decimal("0.077")
        assert result.fee_currency == "USDT"
        assert result.taker_or_maker == "taker"

    def test_handles_missing_fields(self):
        ccxt_trade = {
            "id": "t002",
            "order": "o456",
            "symbol": "ETH/USDT",
            "side": "sell",
            "price": 3000.0,
            "amount": 1.0,
            "fee": None,
            "takerOrMaker": None,
            "timestamp": None,
        }
        result = CCXTDataTransformer.trade_to_ws_trade_execution(ccxt_trade)
        assert result.client_order_id is None
        assert result.fee == Decimal("0")
        assert result.fee_currency == ""
        assert result.taker_or_maker is None
        assert result.timestamp is not None  # falls back to utcnow
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infra/exchange/test_ws_trade_execution.py::TestTradeToWSTradeExecution -v --no-cov`
Expected: FAIL with `AttributeError: type object 'CCXTDataTransformer' has no attribute 'trade_to_ws_trade_execution'`

- [ ] **Step 3: Implement transformer method**

Add to `CCXTDataTransformer` class in `transformer.py` (after `balance_to_ws_account_update`, before `_parse_timestamp`):

```python
@staticmethod
def trade_to_ws_trade_execution(trade: dict[str, Any]) -> WSTradeExecution:
    """Convert a CCXT trade dict (from watchMyTrades) to WSTradeExecution.

    Args:
        trade: CCXT unified trade structure.

    Returns:
        WSTradeExecution with per-fill data.
    """
    fee_info = trade.get("fee") or {}
    ts = trade.get("timestamp")
    timestamp = (
        datetime.fromtimestamp(ts / 1000, tz=UTC)
        if ts is not None
        else datetime.now(UTC)
    )
    return WSTradeExecution(
        trade_id=str(trade.get("id", "")),
        order_id=str(trade.get("order", "")),
        client_order_id=trade.get("clientOrderId"),
        symbol=trade.get("symbol", ""),
        side=trade.get("side", ""),
        price=Decimal(str(trade.get("price") or 0)),
        amount=Decimal(str(trade.get("amount") or 0)),
        fee=Decimal(str(fee_info.get("cost") or 0)),
        fee_currency=fee_info.get("currency") or "",
        taker_or_maker=trade.get("takerOrMaker"),
        timestamp=timestamp,
    )
```

Add `WSTradeExecution` to imports from `ws_types`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/infra/exchange/test_ws_trade_execution.py -v --no-cov`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/squant/infra/exchange/ccxt/transformer.py tests/unit/infra/exchange/test_ws_trade_execution.py
git commit -m "feat: add trade_to_ws_trade_execution transformer"
```

---

## Chunk 2: Provider — watchMyTrades + Reconnect

### Task 4: CCXTStreamProvider — watchMyTrades and Reconnect Handlers

**Files:**
- Modify: `src/squant/infra/exchange/ccxt/provider.py`
- Test: `tests/unit/infra/exchange/test_provider_my_trades.py`

**Context:** The provider uses subscription loops (e.g., `_orders_loop` at line 932) that call CCXT `watch_*()` methods in a while loop. Messages are dispatched via `_dispatch()` to registered handlers. The `_dispatch()` type union at line 993 must include `WSTradeExecution`. `reconnect()` at line 303 recreates the exchange instance — loops re-subscribe automatically because each iteration calls the CCXT method.

- [ ] **Step 1: Write tests**

```python
# tests/unit/infra/exchange/test_provider_my_trades.py
from collections import deque
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.ws_types import WSTradeExecution


class TestWatchMyTrades:
    @pytest.fixture
    def provider(self):
        p = CCXTStreamProvider.__new__(CCXTStreamProvider)
        p._exchange = MagicMock()
        p._exchange_id = "okx"
        p._credentials = MagicMock()
        p._running = True
        p._connected = True
        p._subscription_tasks = {}
        p._handlers = []
        p._reconnect_handlers = []
        p._transformer = MagicMock()
        p._consecutive_errors = {}
        p._subscription_reconnect_count = {}
        p._reconnect_lock = MagicMock()
        return p

    async def test_watch_my_trades_creates_task(self, provider):
        with patch.object(provider, "_my_trades_loop", new_callable=AsyncMock):
            import asyncio
            # Mock create_task
            with patch("asyncio.create_task") as mock_create:
                mock_task = MagicMock()
                mock_task.done.return_value = False
                mock_create.return_value = mock_task
                await provider.watch_my_trades("BTC/USDT")
                assert "my_trades:BTC/USDT" in provider._subscription_tasks

    async def test_watch_my_trades_requires_credentials(self, provider):
        provider._credentials = None
        from squant.infra.exchange.exceptions import ExchangeAuthenticationError
        with pytest.raises(ExchangeAuthenticationError):
            await provider.watch_my_trades("BTC/USDT")

    async def test_watch_my_trades_skips_duplicate(self, provider):
        mock_task = MagicMock()
        mock_task.done.return_value = False
        provider._subscription_tasks["my_trades:BTC/USDT"] = mock_task
        # Should not create a new task
        await provider.watch_my_trades("BTC/USDT")
        # Task should still be the same
        assert provider._subscription_tasks["my_trades:BTC/USDT"] is mock_task


class TestReconnectHandlers:
    @pytest.fixture
    def provider(self):
        p = CCXTStreamProvider.__new__(CCXTStreamProvider)
        p._reconnect_handlers = []
        return p

    async def test_add_reconnect_handler(self, provider):
        handler = AsyncMock()
        provider.add_reconnect_handler(handler)
        assert handler in provider._reconnect_handlers

    async def test_remove_reconnect_handler(self, provider):
        handler = AsyncMock()
        provider.add_reconnect_handler(handler)
        provider.remove_reconnect_handler(handler)
        assert handler not in provider._reconnect_handlers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/infra/exchange/test_provider_my_trades.py -v --no-cov`
Expected: FAIL (methods don't exist yet)

- [ ] **Step 3: Implement provider changes**

In `provider.py`:

**3a. Add `_reconnect_handlers` to `__init__`** (around line 150):
```python
self._reconnect_handlers: list[Callable[[], Awaitable[None]]] = []
```

Also add `Awaitable` to the import from `collections.abc` (line 9 already imports `Callable` and `Coroutine`).

**3b. Add `add_reconnect_handler` and `remove_reconnect_handler` methods** (after `remove_handler` at line 501):
```python
def add_reconnect_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
    """Register a callback invoked after successful WS reconnection."""
    if handler not in self._reconnect_handlers:
        self._reconnect_handlers.append(handler)

def remove_reconnect_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
    """Remove a reconnect callback."""
    if handler in self._reconnect_handlers:
        self._reconnect_handlers.remove(handler)
```

**3c. Invoke reconnect handlers in `reconnect()` method** (after `logger.info("Successfully reconnected...")` around line 340):
```python
# Notify reconnect handlers
for handler in self._reconnect_handlers:
    try:
        await handler()
    except Exception as e:
        logger.error(f"Reconnect handler error: {e}")
```

**3d. Add `watch_my_trades()` method** (after `watch_orders` at line 624):
```python
async def watch_my_trades(self, symbol: str) -> None:
    """Subscribe to user trade execution feed (private channel).

    Args:
        symbol: Trading symbol (required — Binance/Bybit require it;
                OKX supports None but we use symbol for consistency).
    """
    if not self._credentials:
        raise ExchangeAuthenticationError(
            message="Credentials required for private channels",
            exchange=self._exchange_id,
        )
    key = f"my_trades:{symbol}"
    if key in self._subscription_tasks:
        if not self._subscription_tasks[key].done():
            logger.debug(f"Already watching my trades: {symbol}")
            return
        logger.warning(f"Restarting dead my_trades task for {symbol}")
        del self._subscription_tasks[key]
    task = asyncio.create_task(self._my_trades_loop(symbol))
    self._subscription_tasks[key] = task
    logger.info(f"Started watching my trades: {symbol}")
```

**3e. Add `_my_trades_loop()` method** (after `_orders_loop` at line 959):
```python
async def _my_trades_loop(self, symbol: str) -> None:
    """Background loop for user trade execution updates."""
    key = f"my_trades:{symbol}"
    try:
        if not await self._wait_until_ready(key):
            return
        while self._running:
            try:
                if not self._exchange:
                    await asyncio.sleep(1)
                    continue
                trades = await self._exchange.watch_my_trades(symbol)
                self._mark_success(key)
                for trade in trades:
                    ws_trade = self._transformer.trade_to_ws_trade_execution(trade)
                    await self._dispatch("trade_execution", ws_trade)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not await self._handle_loop_error(key, e):
                    break
                await asyncio.sleep(1)
    finally:
        self._subscription_tasks.pop(key, None)
        logger.info(f"My trades loop exited for {symbol}")
```

**3f. Update `_dispatch()` type union** (line 993):
Change from:
```python
data: WSTicker | WSCandle | WSTrade | WSOrderBook | WSOrderUpdate | WSAccountUpdate,
```
To:
```python
data: WSTicker | WSCandle | WSTrade | WSOrderBook | WSOrderUpdate | WSAccountUpdate | WSTradeExecution,
```

Add `WSTradeExecution` to imports from `ws_types`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/infra/exchange/test_provider_my_trades.py -v --no-cov`
Expected: All PASS

- [ ] **Step 5: Run existing provider tests**

Run: `uv run pytest tests/unit/infra/exchange/ -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/infra/exchange/ccxt/provider.py tests/unit/infra/exchange/test_provider_my_trades.py
git commit -m "feat: add watchMyTrades WS channel and reconnect handlers to provider"
```

---

## Chunk 3: Database Migration + Config

### Task 5: Alembic Migration

**Files:**
- Modify: `src/squant/models/order.py`
- Create: Alembic migration (auto-generated)

**Context:** Trade model at `models/order.py` lines 73-102. `fill_source` is `String(8)` at line 91. `exchange_tid` is `String(64)` nullable at line 80. Order model at lines 18-70.

- [ ] **Step 1: Update Trade model**

In `src/squant/models/order.py`, modify the `Trade` class:

Add after `fill_source` field (line 91):
```python
taker_or_maker: Mapped[str | None] = mapped_column(String(8), nullable=True)
```

Change `fill_source` from `String(8)` to `String(16)`:
```python
fill_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

- [ ] **Step 2: Update Order model**

Add to `Order` class (after existing fields, before relationships):
```python
corrections: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
```

Import `JSON` from `sqlalchemy` if not already imported.

- [ ] **Step 3: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add trade sync fields"`
Expected: New migration file created in `alembic/versions/`

- [ ] **Step 4: Manually verify migration**

Read the generated migration file and verify it contains:
1. `ALTER TABLE trades ALTER COLUMN fill_source TYPE VARCHAR(16)` (or equivalent)
2. `ADD COLUMN taker_or_maker VARCHAR(8)` to trades
3. `ADD COLUMN corrections JSON` to orders
4. Create unique filtered index on `trades.exchange_tid WHERE exchange_tid IS NOT NULL`

If the unique index is not auto-generated, add it manually:
```python
from sqlalchemy import Index

# In upgrade():
op.create_index(
    "ix_trades_exchange_tid_unique",
    "trades",
    ["exchange_tid"],
    unique=True,
    postgresql_where=sa.text("exchange_tid IS NOT NULL"),
)

# In downgrade():
op.drop_index("ix_trades_exchange_tid_unique", table_name="trades")
```

- [ ] **Step 5: Run migration**

Run: `uv run alembic upgrade head`
Expected: Migration applied successfully

- [ ] **Step 6: Commit**

```bash
git add src/squant/models/order.py alembic/versions/
git commit -m "feat: add trade sync DB fields (taker_or_maker, corrections, fill_source widen, exchange_tid unique index)"
```

---

### Task 6: RiskConfig New Fields

**Files:**
- Modify: `src/squant/engine/risk/models.py`

**Context:** `RiskConfig` at `models.py` lines 53-147. Has `order_poll_interval` and `balance_check_interval` at lines 139-147.

- [ ] **Step 1: Add reconciliation config fields**

Add after `balance_check_interval` in `RiskConfig`:
```python
reconcile_interval_ms: int = Field(
    default=200,
    ge=50,
    le=5000,
    description="Minimum interval between REST reconciliation queries (milliseconds)",
)
reconcile_batch_size: int = Field(
    default=20,
    ge=1,
    le=100,
    description="Maximum orders per reconciliation batch",
)
```

- [ ] **Step 2: Run existing risk tests**

Run: `uv run pytest tests/unit/engine/risk/ -v --no-cov`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/squant/engine/risk/models.py
git commit -m "feat: add reconciliation config fields to RiskConfig"
```

---

## Chunk 4: Engine Fill Processing Refactor

### Task 7: Engine — New Fill Processing via watchMyTrades

**Files:**
- Modify: `src/squant/engine/live/engine.py`
- Test: `tests/unit/engine/live/test_fill_sync.py`

**Context:** This is the core refactor. The engine currently processes fills via `_process_single_ws_update()` (line 1289) using aggregated data from `watchOrders`. We split responsibilities: `watchMyTrades` handles fills, `watchOrders` handles status changes only.

Key existing methods:
- `_pending_ws_updates: deque[WSOrderUpdate]` (line 332)
- `_handle_private_ws_message()` (line 723) — routes WS messages
- `_drain_ws_updates()` (line 1274) — processes buffered updates
- `_process_single_ws_update()` (line 1289) — handles each update
- `_record_fill()` (line 2012) — records a fill
- `_start_private_ws()` (line 679) — sets up private WS
- `_compute_incremental_fill_price()` (line 68) — reverse-calculates fill price

- [ ] **Step 1: Write tests for new fill processing**

```python
# tests/unit/engine/live/test_fill_sync.py
from collections import OrderedDict, deque
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from squant.infra.exchange.ws_types import WSTradeExecution, WSOrderUpdate


class TestProcessTradeExecution:
    """Test _process_trade_execution method."""

    @pytest.fixture
    def engine(self):
        """Minimal engine mock for fill sync testing."""
        from squant.engine.live.engine import LiveTradingEngine, LiveOrder
        from squant.models.enums import OrderSide, OrderStatus

        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._is_running = True
        engine._symbol = "BTC/USDT"
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._processed_trade_ids = OrderedDict()
        engine._MAX_PROCESSED_TRADE_IDS = 10000
        engine._live_orders = {}
        engine._exchange_order_map = {}
        engine._pending_order_events = []
        engine._context = MagicMock()
        engine._risk_manager = MagicMock()
        engine._current_price = Decimal("96500")
        engine._has_recent_fill = False

        # Create a tracked order
        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.02"),
            price=None,
            status=OrderStatus.SUBMITTED,
        )
        live_order.filled_amount = Decimal("0")
        live_order.avg_fill_price = Decimal("0")
        live_order.fee = Decimal("0")
        engine._live_orders["int-001"] = live_order
        engine._exchange_order_map["exch-001"] = "int-001"

        return engine

    def test_records_fill_from_trade_execution(self, engine):
        exec = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            fee=Decimal("0.077"),
            fee_currency="USDT",
            taker_or_maker="taker",
            timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec)

            mock_record.assert_called_once()
            args = mock_record.call_args
            assert args[0][1] == Decimal("96500")   # fill_price
            assert args[0][2] == Decimal("0.008")    # fill_amount

        assert "t001" in engine._processed_trade_ids
        assert engine._has_recent_fill is True

    def test_dedup_skips_duplicate_trade_id(self, engine):
        engine._processed_trade_ids["t001"] = True

        exec = WSTradeExecution(
            trade_id="t001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec)
            mock_record.assert_not_called()

    def test_skips_unknown_order(self, engine):
        exec = WSTradeExecution(
            trade_id="t999",
            order_id="unknown-order",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill") as mock_record:
            engine._process_trade_execution(exec)
            mock_record.assert_not_called()

    def test_lru_eviction_on_overflow(self, engine):
        engine._MAX_PROCESSED_TRADE_IDS = 10
        # Fill to capacity
        for i in range(10):
            engine._processed_trade_ids[f"old-{i}"] = True

        exec = WSTradeExecution(
            trade_id="new-001",
            order_id="exch-001",
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("96500"),
            amount=Decimal("0.008"),
            timestamp=datetime.now(UTC),
        )

        with patch.object(engine, "_record_fill"):
            engine._process_trade_execution(exec)

        assert "new-001" in engine._processed_trade_ids
        # Oldest entries should be evicted (half removed)
        assert len(engine._processed_trade_ids) <= 6  # 10 - 5 evicted + 1 new


class TestDrainWSUpdatesOrdering:
    """Test that fills are processed before status changes."""

    @pytest.fixture
    def engine(self):
        from squant.engine.live.engine import LiveTradingEngine

        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._pending_ws_trade_executions = deque(maxlen=1000)
        engine._pending_ws_updates = deque(maxlen=1000)
        engine._is_running = True
        return engine

    def test_fills_processed_before_status_changes(self, engine):
        call_order = []

        def mock_process_trade(exec):
            call_order.append(("fill", exec.trade_id))

        def mock_process_status(update):
            call_order.append(("status", update.order_id))

        engine._process_trade_execution = mock_process_trade
        engine._process_single_ws_update = mock_process_status

        # Add a status update and a fill
        engine._pending_ws_updates.append(
            WSOrderUpdate(
                order_id="o1", symbol="BTC/USDT", side="buy",
                order_type="market", status="cancelled",
                price=Decimal("0"), size=Decimal("0"),
                filled_size=Decimal("0"), avg_price=Decimal("0"),
                timestamp=datetime.now(UTC),
            )
        )
        engine._pending_ws_trade_executions.append(
            WSTradeExecution(
                trade_id="t1", order_id="o2", symbol="BTC/USDT",
                side="buy", price=Decimal("96500"),
                amount=Decimal("0.01"), timestamp=datetime.now(UTC),
            )
        )

        engine._drain_ws_updates()

        assert call_order[0][0] == "fill"
        assert call_order[1][0] == "status"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/live/test_fill_sync.py -v --no-cov`
Expected: FAIL (new methods/attributes don't exist)

- [ ] **Step 3: Add new attributes to engine constructor**

In `LiveTradingEngine.__init__()`, add alongside `_pending_ws_updates` (around line 332):

```python
self._pending_ws_trade_executions: deque[WSTradeExecution] = deque(maxlen=1000)
self._processed_trade_ids: OrderedDict[str, bool] = OrderedDict()
self._MAX_PROCESSED_TRADE_IDS = 10000
```

Add `WSTradeExecution` as a **runtime** import (not under `TYPE_CHECKING`, since it's used in `isinstance()` checks and deque type annotations). Keep `WSCandle` and `WSOrderUpdate` under `TYPE_CHECKING` as they already are:
```python
from collections import OrderedDict
from squant.infra.exchange.ws_types import WSTradeExecution  # runtime import
```

- [ ] **Step 4: Add `_process_trade_execution()` method**

Add new method (after `_process_single_ws_update`):

```python
def _process_trade_execution(self, exec: WSTradeExecution) -> None:
    """Process a per-fill record from watchMyTrades.

    Args:
        exec: Individual fill data from exchange WS.
    """
    # Dedup by trade_id
    if exec.trade_id in self._processed_trade_ids:
        logger.debug(f"Skipping duplicate trade: {exec.trade_id}")
        return

    # Find the corresponding LiveOrder
    internal_id = self._exchange_order_map.get(exec.order_id)
    if internal_id is None:
        # Fill for an order not managed by this session (e.g., another session
        # on same account, or manual trade). Skip silently.
        logger.debug(
            f"Ignoring trade {exec.trade_id} for unknown order {exec.order_id}"
        )
        return

    live_order = self._live_orders.get(internal_id)
    if live_order is None:
        logger.warning(
            f"Trade {exec.trade_id}: internal_id {internal_id} not in _live_orders"
        )
        return

    # Capture pre-fill state for risk checks
    had_open_trade = self._context._open_trade is not None
    circuit_breaker_before = self._circuit_breaker_triggered

    # Update LiveOrder tracking fields (must happen before _record_fill)
    old_filled = live_order.filled_amount
    live_order.filled_amount += exec.amount
    if old_filled > 0 and live_order.avg_fill_price:
        # Weighted average price
        live_order.avg_fill_price = (
            live_order.avg_fill_price * old_filled + exec.price * exec.amount
        ) / live_order.filled_amount
    else:
        live_order.avg_fill_price = exec.price
    live_order.fee += exec.fee
    live_order.updated_at = exec.timestamp

    # Status transition
    if live_order.filled_amount >= live_order.amount:
        live_order.status = OrderStatus.FILLED
    elif live_order.filled_amount > 0:
        live_order.status = OrderStatus.PARTIAL

    # Record fill with exact data
    self._record_fill(
        live_order,
        exec.price,       # exact fill price
        exec.amount,      # exact fill amount
        exec.fee,         # exact fee for this fill
        live_order.fee,   # running total fee
        "ws",
        exec.timestamp,
        exchange_tid=exec.trade_id,
        taker_or_maker=exec.taker_or_maker,
    )

    # Check trade completion for risk tracking (circuit breaker, consecutive losses)
    self._check_trade_completion(had_open_trade, circuit_breaker_before, "ws")

    # Track processed trade_id
    self._processed_trade_ids[exec.trade_id] = True

    # LRU eviction: remove oldest half when cap exceeded
    if len(self._processed_trade_ids) > self._MAX_PROCESSED_TRADE_IDS:
        evict_count = self._MAX_PROCESSED_TRADE_IDS // 2
        for _ in range(evict_count):
            self._processed_trade_ids.popitem(last=False)

    self._has_recent_fill = True
```

Note: `_record_fill()` signature will need `exchange_tid` and `taker_or_maker` params added (Step 6).

- [ ] **Step 5: Update `_handle_private_ws_message()`**

Change `_handle_private_ws_message()` (line 723) to also handle `"trade_execution"`:

```python
async def _handle_private_ws_message(self, msg: dict[str, Any]) -> None:
    """Handle messages from private WS provider."""
    msg_type = msg.get("type")
    data = msg.get("data")
    if not data:
        return

    if msg_type == "order":
        self.on_order_update(data)
    elif msg_type == "trade_execution":
        if isinstance(data, WSTradeExecution):
            self._pending_ws_trade_executions.append(data)
```

- [ ] **Step 6: Update `_drain_ws_updates()`**

Replace `_drain_ws_updates()` (line 1274):

```python
def _drain_ws_updates(self) -> None:
    """Process all buffered WebSocket updates.

    Order: fills first (from watchMyTrades), then status changes (from watchOrders).
    This ensures fill records exist before evaluating terminal status.
    """
    # 1. Process per-fill data first
    if self._pending_ws_trade_executions:
        executions = list(self._pending_ws_trade_executions)
        self._pending_ws_trade_executions.clear()
        for exec in executions:
            self._process_trade_execution(exec)

    # 2. Then process order status changes
    if self._pending_ws_updates:
        updates = list(self._pending_ws_updates)
        self._pending_ws_updates.clear()
        for update in updates:
            self._process_single_ws_update(update)
```

- [ ] **Step 7: Update `_record_fill()` to accept exchange_tid and taker_or_maker**

Modify `_record_fill()` signature (line 2012) to add optional params:

```python
def _record_fill(
    self,
    live_order: LiveOrder,
    fill_price: Decimal | None,
    fill_amount: Decimal,
    fee_delta: Decimal | None,
    total_fee: Decimal,
    source: str,
    exchange_timestamp: datetime | None = None,
    exchange_tid: str | None = None,
    taker_or_maker: str | None = None,
) -> None:
```

In the `"fill"` audit event dict (around line 2064-2080), add:
```python
"exchange_tid": exchange_tid,
"taker_or_maker": taker_or_maker,
```

- [ ] **Step 8: Simplify `_process_single_ws_update()` — remove fill processing**

In `_process_single_ws_update()` (line 1289), remove the fill detection and `_record_fill()` call block (approximately lines 1337-1373). Keep only:
- Status mapping and update
- CANCELLED/REJECTED handling
- FILLED status → if local not FILLED, queue for reconciliation
- Fee/price metadata updates (non-fill)

The key change: when status is `FILLED` from `watchOrders` but local `filled_amount < amount`, add order to a `_orders_needing_reconciliation: set[str]` instead of trying to process the fill.

Add to constructor:
```python
self._orders_needing_reconciliation: set[str] = set()
```

- [ ] **Step 9: Simplify `_update_order_from_response()` — remove fill processing from REST polling**

In `_update_order_from_response()` (line 1921), remove the fill detection block (approximately lines 1948-1983). Keep:
- Status updates (CANCELLED, REJECTED, FILLED)
- Fee metadata updates
- Status change audit events

This ensures REST polling only syncs order **status**, not fills.

- [ ] **Step 10: Update `_start_private_ws()` to subscribe to watchMyTrades**

In `_start_private_ws()` (line 679), after `await self._private_ws.watch_orders(self._symbol)`:

```python
# Subscribe to per-fill data
await self._private_ws.watch_my_trades(self._symbol)

# Register reconnect handler for fill reconciliation
self._private_ws.add_reconnect_handler(self._on_ws_reconnect)
```

Add placeholder for `_on_ws_reconnect` (will be fully implemented in Task 8):
```python
async def _on_ws_reconnect(self) -> None:
    """Handle WS reconnection — trigger fill reconciliation for active orders."""
    logger.info("WS reconnected, scheduling fill reconciliation for active orders")
    for internal_id in self._live_orders:
        self._orders_needing_reconciliation.add(internal_id)
```

- [ ] **Step 11: Run tests**

Run: `uv run pytest tests/unit/engine/live/test_fill_sync.py -v --no-cov`
Expected: All PASS

- [ ] **Step 12: Run all engine tests**

Run: `uv run pytest tests/unit/engine/ -v --no-cov`
Expected: All PASS (existing tests may need minor updates if they mock fill processing)

- [ ] **Step 13: Commit**

```bash
git add src/squant/engine/live/engine.py tests/unit/engine/live/test_fill_sync.py
git commit -m "feat: refactor engine fill processing to use watchMyTrades per-fill data"
```

---

### Task 8: Engine — REST Reconciliation

**Files:**
- Modify: `src/squant/engine/live/engine.py`
- Test: `tests/unit/engine/live/test_fill_sync.py` (extend)

**Context:** Reconciliation is triggered by WS reconnect, session resume, or fill mismatch. Uses `get_order_trades()` REST method from Task 2.

- [ ] **Step 1: Write reconciliation tests**

Append to `tests/unit/engine/live/test_fill_sync.py`:

```python
class TestReconcileOrderFills:
    @pytest.fixture
    def engine(self):
        from squant.engine.live.engine import LiveTradingEngine, LiveOrder
        from squant.models.enums import OrderSide, OrderStatus

        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._is_running = True
        engine._symbol = "BTC/USDT"
        engine._adapter = AsyncMock()
        engine._processed_trade_ids = OrderedDict()
        engine._MAX_PROCESSED_TRADE_IDS = 10000
        engine._live_orders = {}
        engine._exchange_order_map = {}
        engine._pending_order_events = []
        engine._orders_needing_reconciliation = set()
        engine._context = MagicMock()
        engine._risk_manager = MagicMock()
        engine._risk_manager = MagicMock()
        engine._risk_manager.config.reconcile_interval_ms = 200
        engine._risk_manager.config.reconcile_batch_size = 20
        engine._current_price = Decimal("96500")
        engine._has_recent_fill = False

        live_order = LiveOrder(
            internal_id="int-001",
            exchange_order_id="exch-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type="market",
            amount=Decimal("0.02"),
            price=None,
            status=OrderStatus.PARTIAL,
        )
        live_order.filled_amount = Decimal("0.008")
        live_order.avg_fill_price = Decimal("96500")
        live_order.fee = Decimal("0.077")
        engine._live_orders["int-001"] = live_order
        engine._exchange_order_map["exch-001"] = "int-001"
        engine._processed_trade_ids["t001"] = True

        return engine

    async def test_reconcile_finds_missing_fills(self, engine):
        from squant.infra.exchange.types import TradeInfo

        engine._adapter.get_order_trades.return_value = [
            TradeInfo(
                trade_id="t001", order_id="exch-001", symbol="BTC/USDT",
                side="buy", price=Decimal("96500"), amount=Decimal("0.008"),
                fee=Decimal("0.077"), fee_currency="USDT", taker_or_maker="taker",
                timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
            ),
            TradeInfo(
                trade_id="t002", order_id="exch-001", symbol="BTC/USDT",
                side="buy", price=Decimal("96480"), amount=Decimal("0.005"),
                fee=Decimal("0.048"), fee_currency="USDT", taker_or_maker="maker",
                timestamp=datetime(2026, 3, 20, 10, 30, 17, tzinfo=UTC),
            ),
        ]

        with patch.object(engine, "_record_fill") as mock_record:
            await engine._reconcile_order_fills(engine._live_orders["int-001"])

            # t001 already processed, only t002 should be recorded
            mock_record.assert_called_once()
            args = mock_record.call_args
            assert args[0][1] == Decimal("96480")  # fill_price of t002

        assert "t002" in engine._processed_trade_ids

    async def test_reconcile_records_correction_on_mismatch(self, engine):
        from squant.infra.exchange.types import TradeInfo

        engine._adapter.get_order_trades.return_value = [
            TradeInfo(
                trade_id="t001", order_id="exch-001", symbol="BTC/USDT",
                side="buy", price=Decimal("96510"), amount=Decimal("0.008"),
                fee=Decimal("0.08"), fee_currency="USDT",
                timestamp=datetime(2026, 3, 20, 10, 30, 15, tzinfo=UTC),
            ),
        ]

        with patch.object(engine, "_record_fill"):
            await engine._reconcile_order_fills(engine._live_orders["int-001"])

        # No missing fills (t001 already known), but price differs (96510 vs 96500)
        # Reconciliation only records corrections when fills are missing
        # Since t001 is already processed, no missing fills → no correction
        corrections = [e for e in engine._pending_order_events if e["type"] == "correction"]
        assert len(corrections) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/engine/live/test_fill_sync.py::TestReconcileOrderFills -v --no-cov`
Expected: FAIL

- [ ] **Step 3: Implement `_reconcile_order_fills()`**

Add to `LiveTradingEngine`:

```python
async def _reconcile_order_fills(self, live_order: LiveOrder) -> None:
    """Reconcile fills for a single order against exchange records.

    Fetches all fills from exchange via REST, compares with locally
    processed trade_ids, and records any missing fills.
    """
    if not live_order.exchange_order_id:
        return

    try:
        trades = await self._adapter.get_order_trades(
            live_order.symbol, live_order.exchange_order_id
        )
    except Exception as e:
        logger.error(
            f"Failed to fetch order trades for {live_order.exchange_order_id}: {e}"
        )
        return

    missing_trade_ids = []
    for trade in trades:
        if trade.trade_id in self._processed_trade_ids:
            continue

        # Record the missing fill
        self._record_fill(
            live_order,
            trade.price,
            trade.amount,
            trade.fee,
            live_order.fee + trade.fee,
            "reconcile",
            trade.timestamp,
            exchange_tid=trade.trade_id,
            taker_or_maker=trade.taker_or_maker,
        )
        self._processed_trade_ids[trade.trade_id] = True
        missing_trade_ids.append(trade.trade_id)

    # Record correction if fills were missing
    if missing_trade_ids:
        # Recalculate expected totals from exchange
        exchange_filled = sum(t.amount for t in trades)
        exchange_total_fee = sum(t.fee for t in trades)
        exchange_avg_price = (
            sum(t.price * t.amount for t in trades) / exchange_filled
            if exchange_filled > 0
            else Decimal("0")
        )

        corrections = []
        if live_order.filled_amount != exchange_filled:
            corrections.append({
                "field": "filled_amount",
                "before": str(live_order.filled_amount),
                "after": str(exchange_filled),
            })
        if abs(live_order.avg_fill_price - exchange_avg_price) > Decimal("0.01"):
            corrections.append({
                "field": "avg_fill_price",
                "before": str(live_order.avg_fill_price),
                "after": str(exchange_avg_price),
            })

        if corrections:
            self._pending_order_events.append({
                "type": "correction",
                "internal_id": live_order.internal_id,
                "exchange_order_id": live_order.exchange_order_id,
                "corrections": corrections,
                "reason": "reconcile_missing_fills",
                "missing_trade_ids": missing_trade_ids,
                "timestamp": datetime.now(UTC).isoformat(),
            })

        logger.info(
            f"Reconciled order {live_order.exchange_order_id}: "
            f"{len(missing_trade_ids)} missing fills recovered"
        )
```

- [ ] **Step 4: Implement `_reconcile_pending_orders()`**

Process the `_orders_needing_reconciliation` set, called from `process_candle()`:

```python
async def _reconcile_pending_orders(self) -> None:
    """Reconcile orders that need fill data recovery."""
    if not self._orders_needing_reconciliation:
        return

    batch = list(self._orders_needing_reconciliation)[:self._risk_manager.config.reconcile_batch_size]
    interval = self._risk_manager.config.reconcile_interval_ms / 1000.0

    for internal_id in batch:
        live_order = self._live_orders.get(internal_id)
        if live_order is None:
            self._orders_needing_reconciliation.discard(internal_id)
            continue

        await self._reconcile_order_fills(live_order)
        self._orders_needing_reconciliation.discard(internal_id)

        if interval > 0:
            await asyncio.sleep(interval)
```

Call `await self._reconcile_pending_orders()` in `process_candle()` after `_drain_ws_updates()` and before `_process_order_requests()`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/engine/live/test_fill_sync.py -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Run all engine tests**

Run: `uv run pytest tests/unit/engine/ -v --no-cov`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/squant/engine/live/engine.py tests/unit/engine/live/test_fill_sync.py
git commit -m "feat: add REST fill reconciliation for WS reconnect and session recovery"
```

---

## Chunk 5: Persistence + API Schemas

### Task 9: Service Layer — Correction Event Persistence

**Files:**
- Modify: `src/squant/services/live_trading.py`

**Context:** `_create_order_persist_callback()` at line 737 creates an async callback that handles `"placed"`, `"fill"`, and `"status_change"` events. We add `"correction"` handling.

- [ ] **Step 1: Add correction event handling**

In `_persist_orders()` (inside `_create_order_persist_callback`), add after `"status_change"` handler:

```python
elif event["type"] == "correction":
    # Update order with corrected values
    internal_id = event["internal_id"]
    db_order_id = order_id_map.get(internal_id)
    if db_order_id:
        update_data = {}
        for c in event.get("corrections", []):
            field = c["field"]
            if field == "filled_amount":
                update_data["filled"] = Decimal(c["after"])
            elif field == "avg_fill_price":
                update_data["avg_price"] = Decimal(c["after"])
            elif field == "status":
                mapped_status = _map_event_status(c["after"])
                if mapped_status:
                    update_data["status"] = mapped_status

        if update_data:
            await order_repo.update(db_order_id, **update_data)

        # Append correction record to JSONB field
        order = await order_repo.get(db_order_id)
        if order:
            existing = order.corrections or []
            existing.append({
                "timestamp": event["timestamp"],
                "reason": event["reason"],
                "changes": event["corrections"],
                "missing_trade_ids": event.get("missing_trade_ids", []),
            })
            await order_repo.update(db_order_id, corrections=existing)
```

Also update the `"fill"` event handler to pass `exchange_tid` and `taker_or_maker`:

```python
# In "fill" event handler, when creating Trade record:
exchange_tid=event.get("exchange_tid"),
taker_or_maker=event.get("taker_or_maker"),
```

- [ ] **Step 2: Run existing service tests**

Run: `uv run pytest tests/unit/services/ -v --no-cov`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/squant/services/live_trading.py
git commit -m "feat: handle correction events in order persistence callback"
```

---

### Task 10: Backend Schemas + API Type Generation

**Files:**
- Modify: `src/squant/schemas/order.py`

**Context:** `TradeDetail` at line 83 is the Pydantic response schema for individual fills. Currently missing `fill_source` and `taker_or_maker`.

- [ ] **Step 1: Update TradeDetail schema**

Add to `TradeDetail` class:
```python
fill_source: str | None = Field(None, description="Fill source: ws, poll, or reconcile")
taker_or_maker: str | None = Field(None, description="Maker or taker fill")
```

- [ ] **Step 2: Add corrections to OrderDetail schema**

Add to `OrderDetail` class:
```python
corrections: list | None = Field(None, description="Data correction audit log")
```

- [ ] **Step 3: Regenerate OpenAPI types**

Run: `./scripts/generate-api-types.sh`
Expected: TypeScript types regenerated in `frontend/src/types/generated/`

- [ ] **Step 4: Run frontend type check**

Run: `cd frontend && pnpm build`
Expected: Build succeeds (type check passes)

- [ ] **Step 5: Commit**

```bash
git add src/squant/schemas/order.py frontend/src/types/
git commit -m "feat: add fill_source, taker_or_maker, corrections to API schemas"
```

---

## Chunk 6: Frontend

### Task 11: Frontend — Per-Fill Display in Session Detail

**Files:**
- Modify: `frontend/src/types/order.ts`
- Modify: `frontend/src/views/trading/SessionDetail.vue`

**Context:** `SessionDetail.vue` already fetches audit orders via `GET /api/v1/live/{run_id}/orders` which returns `OrderWithTrades` (includes `trades` array). Currently only order-level data is displayed.

- [ ] **Step 1: Update TypeScript types**

In `frontend/src/types/order.ts`, add/update:

```typescript
export interface TradeDetail {
  id: string
  order_id: string
  exchange_tid: string | null
  price: number
  amount: number
  fee: number
  fee_currency: string | null
  fill_source: string | null
  taker_or_maker: string | null
  timestamp: string
}

export interface CorrectionRecord {
  timestamp: string
  reason: string
  changes: Array<{ field: string; before: string; after: string }>
  missing_trade_ids?: string[]
}

export interface OrderWithTrades extends Order {
  trades: TradeDetail[]
  corrections: CorrectionRecord[] | null
}
```

- [ ] **Step 2: Add expandable rows to order table in SessionDetail.vue**

In the orders table section, add an expand column using Element Plus `el-table` expand feature:

```vue
<el-table-column type="expand">
  <template #default="{ row }">
    <div v-if="row.trades && row.trades.length > 0" class="fill-details">
      <el-table :data="row.trades" size="small" :show-header="true">
        <el-table-column prop="exchange_tid" label="成交ID" width="120">
          <template #default="{ row: trade }">
            {{ trade.exchange_tid ? trade.exchange_tid.substring(0, 10) + '...' : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="price" label="成交价" width="120" />
        <el-table-column prop="amount" label="成交量" width="100" />
        <el-table-column prop="fee" label="手续费" width="100">
          <template #default="{ row: trade }">
            {{ trade.fee }} {{ trade.fee_currency }}
          </template>
        </el-table-column>
        <el-table-column prop="taker_or_maker" label="类型" width="80" />
        <el-table-column prop="fill_source" label="来源" width="80" />
        <el-table-column prop="timestamp" label="成交时间" width="180">
          <template #default="{ row: trade }">
            {{ formatTime(trade.timestamp) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
    <div v-if="row.corrections && row.corrections.length > 0" class="correction-log">
      <el-alert type="warning" :closable="false" style="margin-top: 8px">
        <template #title>数据修正记录</template>
        <div v-for="(c, i) in row.corrections" :key="i" style="margin-top: 4px">
          <span>[{{ formatTime(c.timestamp) }}] {{ c.reason }}</span>
          <ul style="margin: 4px 0">
            <li v-for="(change, j) in c.changes" :key="j">
              {{ change.field }}: {{ change.before }} → {{ change.after }}
            </li>
          </ul>
        </div>
      </el-alert>
    </div>
  </template>
</el-table-column>
```

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && pnpm test`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/order.ts frontend/src/views/trading/SessionDetail.vue
git commit -m "feat: add per-fill expandable rows and correction log to session detail"
```

---

### Task 12: Frontend — Order History Detail Dialog

**Files:**
- Modify: `frontend/src/views/order/OrderHistory.vue`

**Context:** `OrderHistory.vue` displays order list. Currently no detail view for individual fills.

- [ ] **Step 1: Add detail dialog**

Add an `el-dialog` that shows when clicking an order row:

```vue
<el-dialog v-model="showOrderDetail" title="订单详情" width="700px">
  <template v-if="selectedOrder">
    <!-- Order basic info -->
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="交易所订单ID">{{ selectedOrder.exchange_oid }}</el-descriptions-item>
      <el-descriptions-item label="方向">{{ selectedOrder.side }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ selectedOrder.type }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ selectedOrder.status }}</el-descriptions-item>
      <el-descriptions-item label="数量">{{ selectedOrder.amount }}</el-descriptions-item>
      <el-descriptions-item label="成交量">{{ selectedOrder.filled }}</el-descriptions-item>
      <el-descriptions-item label="均价">{{ selectedOrder.avg_price }}</el-descriptions-item>
      <el-descriptions-item label="手续费">{{ selectedOrder.commission }} {{ selectedOrder.commission_asset }}</el-descriptions-item>
    </el-descriptions>

    <!-- Per-fill table -->
    <h4 style="margin: 16px 0 8px">逐笔成交</h4>
    <el-table :data="selectedOrder.trades || []" size="small" border>
      <el-table-column prop="exchange_tid" label="成交ID" width="120" />
      <el-table-column prop="price" label="价格" />
      <el-table-column prop="amount" label="数量" />
      <el-table-column prop="fee" label="手续费" />
      <el-table-column prop="taker_or_maker" label="类型" width="80" />
      <el-table-column prop="timestamp" label="时间" />
    </el-table>

    <!-- Corrections -->
    <div v-if="selectedOrder.corrections?.length" style="margin-top: 16px">
      <h4>修正记录</h4>
      <el-timeline>
        <el-timeline-item
          v-for="(c, i) in selectedOrder.corrections"
          :key="i"
          :timestamp="c.timestamp"
        >
          <p>{{ c.reason }}</p>
          <p v-for="(ch, j) in c.changes" :key="j">
            {{ ch.field }}: {{ ch.before }} → {{ ch.after }}
          </p>
        </el-timeline-item>
      </el-timeline>
    </div>
  </template>
</el-dialog>
```

Add state and handler:
```typescript
const showOrderDetail = ref(false)
const selectedOrder = ref<OrderWithTrades | null>(null)

const handleRowClick = async (row: Order) => {
  // Fetch order with trades from API
  const res = await getOrderDetail(row.id)
  selectedOrder.value = res
  showOrderDetail.value = true
}
```

Note: May need to add a `getOrderDetail` API method if not already available. Check `frontend/src/api/order.ts` for existing methods.

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && pnpm test`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/order/OrderHistory.vue frontend/src/api/order.ts
git commit -m "feat: add order detail dialog with per-fill table and corrections"
```

---

## Final Steps

### Task 13: Lint, Format, Full Test Suite

- [ ] **Step 1: Lint and format**

Run: `cd /workspaces/Squant && ./scripts/dev.sh format && ./scripts/dev.sh lint`
Expected: All clean

- [ ] **Step 2: Run full backend test suite**

Run: `uv run pytest tests/unit -v --no-cov -n auto`
Expected: All PASS

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && pnpm test && pnpm build`
Expected: All PASS, build succeeds

- [ ] **Step 4: Final commit if any fixups**

```bash
git add -A
git commit -m "chore: lint and format fixes"
```
