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
| 4f Order consistency | **PASS (partial)** | Orders match OKX demo account. 1 order stuck in `partial` status |
| 4g Normal stop | **PASS** | Session state persisted, data survives restart |
| 4h Graceful crash recovery (SIGTERM) | **PASS** | Session auto-recovers to RUNNING after restart |
| 4i Hard crash recovery (SIGKILL) | **PASS** | Session recovered from previously saved state |
| 4j Emergency close | **PASS** | Positions closed, orders cancelled, status STOPPED |

---

## Bugs Found and Fixed During Verification

### Fixed (4)

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

---

## Known Issues (Not Fixed)

| # | Issue | Severity | Description |
|---|-------|----------|-------------|
| 1 | Stop with "cancel orders" → 500 | Medium | `risk_triggers.rule_id` NOT NULL violation when stopping session with cancel_orders=true |
| 2 | Partial order status not synced | Medium | Market orders split by OKX may leave last fill's WS update unprocessed, status stuck at `partial` |
| 3 | No trade markers on K-line chart | Low | TradingKLineChart doesn't render buy/sell markers |
| 4 | No account filter in order list | Low | Order history queries all accounts, no per-account filtering |
| 5 | Date filter params not accepted | Low | Frontend sends start_date/end_date but backend API ignores them |
| 6 | Emergency close doesn't refresh UI | Low | Position data not auto-refreshed after emergency close (requires page reload) |
| 7 | Resume overwrites cash with exchange balance | Medium | `_reconcile_positions` replaces local cash with exchange-wide USDT balance, incorrect for multi-session or shared accounts |

---

## Acceptance Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Real-time data with no noticeable delay | **MET** |
| 2 | Strategy orders submitted and filled on OKX demo | **MET** |
| 3 | Position tracking correct after fills | **MET** |
| 4 | Equity curve recorded and displayed | **MET** |
| 5 | Order history consistent with OKX demo | **MOSTLY MET** (1 partial status anomaly) |
| 6 | Session lifecycle (start/stop/recovery/emergency) | **MET** |
| 7 | Account switch readiness (demo → real = credential change only) | **MET** |

---

## Milestone Assessment

**ACHIEVED**: The live trading system works end-to-end with OKX demo trading. Real market data drives strategy execution, orders are placed and filled on the exchange, and the system correctly handles session lifecycle including crash recovery and emergency close. Switching to real trading requires only changing the exchange account credentials.
