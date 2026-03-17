# Live Trading E2E Verification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify exchange adapters to CCXT, then verify live trading end-to-end using OKX demo trading account.

**Architecture:** Remove native OKX/Binance adapters, route all exchange interactions through CCXTRestAdapter. Then verify each integration layer (connectivity → market data → engine → full lifecycle) against OKX demo trading.

**Tech Stack:** Python 3.12, FastAPI, CCXT, SQLAlchemy async, Redis pub/sub, Vue 3 frontend

**Spec:** `docs/superpowers/specs/2026-03-17-live-trading-e2e-verification-design.md`

---

## Implementation Notes (MUST READ)

The following gotchas were identified during plan review. The implementer **must** read the actual source files before implementing each task — the code snippets in this plan are guides, not copy-paste-ready.

### API Signature Gotchas

1. **`_create_adapter()` is synchronous** (`services/live_trading.py`). Do NOT change it to async. It returns an adapter that is NOT yet connected. The caller calls `await adapter.connect()` externally with a timeout wrapper. Only change the body (adapter instantiation), not the signature.

2. **`ExchangeCredentials`** is in `infra/exchange/ccxt/types.py`, not `base.py`.

3. **`OrderRequest` field name**: The field is `type`, not `order_type`. Example: `OrderRequest(symbol="BTC/USDT", side=OrderSide.BUY, type=OrderType.LIMIT, ...)`.

4. **`OrderResponse` field name**: The field is `filled`, not `filled_amount`.

5. **`CancelOrderRequest`**, not `CancelRequest`. Located in `infra/exchange/types.py`.

6. **`OrderSide` and `OrderType`** are defined in `models/enums.py` and re-exported. Import from `squant.infra.exchange.types` or `squant.models.enums`.

7. **`get_balance()` returns `AccountBalance`** (Pydantic model with `.balances` list), not a `dict`. Assert `len(balance.balances) > 0`.

8. **`CCXTStreamProvider` methods**: Use `connect()` / `close()` / `is_connected`, NOT `start()` / `stop()` / `is_running`. It has no `subscribe_ohlcv()` method — use `add_handler(callback)` + `watch_ohlcv(symbol, timeframe)`.

9. **`create_strategy_instance` does not exist** in `engine/sandbox.py`. Use `compile_strategy()` or the service-level strategy loading mechanism.

10. **`SecretStr | None` fields** in config: `OKXSettings.api_key`, `.api_secret`, `.passphrase` can be `None`. Check for `None` before calling `.get_secret_value()`.

### Behavioral Gotchas

11. **Task 4 (account service `test_connection`)**: The existing method has careful per-exception error handling (`ExchangeAuthenticationError`, `ExchangeConnectionError`, `ExchangeAPIError`). Only change the adapter creation portion. Do NOT replace the entire method or simplify error handling.

12. **Task 5 (API deps)**: The `Exchange` dependency (`get_exchange()`) uses `credentials=None` (unauthenticated, for market data only). Account balance and order endpoints need authenticated adapters. You must either create a new `AuthenticatedExchange` dependency or route through the account service.

13. **Task 6 (StreamManager)**: `_get_exchange_credentials()` in `manager.py` reads global testnet settings. After removing global settings (Task 7), private WebSocket credentials must come from the active trading session's account, not global config.

14. **Task 7 (config cleanup)**: `tests/unit/test_config.py` has assertions on `use_ccxt_provider`. Update this test too.

15. **Test timeout**: Use `@pytest.mark.timeout(180)` or `--timeout=180` (with hyphen), not `-timeout 180`.

16. **Shared test fixtures**: `tests/integration/exchange/` tests should use a shared `conftest.py` for credential loading instead of duplicating `_get_credentials()` in each file.

---

## File Structure

### Files to Create
- `src/squant/infra/exchange/ws_types.py` — Relocated shared WebSocket message types
- `tests/integration/exchange/__init__.py` — New test package
- `tests/integration/exchange/test_ccxt_okx.py` — OKX connectivity integration tests
- `tests/integration/exchange/test_market_data.py` — Market data flow integration tests
- `tests/integration/exchange/test_engine_integration.py` — Engine integration tests
- `tests/templates/first_bar_buy.py` — Test strategy for Layer 3
- `tests/templates/bar_count.py` — Test strategy for Layer 4
- `scripts/verify-config.py` — Layer 0 configuration verification script

### Files to Delete
- `src/squant/infra/exchange/okx/adapter.py`
- `src/squant/infra/exchange/okx/client.py`
- `src/squant/infra/exchange/okx/ws_client.py`
- `src/squant/infra/exchange/okx/ws_types.py`
- `src/squant/infra/exchange/okx/__init__.py`
- `src/squant/infra/exchange/binance/adapter.py`
- `src/squant/infra/exchange/binance/client.py`
- `src/squant/infra/exchange/binance/ws_client.py`
- `src/squant/infra/exchange/binance/ws_types.py`
- `src/squant/infra/exchange/binance/__init__.py`
- `tests/unit/test_okx_adapter.py`
- `tests/unit/test_okx_ws_client.py`
- `tests/unit/test_binance_adapter.py`
- `tests/unit/test_binance_ws_client.py`
- `tests/integration/test_okx_integration.py`

### Files to Modify
- `src/squant/infra/exchange/__init__.py` — Remove native adapter exports
- `src/squant/infra/exchange/ccxt/provider.py` — Update ws_types import path
- `src/squant/infra/exchange/ccxt/transformer.py` — Update ws_types import path
- `src/squant/config.py` — Remove global testnet settings and use_ccxt_provider flag
- `src/squant/api/deps.py` — Replace OKXExchange with generic Exchange dependency
- `src/squant/api/v1/account.py` — Replace OKXExchange dependency
- `src/squant/api/v1/orders.py` — Replace OKXExchange dependency
- `src/squant/services/live_trading.py` — Unify _create_adapter() to always use CCXTRestAdapter
- `src/squant/services/account.py` — Unify connection test to use CCXTRestAdapter
- `src/squant/websocket/manager.py` — Remove native OKX WebSocket fallback
- `src/squant/engine/paper/engine.py` — Update ws_types import path
- `src/squant/engine/paper/manager.py` — Update ws_types import path
- `src/squant/engine/live/engine.py` — Update ws_types import path
- `src/squant/engine/live/manager.py` — Update ws_types import path
- `tests/unit/engine/paper/test_engine.py` — Update ws_types import path
- `tests/unit/engine/paper/test_manager.py` — Update ws_types import path
- `tests/unit/engine/paper/test_ws_events.py` — Update ws_types import path
- `tests/unit/engine/paper/test_risk_integration.py` — Update ws_types import path
- `tests/unit/engine/live/test_engine.py` — Update ws_types import path
- `tests/unit/engine/live/test_manager.py` — Update ws_types import path
- `tests/unit/engine/live/test_review_fixes.py` — Update ws_types import path
- `tests/unit/services/test_live_trading.py` — Update adapter mocks
- `tests/unit/services/test_live_trading_order_audit.py` — Update ws_types import path
- `tests/unit/services/test_account.py` — Update adapter mocks
- `tests/unit/api/test_deps.py` — Update dependency tests
- `tests/integration/test_paper_trading.py` — Update ws_types import path
- `tests/integration/services/test_account_service.py` — Update adapter usage

---

## Chunk 1: Layer 0 + Layer 0.5 (CCXT Adapter Unification)

### Task 1: Configuration Verification Script

**Files:**
- Create: `scripts/verify-config.py`

- [ ] **Step 1: Write the config verification script**

```python
#!/usr/bin/env python3
"""Verify environment configuration for live trading E2E verification."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def main() -> None:
    from squant.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    checks: list[tuple[str, bool, str]] = []

    # Core settings
    checks.append((
        "DEFAULT_EXCHANGE",
        settings.default_exchange == "okx",
        f"got '{settings.default_exchange}', expected 'okx'",
    ))
    checks.append((
        "SECRET_KEY length >= 32",
        len(settings.secret_key.get_secret_value()) >= 32,
        f"got length {len(settings.secret_key.get_secret_value())}",
    ))
    checks.append((
        "ENCRYPTION_KEY set",
        bool(settings.encryption_key.get_secret_value()),
        "not set",
    ))

    # OKX credentials
    checks.append((
        "OKX_API_KEY set",
        bool(settings.okx.api_key.get_secret_value()),
        "not set",
    ))
    checks.append((
        "OKX_API_SECRET set",
        bool(settings.okx.api_secret.get_secret_value()),
        "not set",
    ))
    checks.append((
        "OKX_PASSPHRASE set",
        bool(settings.okx.passphrase.get_secret_value()),
        "not set",
    ))

    # Live trading
    checks.append((
        "LIVE_AUTO_RECOVERY",
        settings.live.auto_recovery is True,
        f"got {settings.live.auto_recovery}, expected True",
    ))

    # Database & Redis
    db_url = settings.database.url.get_secret_value()
    checks.append((
        "DATABASE_URL set",
        "postgresql" in db_url,
        f"got '{db_url[:30]}...'",
    ))
    checks.append((
        "REDIS_URL set",
        bool(settings.redis.url),
        "not set",
    ))

    # Print results
    all_pass = True
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}" + (f" — {detail}" if not passed else ""))

    if all_pass:
        print("\nAll checks passed.")
    else:
        print("\nSome checks failed. Fix before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the script to verify current config**

Run: `uv run python scripts/verify-config.py`
Expected: Some checks may fail (e.g., OKX credentials not set yet). This is expected at this stage — the script itself should run without errors.

- [ ] **Step 3: Commit**

```bash
git add scripts/verify-config.py
git commit -m "feat: add configuration verification script for live trading E2E"
```

---

### Task 2: Relocate Shared WebSocket Types

**Files:**
- Create: `src/squant/infra/exchange/ws_types.py`
- Read: `src/squant/infra/exchange/okx/ws_types.py` (source of truth for types to relocate)
- Modify: 7+ files that import from `okx/ws_types.py`

- [ ] **Step 1: Read the current ws_types.py to understand all types**

Read: `src/squant/infra/exchange/okx/ws_types.py`
Note all type definitions: `WSCandle`, `WSTicker`, `WSTrade`, `WSOrderUpdate`, `WSOrderBook`, `WSOrderBookLevel`, `WSAccountUpdate`, `WSBalanceUpdate`, `WSMessage`, and any others.

- [ ] **Step 2: Create the new shared ws_types.py**

Copy all exchange-agnostic types from `okx/ws_types.py` to `infra/exchange/ws_types.py`. Exclude OKX-specific constants (`OKXChannel`, `CANDLE_CHANNELS`). Keep `WSMessageType` import from `types.py` for re-export.

Create: `src/squant/infra/exchange/ws_types.py`

- [ ] **Step 3: Update import paths in source files**

Update all files that import from `squant.infra.exchange.okx.ws_types` to import from `squant.infra.exchange.ws_types`:

Files to update:
- `src/squant/infra/exchange/ccxt/provider.py`
- `src/squant/infra/exchange/ccxt/transformer.py`
- `src/squant/websocket/manager.py`
- `src/squant/engine/paper/engine.py`
- `src/squant/engine/paper/manager.py`
- `src/squant/engine/live/engine.py`
- `src/squant/engine/live/manager.py`

For each file, change:
```python
# Before
from squant.infra.exchange.okx.ws_types import WSCandle, WSTicker, ...
# After
from squant.infra.exchange.ws_types import WSCandle, WSTicker, ...
```

- [ ] **Step 4: Update import paths in test files**

Files to update:
- `tests/unit/engine/paper/test_engine.py`
- `tests/unit/engine/paper/test_manager.py`
- `tests/unit/engine/paper/test_ws_events.py`
- `tests/unit/engine/paper/test_risk_integration.py`
- `tests/unit/engine/live/test_engine.py`
- `tests/unit/engine/live/test_manager.py`
- `tests/unit/engine/live/test_review_fixes.py`
- `tests/unit/services/test_live_trading_order_audit.py`
- `tests/integration/test_paper_trading.py`

Same pattern: change `squant.infra.exchange.okx.ws_types` → `squant.infra.exchange.ws_types`

- [ ] **Step 5: Run tests to verify imports are correct**

Run: `uv run pytest tests/unit -v --no-cov -n auto -x`
Expected: All tests pass. No import errors.

- [ ] **Step 6: Commit**

```bash
git add src/squant/infra/exchange/ws_types.py
git add -u  # stages all modified files
git commit -m "refactor: relocate shared WS types from okx/ to exchange/ws_types.py"
```

---

### Task 3: Unify _create_adapter() in LiveTradingService

**Files:**
- Modify: `src/squant/services/live_trading.py`

- [ ] **Step 1: Read current _create_adapter() implementation**

Read: `src/squant/services/live_trading.py` — find `_create_adapter()` method (around line 571-618)

- [ ] **Step 2: Write failing test for unified adapter creation**

Create or update test in `tests/unit/services/test_live_trading.py`:

```python
async def test_create_adapter_uses_ccxt_for_okx(self):
    """After unification, OKX should use CCXTRestAdapter."""
    # ... mock account with exchange="okx", testnet=True
    adapter = await self.service._create_adapter(account)
    assert isinstance(adapter, CCXTRestAdapter)

async def test_create_adapter_uses_ccxt_for_binance(self):
    """After unification, Binance should use CCXTRestAdapter."""
    # ... mock account with exchange="binance", testnet=False
    adapter = await self.service._create_adapter(account)
    assert isinstance(adapter, CCXTRestAdapter)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_live_trading.py -k "test_create_adapter_uses_ccxt" -v --no-cov`
Expected: FAIL (currently returns OKXAdapter)

- [ ] **Step 4: Update _create_adapter() to use CCXTRestAdapter for all exchanges**

In `src/squant/services/live_trading.py`, replace the branching logic:

```python
async def _create_adapter(self, account) -> ExchangeAdapter:
    creds = await self.account_service.get_decrypted_credentials(account)
    credentials = ExchangeCredentials(
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        passphrase=creds.get("passphrase"),
        sandbox=account.testnet,
    )
    adapter = CCXTRestAdapter(account.exchange, credentials)
    await adapter.connect()
    return adapter
```

Remove imports of `OKXAdapter` and `BinanceAdapter`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/services/test_live_trading.py -k "test_create_adapter_uses_ccxt" -v --no-cov`
Expected: PASS

- [ ] **Step 6: Run full live trading service tests**

Run: `uv run pytest tests/unit/services/test_live_trading.py -v --no-cov`
Expected: All pass (some tests may need mock updates for CCXTRestAdapter instead of OKXAdapter)

- [ ] **Step 7: Commit**

```bash
git add src/squant/services/live_trading.py tests/unit/services/test_live_trading.py
git commit -m "refactor: unify _create_adapter() to use CCXTRestAdapter for all exchanges"
```

---

### Task 4: Unify Account Service Connection Test

**Files:**
- Modify: `src/squant/services/account.py`
- Modify: `tests/unit/services/test_account.py`

- [ ] **Step 1: Read current test_connection() implementation**

Read: `src/squant/services/account.py` — find `test_connection()` method

- [ ] **Step 2: Update test_connection() to use CCXTRestAdapter**

Replace native adapter branching with unified CCXTRestAdapter instantiation. Same pattern as Task 3:

```python
async def test_connection(self, account_id: str) -> dict:
    account = await self._get_account(account_id)
    creds = await self.get_decrypted_credentials(account)
    credentials = ExchangeCredentials(
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        passphrase=creds.get("passphrase"),
        sandbox=account.testnet,
    )
    adapter = CCXTRestAdapter(account.exchange, credentials)
    try:
        await adapter.connect()
        balance = await adapter.get_balance()
        return {"success": True, "message": "Connection successful", "balance_count": len(balance)}
    except Exception as e:
        return {"success": False, "message": str(e), "balance_count": 0}
    finally:
        await adapter.close()
```

Remove imports of `OKXAdapter` and `BinanceAdapter`.

- [ ] **Step 3: Update account service tests**

Update mocks in `tests/unit/services/test_account.py` to expect `CCXTRestAdapter` instead of native adapters.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_account.py -v --no-cov`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/squant/services/account.py tests/unit/services/test_account.py
git commit -m "refactor: unify account service connection test to use CCXTRestAdapter"
```

---

### Task 5: Update API Dependencies

**Files:**
- Modify: `src/squant/api/deps.py`
- Modify: `src/squant/api/v1/account.py`
- Modify: `src/squant/api/v1/orders.py`
- Modify: `tests/unit/api/test_deps.py`

- [ ] **Step 1: Read current deps.py to understand OKXExchange and Exchange**

Read: `src/squant/api/deps.py` — understand both dependency patterns

- [ ] **Step 2: Remove OKXExchange, update Exchange dependency**

In `deps.py`:
- Remove `get_okx_exchange()` async generator function
- Remove `OKXExchange` type alias
- Update `get_exchange()` to not depend on global testnet settings — use a cached `CCXTRestAdapter` with `credentials=None` (for public market data endpoints) or source from account (for authenticated endpoints)

- [ ] **Step 3: Update account.py routes**

In `src/squant/api/v1/account.py`:
- Replace `OKXExchange` parameter with `Exchange` or remove direct adapter dependency
- Balance endpoints should use the account service (which now uses CCXTRestAdapter internally) rather than injecting an adapter directly

- [ ] **Step 4: Update orders.py routes**

In `src/squant/api/v1/orders.py`:
- Replace `OKXExchange` parameter with `Exchange` or route through order service

- [ ] **Step 5: Update deps tests**

Update `tests/unit/api/test_deps.py` to remove OKXExchange tests, update Exchange dependency tests.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/api/ -v --no-cov`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/squant/api/deps.py src/squant/api/v1/account.py src/squant/api/v1/orders.py tests/unit/api/test_deps.py
git commit -m "refactor: replace OKXExchange dependency with unified Exchange"
```

---

### Task 6: Remove Native OKX WebSocket Fallback from StreamManager

**Files:**
- Modify: `src/squant/websocket/manager.py`

- [ ] **Step 1: Read StreamManager to identify all native OKX WebSocket paths**

Read: `src/squant/websocket/manager.py` — find all references to `use_ccxt_provider`, `OKXWebSocketClient`, native OKX fallback code

- [ ] **Step 2: Remove native OKX WebSocket paths**

In `manager.py`:
- Remove all `if self._settings.use_ccxt_provider` / `else` branches — keep only the CCXT path
- Remove `OKXWebSocketClient` import and instantiation
- Remove `_start_native_okx()` or similar fallback methods
- Remove references to `_okx_ws_client`
- Update `_get_exchange_credentials()` to not depend on global testnet settings — private WebSocket credentials should come from the active trading session's account, not global config

- [ ] **Step 3: Run WebSocket-related tests**

Run: `uv run pytest tests/unit/websocket/ -v --no-cov`
Expected: All pass (some tests for native OKX WS may need removal)

- [ ] **Step 4: Commit**

```bash
git add src/squant/websocket/manager.py
git commit -m "refactor: remove native OKX WebSocket fallback, always use CCXTStreamProvider"
```

---

### Task 7: Clean Up Config — Remove Global Testnet and use_ccxt_provider

**Files:**
- Modify: `src/squant/config.py`

- [ ] **Step 1: Read config.py to identify all settings to remove**

Read: `src/squant/config.py` — find:
- `OKXSettings.testnet`
- `BinanceSettings.testnet`
- `BybitSettings.testnet`
- `use_ccxt_provider` field
- Any flat aliases for these fields

- [ ] **Step 2: Remove the settings**

In `config.py`:
- Remove `testnet` field from `OKXSettings`, `BinanceSettings`, `BybitSettings`
- Remove `use_ccxt_provider` field
- Remove corresponding flat property aliases (e.g., `okx_testnet`, `binance_testnet`, `use_ccxt_provider`)

- [ ] **Step 3: Run full test suite to catch any remaining references**

Run: `uv run pytest tests/unit -v --no-cov -n auto -x`
Expected: All pass. Any test that referenced these settings will fail here and needs fixing.

- [ ] **Step 4: Fix any broken tests**

Search for and update any tests that reference the removed settings.

- [ ] **Step 5: Commit**

```bash
git add src/squant/config.py
git add -u  # any test fixes
git commit -m "refactor: remove global testnet settings and use_ccxt_provider flag"
```

---

### Task 8: Delete Native Adapter Files and Update Exports

**Files:**
- Delete: all files in `src/squant/infra/exchange/okx/` and `src/squant/infra/exchange/binance/`
- Delete: native adapter test files
- Modify: `src/squant/infra/exchange/__init__.py`

- [ ] **Step 1: Update __init__.py exports**

Read and modify `src/squant/infra/exchange/__init__.py`:
- Remove `OKXAdapter`, `BinanceAdapter` from imports and `__all__`
- Keep `ExchangeAdapter`, `CCXTRestAdapter`, and other CCXT exports

- [ ] **Step 2: Delete native adapter source files**

```bash
rm -rf src/squant/infra/exchange/okx/
rm -rf src/squant/infra/exchange/binance/
```

- [ ] **Step 3: Delete native adapter test files**

```bash
rm -f tests/unit/test_okx_adapter.py
rm -f tests/unit/test_okx_ws_client.py
rm -f tests/unit/test_binance_adapter.py
rm -f tests/unit/test_binance_ws_client.py
rm -f tests/integration/test_okx_integration.py
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/unit -v --no-cov -n auto`
Expected: All pass. No import errors from deleted files.

- [ ] **Step 5: Run lint**

Run: `./scripts/dev.sh lint`
Expected: No errors related to missing imports.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: delete native OKX and Binance adapters, unification complete"
```

---

### Task 9: Verify Full Test Suite Passes

**Files:** None (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit -v --no-cov -n auto`
Expected: All pass

- [ ] **Step 2: Run lint**

Run: `./scripts/dev.sh lint`
Expected: No blocking errors

- [ ] **Step 3: Run integration tests (if Docker services available)**

Run: `uv run pytest tests/integration -v --no-cov`
Expected: All pass

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && pnpm test`
Expected: All pass (frontend shouldn't be affected, but verify)

- [ ] **Step 5: Commit any final fixes**

If any tests needed fixing:
```bash
git add -u
git commit -m "fix: resolve remaining test issues after CCXT unification"
```

---

## Chunk 2: Layer 1 + Layer 2 (Exchange Connectivity & Market Data)

### Task 10: Create Test Strategy Files

**Files:**
- Create: `tests/templates/first_bar_buy.py`
- Create: `tests/templates/bar_count.py`

- [ ] **Step 1: Write FirstBarBuyStrategy**

```python
"""Minimal test strategy: buys once on the first bar, then idles."""
from decimal import Decimal


class FirstBarBuyStrategy:
    def on_init(self):
        self.bought = False

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
            self.bought = True

    def on_stop(self):
        pass
```

- [ ] **Step 2: Write BarCountStrategy**

```python
"""Deterministic test strategy: buys on bar 3, sells on bar 8, repeats."""
from decimal import Decimal


class BarCountStrategy:
    def on_init(self):
        self.bar_count = 0

    def on_bar(self, bar):
        self.bar_count += 1
        pos = self.ctx.get_position(bar.symbol)
        if self.bar_count == 3 and not pos:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
        elif self.bar_count == 8 and pos:
            self.ctx.sell(bar.symbol, Decimal("0.01"))
            self.bar_count = 0

    def on_stop(self):
        pass
```

- [ ] **Step 3: Commit**

```bash
git add tests/templates/first_bar_buy.py tests/templates/bar_count.py
git commit -m "feat: add test strategies for live trading E2E verification"
```

---

### Task 11: Layer 1 — Exchange Connectivity Tests

**Files:**
- Create: `tests/integration/exchange/__init__.py`
- Create: `tests/integration/exchange/test_ccxt_okx.py`

- [ ] **Step 1: Create test package**

Create empty `tests/integration/exchange/__init__.py`.

- [ ] **Step 2: Write exchange connectivity tests**

Create `tests/integration/exchange/test_ccxt_okx.py`:

```python
"""
Layer 1: Exchange Connectivity Tests — OKX Demo Trading via CCXT.

Tests verify that CCXTRestAdapter can interact with OKX demo trading account.
Requires OKX demo trading API credentials in .env.

Run: uv run pytest tests/integration/exchange/test_ccxt_okx.py -v
"""
import pytest
from decimal import Decimal

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.ccxt.types import ExchangeCredentials
from squant.infra.exchange.types import OrderRequest, OrderSide, OrderType
from squant.config import get_settings


def _get_credentials() -> ExchangeCredentials | None:
    """Load OKX demo credentials from settings."""
    get_settings.cache_clear()
    settings = get_settings()
    api_key = settings.okx.api_key.get_secret_value()
    if not api_key:
        return None
    return ExchangeCredentials(
        api_key=api_key,
        api_secret=settings.okx.api_secret.get_secret_value(),
        passphrase=settings.okx.passphrase.get_secret_value(),
        sandbox=True,  # Demo trading
    )


skip_no_creds = pytest.mark.skipif(
    _get_credentials() is None,
    reason="OKX demo trading credentials not configured",
)


@pytest.fixture
async def adapter():
    """Create and connect a CCXTRestAdapter for OKX demo trading."""
    creds = _get_credentials()
    assert creds is not None
    adapter = CCXTRestAdapter("okx", creds)
    await adapter.connect()
    yield adapter
    await adapter.close()


@skip_no_creds
class TestOKXConnectivity:
    """Layer 1: Verify CCXTRestAdapter works with OKX demo trading."""

    async def test_1a_connection_and_balance(self, adapter):
        """1a/1b: Connect and query balance."""
        balance = await adapter.get_balance()
        assert isinstance(balance, dict)
        # OKX demo accounts come pre-funded
        assert len(balance) > 0

    async def test_1c_load_markets(self, adapter):
        """1c: Load market info."""
        # load_markets is called during connect(), verify we can get ticker
        ticker = await adapter.get_ticker("BTC/USDT")
        assert ticker is not None
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last > 0

    async def test_1d_place_query_cancel_order(self, adapter):
        """1d: Place a limit order, query it, then cancel."""
        # Get current price to place order far away
        ticker = await adapter.get_ticker("BTC/USDT")
        far_price = ticker.last * Decimal("0.5")  # 50% below market

        # Place limit buy order
        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=far_price,
        )
        response = await adapter.place_order(request)
        assert response.order_id, "Order should have an exchange order ID"
        assert response.status is not None

        # Query order
        order = await adapter.get_order("BTC/USDT", response.order_id)
        assert order is not None
        assert order.order_id == response.order_id

        # Cancel order
        from squant.infra.exchange.types import CancelRequest
        cancel = CancelRequest(symbol="BTC/USDT", order_id=response.order_id)
        result = await adapter.cancel_order(cancel)
        assert result is not None

    async def test_1e_market_order_fill(self, adapter):
        """1e: Place a market order and verify fill."""
        request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )
        response = await adapter.place_order(request)
        assert response.order_id

        # Query — market orders should fill quickly
        import asyncio
        await asyncio.sleep(2)
        order = await adapter.get_order("BTC/USDT", response.order_id)
        assert order.filled_amount > 0

        # Clean up: sell back
        sell_request = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=order.filled_amount,
        )
        await adapter.place_order(sell_request)
```

- [ ] **Step 3: Run connectivity tests (if credentials available)**

Run: `uv run pytest tests/integration/exchange/test_ccxt_okx.py -v --no-cov`
Expected: All pass if OKX demo credentials are configured; skip if not.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/exchange/
git commit -m "test: add Layer 1 exchange connectivity tests for OKX demo trading"
```

---

### Task 12: Layer 2 — Market Data Flow Tests

**Files:**
- Create: `tests/integration/exchange/test_market_data.py`

- [ ] **Step 1: Write market data flow tests**

Create `tests/integration/exchange/test_market_data.py`:

```python
"""
Layer 2: Market Data Flow Tests.

Tests verify that WebSocket receives real-time K-line data
and routes it through Redis pub/sub.

Run: uv run pytest tests/integration/exchange/test_market_data.py -v
"""
import asyncio
import pytest
from unittest.mock import AsyncMock

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider


@pytest.mark.integration
class TestMarketDataFlow:
    """Layer 2: Verify WebSocket → candle close detection → Redis routing."""

    async def test_2a_websocket_connection(self):
        """2a: CCXTStreamProvider can connect to OKX WebSocket."""
        provider = CCXTStreamProvider("okx", credentials=None)
        try:
            await provider.start()
            assert provider.is_running
        finally:
            await provider.stop()

    async def test_2bc_candle_reception_and_close_detection(self):
        """2b+2c: Subscribe to BTC/USDT 1m, verify candle data and close detection."""
        provider = CCXTStreamProvider("okx", credentials=None)
        closed_candles = []
        open_candles = []

        async def on_candle(candle):
            if candle.is_closed:
                closed_candles.append(candle)
            else:
                open_candles.append(candle)

        try:
            await provider.start()
            await provider.subscribe_ohlcv("BTC/USDT", "1m", on_candle)

            # Wait for at least 2 minutes to see 1+ closed candles
            # In practice, run this manually for 5+ minutes for full verification
            await asyncio.sleep(130)

            assert len(open_candles) > 0, "Should receive open candle updates"
            assert len(closed_candles) >= 1, "Should detect at least 1 closed candle in 2+ minutes"

            # Verify candle structure
            candle = closed_candles[0] if closed_candles else open_candles[0]
            assert candle.symbol == "BTC/USDT"
            assert candle.open > 0
            assert candle.high > 0
            assert candle.low > 0
            assert candle.close > 0
            assert candle.volume >= 0
            assert candle.timestamp > 0
        finally:
            await provider.stop()
```

Note: This test takes ~2 minutes to run due to waiting for candle close. For the 5-minute verification mentioned in the spec, run manually and observe.

- [ ] **Step 2: Run market data tests**

Run: `uv run pytest tests/integration/exchange/test_market_data.py -v --no-cov -timeout 180`
Expected: Pass (takes ~2 minutes)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/exchange/test_market_data.py
git commit -m "test: add Layer 2 market data flow tests"
```

---

## Chunk 3: Layer 3 + Layer 4 (Engine Integration & Full Lifecycle)

### Task 13: Layer 3 — Engine Integration Tests

**Files:**
- Create: `tests/integration/exchange/test_engine_integration.py`

- [ ] **Step 1: Write engine integration tests**

Create `tests/integration/exchange/test_engine_integration.py`:

```python
"""
Layer 3: Engine Integration Tests.

Tests verify that the LiveTradingEngine correctly processes candles,
executes strategy, validates risk, and submits orders to OKX demo account.

Requires: OKX demo trading credentials, running backend services.
Run: uv run pytest tests/integration/exchange/test_engine_integration.py -v
"""
import asyncio
import pytest
from decimal import Decimal
from pathlib import Path

from squant.config import get_settings
from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.ccxt.types import ExchangeCredentials


def _get_credentials() -> ExchangeCredentials | None:
    get_settings.cache_clear()
    settings = get_settings()
    api_key = settings.okx.api_key.get_secret_value()
    if not api_key:
        return None
    return ExchangeCredentials(
        api_key=api_key,
        api_secret=settings.okx.api_secret.get_secret_value(),
        passphrase=settings.okx.passphrase.get_secret_value(),
        sandbox=True,
    )


skip_no_creds = pytest.mark.skipif(
    _get_credentials() is None,
    reason="OKX demo trading credentials not configured",
)


@skip_no_creds
class TestEngineIntegration:
    """Layer 3: Verify engine integration with OKX demo trading.

    These tests require a running backend (DB, Redis) and OKX demo credentials.
    They are designed to be run semi-manually during E2E verification.
    """

    async def test_3a_strategy_loads_in_sandbox(self):
        """3a: Strategy file loads correctly in RestrictedPython sandbox."""
        from squant.engine.sandbox import create_strategy_instance

        strategy_code = Path("tests/templates/first_bar_buy.py").read_text()
        instance = create_strategy_instance(strategy_code, "FirstBarBuyStrategy", {})
        assert instance is not None
        instance.on_init()
        assert instance.bought is False

    async def test_3e_order_submission_to_exchange(self):
        """3e: Order can be submitted to OKX demo account via CCXT."""
        creds = _get_credentials()
        adapter = CCXTRestAdapter("okx", creds)
        try:
            await adapter.connect()

            from squant.infra.exchange.types import OrderRequest, OrderSide, OrderType
            request = OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.001"),
            )
            response = await adapter.place_order(request)
            assert response.order_id, "Should receive exchange order ID"

            # Wait and verify fill
            await asyncio.sleep(2)
            order = await adapter.get_order("BTC/USDT", response.order_id)
            assert order.filled_amount > 0, "Market order should fill"

            # Clean up
            sell = OrderRequest(
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=order.filled_amount,
            )
            await adapter.place_order(sell)
        finally:
            await adapter.close()
```

Note: Steps 3b (K-line triggers on_bar), 3c, 3d, 3f, 3g require a fully running backend with WebSocket. These are best verified manually or via the full E2E flow in Layer 4. The tests above cover the independently testable components.

- [ ] **Step 2: Run engine integration tests**

Run: `uv run pytest tests/integration/exchange/test_engine_integration.py -v --no-cov`
Expected: Pass if credentials configured.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/exchange/test_engine_integration.py
git commit -m "test: add Layer 3 engine integration tests"
```

---

### Task 14: Layer 4 — Manual Verification Checklist

**Files:**
- Create: `docs/superpowers/plans/layer4-verification-checklist.md`

- [ ] **Step 1: Create the manual verification checklist**

This document guides the manual verification of the full lifecycle. It's a checklist, not automated tests.

```markdown
# Layer 4: Full Lifecycle Verification Checklist

## Prerequisites
- [ ] Backend running (`./scripts/dev.sh backend`)
- [ ] Frontend running (`cd frontend && pnpm dev`)
- [ ] OKX demo trading account configured in the system
- [ ] BarCountStrategy uploaded as a strategy

## 4a: Full Startup via UI
- [ ] Navigate to Live Trading page
- [ ] Select BarCountStrategy
- [ ] Configure: BTC/USDT, 1m timeframe, OKX demo account
- [ ] Set risk config: min_order_value=1, max_position_size=0.9, max_order_size=0.5
- [ ] Click Start → Status becomes RUNNING
- [ ] Note run_id: _______________

## 4b: Real-time Price Display
- [ ] Monitor page shows real-time BTC/USDT price updates
- [ ] Price matches OKX website (within 1 second)

## 4c: Trading Loop
- [ ] Wait for bar 3 (~3 minutes) → BUY order appears
- [ ] Order fills → Position shows 0.01 BTC
- [ ] Equity snapshot updates
- [ ] Wait for bar 8 (~8 minutes) → SELL order appears
- [ ] Order fills → Position closes
- [ ] Realized PnL visible

## 4d: Order/Position Visibility
- [ ] SessionDetail page shows orders (pending → filled)
- [ ] Positions section shows open position during hold period
- [ ] Equity curve chart renders with data points

## 4e: Order History
- [ ] Navigate to OrderHistory page
- [ ] Orders from this session are visible
- [ ] Filter by symbol BTC/USDT works

## 4f: Order Consistency with Exchange
- [ ] Log in to OKX demo trading web interface
- [ ] Compare order list: IDs, sides, amounts, prices, statuses match
- [ ] Compare fill prices: match within rounding

## 4g: Normal Stop
- [ ] Click Stop on the session
- [ ] Pending orders cancelled (if any)
- [ ] Status changes to STOPPED
- [ ] Session result persisted (check DB or API response)

## 4h: Graceful Crash Recovery
- [ ] Start a new session with BarCountStrategy
- [ ] Wait for at least 1 order to fill
- [ ] Send SIGTERM to backend process: `kill -TERM <pid>`
- [ ] Restart backend: `./scripts/dev.sh backend`
- [ ] Check: session status should be INTERRUPTED then auto-recover to RUNNING
- [ ] Verify: session resumes, strategy continues from correct bar count

## 4i: Hard Crash Recovery
- [ ] Start a new session
- [ ] Send SIGKILL: `kill -9 <pid>`
- [ ] Restart backend
- [ ] Check: session marked INTERRUPTED
- [ ] Expected: recovery may fail (no state saved) → status becomes ERROR
- [ ] This is acceptable behavior — verify no crash/hang

## 4j: Emergency Close
- [ ] Start a new session, wait for a position to open
- [ ] Call emergency-close via API or UI
- [ ] All orders cancelled
- [ ] Position closed (sell order placed and filled)
- [ ] Status becomes STOPPED

## Results
- Issues found: _______________
- All checks passed: [ ] Yes / [ ] No
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/layer4-verification-checklist.md
git commit -m "docs: add Layer 4 manual verification checklist"
```

---

### Task 15: Final Integration — Run All Tests and Update Docs

**Files:**
- Modify: `CLAUDE.md` (update architecture section)

- [ ] **Step 1: Run complete test suite**

```bash
uv run pytest tests/unit -v --no-cov -n auto
uv run pytest tests/integration -v --no-cov  # if Docker services available
cd frontend && pnpm test
```

Expected: All pass.

- [ ] **Step 2: Run lint**

Run: `./scripts/dev.sh lint`
Expected: No blocking errors.

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, update the following sections:
- **Exchange abstraction**: Remove references to native OKX/Binance adapters. State that all exchanges use CCXT.
- **Known Gotchas**: Remove `RedisClient` gotcha if it was related to OKX adapter.
- **Key Patterns**: Update `Exchange` dependency description.
- **Common Constructor Signatures**: Remove `OKXAdapter` entry, keep `CCXTRestAdapter`.

- [ ] **Step 4: Regenerate API types (if schemas changed)**

Run: `./scripts/generate-api-types.sh`
Expected: No drift if no schema changes were made.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect CCXT-only architecture"
```
