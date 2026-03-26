# Batch D: Order Error Handling, Fee Tracking, Risk Tooltips

**Goal:** Improve trading reliability and usability — let strategies know why orders fail, track fees by currency with USDT conversion, and add risk config tooltips.

**Scope:** 4 independent changes in one iteration.

---

## 1. Order Rejection Reason

### 1.1 Problem

When `_submit_order` fails (exchange error, insufficient funds), the order is marked REJECTED and moved to `_completed_orders`. The strategy receives it in `on_order_done` but has no way to know *why* — `order.status == REJECTED` is the only signal. The strategy cannot distinguish between a transient exchange error and a permanent business rejection.

### 1.2 Design

**Note:** The DB-layer `Order` model (`models/order.py`) already has a `reject_reason` column, used for audit persistence. This change adds `reject_reason` to the *in-engine* `SimulatedOrder` dataclass (`backtest/types.py`), which is what the strategy receives in `on_order_done`.

Add `reject_reason: str | None = None` to `SimulatedOrder`.

Add `REJECTED = "rejected"` to `backtest/types.py OrderStatus` enum (currently only has PENDING/FILLED/PARTIAL/CANCELLED). The live engine already uses `models/enums.OrderStatus.REJECTED` — this aligns the backtest enum.

`_submit_order` sets `reject_reason` before marking REJECTED:

| Scenario | reject_reason | Example |
|----------|--------------|---------|
| Exchange temporarily unavailable | `"exchange_unavailable"` | OKX 50001 |
| Insufficient funds | `"insufficient_funds"` | Balance too low / position too small |
| Other exchange error | `"exchange_error: {message}"` | Any other ExchangeAPIError |
| Risk manager rejection | `"risk_rejected: {reason}"` | Paper engine `_validate_order_risk` |

**Risk rejection status change:** Paper engine `_validate_order_risk` currently sets `order.status = OrderStatus.CANCELLED`. Change to `REJECTED` for consistency with live engine, and set `order.reject_reason = "risk_rejected: {reason}"`.

**Backtest runner fill rejection:** In `runner.py`, when `_process_fill` raises `ValueError`, set `order.reject_reason = f"fill_rejected: {e}"` on the order object before calling `cancel_order()`. The status remains CANCELLED (this is a fill-time rejection, not a submission rejection).

Strategy usage:
```python
def on_order_done(self, order):
    if order.status == OrderStatus.REJECTED:
        if order.reject_reason == "insufficient_funds":
            # reduce order size next time
        elif order.reject_reason and order.reject_reason.startswith("exchange_"):
            # log and skip, will try next bar
```

**Scope:**
- `backtest/types.py`: add `REJECTED` to `OrderStatus`, add `reject_reason` to `SimulatedOrder`
- `live/engine.py _submit_order`: set `reject_reason` before REJECTED in all error paths
- `paper/engine.py _validate_order_risk`: change status to REJECTED, set `reject_reason`
- `backtest/runner.py`: set `reject_reason` on fill rejection (before cancel_order)
- Trading log `[ERROR] [order]` messages: include reject_reason
- `build_result_snapshot` / `restore_state`: serialize `reject_reason` in completed orders

**Not in scope:** Auto-retry. Strategy decides retry logic.

---

## 2. Mixed Currency Fee Tracking

### 2.1 Problem

`BacktestContext._total_fees` is a single `Decimal` that sums fees across all currencies (BTC + USDT). This produces a meaningless total when trading BTC/USDT with base-currency fees.

### 2.2 Design

Add per-currency fee tracking alongside existing `_total_fees` (kept for backward compatibility).

**Backend:**
- New field: `_fees_by_currency: dict[str, Decimal] = {}`
- In `_process_fill`, accumulate: `_fees_by_currency[currency] += fill.fee`
  - `currency` = `fill.fee_currency` if set, else quote currency derived from `fill.symbol.split("/")[1]`
- `build_result_snapshot()`: add `"fees_by_currency": {currency: str(amount), ...}`
- `restore_state()`: restore `_fees_by_currency`
- `get_state_snapshot()` (for WS bar_update): add `fees_by_currency`
- Status response schemas: add `fees_by_currency: dict[str, str]` field (optional, default empty dict)

**USDT conversion logic:**
- Backend computes `fees_usdt_equivalent` in status response
- Mapping: fee currency → symbol → price:
  - If fee currency == quote currency of the trading pair (e.g., "USDT"), use amount directly
  - If fee currency == base currency (e.g., "BTC"), look up `_last_prices["BTC/USDT"]` (the trading symbol) and multiply
  - **Limitation:** Only supports `*/USDT` pairs. For non-USDT quote pairs (e.g., ETH/BTC), USDT equivalent is not computed — field is omitted or null
- Frontend displays `fees_usdt_equivalent` directly when available, shows "~" prefix when partially converted

**Frontend:**
- Status panel: display fee breakdown by currency (e.g., `BTC: 0.00001 | USDT: 0.694`)
- Below breakdown: show USDT equivalent total (from API response)

---

## 3. Risk Config Tooltips

### 3.1 Problem

Risk config form fields have labels only (e.g., "熔断触发次数"). Users don't understand what each parameter does without documentation.

### 3.2 Design

Add `el-tooltip` to each risk config field label in `LiveTrading.vue` and `PaperTrading.vue`.

| Field | Label | Tooltip |
|-------|-------|---------|
| max_position_size | 最大持仓比例 | 单个交易对的持仓价值不超过账户总资金的该比例 |
| max_order_size | 最大单笔下单比例 | 单笔订单金额不超过账户总资金的该比例 |
| daily_trade_limit | 每日交易限制 | 每日（UTC 0 点重置）最多成交笔数，超过后拒绝新订单 |
| daily_loss_limit | 日最大亏损比例 | 当日已实现亏损达到初始资金的该比例时，拒绝新订单 |
| price_deviation_limit | 价格偏离限制 | 下单价格偏离当前市价超过该比例时拒绝，防止滑点过大 |
| circuit_breaker_threshold | 熔断触发次数 | 连续亏损达到该次数时自动停止交易 30 分钟 |
| min_order_value | 最小下单金额 | 订单金额低于该值时静默忽略，避免产生过小订单 |

Implementation: wrap each `<el-form-item>` label with `<el-tooltip>` using `placement="top"` and an info icon.

---

## 4. Files Changed (Estimated)

| File | Change |
|------|--------|
| `engine/backtest/types.py` | Add `REJECTED` to `OrderStatus`, add `reject_reason` to `SimulatedOrder` |
| `engine/backtest/context.py` | Add `_fees_by_currency`, accumulate in `_process_fill`, serialize/restore, compute USDT equivalent |
| `engine/backtest/runner.py` | Set `reject_reason` on fill rejection |
| `engine/live/engine.py` | Set `reject_reason` in `_submit_order` error paths |
| `engine/paper/engine.py` | Change risk rejection to REJECTED status, set `reject_reason` |
| `schemas/paper_trading.py` | Add `fees_by_currency`, `fees_usdt_equivalent` to status response |
| `schemas/live_trading.py` | Add `fees_by_currency`, `fees_usdt_equivalent` to status response |
| `api/v1/paper_trading.py` | Pass `fees_by_currency` in status construction |
| `api/v1/live_trading.py` | Pass `fees_by_currency` in status construction |
| `services/paper_trading.py` | Include `fees_by_currency` in get_status fallback |
| `services/live_trading.py` | Include `fees_by_currency` in get_status fallback |
| `frontend/.../LiveTrading.vue` | Add risk config tooltips |
| `frontend/.../PaperTrading.vue` | Add risk config tooltips |
| `frontend/.../SessionDetail.vue` | Display fee breakdown + USDT equivalent |
| `frontend/src/types/trading.ts` | Add `fees_by_currency`, `fees_usdt_equivalent` to status types |
| `frontend/src/types/generated/*` | Regenerated by `./scripts/generate-api-types.sh` |
