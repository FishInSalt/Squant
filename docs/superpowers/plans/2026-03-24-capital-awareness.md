# Batch B: Capital Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add capital visibility on session creation, insufficient-funds notification on order rejection, balance check on session resume, and full order reconciliation on crash recovery.

**Architecture:** New `GET /api/v1/live/account-balance/{account_id}` endpoint computes available balance (account total - running sessions' equity). Engine's `_submit_order()` detects `InvalidOrderError(field="amount")` and fires user notification. Resume flow gains a balance sufficiency check and a full exchange-vs-DB order reconciliation step.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / CCXT / Vue 3 / Element Plus / Pydantic

**Spec:** `docs/superpowers/specs/2026-03-24-capital-awareness-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/squant/infra/exchange/base.py` | Add abstract `get_account_total_value`, `get_orders` |
| Modify | `src/squant/infra/exchange/ccxt/rest_adapter.py` | Implement `get_account_total_value`, `get_orders` |
| Create | `tests/unit/infra/exchange/test_account_total_value.py` | Tests for multi-currency balance conversion |
| Create | `tests/unit/infra/exchange/test_get_orders.py` | Tests for get_orders with pagination |
| Modify | `src/squant/schemas/live_trading.py` | Add `AccountBalanceResponse` schema |
| Modify | `src/squant/services/live_trading.py` | Add `get_account_available_balance`, `list_running_by_account`, resume balance check, B4 reconciliation |
| Create | `tests/unit/services/test_live_balance.py` | Tests for balance service method |
| Modify | `src/squant/api/v1/live_trading.py` | Add balance endpoint |
| Modify | `src/squant/engine/live/engine.py` | Add insufficient funds notification in `_submit_order` |
| Create | `tests/unit/engine/live/test_insufficient_funds.py` | Tests for B2 notification logic |
| Modify | `frontend/src/api/live.ts` | Add `getAccountBalance` API call |
| Modify | `frontend/src/views/trading/LiveTrading.vue` | Balance display with tooltip |
| Create | `tests/unit/services/test_resume_balance_check.py` | Tests for B1+ resume check |
| Create | `tests/unit/services/test_recovery_reconciliation.py` | Tests for B4 reconciliation |

---

## Task 1: Exchange Adapter — `get_account_total_value`

**Files:**
- Modify: `src/squant/infra/exchange/base.py:66-92`
- Modify: `src/squant/infra/exchange/ccxt/rest_adapter.py:324-389`
- Create: `tests/unit/infra/exchange/test_account_total_value.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infra/exchange/test_account_total_value.py
"""Tests for get_account_total_value (multi-currency conversion)."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.types import Ticker


@pytest.fixture
def adapter():
    a = CCXTRestAdapter.__new__(CCXTRestAdapter)
    a._exchange = AsyncMock()
    a._exchange_id = "okx"
    a._credentials = MagicMock()
    return a


class TestGetAccountTotalValue:
    """Test get_account_total_value with various currency combinations."""

    async def test_single_quote_currency(self, adapter):
        """Only USDT balance — no ticker lookups needed."""
        adapter._exchange.fetch_balance.return_value = {
            "info": {},
            "free": {"USDT": 5000.0},
            "used": {"USDT": 0.0},
            "total": {"USDT": 5000.0},
        }
        total, balances = await adapter.get_account_total_value("USDT")
        assert total == Decimal("5000")
        assert len(balances) == 1
        adapter._exchange.fetch_ticker.assert_not_called()

    async def test_multi_currency_with_ticker_conversion(self, adapter):
        """USDT + BTC — BTC converted via ticker."""
        adapter._exchange.fetch_balance.return_value = {
            "info": {},
            "free": {"USDT": 1000.0, "BTC": 0.5},
            "used": {"USDT": 0.0, "BTC": 0.0},
            "total": {"USDT": 1000.0, "BTC": 0.5},
        }
        adapter._exchange.fetch_ticker.return_value = {"last": 60000.0}
        total, balances = await adapter.get_account_total_value("USDT")
        # 1000 + 0.5 * 60000 = 31000
        assert total == Decimal("31000")
        adapter._exchange.fetch_ticker.assert_called_once_with("BTC/USDT")

    async def test_okx_total_eq_priority(self, adapter):
        """OKX returns totalEq in info — use it directly."""
        adapter._exchange.fetch_balance.return_value = {
            "info": {"data": [{"totalEq": "50000.5"}]},
            "free": {"USDT": 1000.0, "BTC": 0.5},
            "used": {},
            "total": {"USDT": 1000.0, "BTC": 0.5},
        }
        total, balances = await adapter.get_account_total_value("USDT")
        assert total == Decimal("50000.5")
        adapter._exchange.fetch_ticker.assert_not_called()

    async def test_ticker_failure_skips_currency(self, adapter):
        """If ticker lookup fails, skip that currency with warning."""
        adapter._exchange.fetch_balance.return_value = {
            "info": {},
            "free": {"USDT": 1000.0, "ETH": 2.0},
            "used": {},
            "total": {"USDT": 1000.0, "ETH": 2.0},
        }
        adapter._exchange.fetch_ticker.side_effect = Exception("API error")
        total, balances = await adapter.get_account_total_value("USDT")
        # Only USDT counted, ETH skipped
        assert total == Decimal("1000")

    async def test_zero_balances_excluded(self, adapter):
        """Zero-balance currencies should not appear in result."""
        adapter._exchange.fetch_balance.return_value = {
            "info": {},
            "free": {"USDT": 500.0, "BTC": 0.0},
            "used": {"USDT": 0.0, "BTC": 0.0},
            "total": {"USDT": 500.0, "BTC": 0.0},
        }
        total, balances = await adapter.get_account_total_value("USDT")
        assert total == Decimal("500")
        assert len(balances) == 1

    async def test_no_credentials_raises(self, adapter):
        """Should raise if no credentials."""
        adapter._credentials = None
        with pytest.raises(Exception, match="[Cc]redentials"):
            await adapter.get_account_total_value("USDT")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/infra/exchange/test_account_total_value.py -v --no-cov`
Expected: FAIL — `get_account_total_value` does not exist

- [ ] **Step 3: Add abstract method to base**

In `src/squant/infra/exchange/base.py`, after the `get_balance_currency` method (line ~91), add:

```python
@abstractmethod
async def get_account_total_value(
    self, quote_currency: str
) -> tuple[Decimal, list["Balance"]]:
    """Get total account value converted to quote currency.

    Tries exchange-native total equity first (e.g., OKX totalEq),
    then falls back to manual conversion via ticker lookups.

    Args:
        quote_currency: Target currency for conversion (e.g., 'USDT').

    Returns:
        Tuple of (total_value_in_quote, list_of_balances).
    """
    ...
```

Add imports at top: `from decimal import Decimal` and `from datetime import datetime` (needed for `get_orders` too)

- [ ] **Step 4: Implement in CCXT adapter**

In `src/squant/infra/exchange/ccxt/rest_adapter.py`, after `_get_balance_impl` (line ~389), add:

```python
async def get_account_total_value(
    self, quote_currency: str
) -> tuple[Decimal, list[Balance]]:
    """Get total account value in quote currency.

    Priority: OKX totalEq from raw info > manual ticker conversion.
    """
    if not self._exchange:
        raise ExchangeConnectionError(
            message="Exchange not connected. Call connect() first.",
            exchange=self._exchange_id,
        )
    if not self._credentials:
        raise ExchangeAuthenticationError(
            message="Credentials required for balance query",
            exchange=self._exchange_id,
        )

    try:
        raw = await self._exchange.fetch_balance()
    except ccxt.AuthenticationError as e:
        raise ExchangeAuthenticationError(
            message=f"Authentication failed: {e}", exchange=self._exchange_id
        ) from e
    except ccxt.RateLimitExceeded as e:
        raise ExchangeRateLimitError(
            message=f"Rate limit exceeded: {e}", exchange=self._exchange_id
        ) from e
    except Exception as e:
        raise ExchangeAPIError(
            message=f"Failed to fetch balance: {e}", exchange=self._exchange_id
        ) from e

    # Parse structured balances
    free_balances = raw.get("free", {})
    used_balances = raw.get("used", {})
    total_balances = raw.get("total", {})
    all_currencies = set(free_balances.keys()) | set(used_balances.keys())

    balances: list[Balance] = []
    for currency in all_currencies:
        total = total_balances.get(currency, 0) or 0
        free = free_balances.get(currency, 0) or 0
        used = used_balances.get(currency, 0) or 0
        if total == 0 and free == 0 and used == 0:
            continue
        balances.append(
            Balance(
                currency=currency,
                available=Decimal(str(free)) if free else Decimal("0"),
                frozen=Decimal(str(used)) if used else Decimal("0"),
            )
        )

    # Priority 1: OKX totalEq from raw info
    info = raw.get("info", {})
    if isinstance(info, dict):
        data = info.get("data", [])
        if isinstance(data, list) and data:
            total_eq = data[0].get("totalEq")
            if total_eq:
                return Decimal(str(total_eq)), balances

    # Priority 2: Manual conversion
    quote_upper = quote_currency.upper()
    total_value = Decimal("0")
    for b in balances:
        if b.currency.upper() == quote_upper:
            total_value += b.total
        else:
            try:
                ticker = await self._exchange.fetch_ticker(
                    f"{b.currency.upper()}/{quote_upper}"
                )
                price = Decimal(str(ticker["last"]))
                total_value += b.total * price
            except Exception:
                logger.warning(
                    f"Failed to fetch ticker for {b.currency}/{quote_upper}, "
                    f"skipping {b.total} {b.currency} in total value calculation"
                )

    return total_value, balances
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/infra/exchange/test_account_total_value.py -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/infra/exchange/base.py src/squant/infra/exchange/ccxt/rest_adapter.py tests/unit/infra/exchange/test_account_total_value.py
git commit -m "feat(B1): add get_account_total_value for multi-currency balance conversion"
```

---

## Task 2: Exchange Adapter — `get_orders` (with pagination)

**Files:**
- Modify: `src/squant/infra/exchange/base.py`
- Modify: `src/squant/infra/exchange/ccxt/rest_adapter.py`
- Create: `tests/unit/infra/exchange/test_get_orders.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/infra/exchange/test_get_orders.py
"""Tests for get_orders (open + closed, with pagination)."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.models.enums import OrderStatus


@pytest.fixture
def adapter():
    a = CCXTRestAdapter.__new__(CCXTRestAdapter)
    a._exchange = AsyncMock()
    a._exchange_id = "okx"
    a._credentials = MagicMock()
    return a


def _make_ccxt_order(oid: str, status: str = "closed", ts: int = 1700000000000):
    return {
        "id": oid,
        "clientOrderId": None,
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "status": status,
        "price": 60000.0,
        "amount": 0.001,
        "filled": 0.001 if status == "closed" else 0.0,
        "average": 60000.0 if status == "closed" else None,
        "fee": {"cost": 0.06, "currency": "USDT"} if status == "closed" else None,
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat(),
    }


class TestGetOrders:
    async def test_combines_open_and_closed(self, adapter):
        """Should return both open and closed orders."""
        adapter._exchange.fetch_closed_orders.return_value = [
            _make_ccxt_order("c1", "closed"),
        ]
        adapter._exchange.fetch_open_orders.return_value = [
            _make_ccxt_order("o1", "open"),
        ]
        orders = await adapter.get_orders("BTC/USDT")
        assert len(orders) == 2
        ids = {o.order_id for o in orders}
        assert ids == {"c1", "o1"}

    async def test_with_since_parameter(self, adapter):
        """Should pass since timestamp to CCXT."""
        adapter._exchange.fetch_closed_orders.return_value = []
        adapter._exchange.fetch_open_orders.return_value = []
        since = datetime(2024, 1, 1, tzinfo=UTC)
        await adapter.get_orders("BTC/USDT", since=since)
        call_args = adapter._exchange.fetch_closed_orders.call_args
        assert call_args[0][1] == int(since.timestamp() * 1000)

    async def test_pagination_loops_until_short_page(self, adapter):
        """Should paginate closed orders until a page returns fewer than 100."""
        page1 = [_make_ccxt_order(f"c{i}", ts=1700000000000 + i * 1000) for i in range(100)]
        page2 = [_make_ccxt_order(f"c{i}", ts=1700000100000 + i * 1000) for i in range(100, 130)]
        adapter._exchange.fetch_closed_orders.side_effect = [page1, page2]
        adapter._exchange.fetch_open_orders.return_value = []
        orders = await adapter.get_orders("BTC/USDT")
        assert len(orders) == 130
        assert adapter._exchange.fetch_closed_orders.call_count == 2

    async def test_deduplicates_by_order_id(self, adapter):
        """Should not return duplicate orders from overlap."""
        order = _make_ccxt_order("dup1")
        adapter._exchange.fetch_closed_orders.side_effect = [[order], [order], []]
        adapter._exchange.fetch_open_orders.return_value = []
        orders = await adapter.get_orders("BTC/USDT")
        assert len(orders) == 1

    async def test_no_credentials_raises(self, adapter):
        adapter._credentials = None
        with pytest.raises(Exception, match="[Cc]redentials"):
            await adapter.get_orders("BTC/USDT")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/infra/exchange/test_get_orders.py -v --no-cov`
Expected: FAIL — `get_orders` does not exist

- [ ] **Step 3: Add abstract method to base**

In `src/squant/infra/exchange/base.py`, after `get_account_total_value`:

```python
@abstractmethod
async def get_orders(
    self, symbol: str, since: datetime | None = None
) -> list["OrderResponse"]:
    """Fetch all orders (open + closed) for symbol since given time.

    Handles pagination internally.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT').
        since: Only return orders after this time.

    Returns:
        List of OrderResponse objects.
    """
    ...
```

Add `datetime` to imports if not present.

- [ ] **Step 4: Implement in CCXT adapter**

In `src/squant/infra/exchange/ccxt/rest_adapter.py`, add after `get_account_total_value`:

```python
async def get_orders(
    self, symbol: str, since: datetime | None = None
) -> list[OrderResponse]:
    """Fetch all orders (open + closed) for symbol, with pagination."""
    if not self._exchange:
        raise ExchangeConnectionError(
            message="Exchange not connected.", exchange=self._exchange_id
        )
    if not self._credentials:
        raise ExchangeAuthenticationError(
            message="Credentials required", exchange=self._exchange_id
        )

    since_ms = int(since.timestamp() * 1000) if since else None
    seen_ids: set[str] = set()
    results: list[OrderResponse] = []

    try:
        # Paginate closed orders
        cursor = since_ms
        while True:
            batch = await self._exchange.fetch_closed_orders(
                symbol, since=cursor, limit=100
            )
            if not batch:
                break
            for raw_order in batch:
                oid = raw_order.get("id")
                if oid and oid not in seen_ids:
                    seen_ids.add(oid)
                    results.append(self._transform_order(raw_order))
            if len(batch) < 100:
                break
            # Next page: use last order's timestamp + 1ms
            last_ts = batch[-1].get("timestamp")
            if last_ts and (cursor is None or last_ts > cursor):
                cursor = last_ts + 1
            else:
                break

        # Open orders (no pagination needed — typically few)
        open_orders = await self._exchange.fetch_open_orders(symbol, since=since_ms)
        for raw_order in open_orders:
            oid = raw_order.get("id")
            if oid and oid not in seen_ids:
                seen_ids.add(oid)
                results.append(self._transform_order(raw_order))

    except ccxt.AuthenticationError as e:
        raise ExchangeAuthenticationError(
            message=f"Authentication failed: {e}", exchange=self._exchange_id
        ) from e
    except ccxt.RateLimitExceeded as e:
        raise ExchangeRateLimitError(
            message=f"Rate limit exceeded: {e}", exchange=self._exchange_id
        ) from e
    except Exception as e:
        raise ExchangeAPIError(
            message=f"Failed to fetch orders: {e}", exchange=self._exchange_id
        ) from e

    return results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/infra/exchange/test_get_orders.py -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/infra/exchange/base.py src/squant/infra/exchange/ccxt/rest_adapter.py tests/unit/infra/exchange/test_get_orders.py
git commit -m "feat(B4): add get_orders with pagination for recovery reconciliation"
```

---

## Task 3: Schema + Service — `get_account_available_balance`

**Files:**
- Modify: `src/squant/schemas/live_trading.py`
- Modify: `src/squant/services/live_trading.py`
- Create: `tests/unit/services/test_live_balance.py`

- [ ] **Step 1: Add Pydantic response schema**

In `src/squant/schemas/live_trading.py`, add after existing schemas:

```python
class RunningSessionEquity(BaseModel):
    """Equity info for a running session."""
    run_id: UUID
    strategy_name: str | None = None
    symbol: str
    equity: NumberDecimal


class AccountBalanceResponse(BaseModel):
    """Account balance with available capital calculation."""
    account_total_value: NumberDecimal
    quote_currency: str
    running_sessions: list[RunningSessionEquity] = Field(default_factory=list)
    sessions_total_equity: NumberDecimal = Field(default=Decimal("0"))
    available: NumberDecimal = Field(default=Decimal("0"))
```

- [ ] **Step 2: Write failing tests for service method**

```python
# tests/unit/services/test_live_balance.py
"""Tests for LiveTradingService.get_account_available_balance."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from squant.services.live_trading import LiveTradingService


@pytest.fixture
def service():
    svc = LiveTradingService.__new__(LiveTradingService)
    svc.session = AsyncMock()
    svc.run_repo = AsyncMock()
    return svc


class TestGetAccountAvailableBalance:
    async def test_no_running_sessions(self, service):
        """Available = total when no sessions running."""
        mock_adapter = AsyncMock()
        mock_adapter.get_account_total_value.return_value = (Decimal("5000"), [])
        service.run_repo.list_running_by_account = AsyncMock(return_value=[])

        with patch.object(service, "_create_adapter_for_account", return_value=mock_adapter):
            result = await service.get_account_available_balance(
                account_id=str(uuid4()), quote_currency="USDT"
            )

        assert result.account_total_value == Decimal("5000")
        assert result.available == Decimal("5000")
        assert result.sessions_total_equity == Decimal("0")
        assert result.running_sessions == []

    async def test_with_running_sessions_from_engine(self, service):
        """Deducts running sessions' equity from total."""
        mock_adapter = AsyncMock()
        mock_adapter.get_account_total_value.return_value = (Decimal("5000"), [])

        run1 = MagicMock()
        run1.id = str(uuid4())
        run1.strategy_id = str(uuid4())
        run1.symbol = "BTC/USDT"
        run1.result = {"equity": 1200}

        service.run_repo.list_running_by_account = AsyncMock(return_value=[run1])

        mock_engine = MagicMock()
        mock_engine.context.equity = Decimal("1200")

        mock_manager = MagicMock()
        mock_manager.get.return_value = mock_engine

        with (
            patch.object(service, "_create_adapter_for_account", return_value=mock_adapter),
            patch("squant.services.live_trading.get_live_session_manager", return_value=mock_manager),
            patch("squant.services.live_trading.StrategyRepository") as MockStrategyRepo,
        ):
            mock_strategy_repo = AsyncMock()
            mock_strategy = MagicMock()
            mock_strategy.name = "MA Cross"
            mock_strategy_repo.get.return_value = mock_strategy
            MockStrategyRepo.return_value = mock_strategy_repo

            result = await service.get_account_available_balance(
                account_id=str(uuid4()), quote_currency="USDT"
            )

        assert result.account_total_value == Decimal("5000")
        assert result.sessions_total_equity == Decimal("1200")
        assert result.available == Decimal("3800")
        assert len(result.running_sessions) == 1

    async def test_fallback_to_db_snapshot_equity(self, service):
        """Uses DB result when engine not in memory."""
        mock_adapter = AsyncMock()
        mock_adapter.get_account_total_value.return_value = (Decimal("3000"), [])

        run1 = MagicMock()
        run1.id = str(uuid4())
        run1.strategy_id = str(uuid4())
        run1.symbol = "ETH/USDT"
        run1.result = {"equity": 800}

        service.run_repo.list_running_by_account = AsyncMock(return_value=[run1])

        mock_manager = MagicMock()
        mock_manager.get.return_value = None  # Engine not in memory

        with (
            patch.object(service, "_create_adapter_for_account", return_value=mock_adapter),
            patch("squant.services.live_trading.get_live_session_manager", return_value=mock_manager),
            patch("squant.services.live_trading.StrategyRepository") as MockStrategyRepo,
        ):
            mock_strategy_repo = AsyncMock()
            mock_strategy = MagicMock()
            mock_strategy.name = "RSI Scalp"
            mock_strategy_repo.get.return_value = mock_strategy
            MockStrategyRepo.return_value = mock_strategy_repo

            result = await service.get_account_available_balance(
                account_id=str(uuid4()), quote_currency="USDT"
            )

        assert result.available == Decimal("2200")  # 3000 - 800
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_live_balance.py -v --no-cov`
Expected: FAIL — methods don't exist

- [ ] **Step 4: Implement `list_running_by_account` repo method**

In `src/squant/services/live_trading.py`, inside `LiveStrategyRunRepository` class (after existing methods like `has_running_session`), add:

```python
async def list_running_by_account(self, account_id: str) -> list[StrategyRun]:
    """List all RUNNING sessions for a given exchange account."""
    result = await self.session.execute(
        select(StrategyRun).where(
            StrategyRun.account_id == account_id,
            StrategyRun.mode == RunMode.LIVE,
            StrategyRun.status == RunStatus.RUNNING,
        )
    )
    return list(result.scalars().all())
```

- [ ] **Step 5: Implement `_create_adapter_for_account` helper**

In `LiveTradingService`, add a helper that creates and connects an adapter from account_id (reusable by B1 and B1+):

```python
async def _create_adapter_for_account(self, account_id: str) -> "ExchangeAdapter":
    """Create and connect an exchange adapter for the given account."""
    from squant.services.account import ExchangeAccountRepository

    account_repo = ExchangeAccountRepository(self.session)
    account = await account_repo.get(UUID(account_id))
    if not account:
        raise ExchangeAccountNotFoundError(account_id, "not found")
    if not account.is_active:
        raise ExchangeAccountNotFoundError(account_id, "account is not active")

    adapter = self._create_adapter(account)
    try:
        await asyncio.wait_for(adapter.connect(), timeout=30.0)
    except Exception as e:
        try:
            await adapter.close()
        except Exception:
            pass
        raise LiveExchangeConnectionError(
            f"Failed to connect to exchange: {e}"
        ) from e
    return adapter
```

- [ ] **Step 6: Implement `get_account_available_balance`**

In `LiveTradingService`, add:

```python
async def get_account_available_balance(
    self, account_id: str, quote_currency: str
) -> "AccountBalanceResponse":
    """Calculate available balance for an exchange account.

    available = account_total_value - sum(running sessions' equity)
    """
    from squant.schemas.live_trading import AccountBalanceResponse, RunningSessionEquity
    from squant.services.strategy import StrategyRepository

    adapter = await self._create_adapter_for_account(account_id)
    try:
        total_value, _ = await adapter.get_account_total_value(quote_currency)
    finally:
        await adapter.close()

    # Get running sessions for this account
    running_runs = await self.run_repo.list_running_by_account(account_id)

    session_manager = get_live_session_manager()
    strategy_repo = StrategyRepository(self.session)
    running_sessions = []
    total_equity = Decimal("0")

    for run in running_runs:
        # Try real-time equity from engine
        engine = session_manager.get(UUID(run.id))
        if engine:
            equity = engine.context.equity
        elif run.result and "equity" in run.result:
            equity = Decimal(str(run.result["equity"]))
        else:
            equity = run.initial_capital or Decimal("0")

        # Get strategy name
        strategy = await strategy_repo.get(UUID(run.strategy_id))
        strategy_name = strategy.name if strategy else None

        running_sessions.append(
            RunningSessionEquity(
                run_id=UUID(run.id),
                strategy_name=strategy_name,
                symbol=run.symbol,
                equity=equity,
            )
        )
        total_equity += equity

    available = total_value - total_equity

    return AccountBalanceResponse(
        account_total_value=total_value,
        quote_currency=quote_currency,
        running_sessions=running_sessions,
        sessions_total_equity=total_equity,
        available=available,
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_live_balance.py -v --no-cov`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/squant/schemas/live_trading.py src/squant/services/live_trading.py tests/unit/services/test_live_balance.py
git commit -m "feat(B1): add get_account_available_balance service method"
```

---

## Task 4: API Endpoint + OpenAPI Types

**Files:**
- Modify: `src/squant/api/v1/live_trading.py`

- [ ] **Step 1: Add balance endpoint**

In `src/squant/api/v1/live_trading.py`, add:

```python
from squant.schemas.live_trading import AccountBalanceResponse

@router.get(
    "/account-balance/{account_id}",
    response_model=ApiResponse[AccountBalanceResponse],
)
async def get_account_balance(
    account_id: UUID,
    quote_currency: str = "USDT",
    session: AsyncSession = Depends(get_session),
):
    """Get account balance with available capital for live trading."""
    service = LiveTradingService(session)
    try:
        result = await service.get_account_available_balance(
            str(account_id), quote_currency
        )
        return ApiResponse(data=result)
    except ExchangeAccountNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except LiveExchangeConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except LiveTradingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

- [ ] **Step 2: Run lint**

Run: `./scripts/dev.sh lint`
Expected: PASS (or fix any issues)

- [ ] **Step 3: Regenerate OpenAPI types**

Run: `./scripts/generate-api-types.sh`

- [ ] **Step 4: Commit**

```bash
git add src/squant/api/v1/live_trading.py frontend/src/types/generated/
git commit -m "feat(B1): add GET /api/v1/live/account-balance endpoint + regenerate types"
```

---

## Task 5: B2 — Insufficient Funds Notification

**Files:**
- Modify: `src/squant/engine/live/engine.py:2629-2648`
- Create: `tests/unit/engine/live/test_insufficient_funds.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/engine/live/test_insufficient_funds.py
"""Tests for insufficient funds notification in _submit_order."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from squant.infra.exchange.exceptions import InvalidOrderError
from squant.models.enums import OrderSide, OrderStatus


class TestInsufficientFundsNotification:
    def _make_engine(self):
        """Create a minimal LiveTradingEngine for testing."""
        from squant.engine.live.engine import LiveTradingEngine

        engine = LiveTradingEngine.__new__(LiveTradingEngine)
        engine._run_id = uuid4()
        engine._adapter = AsyncMock()
        engine._live_orders = {}
        engine._exchange_order_map = {}
        engine._timed_out_orders = {}
        engine._pending_order_events = []
        engine._context = MagicMock()
        engine._context._pending_orders = []
        engine._context._completed_orders = []
        engine._context._total_completed_added = 0
        engine._symbol = "BTC/USDT"
        return engine

    def _make_order(self, side=OrderSide.BUY):
        order = MagicMock()
        order.id = "test-order-1"
        order.symbol = "BTC/USDT"
        order.side = side
        order.type = MagicMock(value="market")
        order.amount = Decimal("0.001")
        order.price = None
        order.stop_price = None
        order.status = OrderStatus.PENDING
        return order

    @patch("squant.engine.live.engine._fire_notification")
    async def test_buy_insufficient_funds_fires_notification(self, mock_notify):
        """Buy order rejected for insufficient funds → notification with '余额不足'."""
        engine = self._make_engine()
        order = self._make_order(side=OrderSide.BUY)
        engine._adapter.place_order.side_effect = InvalidOrderError(
            message="Insufficient funds: not enough USDT",
            exchange="okx",
            field="amount",
        )

        await engine._submit_order(order)

        assert order.status == OrderStatus.REJECTED
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs[1]["event_type"] == "insufficient_funds" or \
               call_kwargs[0][2] == "insufficient_funds"

    @patch("squant.engine.live.engine._fire_notification")
    async def test_sell_insufficient_funds_fires_notification(self, mock_notify):
        """Sell order rejected for insufficient holdings → notification with '持仓不足'."""
        engine = self._make_engine()
        order = self._make_order(side=OrderSide.SELL)
        engine._adapter.place_order.side_effect = InvalidOrderError(
            message="Insufficient funds: not enough BTC",
            exchange="okx",
            field="amount",
        )

        await engine._submit_order(order)

        assert order.status == OrderStatus.REJECTED
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0] if mock_notify.call_args[0] else mock_notify.call_args[1]

    @patch("squant.engine.live.engine._fire_notification")
    async def test_other_invalid_order_no_notification(self, mock_notify):
        """InvalidOrderError without field='amount' → no notification."""
        engine = self._make_engine()
        order = self._make_order()
        engine._adapter.place_order.side_effect = InvalidOrderError(
            message="Invalid order: min notional",
            exchange="okx",
            field="price",
        )

        await engine._submit_order(order)

        assert order.status == OrderStatus.REJECTED
        mock_notify.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/engine/live/test_insufficient_funds.py -v --no-cov`
Expected: FAIL — notification not triggered yet

- [ ] **Step 3: Implement in `_submit_order`**

In `src/squant/engine/live/engine.py`, modify the `except Exception` block in `_submit_order()` (line ~2641):

Add import at top of file (with other exchange imports):
```python
from squant.infra.exchange.exceptions import InvalidOrderError
```

Replace lines 2641-2648 with:

```python
            else:
                logger.exception(f"Failed to submit order {order.id}: {e}")
                # Detect insufficient funds and notify user (B2)
                is_insufficient = (
                    isinstance(e, InvalidOrderError) and e.field == "amount"
                )
                if is_insufficient:
                    if order.side == OrderSide.BUY:
                        title = "余额不足"
                        msg = (
                            f"买入失败：{order.symbol} {order.amount}，"
                            "交易所余额不足"
                        )
                    else:
                        title = "持仓不足"
                        msg = (
                            f"卖出失败：{order.symbol} {order.amount}，"
                            "交易所持仓不足（可能因手续费从标的扣除导致）"
                        )
                    _fire_notification(
                        self._run_id,
                        level="warning",
                        event_type="insufficient_funds",
                        title=title,
                        message=msg,
                    )
                # Mark as rejected
                order.status = OrderStatus.REJECTED
                self._context._completed_orders.append(order)
                self._context._total_completed_added += 1
                if order in self._context._pending_orders:
                    self._context._pending_orders.remove(order)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/engine/live/test_insufficient_funds.py -v --no-cov`
Expected: All PASS

- [ ] **Step 5: Run existing engine tests to check for regressions**

Run: `uv run pytest tests/unit/engine/live/ -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/engine/live/engine.py tests/unit/engine/live/test_insufficient_funds.py
git commit -m "feat(B2): add insufficient funds notification with buy/sell distinction"
```

---

## Task 6: B1+ — Resume Balance Check

**Files:**
- Modify: `src/squant/services/live_trading.py:1796-1843`
- Create: `tests/unit/services/test_resume_balance_check.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/services/test_resume_balance_check.py
"""Tests for B1+ resume balance check."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from squant.services.live_trading import LiveTradingService


@pytest.fixture
def service():
    svc = LiveTradingService.__new__(LiveTradingService)
    svc.session = AsyncMock()
    svc.run_repo = AsyncMock()
    return svc


class TestResumeBalanceCheck:
    async def test_sufficient_balance_passes(self, service):
        """Resume proceeds when balance is sufficient."""
        from squant.schemas.live_trading import AccountBalanceResponse

        mock_result = AccountBalanceResponse(
            account_total_value=Decimal("5000"),
            quote_currency="USDT",
            running_sessions=[],
            sessions_total_equity=Decimal("0"),
            available=Decimal("5000"),
        )
        service.get_account_available_balance = AsyncMock(return_value=mock_result)

        # Should not raise
        await service._check_resume_balance(
            account_id="acc-1",
            session_equity=Decimal("1000"),
            quote_currency="USDT",
        )

    async def test_insufficient_balance_raises(self, service):
        """Resume blocked when balance is insufficient."""
        from squant.schemas.live_trading import AccountBalanceResponse

        mock_result = AccountBalanceResponse(
            account_total_value=Decimal("1000"),
            quote_currency="USDT",
            running_sessions=[],
            sessions_total_equity=Decimal("800"),
            available=Decimal("200"),
        )
        service.get_account_available_balance = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Insufficient balance"):
            await service._check_resume_balance(
                account_id="acc-1",
                session_equity=Decimal("500"),
                quote_currency="USDT",
            )

    async def test_balance_check_failure_logs_warning(self, service):
        """If balance check itself fails, log warning but don't block resume."""
        service.get_account_available_balance = AsyncMock(
            side_effect=Exception("Exchange unreachable")
        )
        # Should not raise — balance check failure is non-blocking
        await service._check_resume_balance(
            account_id="acc-1",
            session_equity=Decimal("500"),
            quote_currency="USDT",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_resume_balance_check.py -v --no-cov`
Expected: FAIL — `_check_resume_balance` does not exist

- [ ] **Step 3: Implement `_check_resume_balance`**

In `LiveTradingService`, add:

```python
async def _check_resume_balance(
    self, account_id: str, session_equity: Decimal, quote_currency: str
) -> None:
    """Check if account has sufficient balance to resume a session.

    Raises ValueError if insufficient. Logs warning and continues
    if the balance check itself fails (non-blocking).
    """
    try:
        balance_info = await self.get_account_available_balance(
            account_id, quote_currency
        )
        if session_equity > balance_info.available:
            raise ValueError(
                f"Insufficient balance to resume session. "
                f"Session equity: {session_equity}, "
                f"Available: {balance_info.available} {quote_currency}"
            )
    except ValueError:
        raise  # Re-raise insufficient balance
    except Exception as e:
        logger.warning(
            f"Balance check failed for account {account_id}, "
            f"proceeding with resume: {e}"
        )
```

- [ ] **Step 4: Insert call in `resume()` method**

In `resume()`, after step 10b (line ~1843, after seed_map wiring) and before step 11 (reconciliation), add:

```python
        # 10c. Balance sufficiency check (B1+)
        session_equity = Decimal(str(run.result.get("equity", 0)))
        quote_currency = run.symbol.split("/")[1] if "/" in run.symbol else "USDT"
        await self._check_resume_balance(
            account_id=str(run.account_id),
            session_equity=session_equity,
            quote_currency=quote_currency,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_resume_balance_check.py -v --no-cov`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/squant/services/live_trading.py tests/unit/services/test_resume_balance_check.py
git commit -m "feat(B1+): add resume balance sufficiency check"
```

---

## Task 7: B4 — Recovery Order Reconciliation

**Files:**
- Modify: `src/squant/services/live_trading.py`
- Create: `tests/unit/services/test_recovery_reconciliation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/services/test_recovery_reconciliation.py
"""Tests for B4 recovery order reconciliation on resume."""

import pytest
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from squant.infra.exchange.types import OrderResponse
from squant.models.enums import OrderSide, OrderStatus, OrderType


def _make_exchange_order(oid: str, status=OrderStatus.FILLED, filled=Decimal("0.001")):
    return OrderResponse(
        order_id=oid,
        client_order_id=None,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        status=status,
        price=Decimal("60000"),
        amount=Decimal("0.001"),
        filled=filled,
        avg_price=Decimal("60000"),
        fee=Decimal("0.06"),
        fee_currency="USDT",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_db_order(exchange_oid: str):
    order = MagicMock()
    order.id = str(uuid4())
    order.exchange_oid = exchange_oid
    return order


class TestRecoveryReconciliation:
    async def test_no_missing_orders(self):
        """All exchange orders already in DB — nothing to reconcile."""
        from squant.services.live_trading import LiveTradingService

        svc = LiveTradingService.__new__(LiveTradingService)
        svc.session = AsyncMock()

        adapter = AsyncMock()
        adapter.get_orders.return_value = [_make_exchange_order("e1")]
        adapter.get_order_trades = AsyncMock()

        db_orders = [_make_db_order("e1")]

        report = await svc._reconcile_missing_orders(
            adapter=adapter,
            run_id="run-1",
            account_id="acc-1",
            exchange="okx",
            symbol="BTC/USDT",
            db_orders=db_orders,
            since=datetime.now(UTC) - timedelta(hours=1),
            order_id_map={"int-1": "db-1"},
        )
        assert report["missing_orders_found"] == 0
        adapter.get_order_trades.assert_not_called()

    async def test_missing_order_recovered(self):
        """Exchange has order not in DB — should be created."""
        from squant.services.live_trading import LiveTradingService

        svc = LiveTradingService.__new__(LiveTradingService)
        svc.session = AsyncMock()

        exchange_order = _make_exchange_order("e2", status=OrderStatus.FILLED)
        adapter = AsyncMock()
        adapter.get_orders.return_value = [exchange_order]
        adapter.get_order_trades.return_value = []

        db_orders = []  # No DB orders — e2 is missing

        report = await svc._reconcile_missing_orders(
            adapter=adapter,
            run_id="run-1",
            account_id="acc-1",
            exchange="okx",
            symbol="BTC/USDT",
            db_orders=db_orders,
            since=datetime.now(UTC) - timedelta(hours=1),
            order_id_map={},
        )
        assert report["missing_orders_found"] == 1

    async def test_since_calculated_from_last_bar_time(self):
        """Verify since = last_bar_time - 1 bar interval."""
        from squant.services.live_trading import LiveTradingService

        last_bar = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        since = LiveTradingService._compute_reconciliation_since(
            last_bar_time=last_bar, timeframe="1h"
        )
        expected = datetime(2024, 1, 1, 11, 0, tzinfo=UTC)
        assert since == expected

    async def test_since_fallback_to_started_at(self):
        """No last_bar_time → fallback to started_at."""
        from squant.services.live_trading import LiveTradingService

        started = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        since = LiveTradingService._compute_reconciliation_since(
            last_bar_time=None, timeframe="1h", fallback=started
        )
        assert since == started
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_recovery_reconciliation.py -v --no-cov`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Implement `_compute_reconciliation_since` static method**

```python
@staticmethod
def _compute_reconciliation_since(
    last_bar_time: datetime | None,
    timeframe: str,
    fallback: datetime | None = None,
) -> datetime:
    """Compute the 'since' timestamp for recovery reconciliation.

    Returns last_bar_time - 1 bar interval, or fallback if no last_bar_time.
    """
    if not last_bar_time:
        if fallback:
            return fallback
        return datetime.now(UTC) - timedelta(hours=24)

    # Parse timeframe to timedelta
    tf_map = {
        "1m": timedelta(minutes=1), "3m": timedelta(minutes=3),
        "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30), "1h": timedelta(hours=1),
        "2h": timedelta(hours=2), "4h": timedelta(hours=4),
        "6h": timedelta(hours=6), "12h": timedelta(hours=12),
        "1d": timedelta(days=1), "1w": timedelta(weeks=1),
        "1M": timedelta(days=30),
    }
    interval = tf_map.get(timeframe, timedelta(hours=1))
    return last_bar_time - interval
```

- [ ] **Step 4: Implement `_reconcile_missing_orders`**

```python
async def _reconcile_missing_orders(
    self,
    adapter: "ExchangeAdapter",
    run_id: str,
    account_id: str,
    exchange: str,
    symbol: str,
    db_orders: list,
    since: datetime,
    order_id_map: dict[str, str],
) -> dict[str, Any]:
    """Reconcile orders on exchange that are missing from DB.

    Fetches all exchange orders since `since`, compares against db_orders
    by exchange_order_id, and creates DB records for missing ones.
    """
    from squant.infra.database import get_session_context
    from squant.services.order import OrderRepository, TradeRepository

    report = {"missing_orders_found": 0, "missing_orders_recovered": 0, "errors": []}

    try:
        exchange_orders = await adapter.get_orders(symbol, since=since)
    except Exception as e:
        logger.warning(f"Recovery reconciliation: failed to fetch orders: {e}")
        report["errors"].append(str(e))
        return report

    # Build set of known exchange order IDs from DB
    known_eoids = {o.exchange_oid for o in db_orders if o.exchange_oid}

    missing = [o for o in exchange_orders if o.order_id not in known_eoids]
    report["missing_orders_found"] = len(missing)

    if not missing:
        return report

    logger.info(
        f"Recovery reconciliation for {run_id}: found {len(missing)} "
        f"missing orders on exchange"
    )

    async with get_session_context() as db_session:
        order_repo = OrderRepository(db_session)
        trade_repo = TradeRepository(db_session)

        for ex_order in missing:
            try:
                # Create order record
                db_order = await order_repo.create(
                    run_id=run_id,
                    account_id=account_id,
                    exchange=exchange,
                    exchange_oid=ex_order.order_id,
                    symbol=ex_order.symbol,
                    side=ex_order.side,
                    type=ex_order.type,
                    amount=ex_order.amount,
                    price=ex_order.price,
                    status=ex_order.status,
                )

                # Fetch and record fills
                try:
                    fills = await adapter.get_order_trades(symbol, ex_order.order_id)
                    for fill in fills:
                        await trade_repo.create(
                            order_id=db_order.id,
                            price=fill.price,
                            amount=fill.amount,
                            fee=abs(fill.fee) if fill.fee else Decimal("0"),
                            fee_currency=fill.fee_currency,
                            timestamp=fill.timestamp or datetime.now(UTC),
                            fill_source="recovery",
                            exchange_tid=fill.trade_id,
                            taker_or_maker=fill.taker_or_maker,
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch fills for recovered order "
                        f"{ex_order.order_id}: {e}"
                    )

                # Update order with fill info
                if ex_order.filled and ex_order.filled > 0:
                    await order_repo.update(
                        db_order.id,
                        filled=ex_order.filled,
                        avg_price=ex_order.avg_price,
                        status=ex_order.status,
                    )

                report["missing_orders_recovered"] += 1
                logger.info(
                    f"Recovered missing order {ex_order.order_id} "
                    f"({ex_order.side.value} {ex_order.amount} {symbol})"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to recover order {ex_order.order_id}: {e}"
                )
                report["errors"].append(str(e))

    return report
```

- [ ] **Step 5: Insert B4 call in `resume()` method**

After step 10c (balance check) and before step 11 (existing reconciliation), add:

```python
        # 10d. Recovery reconciliation — find orders on exchange missing from DB (B4)
        last_bar_time = None
        if run.result.get("last_bar_time"):
            last_bar_time = datetime.fromisoformat(run.result["last_bar_time"])
        recovery_since = self._compute_reconciliation_since(
            last_bar_time=last_bar_time,
            timeframe=run.timeframe,
            fallback=run.started_at,
        )
        recovery_report = await self._reconcile_missing_orders(
            adapter=adapter,
            run_id=run.id,
            account_id=str(run.account_id),
            exchange=exchange_account.exchange,
            symbol=run.symbol,
            db_orders=existing_orders,  # from step 10b
            since=recovery_since,
            order_id_map=seed_map,
        )
        logger.info(f"Recovery reconciliation for {run_id}: {recovery_report}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_recovery_reconciliation.py -v --no-cov`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/squant/services/live_trading.py tests/unit/services/test_recovery_reconciliation.py
git commit -m "feat(B4): add recovery order reconciliation on session resume"
```

---

## Task 8: Frontend — Balance Display with Tooltip

**Files:**
- Modify: `frontend/src/api/live.ts`
- Modify: `frontend/src/views/trading/LiveTrading.vue`

- [ ] **Step 1: Add API function**

In `frontend/src/api/live.ts`, add:

```typescript
// 查询账户可用余额
export const getAccountBalance = (accountId: string, quoteCurrency?: string) =>
  get<{
    account_total_value: number
    quote_currency: string
    running_sessions: Array<{
      run_id: string
      strategy_name: string | null
      symbol: string
      equity: number
    }>
    sessions_total_equity: number
    available: number
  }>(`/live/account-balance/${accountId}`, quoteCurrency ? { quote_currency: quoteCurrency } : undefined)
```

- [ ] **Step 2: Add balance state and fetch logic in LiveTrading.vue**

In the `<script setup>` section, add state variables (after existing refs around line 368):

```typescript
import { getAccountBalance } from '@/api/live'

// Balance display state
const balanceLoading = ref(false)
const balanceError = ref('')
const balanceData = ref<{
  account_total_value: number
  quote_currency: string
  running_sessions: Array<{
    run_id: string
    strategy_name: string | null
    symbol: string
    equity: number
  }>
  sessions_total_equity: number
  available: number
} | null>(null)
```

Update `handleAccountChange()` (line ~465):

```typescript
async function handleAccountChange() {
  form.symbol = ''
  balanceData.value = null
  balanceError.value = ''
  loadSymbols()
  await fetchAccountBalance()
}

async function fetchAccountBalance() {
  if (!form.account_id) return
  balanceLoading.value = true
  balanceError.value = ''
  try {
    const response = await getAccountBalance(form.account_id)
    balanceData.value = response.data
  } catch (error) {
    balanceError.value = '余额查询失败，请稍后重试'
    console.error('Failed to fetch account balance:', error)
  } finally {
    balanceLoading.value = false
  }
}
```

- [ ] **Step 3: Add balance display template**

In the template, after the "交易所账户" form-item (line ~83) and before the symbol/timeframe row, add:

```vue
          <!-- Account Balance Display (B1) -->
          <div v-if="form.account_id" class="balance-section">
            <el-skeleton v-if="balanceLoading" :rows="1" animated />
            <el-alert
              v-else-if="balanceError"
              :title="balanceError"
              type="warning"
              :closable="false"
              show-icon
            />
            <div v-else-if="balanceData" class="balance-display">
              <div class="balance-main">
                <span class="balance-label">可用余额：</span>
                <span class="balance-value">{{ formatNumber(balanceData.available, 2) }} {{ balanceData.quote_currency }}</span>
                <el-popover
                  v-if="balanceData.running_sessions.length > 0"
                  placement="bottom"
                  :width="320"
                  trigger="hover"
                >
                  <template #reference>
                    <span class="balance-formula">
                      ＝ {{ formatNumber(balanceData.account_total_value, 2) }}
                      − {{ formatNumber(balanceData.sessions_total_equity, 2) }}（运行中会话占用）
                    </span>
                  </template>
                  <div class="balance-tooltip">
                    <div class="tooltip-row">
                      <span>账户总值</span>
                      <span>{{ formatNumber(balanceData.account_total_value, 2) }} {{ balanceData.quote_currency }}</span>
                    </div>
                    <el-divider style="margin: 8px 0" />
                    <div class="tooltip-section-title">运行中会话占用：</div>
                    <div
                      v-for="s in balanceData.running_sessions"
                      :key="s.run_id"
                      class="tooltip-row"
                    >
                      <span>{{ s.strategy_name || '未知策略' }} ({{ s.symbol }})</span>
                      <span>{{ formatNumber(s.equity, 2) }}</span>
                    </div>
                    <el-divider style="margin: 8px 0" />
                    <div class="tooltip-row total">
                      <span>合计占用</span>
                      <span>{{ formatNumber(balanceData.sessions_total_equity, 2) }}</span>
                    </div>
                    <div class="tooltip-row total">
                      <span>可用余额</span>
                      <span>{{ formatNumber(balanceData.available, 2) }}</span>
                    </div>
                  </div>
                </el-popover>
                <span v-else class="balance-simple">
                  （无运行中会话）
                </span>
              </div>
              <div class="balance-hint">建议预留部分余额用于交易手续费</div>
            </div>
          </div>
```

- [ ] **Step 4: Add styles**

In `<style>` section, add:

```scss
.balance-section {
  margin-bottom: 16px;
}

.balance-display {
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.balance-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.balance-label {
  font-weight: 500;
}

.balance-value {
  font-weight: 600;
  font-size: 16px;
  color: var(--el-color-primary);
}

.balance-formula {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  cursor: help;
  border-bottom: 1px dashed var(--el-border-color);
}

.balance-simple {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.balance-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.balance-tooltip {
  .tooltip-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    font-size: 13px;

    &.total {
      font-weight: 600;
    }
  }

  .tooltip-section-title {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 4px;
  }
}
```

- [ ] **Step 5: Run frontend lint and test**

Run: `cd frontend && pnpm lint && pnpm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/live.ts frontend/src/views/trading/LiveTrading.vue
git commit -m "feat(B1): add account balance display with tooltip breakdown"
```

---

## Task 9: Final Integration + Lint + Regenerate Types

- [ ] **Step 1: Run full backend lint**

Run: `./scripts/dev.sh lint`
Fix any issues.

- [ ] **Step 2: Regenerate OpenAPI types**

Run: `./scripts/generate-api-types.sh`

- [ ] **Step 3: Run full backend unit tests**

Run: `uv run pytest tests/unit -v --no-cov -n auto`
Expected: All PASS

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && pnpm test`
Expected: All PASS

- [ ] **Step 5: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: lint fixes + regenerate OpenAPI types for Batch B"
```

- [ ] **Step 6: Create feature branch and PR**

```bash
git checkout -b cc/capital-awareness
git push -u origin cc/capital-awareness
gh pr create --title "feat: Batch B — capital awareness & validation" --body "..."
```
