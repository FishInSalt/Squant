# Live Trading End-to-End Verification Design

## Context

Squant is a personal quantitative trading system for cryptocurrency. The core trading engines (backtest, paper, live) have been implemented and code-reviewed extensively (31+ bugs fixed, 262 live trading tests). However, the system has **never been tested against a real exchange**. All E2E tests use mocks.

The paper trading module is "barely usable" after integration testing. The live trading module has undergone several rounds of code review but no real-world execution.

**Goal**: Verify the live trading system works end-to-end against OKX Testnet, achieving the following milestone:

> Using real exchange market data to execute strategies, with real-time price updates on the UI, order/position visibility, and order history consistent with the exchange's demo account. After all features pass verification, the user only needs to switch to a real exchange account to begin live trading with real funds.

## Architecture Decision: Unify to CCXT

**Decision**: Remove native OKX and Binance adapters. All exchange interactions (REST + WebSocket) go through CCXT exclusively.

**Current state**: The codebase uses a mixed approach:
- REST orders: native `OKXAdapter` for OKX, native `BinanceAdapter` for Binance, `CCXTRestAdapter` for Bybit
- Public WebSocket: `CCXTStreamProvider` (already unified)
- Private WebSocket: `CCXTStreamProvider` (already unified)

**Rationale**: CCXT already covers all methods in the native adapters. Maintaining two adapter paths doubles the integration surface and makes exchange-switching impossible without code changes. After unification, adding a new exchange is configuration-only.

**Scope of change**:
1. Relocate shared WebSocket message types (`WSCandle`, `WSTicker`, `WSOrderUpdate`, etc.) from `infra/exchange/okx/ws_types.py` to `infra/exchange/ws_types.py` — these types are imported by 7+ files outside the `okx/` directory. OKX-specific constants (`OKXChannel`, `CANDLE_CHANNELS`) are removed along with the native adapter.
2. Update `LiveTradingService._create_adapter()` to use `CCXTRestAdapter` for all exchanges
3. Update `api/deps.py` — replace `OKXExchange` type alias with generic `ExchangeAdapter`
4. Update `api/v1/account.py` and `api/v1/orders.py` — replace `OKXExchange` dependency with a generic authenticated exchange dependency
5. Update `infra/exchange/__init__.py` — remove `OKXAdapter` and `BinanceAdapter` from exports
6. Remove native OKX adapter (`infra/exchange/okx/`) and Binance adapter (`infra/exchange/binance/`)
7. Remove `use_ccxt_provider` flag (WebSocket always uses CCXT)
8. Update `websocket/manager.py` — remove native OKX WebSocket fallback path
9. Update affected tests

**Verification needed before removal**: Confirm CCXT handles OKX-specific behaviors correctly:
- `ordId` present in place_order response (Issue 028)
- Cancel order with `order_id` or `client_order_id` (Issue 026)
- Testnet support via `sandbox=True` parameter
- Passphrase authentication (3-param auth unique to OKX)

## Approach: Layered Verification

Each layer is verified independently before proceeding to the next. Issues found at each layer are fixed before moving on.

```
Layer 0: Configuration Verification     (environment sanity check)
Layer 0.5: CCXT Adapter Unification     (remove native adapters, verify CCXT parity)
Layer 1: Exchange Connectivity           (isolated from engine)
Layer 2: Market Data Flow                (isolated from trading logic)
Layer 3: Engine Integration              (combines Layer 1 + 2 with strategy execution)
Layer 4: Full Lifecycle + Acceptance     (end-to-end verification with acceptance criteria)
```

## Architecture Notes

### StreamManager always uses mainnet WebSocket

`StreamManager._start_ccxt_provider()` intentionally connects to the **mainnet** WebSocket with `credentials=None` for public market data. This means the candle data the engine receives will be **real mainnet prices**, while orders are placed on testnet (simulated order book).

This is by design: testnet market data is unreliable. The strategy sees real market conditions, but trades are executed in a risk-free simulated environment. When switching to a real account, the market data path stays the same — only order execution moves to mainnet.

**Implication for testnet verification**: Use **market orders** for testing (not limit orders at specific prices), since the testnet order book may have different price levels than mainnet. Set `max_price_deviation` generously in risk config.

## Layer 0: Configuration Verification

**Goal**: Confirm the environment is correctly configured before any exchange interaction.

**Checklist**:
- [ ] `DEFAULT_EXCHANGE=okx` in `.env`
- [ ] `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_PASSPHRASE` set with testnet credentials
- [ ] `OKX_TESTNET=true` in `.env`
- [ ] `USE_CCXT_PROVIDER=true` in `.env` (will be removed after Layer 0.5; verify it's `true` before unification)
- [ ] `SECRET_KEY` set (min 32 chars)
- [ ] `ENCRYPTION_KEY` set (32 bytes, consistent for encrypt/decrypt)
- [ ] `LIVE_AUTO_RECOVERY=true` in `.env` (defaults to `False`, required for Layer 4 crash recovery)
- [ ] `DATABASE_URL` and `REDIS_URL` reachable
- [ ] Print effective configuration (exchange, testnet flag, adapter type) to verify no mainnet leakage
- [ ] Verify exchange account record has `testnet=True` in the database after creation

## Layer 0.5: CCXT Adapter Unification

**Goal**: Remove native OKX/Binance adapters and verify CCXT provides equivalent functionality.

**Pre-removal verification** (using existing native adapter as reference):

| Check | Method |
|-------|--------|
| CCXT place_order returns `ordId` | Call `CCXTRestAdapter.place_order()` on OKX Testnet, verify response contains exchange order ID |
| CCXT cancel_order works with order_id | Place then cancel via CCXT, verify success |
| CCXT testnet routing | Confirm `sandbox=True` routes to OKX demo trading, not mainnet |
| CCXT passphrase auth | Verify 3-param authentication works (api_key, secret, passphrase) |
| CCXT balance query | Compare CCXT balance result with OKX native adapter result |
| CCXT market info | Compare `load_markets()` result between CCXT and native adapter |

**Code changes** (ordered by dependency):
1. Relocate shared WS types: move `WSCandle`, `WSTicker`, `WSTrade`, `WSOrderUpdate`, `WSOrderBook`, `WSOrderBookLevel`, `WSAccountUpdate`, `WSBalanceUpdate`, `WSMessage` from `infra/exchange/okx/ws_types.py` to `infra/exchange/ws_types.py`. Remove OKX-specific constants (`OKXChannel`, `CANDLE_CHANNELS`). Update all 7+ importing files.
2. `src/squant/services/live_trading.py` — `_create_adapter()` returns `CCXTRestAdapter` for all exchanges
3. `src/squant/api/deps.py` — Replace `OKXExchange` type alias with generic `ExchangeAdapter`; create an authenticated exchange dependency for endpoints that need credentials
4. `src/squant/api/v1/account.py` — Replace `OKXExchange` dependency with authenticated exchange dependency (balance endpoints)
5. `src/squant/api/v1/orders.py` — Replace `OKXExchange` dependency with authenticated exchange dependency (order service)
6. `src/squant/infra/exchange/__init__.py` — Remove `OKXAdapter` and `BinanceAdapter` from exports
7. `src/squant/services/account.py` — Connection test uses `CCXTRestAdapter`
8. `src/squant/websocket/manager.py` — Remove native OKX WebSocket fallback path
9. `src/squant/config.py` — Remove `use_ccxt_provider` flag (always CCXT)
10. Delete `src/squant/infra/exchange/okx/` directory (now safe — shared types relocated)
11. Delete `src/squant/infra/exchange/binance/` directory
12. Update/remove affected tests

**Exit criteria**: All existing unit and integration tests pass with CCXT adapter. No native adapter code remains.

## Layer 1: Exchange Connectivity

**Goal**: Prove the system can interact with OKX Testnet via `CCXTRestAdapter`.

| Step | Verification | Method |
|------|-------------|--------|
| 1a | Account creation + credential encryption | Create exchange account via API with `testnet=true`, verify encrypted storage and correct decryption |
| 1b | Connection test + balance query | Call test-connection endpoint, confirm real testnet balance returned |
| 1c | Market info loading | Call `load_markets()` via CCXT adapter, confirm testnet trading pairs correct |
| 1d | Place + query + cancel order | Place a limit order far from market price on testnet, query status, then cancel |
| 1e | Fill query | If 1d fills, verify fill record query works |

**Output**: Automated integration tests in `tests/integration/exchange/` (to be created), marked with `@pytest.mark.okx_private`.

**Prerequisites**:
- OKX Testnet API credentials configured in `.env`
- `ENCRYPTION_KEY` set and consistent
- OKX Testnet account funded with test USDT

**Key files involved**:
- `src/squant/infra/exchange/ccxt/rest_adapter.py` — CCXT REST adapter
- `src/squant/infra/exchange/ccxt/provider.py` — CCXT provider with connection management
- `src/squant/api/v1/exchange_accounts.py` — Account CRUD + test endpoint
- `src/squant/services/account.py` — Credential encryption/decryption

## Layer 2: Market Data Flow

**Goal**: Prove WebSocket receives real-time K-line data from mainnet and routes it correctly to Redis and the frontend.

| Step | Verification | Method |
|------|-------------|--------|
| 2a | WebSocket connection | StreamManager connects to mainnet WebSocket, verify handshake + heartbeat |
| 2b | K-line subscription + reception | Subscribe to BTC/USDT 1m, confirm candle data arrives with complete OHLCV fields |
| 2c | Candle close detection | Observe that the `is_closed` heuristic (timestamp change in `CCXTStreamProvider._ohlcv_loop()`) fires **exactly once per minute** for 1m candles, with no missed or duplicate firings. Run for at least 5 consecutive minutes |
| 2d | Redis pub/sub forwarding | Confirm closed candles published to `squant:ws:candles:BTC/USDT:1m` channel |
| 2e | Frontend WebSocket reception | Open frontend K-line chart page, confirm chart updates in real-time with correct prices |
| 2f | Reconnection | Manually disconnect WebSocket, verify auto-reconnect and data flow recovery |

**Key files involved**:
- `src/squant/websocket/manager.py` — StreamManager (mainnet public WebSocket)
- `src/squant/infra/exchange/ccxt/provider.py` — `CCXTStreamProvider._ohlcv_loop()` (candle close detection)
- `src/squant/infra/redis.py` — Redis pub/sub
- `frontend/src/stores/websocket.ts` — Frontend WebSocket client

## Layer 3: Engine Integration

**Goal**: Prove K-line data triggers strategy execution, generates orders, passes risk checks, submits to OKX Testnet, and syncs status back.

| Step | Verification | Method |
|------|-------------|--------|
| 3a | Strategy loading + sandbox | Upload test strategy, confirm RestrictedPython sandbox loads it and calls `on_init()` |
| 3b | K-line triggers on_bar | Start LiveTradingEngine on OKX Testnet, confirm each closed candle triggers `strategy.on_bar(bar)` |
| 3c | Order request generation | Strategy calls `ctx.buy()`, confirm engine receives order request |
| 3d | Risk check rejection | Intentionally exceed position limit, confirm RiskManager rejects and logs |
| 3e | Order submission | Risk-approved order submitted to OKX Testnet via CCXT adapter, confirm exchange_order_id returned |
| 3f | Order status sync — private WebSocket | Confirm order status update arrives via private WebSocket push |
| 3g | Order status sync — REST polling fallback | Disconnect private WebSocket, confirm engine falls back to REST polling and correctly syncs status |

**Test strategy**: Minimal strategy — market-buy a small amount on the first candle, then idle.

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
- `max_price_deviation`: `0.5` (accommodate mainnet/testnet price gap)
- `min_order_value`: `1` (accommodate testnet pricing)
- `max_position_size`: `0.9` (permissive for testing)
- `max_order_size`: `0.5` (permissive for testing)
- Other values: defaults

**Key files involved**:
- `src/squant/engine/live/engine.py` — `process_candle()`, `_sync_pending_orders()`
- `src/squant/engine/risk/manager.py` — `validate_order()`
- `src/squant/engine/sandbox.py` — Strategy sandbox
- `src/squant/services/live_trading.py` — Session lifecycle, `_create_adapter()`
- `src/squant/infra/exchange/ccxt/rest_adapter.py` — CCXT REST adapter
- `src/squant/infra/exchange/ccxt/provider.py` — Private WebSocket for order push

## Layer 4: Full Lifecycle + Acceptance

**Goal**: Verify the complete live trading lifecycle from UI to exchange, with acceptance criteria matching the project milestone.

### Functional Verification

| Step | Verification | Method |
|------|-------------|--------|
| 4a | Full startup via UI | Configure and start live session through frontend, confirm RUNNING status |
| 4b | Real-time price display | Strategy/monitor page shows real-time price updates from mainnet WebSocket |
| 4c | Trading loop | Observe: strategy → order → fill → position update → equity snapshot, complete cycle |
| 4d | Order/position visibility | SessionDetail page shows real-time orders (pending/filled) and open/closed positions |
| 4e | Order history | OrderHistory page shows completed orders; verify records exist and data is correct |
| 4f | Order consistency with exchange | Compare system's order records with OKX Testnet demo account's order history — must match (order ID, side, amount, price, status, fill time) |
| 4g | Normal stop | Stop session; confirm: pending orders cancelled, status STOPPED, state persisted |
| 4h | Graceful crash recovery | Send `SIGTERM` to backend; confirm: state saved → restart → INTERRUPTED → auto-recovery → resumes |
| 4i | Hard crash recovery | Send `SIGKILL` to backend; confirm: restart → INTERRUPTED → recovery attempt (expected: graceful degradation to ERROR if no state saved) |
| 4j | Emergency close | Start session, call emergency-close; confirm: orders cancelled, positions closed, STOPPED |

### Test Strategy

Deterministic bar-counting strategy — buys on bar 3, sells on bar 8, repeats. Guarantees at least one buy+sell cycle within 10 minutes on 1m timeframe.

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

### Acceptance Criteria

All of the following must pass for the milestone to be considered complete:

1. **Real-time data**: Frontend K-line chart and strategy monitor show live mainnet prices with no noticeable delay
2. **Order execution**: Strategy-generated orders are successfully submitted to and filled on OKX Testnet
3. **Position tracking**: System correctly reflects open/closed positions after order fills
4. **Equity curve**: Equity snapshots recorded and displayed on SessionDetail page
5. **Order history consistency**: System's order records match OKX Testnet demo account order history (side, amount, price, status, timestamps)
6. **Session lifecycle**: Start, stop, crash recovery, and emergency close all work as expected
7. **Account switch readiness**: The only difference between testnet and mainnet is the exchange account credentials (`testnet=false` + real API keys). No code or configuration changes needed beyond switching the account.

## Execution Rules

1. **No layer skipping** — complete and fix each layer before moving to the next.
2. **Fix-then-proceed** — issues found at any layer are fixed and re-verified before advancing.
3. **Automated where possible** — Layers 0.5-3 produce reusable integration tests. Layer 4 is manual.
4. **OKX Testnet only** — no mainnet order interaction until all layers pass.
5. **Both sync paths tested** — Layer 3 verifies both private WebSocket and REST polling.
6. **Both crash modes tested** — Layer 4 tests SIGTERM and SIGKILL separately.

## Target Exchange

- **Exchange**: OKX
- **Environment**: Testnet (`OKX_TESTNET=true`, CCXT `sandbox=True`)
- **Adapter**: `CCXTRestAdapter` for REST, `CCXTStreamProvider` for WebSocket (unified)
- **Market data**: Mainnet WebSocket (real prices, by design)
- **Trading pair**: BTC/USDT (spot)
- **Timeframe**: 1m (for quick verification cycles)
