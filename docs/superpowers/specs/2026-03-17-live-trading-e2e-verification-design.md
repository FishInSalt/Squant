# Live Trading End-to-End Verification Design

## Context

Squant is a personal quantitative trading system for cryptocurrency. The core trading engines (backtest, paper, live) have been implemented and code-reviewed extensively (31+ bugs fixed, 262 live trading tests). However, the system has **never been tested against a real exchange**. All E2E tests use mocks.

The paper trading module is "barely usable" after integration testing. The live trading module has undergone several rounds of code review but no real-world execution.

**Goal**: Verify the live trading system works end-to-end against OKX Testnet, using a layered approach that isolates each integration point for precise debugging.

## Approach: Layered Verification

Each layer is verified independently before proceeding to the next. Issues found at each layer are fixed before moving on.

```
Layer 0: Configuration Verification  (environment sanity check)
Layer 1: Exchange Connectivity        (isolated from engine)
Layer 2: Market Data Flow             (isolated from trading logic)
Layer 3: Engine Integration           (combines Layer 1 + 2 with strategy execution)
Layer 4: Full Lifecycle               (end-to-end manual verification)
```

## Critical Architecture Notes

Before execution, be aware of two design decisions that affect testnet verification:

### OKX uses the native adapter, not CCXT

The `LiveTradingService._create_adapter()` creates an `OKXAdapter` (native) for OKX, not a `CCXTRestAdapter`. REST order operations (place, cancel, query) go through the native adapter. Only the private WebSocket for order push uses the `CCXTStreamProvider`. Layer 1 must test the native adapter path.

### StreamManager always uses mainnet WebSocket

`StreamManager._start_ccxt_provider()` intentionally connects to the **mainnet** WebSocket with `credentials=None` for public market data. This means the candle data the engine receives will be mainnet prices, while orders are placed on testnet. This is by design (testnet market data is often stale/unreliable), but creates a **price discrepancy risk**: mainnet BTC might be $95,000 while testnet BTC is at a completely different price.

**Mitigation**: Layer 3 test strategies must use **market orders** (not limit orders at a specific price) to avoid rejection due to price mismatch. Risk config `max_price_deviation` should be set generously (e.g., 0.5) for testnet verification.

## Layer 0: Configuration Verification

**Goal**: Confirm the environment is correctly configured before any exchange interaction.

**Checklist**:
- [ ] `DEFAULT_EXCHANGE=okx` in `.env`
- [ ] `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_PASSPHRASE` set with testnet credentials
- [ ] `OKX_TESTNET=true` in `.env`
- [ ] `SECRET_KEY` set (min 32 chars)
- [ ] `ENCRYPTION_KEY` set (32 bytes, same key used for credential encryption/decryption)
- [ ] `LIVE_AUTO_RECOVERY=true` in `.env` (defaults to `False`, required for Layer 4e/4f crash recovery testing)
- [ ] `DATABASE_URL` and `REDIS_URL` reachable
- [ ] Print effective configuration (exchange, testnet flag, adapter type) to verify no mainnet leakage
- [ ] Verify exchange account record has `testnet=True` in the database after creation

## Layer 1: Exchange Connectivity

**Goal**: Prove the system can interact with OKX Testnet via the **native OKX adapter**.

| Step | Verification | Method |
|------|-------------|--------|
| 1a | Account creation + credential encryption | Create exchange account via API with `testnet=true`, verify encrypted storage and correct decryption via `ENCRYPTION_KEY` |
| 1b | Connection test + balance query | Call test-connection endpoint, confirm real testnet balance returned |
| 1c | Market info loading | Call `load_markets()` via native OKX adapter, confirm testnet trading pairs list is correct |
| 1d | Place + query + cancel order | Place a limit order far from market price on testnet, query status, then cancel |
| 1e | Fill query | If 1d fills (unlikely with far price), verify fill record query works |

**Output**: Automated integration tests in `tests/integration/exchange/` (directory to be created), marked with `@pytest.mark.okx_private`.

**Prerequisites**:
- OKX Testnet API credentials configured in `.env`
- `ENCRYPTION_KEY` set and consistent
- OKX Testnet account funded with test USDT

**Key files involved**:
- `src/squant/infra/exchange/okx/adapter.py` — Native OKX REST adapter (order placement, query, cancel)
- `src/squant/infra/exchange/okx/client.py` — OKX HTTP client
- `src/squant/api/v1/exchange_accounts.py` — Account CRUD + test endpoint
- `src/squant/services/account.py` — Credential encryption/decryption

## Layer 2: Market Data Flow

**Goal**: Prove WebSocket can receive real-time K-line data and route it correctly to Redis and the frontend.

| Step | Verification | Method |
|------|-------------|--------|
| 2a | WebSocket connection | StreamManager connects to mainnet WebSocket (by design), verify handshake + heartbeat |
| 2b | K-line subscription + reception | Subscribe to BTC/USDT 1m, confirm candle data arrives with complete OHLCV fields |
| 2c | Candle close detection | Observe that the `is_closed` heuristic (timestamp change detection in `CCXTStreamProvider._ohlcv_loop()`) fires **exactly once per minute** for 1m candles, with no missed or duplicate firings. Run for at least 5 consecutive minutes. |
| 2d | Redis pub/sub forwarding | Confirm closed candles published to `squant:ws:candles:BTC/USDT:1m` channel |
| 2e | Frontend WebSocket reception | Open frontend K-line chart, confirm real-time updates |
| 2f | Reconnection | Manually disconnect WebSocket, verify auto-reconnect and data flow recovery |

**Note**: StreamManager connects to **mainnet** WebSocket (`credentials=None`, no sandbox flag). This is intentional — testnet market data is unreliable. The `wspap.okx.com` testnet WebSocket URL is relevant only for the native OKX WebSocket client (used for private order push in Layer 3), not for the public market data stream.

**Key files involved**:
- `src/squant/websocket/manager.py` — StreamManager (mainnet public WebSocket)
- `src/squant/infra/exchange/ccxt/provider.py` — `CCXTStreamProvider._ohlcv_loop()` (candle close detection)
- `src/squant/infra/redis.py` — Redis pub/sub
- `frontend/src/stores/websocket.ts` — Frontend WebSocket client

## Layer 3: Engine Integration

**Goal**: Prove that K-line data triggers strategy execution, generates orders, passes risk checks, and submits to OKX Testnet.

| Step | Verification | Method |
|------|-------------|--------|
| 3a | Strategy loading + sandbox | Upload a simple test strategy, confirm RestrictedPython sandbox loads it and calls `on_init()` |
| 3b | K-line triggers on_bar | Start LiveTradingEngine on OKX Testnet, confirm each closed candle triggers `strategy.on_bar(bar)` |
| 3c | Order request generation | Strategy calls `ctx.buy()` in on_bar, confirm engine receives order request |
| 3d | Risk check rejection | Intentionally exceed position limit, confirm RiskManager rejects order and logs it |
| 3e | Order submission to exchange | Risk-approved order submitted to OKX Testnet via native OKX adapter, confirm exchange_order_id returned |
| 3f | Order status sync — private WebSocket | Confirm order status update arrives via private WebSocket push (`CCXTStreamProvider` with testnet credentials) |
| 3g | Order status sync — REST polling fallback | Disable/disconnect private WebSocket, confirm engine falls back to REST polling via `_sync_pending_orders()` and correctly syncs order status |

**Test strategy**: Minimal strategy that buys a small fixed amount on the first candle using a **market order**. Market order avoids price mismatch between mainnet candle price and testnet order book.

```python
class FirstBarBuyStrategy(Strategy):
    def on_init(self):
        self.bought = False

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
            self.bought = True
```

**Risk config for testnet**:
- `max_price_deviation`: `0.5` (generous, to accommodate mainnet/testnet price gap)
- `min_order_value`: `1` (lower than default 10, to accommodate testnet pricing)
- `max_position_size`: `0.9` (permissive for testing)
- `max_order_size`: `0.5` (permissive for testing)
- Other values: defaults

**Amount note**: `0.01 BTC` is chosen to comfortably exceed minimum order sizes on OKX Testnet. Verify the actual testnet minimum before execution; adjust if needed.

**Key files involved**:
- `src/squant/engine/live/engine.py` — `LiveTradingEngine.process_candle()`, `_sync_pending_orders()`
- `src/squant/engine/risk/manager.py` — `RiskManager.validate_order()`
- `src/squant/engine/sandbox.py` — Strategy sandbox
- `src/squant/services/live_trading.py` — `_create_adapter()` returns `OKXAdapter` for OKX
- `src/squant/infra/exchange/okx/adapter.py` — Native OKX adapter for REST orders
- `src/squant/infra/exchange/ccxt/provider.py` — Private WebSocket for order push

## Layer 4: Full Lifecycle Verification

**Goal**: Manually verify the complete live trading lifecycle on OKX Testnet, from UI to exchange and back.

| Step | Verification | Method |
|------|-------------|--------|
| 4a | Full startup via UI | Configure and start a live session through the frontend, confirm status becomes RUNNING |
| 4b | Trading loop | Observe: strategy executes → order placed → filled → position updated → equity snapshot recorded |
| 4c | Monitoring pages | Verify Monitor and SessionDetail pages show real-time status, positions, orders, equity curve |
| 4d | Normal stop | Call stop, confirm: pending orders cancelled, status becomes STOPPED, engine state persisted to DB |
| 4e | Graceful crash recovery | Send `SIGTERM` to backend while session is RUNNING. Confirm: state persisted on shutdown → restart → session marked INTERRUPTED → auto-recovery → resumes running |
| 4f | Hard crash recovery | Send `SIGKILL` to backend while session is RUNNING. Confirm: no state saved → restart → session marked INTERRUPTED → recovery attempt (may fail due to missing state, which is expected and should be handled gracefully as ERROR) |
| 4g | Emergency close | Start new session, call emergency-close, confirm: all orders cancelled, positions closed, status STOPPED |

**Test strategy**: Deterministic bar-counting strategy that buys on bar N and sells on bar M (e.g., buy on bar 3, sell on bar 8). This avoids dependence on price patterns (MA crossover may not trigger on testnet's potentially flat market data).

```python
class BarCountStrategy(Strategy):
    def on_init(self):
        self.bar_count = 0

    def on_bar(self, bar):
        self.bar_count += 1
        pos = self.ctx.get_position(bar.symbol)
        if self.bar_count == 3 and not pos:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
        elif self.bar_count == 8 and pos:
            self.ctx.sell(bar.symbol, Decimal("0.01"))
            self.bar_count = 0  # reset for next cycle
```

**Output**: Manual verification checklist + discovered issues list for subsequent fixes.

## Execution Rules

1. **No layer skipping** — complete and fix each layer before moving to the next.
2. **Fix-then-proceed** — issues found at any layer are fixed and re-verified before advancing.
3. **Automated where possible** — Layers 1-3 produce reusable integration test scripts. Layer 4 is manual.
4. **OKX Testnet only** — no mainnet order interaction until all 4 layers pass.
5. **Both sync paths tested** — Layer 3 explicitly verifies both private WebSocket and REST polling for order status.
6. **Both crash modes tested** — Layer 4 tests graceful (SIGTERM) and hard (SIGKILL) termination separately.

## Target Exchange

- **Exchange**: OKX
- **Environment**: Testnet (`OKX_TESTNET=true`)
- **Adapter**: Native OKX adapter (`OKXAdapter`) for REST, `CCXTStreamProvider` for private WebSocket
- **Market data**: Mainnet WebSocket (by design, via StreamManager)
- **Trading pair**: BTC/USDT (spot)
- **Timeframe**: 1m (for quick verification cycles)
