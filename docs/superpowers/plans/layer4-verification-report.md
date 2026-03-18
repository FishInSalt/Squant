# Layer 4 Verification Report

**Date**: 2026-03-18
**Branch**: cc/live-trading-e2e-verification
**Exchange**: OKX Demo Trading (模拟交易)
**Strategy**: BarCountStrategy (buy bar 3, sell bar 8, repeat)
**Trading Pair**: BTC/USDT, 1m timeframe

---

## Verification Results

| Item | Result | Notes |
|------|--------|-------|
| 4a Startup via UI | **PASS** | Session starts and enters RUNNING state |
| 4b Real-time prices | **PASS** | BTC/USDT price updates in real-time on monitor page |
| 4c Trading loop | **PASS** | Buy on bar 3 → fill → hold → sell on bar 8 → fill. Full cycle verified |
| 4d Order/position visibility | **PASS** | SessionDetail shows orders and positions in real-time |
| 4e Order history | **PASS** | Fixed: query now spans all accounts (was querying wrong account) |
| 4f Order consistency | **PASS** | Orders match OKX demo account. Partial status sync fixed. |
| 4g Normal stop | **PASS** | Session state persisted, data survives restart |
| 4h Graceful crash recovery (SIGTERM) | **PASS** | Session auto-recovers to RUNNING after restart |
| 4i Hard crash recovery (SIGKILL) | **PASS** | Session recovered from previously saved state |
| 4j Emergency close | **PASS** | Positions closed, orders cancelled, status STOPPED |

---

## Bugs Found and Fixed During Verification (11 total)

### Found during manual verification (4)

1. **clOrdId format incompatible with OKX** (commit e98e7b4)
   - OKX requires clOrdId max 32 chars, alphanumeric only
   - UUID with hyphens is 36 chars → stripped hyphens before sending

2. **Duplicate order submission after fill** (commit bd4f922)
   - SimulatedOrder not moved from _pending_orders after LiveOrder filled
   - Next bar re-submitted same order → bought 0.02 instead of 0.01
   - Fix: sync terminal status to SimulatedOrder in _cleanup_completed_orders

3. **Order history page empty** (commit e1f83fc)
   - Read-only endpoints queried first active account, not the trading account
   - Fix: list/stats/open endpoints now query across all accounts

4. **Risk config rejection** (user config)
   - Initial equity too low (1000) for 0.01 BTC order at ~$71k
   - Resolution: use initial_equity=2000+ with max_order_size=0.9

### Found during verification, fixed subsequently (7)

5. **Stop with "cancel orders" → 500 error**
   - `risk_triggers.rule_id` NOT NULL violation
   - Fix: Alembic migration to make rule_id nullable (matching model definition)

6. **Partial order status not synced to DB**
   - Market orders split by OKX left DB status at `partial`
   - Fix: Added `status_change` audit event emission in 3 locations (WS, polling, cleanup) + handler in `_persist_orders`

7. **No trade markers on K-line chart**
   - TradingKLineChart had marker support but SessionDetail didn't pass trade data for live sessions
   - Fix: Pass liveFills and liveOpenTrade from audit orders + WebSocket events

8. **No account filter in order list**
   - Fix: Added `account_id` query param to API, replaced "交易所" dropdown with "账户" dropdown in frontend

9. **Date filter params not accepted**
   - Frontend sent `start_date`/`end_date` but backend API ignored them
   - Fix: Added `start_time`/`end_time` params to API, aligned frontend param names

10. **Emergency close doesn't refresh UI**
    - Position data not auto-refreshed after emergency close
    - Fix: Added `loadStatus()` call after emergency close succeeds

11. **Resume overwrites cash with exchange balance**
    - `_reconcile_positions` replaced session cash with exchange-wide USDT balance
    - Fix: Changed to warning-only (no overwrite), consistent with `_sync_balance()` behavior

---

## Acceptance Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Real-time data with no noticeable delay | **MET** |
| 2 | Strategy orders submitted and filled on OKX demo | **MET** |
| 3 | Position tracking correct after fills | **MET** |
| 4 | Equity curve recorded and displayed | **MET** |
| 5 | Order history consistent with OKX demo | **MET** |
| 6 | Session lifecycle (start/stop/recovery/emergency) | **MET** |
| 7 | Account switch readiness (demo → real = credential change only) | **MET** |

---

## Milestone Assessment

**ACHIEVED**: The live trading system works end-to-end with OKX demo trading. Real market data drives strategy execution, orders are placed and filled on the exchange, and the system correctly handles session lifecycle including crash recovery and emergency close. Switching to real trading requires only changing the exchange account credentials. All 7 acceptance criteria are met.
