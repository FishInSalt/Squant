# Layer 4: Full Lifecycle Verification Checklist

## Prerequisites
- [ ] Backend running (`./scripts/dev.sh backend`)
- [ ] Frontend running (`cd frontend && pnpm dev`)
- [ ] OKX demo trading account configured in the system (via UI or API)
- [ ] BarCountStrategy uploaded as a strategy (from `tests/templates/bar_count.py`)

## 4a: Full Startup via UI
- [ ] Navigate to Live Trading page
- [ ] Select BarCountStrategy
- [ ] Configure: BTC/USDT, 1m timeframe, OKX demo account
- [ ] Set risk config: min_order_value=1, max_position_size=0.9, max_order_size=0.5
- [ ] Click Start -> Status becomes RUNNING
- [ ] Note run_id: _______________

## 4b: Real-time Price Display
- [ ] Monitor page shows real-time BTC/USDT price updates
- [ ] Price matches OKX website (within 1 second)

## 4c: Trading Loop
- [ ] Wait for bar 3 (~3 minutes) -> BUY order appears
- [ ] Order fills -> Position shows 0.01 BTC
- [ ] Equity snapshot updates
- [ ] Wait for bar 8 (~8 minutes) -> SELL order appears
- [ ] Order fills -> Position closes
- [ ] Realized PnL visible

## 4d: Order/Position Visibility
- [ ] SessionDetail page shows orders (pending -> filled)
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
- [ ] Verify: session resumes, strategy continues from correct state

## 4i: Hard Crash Recovery
- [ ] Start a new session
- [ ] Send SIGKILL: `kill -9 <pid>`
- [ ] Restart backend
- [ ] Check: session marked INTERRUPTED
- [ ] Expected: recovery may fail (no state saved) -> status becomes ERROR
- [ ] This is acceptable behavior - verify no crash/hang

## 4j: Emergency Close
- [ ] Start a new session, wait for a position to open
- [ ] Call emergency-close via API or UI
- [ ] All orders cancelled
- [ ] Position closed (sell order placed and filled)
- [ ] Status becomes STOPPED

## Acceptance Criteria
- [ ] 1. Real-time data: Frontend shows live prices with no noticeable delay
- [ ] 2. Order execution: Strategy orders submitted to and filled on OKX demo
- [ ] 3. Position tracking: Open/closed positions correctly reflected
- [ ] 4. Equity curve: Snapshots recorded and displayed
- [ ] 5. Order history consistency: System records match OKX demo account
- [ ] 6. Session lifecycle: Start, stop, crash recovery, emergency close all work
- [ ] 7. Account switch readiness: Only credential change needed for real trading

## Results
- Issues found: _______________
- All checks passed: [ ] Yes / [ ] No
- Date: _______________
