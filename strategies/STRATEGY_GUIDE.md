# Squant 策略开发指南

本文档详细介绍如何编写交易策略，涵盖策略结构、可用接口、订单类型、
成交机制、风控规则等全部内容。适用于回测、模拟交易和实盘交易三种模式。

---

## 目录

1. [策略基本结构](#1-策略基本结构)
2. [生命周期与执行顺序](#2-生命周期与执行顺序)
3. [策略参数](#3-策略参数)
4. [K线数据 (Bar)](#4-k线数据-bar)
5. [历史数据查询](#5-历史数据查询)
6. [内置技术指标 (ta)](#6-内置技术指标-ta)
7. [账户状态查询](#7-账户状态查询)
8. [持仓管理](#8-持仓管理)
9. [下单接口](#9-下单接口)
10. [订单类型详解](#10-订单类型详解)
11. [订单生命周期](#11-订单生命周期)
12. [成交价格机制](#12-成交价格机制)
13. [风险管理](#13-风险管理)
14. [沙箱环境与限制](#14-沙箱环境与限制)
15. [常见策略模式](#15-常见策略模式)
16. [注意事项与陷阱](#16-注意事项与陷阱)
17. [完整策略模板](#17-完整策略模板)
18. [绩效指标](#18-绩效指标)

---

## 1. 策略基本结构

每个策略是一个继承自 `Strategy` 的 Python 类，必须实现 `on_bar`，可选实现其他生命周期方法：

```python
class MyStrategy(Strategy):
    def on_init(self):
        """策略初始化 — 系统启动时调用一次。

        用途：
        - 读取策略参数
        - 初始化指标计算所需的状态变量
        - 设置交易信号的阈值

        此时尚无K线数据，不能下单。
        """
        pass

    def on_bar(self, bar):
        """每根K线回调 — 每根收盘K线调用一次。

        用途：
        - 获取历史数据，计算技术指标
        - 判断交易信号
        - 下单/平仓
        - 记录日志

        这是策略的核心逻辑所在。
        """
        pass

    def on_fill(self, fill):
        """成交回调 — 订单成交时调用（在 on_bar 之前）。

        用途：
        - 成交后立即挂止损单（如 buy fill 后挂 stop-loss）
        - 记录成交信息
        - 更新策略内部状态

        fill 对象属性：order_id, symbol, side, price, amount, fee, timestamp
        注意：on_fill 中下的订单在下一根K线才成交。
        """
        pass

    def on_order_done(self, order):
        """订单完成回调 — 订单到达终态时调用（FILLED 或 CANCELLED）。

        用途：
        - OCO 管理：一侧成交/取消后取消另一侧
        - 记录订单完成状态
        - 根据成交结果调整策略状态

        order 对象属性：id, symbol, side, type, amount, price, stop_price,
                       status, filled_amount, filled_price, filled_at
        """
        pass

    def on_stop(self):
        """策略停止 — 系统关闭时调用一次。

        用途：
        - 记录最终状态
        - 输出统计信息

        注意：不会自动平仓，持仓以最后收盘价计算权益。
        """
        pass
```

**最小可运行策略**（只需实现 `on_bar`）：

```python
class MinimalStrategy(Strategy):
    def on_bar(self, bar):
        if not self.ctx.has_position(bar.symbol):
            self.ctx.buy(bar.symbol, Decimal("0.01"))
```

---

## 2. 生命周期与执行顺序

理解引擎在每根K线上的执行顺序，对编写正确的策略至关重要。

### 回测模式（每根K线）

```
1. 撮合挂单 → 生成成交记录（使用当前K线的 open 价格）
2. 处理成交 → 更新持仓、资金、交易记录
3. 移除已完成订单
4. 过期检查 → 倒计时 bars_remaining，到期则取消
5. 设置当前K线 + 加入历史缓冲区
6. 记录权益快照（在策略回调之前，捕获决策前的状态）
6.5. 回调通知：
     - 调用 on_fill(fill) — 逐个通知本轮所有成交
     - 调用 on_order_done(order) — 逐个通知已完成/已取消订单
7. 调用 strategy.on_bar(bar)（带 CPU/内存限制）
```

**关键含义**：`on_bar()` 中下的市价单，在**下一根K线**才成交（使用下一根的 open 价格），
这是为了防止未来数据偷看（look-ahead bias）。

**回调顺序**：`on_fill()` → `on_order_done()` → `on_bar()`，同一根K线内按此顺序执行。
回调中下的订单同样在下一根K线成交。

### 模拟交易模式（每次K线更新）

```
每次K线更新（含未收盘K线）：
  1. 成交市价单 → 使用实时 bid/ask 或 close±slippage
  2. 匹配挂单 → STOP、STOP_LIMIT、LIMIT
  3. 移除已完成订单

仅在K线收盘时：
  4. 设置当前K线 + 加入历史缓冲区
  5. 过期检查
  6. 记录权益快照
  6.5. 回调通知：on_fill → on_order_done（累积自上一次收盘以来的所有成交/完成）
  7. 调用 strategy.on_bar(bar)
  8. 持久化状态（用于崩溃恢复）
```

**与回测的区别**：模拟交易使用实时行情的 bid/ask 价差来成交，更贴近实盘。

---

## 3. 策略参数

通过 `self.ctx.params` 获取在创建会话时传入的参数字典。

```python
def on_init(self):
    # 使用 .get() 并提供默认值，使策略可配置
    self.fast_period = self.ctx.params.get("fast_period", 5)
    self.slow_period = self.ctx.params.get("slow_period", 20)
    self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))

    # 参数类型注意：从 API 传入的数字可能是 int/float/str
    # 始终用 Decimal(str(...)) 转换金额和价格
    self.stop_loss_pct = Decimal(str(self.ctx.params.get("stop_loss_pct", "0.02")))
```

---

## 4. K线数据 (Bar)

`on_bar(bar)` 的参数是一个不可变的 `Bar` 对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `bar.time` | `datetime` | K线开盘时间 (UTC) |
| `bar.symbol` | `str` | 交易对（如 `"BTC/USDT"`）|
| `bar.open` | `Decimal` | 开盘价 |
| `bar.high` | `Decimal` | 最高价 |
| `bar.low` | `Decimal` | 最低价 |
| `bar.close` | `Decimal` | 收盘价 |
| `bar.volume` | `Decimal` | 成交量（基础货币计） |

```python
def on_bar(self, bar):
    # 直接使用K线数据
    spread = bar.high - bar.low
    body = abs(bar.close - bar.open)
    is_bullish = bar.close > bar.open

    self.ctx.log(f"[{bar.time}] {bar.symbol} 收盘: {bar.close}")
```

---

## 5. 历史数据查询

所有历史数据方法返回列表，**按时间从旧到新排列**。
如果请求的数量超过可用历史，则返回全部可用数据。

历史缓冲区最多保留 **1000 根K线**（默认 `max_bar_history=1000`）。

```python
# 获取最近 N 根K线的收盘价
closes = self.ctx.get_closes(20)    # list[Decimal]，最旧在前

# 获取最近 N 根完整K线
bars = self.ctx.get_bars(10)        # list[Bar]

# 获取最近 N 根K线的 OHLCV 分量
opens   = self.ctx.get_opens(10)    # list[Decimal]
highs   = self.ctx.get_highs(10)    # list[Decimal]
lows    = self.ctx.get_lows(10)     # list[Decimal]
volumes = self.ctx.get_volumes(10)  # list[Decimal]
```

**等待历史积累**：在指标计算前务必检查数据是否充足。

```python
def on_bar(self, bar):
    closes = self.ctx.get_closes(20)
    if len(closes) < 20:
        return  # 数据不足，跳过本根K线

    ma20 = sum(closes) / 20
    # ...
```

---

## 6. 内置技术指标 (ta)

系统内置了 `ta` 模块，提供常用技术指标的纯函数实现。所有函数接收 `list[Decimal]`
参数（与 `ctx.get_closes()` 等返回值兼容），返回 `Decimal` 或 `None`（数据不足时）。

`ta` 模块在沙箱中自动注入，无需导入。

### 指标一览

| 函数 | 签名 | 返回值 | 说明 |
|------|------|--------|------|
| `ta.sma` | `(data, period)` | `Decimal \| None` | 简单移动平均 |
| `ta.ema` | `(data, period)` | `Decimal \| None` | 指数移动平均 |
| `ta.rsi` | `(data, period=14)` | `Decimal \| None` | 相对强弱指数 (0-100) |
| `ta.macd` | `(data, fast=12, slow=26, signal=9)` | `tuple \| None` | MACD (macd_line, signal_line, histogram) |
| `ta.bollinger_bands` | `(data, period=20, num_std=2)` | `tuple \| None` | 布林带 (upper, middle, lower) |
| `ta.atr` | `(highs, lows, closes, period=14)` | `Decimal \| None` | 平均真实波幅 |
| `ta.stdev` | `(data, period)` | `Decimal \| None` | 总体标准差 |
| `ta.highest` | `(data, period)` | `Decimal \| None` | 区间最高值 |
| `ta.lowest` | `(data, period)` | `Decimal \| None` | 区间最低值 |
| `ta.crossover` | `(fast, slow)` | `bool` | 快线上穿慢线 |
| `ta.crossunder` | `(fast, slow)` | `bool` | 快线下穿慢线 |

### 使用示例

```python
class TADemoStrategy(Strategy):
    def on_bar(self, bar):
        closes = self.ctx.get_closes(50)
        if len(closes) < 26:
            return

        # 移动平均
        sma20 = ta.sma(closes, 20)
        ema10 = ta.ema(closes, 10)

        # RSI
        rsi_val = ta.rsi(closes, 14)
        if rsi_val is not None and rsi_val < Decimal("30"):
            self.ctx.log("RSI 超卖")

        # MACD
        result = ta.macd(closes)
        if result is not None:
            macd_line, signal_line, histogram = result
            if histogram > 0:
                self.ctx.log("MACD 多头")

        # 布林带
        bb = ta.bollinger_bands(closes, 20)
        if bb is not None:
            upper, middle, lower = bb
            if bar.close < lower:
                self.ctx.log("价格触及布林带下轨")

        # ATR（需要高低价数据）
        highs = self.ctx.get_highs(20)
        lows = self.ctx.get_lows(20)
        atr_val = ta.atr(highs, lows, closes[-20:], 14)

        # 区间极值
        high_20 = ta.highest(closes, 20)
        low_20 = ta.lowest(closes, 20)

        # 均线交叉
        fast_ma = [ta.sma(closes[:i], 5) for i in range(len(closes)-1, len(closes)+1)]
        slow_ma = [ta.sma(closes[:i], 20) for i in range(len(closes)-1, len(closes)+1)]
        if None not in fast_ma and None not in slow_ma:
            if ta.crossover(fast_ma, slow_ma):
                self.ctx.buy(bar.symbol, Decimal("0.01"))
            elif ta.crossunder(fast_ma, slow_ma):
                self.ctx.close_position(bar.symbol)
```

### 注意事项

- **数据不足时返回 None**：所有指标在数据不足时返回 `None`，务必检查。
- **数据顺序**：所有数据列表必须按时间从旧到新排列（与 `ctx.get_closes()` 一致）。
- **ATR 需要三个序列**：`ta.atr()` 需要分别传入 highs、lows、closes。
- **MACD 需要较多数据**：默认参数 `(12, 26, 9)` 至少需要 34 根K线。
- **crossover/crossunder 需要序列**：传入至少 2 个值的列表，用于比较相邻两期。

---

## 7. 账户状态查询

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `self.ctx.cash` | `Decimal` | 当前可用资金 |
| `self.ctx.equity` | `Decimal` | 总权益 = 资金 + 持仓市值 |
| `self.ctx.initial_capital` | `Decimal` | 初始资金 |
| `self.ctx.commission_rate` | `Decimal` | 手续费率 |
| `self.ctx.slippage` | `Decimal` | 滑点率 |
| `self.ctx.total_fees` | `Decimal` | 累计手续费 |
| `self.ctx.unrealized_pnl` | `Decimal` | 浮动盈亏（所有持仓按当前价计算）|
| `self.ctx.realized_pnl` | `Decimal` | 已实现盈亏（所有已平仓交易的 PnL 总和）|
| `self.ctx.return_pct` | `Decimal` | 总收益率（如 0.05 = 5%）|
| `self.ctx.max_drawdown` | `Decimal` | 最大回撤（如 0.10 = 10%）|
| `self.ctx.pending_orders` | `list` | 当前挂单列表 |
| `self.ctx.completed_orders` | `list` | 已完成订单列表 |
| `self.ctx.fills` | `list` | 全部成交记录 |
| `self.ctx.trades` | `list` | 已平仓交易记录 |
| `self.ctx.equity_curve` | `list` | 权益曲线快照 |

```python
def on_bar(self, bar):
    # 基于权益比例的仓位管理
    risk_per_trade = self.ctx.equity * Decimal("0.02")  # 每笔风险 2%

    # 检查是否有足够资金
    if self.ctx.cash < Decimal("100"):
        self.ctx.log("资金不足，暂停开仓")
        return

    # 直接使用内置指标（无需手算）
    self.ctx.log(f"收益率: {self.ctx.return_pct:.2%}")
    self.ctx.log(f"浮动盈亏: {self.ctx.unrealized_pnl}")
    self.ctx.log(f"最大回撤: {self.ctx.max_drawdown:.2%}")

    # 回撤超限暂停开仓
    if self.ctx.max_drawdown > Decimal("0.15"):
        self.ctx.log("回撤超过15%，暂停开仓")
        return
```

---

## 8. 持仓管理

本系统仅支持**现货交易**，不支持做空。

```python
# 检查是否持仓
if self.ctx.has_position(bar.symbol):
    # 获取持仓详情
    pos = self.ctx.get_position(bar.symbol)
    # pos.symbol       — 交易对
    # pos.amount        — 持仓数量
    # pos.avg_entry_price — 成交均价（加仓会自动计算加权均价）

    # 计算浮动盈亏
    unrealized_pnl = (bar.close - pos.avg_entry_price) * pos.amount
    pnl_pct = (bar.close - pos.avg_entry_price) / pos.avg_entry_price

    self.ctx.log(f"持仓 {pos.amount} @ {pos.avg_entry_price}, 浮盈: {unrealized_pnl:.2f}")

# 获取所有持仓（返回副本，安全遍历）
all_positions = self.ctx.positions  # dict[str, Position]
```

**加仓时的均价计算**：系统自动按成交量加权平均。

```
已有 0.5 BTC @ 50000
加仓 0.3 BTC @ 52000
新均价 = (0.5 * 50000 + 0.3 * 52000) / 0.8 = 50750
```

---

## 9. 下单接口

### 9.1 买入 — `self.ctx.buy()`

```python
order_id = self.ctx.buy(
    symbol,                        # str: 交易对
    amount,                        # Decimal: 买入数量（基础货币）
    price=None,                    # Decimal|None: 限价（设置则为限价单）
    stop_price=None,               # Decimal|None: 止损触发价
    valid_for_bars=None,           # int|None: 有效K线数（None=GTC永久有效）
)
# 返回: str (订单ID) 或 None (低于最小订单金额被拒绝)
# 抛出: ValueError — 数量 ≤ 0 或资金不足
```

### 9.2 卖出 — `self.ctx.sell()`

```python
order_id = self.ctx.sell(
    symbol,                        # str: 交易对
    amount,                        # Decimal: 卖出数量
    price=None,                    # Decimal|None: 限价
    stop_price=None,               # Decimal|None: 止损触发价
    valid_for_bars=None,           # int|None: 有效K线数
)
# 返回: str (订单ID) 或 None
# 抛出: ValueError — 数量 ≤ 0 或超出可卖持仓
```

### 9.3 取消订单 — `self.ctx.cancel_order()`

```python
success = self.ctx.cancel_order(order_id)  # bool: True=取消成功
```

### 9.4 查询订单 — `self.ctx.get_order()`

```python
order = self.ctx.get_order(order_id)  # SimulatedOrder | None
if order:
    # order.id            — 订单 UUID
    # order.status        — "pending" / "filled" / "partial" / "cancelled"
    # order.filled        — 已成交数量
    # order.remaining     — 未成交数量 (= amount - filled)
    # order.avg_fill_price — 成交均价
    # order.bars_remaining — 剩余有效K线数 (None=GTC)
    # order.is_complete   — 是否已结束 (filled 或 cancelled)
```

### 9.5 一键平仓 — `self.ctx.close_position()`

```python
order_id = self.ctx.close_position(symbol)
# 市价卖出该标的的全部持仓
# 自动取消该标的所有挂单卖出订单后再下单
# 返回: str (订单ID) 或 None (无持仓)
```

等效于：
```python
pos = self.ctx.get_position(bar.symbol)
if pos:
    # 先取消该标的所有挂单卖出订单（释放可卖数量）
    for order in self.ctx.pending_orders:
        if order.symbol == bar.symbol and order.side == OrderSide.SELL:
            self.ctx.cancel_order(order.id)
    # 再市价卖出全部持仓
    self.ctx.sell(bar.symbol, pos.amount)
```

### 9.6 目标持仓 — `self.ctx.target_position()`

```python
order_id = self.ctx.target_position(symbol, target_amount)
# 自动计算当前持仓与目标的差额，买入或卖出
# target_amount >= 0（不支持做空）
# 自动取消同方向的挂单后再调仓
# 返回: str (订单ID) 或 None (已达目标/金额过小)
```

示例：
```python
# 调仓至 0.5 BTC（多退少补）
self.ctx.target_position(bar.symbol, Decimal("0.5"))

# 全部平仓
self.ctx.target_position(bar.symbol, Decimal("0"))
```

### 9.7 目标比例 — `self.ctx.target_percent()`

```python
order_id = self.ctx.target_percent(symbol, percent)
# percent: 0~1 的 Decimal，表示目标持仓占总权益的比例
# 根据当前权益和收盘价自动计算目标数量，委托给 target_position
# 返回: str (订单ID) 或 None
```

示例：
```python
# 50% 权益配置到 BTC
self.ctx.target_percent(bar.symbol, Decimal("0.5"))

# 清仓
self.ctx.target_percent(bar.symbol, Decimal("0"))
```

---

## 10. 订单类型详解

通过 `price` 和 `stop_price` 参数组合自动推断订单类型：

| `price` | `stop_price` | 订单类型 | 说明 |
|---------|-------------|----------|------|
| `None` | `None` | **市价单** (MARKET) | 立即按市价成交 |
| 设定 | `None` | **限价单** (LIMIT) | 到达指定价格时成交 |
| `None` | 设定 | **止损单** (STOP) | 触发后按市价成交 |
| 设定 | 设定 | **止损限价单** (STOP_LIMIT) | 触发后变为限价单 |

### 10.1 市价单 (MARKET)

最简单的订单类型，在下一根K线（回测）或当前 tick（模拟）成交。

```python
# 市价买入 0.1 BTC
self.ctx.buy(bar.symbol, Decimal("0.1"))

# 市价全部卖出
pos = self.ctx.get_position(bar.symbol)
if pos:
    self.ctx.sell(bar.symbol, pos.amount)
```

### 10.2 限价单 (LIMIT)

设定目标价格，价格到达时成交。可能享受跳空改善价。

```python
# 限价买入：价格跌到 49000 时买入
self.ctx.buy(bar.symbol, Decimal("0.1"), price=Decimal("49000"))

# 限价卖出：价格涨到 55000 时卖出（止盈）
self.ctx.sell(bar.symbol, Decimal("0.1"), price=Decimal("55000"))

# 限价单 + 有效期：10 根K线内有效，超时自动取消
self.ctx.buy(bar.symbol, Decimal("0.1"), price=Decimal("49000"), valid_for_bars=10)
```

**触发条件**：
- 买入限价单：当 `bar.low ≤ limit_price` 时触发
- 卖出限价单：当 `bar.high ≥ limit_price` 时触发

**成交价格**：
- 正常情况：以限价成交
- 跳空改善：如果开盘价更优，以开盘价成交
  - 买入：`fill_price = min(limit_price, bar.open)`
  - 卖出：`fill_price = max(limit_price, bar.open)`

### 10.3 止损单 (STOP)

当价格突破止损价时，触发市价成交。**常用于保护利润或限制亏损。**

```python
# 止损卖出：价格跌破 48000 时市价卖出
pos = self.ctx.get_position(bar.symbol)
if pos:
    self.ctx.sell(bar.symbol, pos.amount, stop_price=Decimal("48000"))

# 突破买入：价格突破 52000 时追涨买入
self.ctx.buy(bar.symbol, Decimal("0.1"), stop_price=Decimal("52000"))
```

**触发条件**：
- 买入止损单：当 `bar.high ≥ stop_price` 时触发
- 卖出止损单：当 `bar.low ≤ stop_price` 时触发

**成交价格**（触发后按市价执行）：
- 买入：`max(stop_price, bar.open) × (1 + slippage)`
- 卖出：`min(stop_price, bar.open) × (1 - slippage)`
- 如果开盘即跳空过止损价，以跳空价成交（更差）

### 10.4 止损限价单 (STOP_LIMIT)

两阶段订单：先触发止损，然后变为限价单等待成交。
**防止在极端行情中以过差的价格成交。**

```python
# 止损限价卖出：
#   当价格跌至 48000 时触发，然后以不低于 47500 的价格限价卖出
pos = self.ctx.get_position(bar.symbol)
if pos:
    self.ctx.sell(
        bar.symbol,
        pos.amount,
        stop_price=Decimal("48000"),    # 触发价
        price=Decimal("47500"),          # 限价（最差可接受价格）
    )

# 止损限价买入：
#   当价格突破 52000 时触发，然后以不高于 52500 的价格限价买入
self.ctx.buy(
    bar.symbol,
    Decimal("0.1"),
    stop_price=Decimal("52000"),
    price=Decimal("52500"),
)
```

**两阶段执行**：
1. **触发阶段**：价格达到 `stop_price` 时，订单被激活 (`triggered=True`)
2. **限价阶段**：激活后变为普通限价单，等待 `price` 被触及

**风险**：如果触发后价格快速远离限价，订单可能不成交（挂单等待）。

---

## 11. 订单生命周期

```
              ┌── 成交 → FILLED
              │
PENDING ──────┼── 部分成交 → PARTIAL ── 后续K线继续成交 → FILLED
              │                    └── 过期/取消 → CANCELLED
              ├── 过期 → CANCELLED
              └── 手动取消 → CANCELLED
```

### 订单状态

| 状态 | 说明 |
|------|------|
| `PENDING` | 等待成交（初始状态）|
| `PARTIAL` | 部分成交（大单被成交量限制截断）|
| `FILLED` | 完全成交 |
| `CANCELLED` | 已取消（手动取消、过期、或风控拒绝）|

### 有效期 (valid_for_bars)

- `None`（默认）：GTC（Good Till Cancel），永久有效
- `N`：N 根收盘K线后自动取消
- **仅对非市价单生效**，市价单忽略此参数

```python
# 5 根K线内有效的限价买入
order_id = self.ctx.buy(bar.symbol, Decimal("0.1"),
                        price=Decimal("49000"),
                        valid_for_bars=5)
```

### 部分成交

当启用成交量参与限制（`max_volume_participation`）时，
大单可能无法在一根K线内全部成交，剩余部分保持 `PARTIAL` 状态，
在后续K线中继续尝试成交。

### 事件回调 (on_fill / on_order_done)

策略可通过覆写 `on_fill` 和 `on_order_done` 方法来响应成交和订单完成事件。
这些回调在每根K线的 `on_bar()` **之前**被调用，调用顺序为：
`on_fill()` → `on_order_done()` → `on_bar()`。

**on_fill(fill)** — 每次成交触发一次：

```python
def on_fill(self, fill):
    """fill 属性：
    - fill.order_id: 关联的订单 ID
    - fill.symbol: 交易标的
    - fill.side: OrderSide.BUY 或 OrderSide.SELL
    - fill.price: 实际成交价格
    - fill.amount: 成交数量
    - fill.fee: 手续费
    - fill.timestamp: 成交时间
    """
    # 示例：买入成交后立即挂止损单
    if fill.side == OrderSide.BUY:
        stop_price = fill.price * Decimal("0.95")  # 5% 止损
        self.ctx.sell(fill.symbol, fill.amount, stop_price=stop_price)
```

**on_order_done(order)** — 订单到达终态（FILLED 或 CANCELLED）时触发：

```python
def on_order_done(self, order):
    """order 属性：
    - order.id: 订单 ID
    - order.status: OrderStatus.FILLED 或 OrderStatus.CANCELLED
    - order.symbol, order.side, order.type
    - order.filled_amount, order.filled_price, order.filled_at
    """
    # 示例：OCO 管理 — 一侧完成后取消另一侧
    if order.status == OrderStatus.FILLED and order.id == self.take_profit_id:
        self.ctx.cancel_order(self.stop_loss_id)
    elif order.status == OrderStatus.FILLED and order.id == self.stop_loss_id:
        self.ctx.cancel_order(self.take_profit_id)
```

**注意事项**：
- 回调中下的订单同样在**下一根K线**成交
- 回调中抛出的异常会被捕获并记录，**不会**导致策略崩溃
- 沙箱中可使用 `Fill` 和 `OrderStatus` 类型进行类型检查
- RestrictedPython 限制：不能使用 `+=` 等增量赋值，需写成 `self.x = self.x + 1`

---

## 12. 成交价格机制

### 回测模式

| 订单类型 | 成交价格 |
|---------|---------|
| 市价买入 | `bar.open × (1 + slippage)`, 限制在 `[low, high]` |
| 市价卖出 | `bar.open × (1 - slippage)`, 限制在 `[low, high]` |
| 限价买入 | `min(limit_price, bar.open)` |
| 限价卖出 | `max(limit_price, bar.open)` |
| 止损买入 | `max(stop_price, bar.open) × (1 + slippage)`, 限制在 `[low, high]` |
| 止损卖出 | `min(stop_price, bar.open) × (1 - slippage)`, 限制在 `[low, high]` |
| 止损限价 | 触发当根：`limit_price`；后续根：按限价单逻辑 |

### 模拟交易模式

模拟交易使用 **实时 Ticker 数据** 提供更真实的成交价格：

| 订单类型 | 成交价格 |
|---------|---------|
| 市价买入 | 有 ask → `ask`；无 ask → `close × (1 + slippage)` |
| 市价卖出 | 有 bid → `bid`；无 bid → `close × (1 - slippage)` |
| 限价单 | 同回测逻辑，支持跳空改善价 |
| 止损单 | 触发后按市价执行（使用 bid/ask） |
| 止损限价 | 触发后按限价逻辑执行 |

### 手续费计算

每笔成交的手续费 = `成交价 × 成交量 × commission_rate`

```
买入 0.1 BTC @ 50000, commission_rate = 0.001
手续费 = 50000 × 0.1 × 0.001 = 5 USDT
实际花费 = 50000 × 0.1 + 5 = 5005 USDT
```

### 最小订单金额

订单名义价值（`amount × price`）低于 `min_order_value`（默认 5 USDT）时，
`buy()` / `sell()` 静默返回 `None`，不会抛出异常。

```python
order_id = self.ctx.buy(bar.symbol, Decimal("0.0001"))
if order_id is None:
    self.ctx.log("订单金额过小，被拒绝")
```

---

## 13. 风险管理

风险管理在模拟交易和实盘交易中可选启用。
当配置了风控参数时，每笔成交前都会进行风控检查，违规订单会被取消。

### 风控规则一览

| 规则 | 默认值 | 说明 |
|------|--------|------|
| **最大持仓比例** | 10% 权益 | 单个标的持仓市值不超过权益的 10% |
| **最大持仓金额** | 无限制 | 持仓市值的绝对上限 |
| **最大单笔订单** | 5% 权益 | 单笔订单金额不超过权益的 5% |
| **最小订单金额** | 10 USDT | 低于此值的订单被拒绝 |
| **日内交易次数** | 100 次/天 | 超出后新订单被拒绝 |
| **日内亏损限制** | 5% 权益 | 当日亏损（含浮亏）超限后停止交易 |
| **总亏损限制** | 20% 初始资金 | 累计亏损超限后**引擎自动停止** |
| **价格偏差限制** | 2% | 限价单价格偏离当前价超过 2% 被拒绝 |
| **熔断机制** | 连续 5 笔亏损 | 触发后冷却 30 分钟，期间拒绝所有订单 |

### 风控检查顺序

```
1. 熔断检查 → 冷却期内拒绝所有订单
2. 日内交易次数 → 超出限制拒绝
3. 日内亏损 → 含浮亏超限拒绝
4. 总亏损 → 超限自动停止引擎
5. 单笔订单大小 → 超限拒绝
6. 持仓大小 → 超限拒绝
7. 价格偏差 → 限价偏离过大拒绝
```

**总亏损触发时**：引擎自动停止，不仅仅是拒绝订单。

---

## 14. 沙箱环境与限制

策略在安全沙箱中运行，以下内容**自动注入**，无需导入：

| 名称 | 说明 |
|------|------|
| `Strategy` | 策略基类 |
| `Bar` | K线数据类型 |
| `Position` | 持仓信息类型 |
| `Fill` | 成交记录类型（用于 `on_fill` 回调）|
| `OrderSide` | `OrderSide.BUY`, `OrderSide.SELL` |
| `OrderType` | `OrderType.MARKET`, `LIMIT`, `STOP`, `STOP_LIMIT` |
| `OrderStatus` | `OrderStatus.PENDING`, `FILLED`, `CANCELLED`（用于 `on_order_done`）|
| `ta` | 内置技术指标模块（详见[第 6 节](#6-内置技术指标-ta)）|
| `Decimal` | 精确小数 |
| `math` | 数学函数模块（部分函数） |
| `statistics` | 统计函数模块（mean, median, stdev 等） |

### 可用内置函数

`abs`, `round`, `pow`, `divmod`, `int`, `float`, `bool`, `str`, `len`,
`list`, `dict`, `set`, `tuple`, `range`, `enumerate`, `zip`, `reversed`,
`sorted`, `map`, `filter`, `all`, `any`, `sum`, `min`, `max`,
`isinstance`, `hasattr`, `format`, `repr`, `print` 等。

### 可用 math 函数

三角函数: `sin`, `cos`, `tan`, `atan2`, `sqrt`
指数/对数: `exp`, `log`, `log2`, `log10`, `pow`
取整: `ceil`, `floor`, `trunc`, `fabs`
常数: `pi`, `e`, `inf`, `nan`

**不可用**（防止 DoS）: `factorial`, `comb`, `perm`, `gcd`

### 可用 statistics 函数

集中趋势: `mean`, `fmean`, `harmonic_mean`, `median`, `median_low`, `median_high`, `mode`, `multimode`
离散度: `stdev`, `variance`, `pstdev`, `pvariance`, `quantiles`
相关性: `correlation`, `covariance`, `linear_regression`

```python
# 在策略中使用 statistics 模块
closes = self.ctx.get_closes(20)
if len(closes) >= 20:
    avg = statistics.mean(closes)
    med = statistics.median(closes)
    sd = statistics.stdev(closes)
    self.ctx.log(f"均值={avg}, 中位数={med}, 标准差={sd:.2f}")
```

### 禁止事项

- **禁止导入**：`os`, `sys`, `subprocess`, `socket`, `asyncio`, `threading`,
  `pickle`, `io`, `requests`, `httpx` 等系统/网络模块
- **禁止函数**：`eval`, `exec`, `open`, `__import__`, `getattr`, `setattr` 等
- **禁止属性访问**：`__builtins__`, `__globals__`, `__class__`, `__dict__` 等
- **写保护**：只能写入 `self.*` 属性和自己创建的数据结构

### 资源限制

- **CPU 时间**：每次 `on_bar()` 调用最多 30 秒
- **内存**：最多 2048 MB

超出限制将抛出 `ResourceLimitExceededError` 并终止会话。

---

## 15. 常见策略模式

### 15.1 均线交叉策略（使用 ta 模块）

```python
class MACrossStrategy(Strategy):
    def on_init(self):
        self.fast = self.ctx.params.get("fast", 5)
        self.slow = self.ctx.params.get("slow", 20)
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))
        self.prev_fast_ma = None
        self.prev_slow_ma = None

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.slow + 1)
        if len(closes) < self.slow:
            return

        fast_ma = ta.sma(closes, self.fast)
        slow_ma = ta.sma(closes, self.slow)
        if fast_ma is None or slow_ma is None:
            return

        if self.prev_fast_ma is not None:
            pos = self.ctx.get_position(bar.symbol)

            # 金叉买入
            if self.prev_fast_ma < self.prev_slow_ma and fast_ma > slow_ma:
                if not pos:
                    self.ctx.buy(bar.symbol, self.amount)

            # 死叉卖出
            elif self.prev_fast_ma > self.prev_slow_ma and fast_ma < slow_ma:
                if pos:
                    self.ctx.sell(bar.symbol, pos.amount)

        self.prev_fast_ma = fast_ma
        self.prev_slow_ma = slow_ma
```

### 15.2 带止损止盈的策略（使用 on_fill + on_order_done）

```python
class StopLossStrategy(Strategy):
    def on_init(self):
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))
        self.stop_loss_pct = Decimal(str(self.ctx.params.get("stop_loss", "0.02")))
        self.take_profit_pct = Decimal(str(self.ctx.params.get("take_profit", "0.05")))
        self.stop_order_id = None
        self.tp_order_id = None

    def on_fill(self, fill):
        # 买入成交后立即挂止损 + 止盈（OCO 配对）
        if fill.side == OrderSide.BUY:
            stop_price = fill.price * (1 - self.stop_loss_pct)
            self.stop_order_id = self.ctx.sell(
                fill.symbol, fill.amount, stop_price=stop_price,
            )
            tp_price = fill.price * (1 + self.take_profit_pct)
            self.tp_order_id = self.ctx.sell(
                fill.symbol, fill.amount, price=tp_price,
            )
            self.ctx.log(f"设置止损 @ {stop_price}, 止盈 @ {tp_price}")

    def on_order_done(self, order):
        # OCO 管理：一侧完成后取消另一侧
        if order.status == OrderStatus.FILLED:
            if order.id == self.stop_order_id:
                if self.tp_order_id:
                    self.ctx.cancel_order(self.tp_order_id)
                self.ctx.log(f"止损触发 @ {order.filled_price}")
            elif order.id == self.tp_order_id:
                if self.stop_order_id:
                    self.ctx.cancel_order(self.stop_order_id)
                self.ctx.log(f"止盈触发 @ {order.filled_price}")

        # 不论成交还是取消，重置 ID
        if order.id == self.stop_order_id:
            self.stop_order_id = None
        if order.id == self.tp_order_id:
            self.tp_order_id = None

    def on_bar(self, bar):
        # 无持仓且无挂单 → 寻找买入信号
        if self.ctx.has_position(bar.symbol) or self.stop_order_id or self.tp_order_id:
            return

        closes = self.ctx.get_closes(20)
        if len(closes) < 20:
            return

        ma20 = ta.sma(closes, 20)
        if ma20 is not None and bar.close > ma20:
            order_id = self.ctx.buy(bar.symbol, self.amount)
            if order_id:
                self.ctx.log(f"买入信号触发 @ {bar.close}")
```

### 15.3 基于权益比例的仓位管理

```python
class PositionSizingStrategy(Strategy):
    def on_init(self):
        self.risk_pct = Decimal(str(self.ctx.params.get("risk_pct", "0.02")))

    def on_bar(self, bar):
        if self.ctx.has_position(bar.symbol):
            return

        # 信号判断（简化）
        closes = self.ctx.get_closes(20)
        if len(closes) < 20:
            return
        ma = sum(closes) / 20
        if bar.close <= ma:
            return

        # 基于权益和风险比例计算仓位大小
        risk_amount = self.ctx.equity * self.risk_pct
        stop_distance = bar.close * Decimal("0.02")  # 假设 2% 止损距离

        if stop_distance > 0:
            position_size = risk_amount / stop_distance
        else:
            return

        # 确保不超过可用资金
        max_affordable = self.ctx.cash * Decimal("0.95") / bar.close  # 留 5% 余量
        position_size = min(position_size, max_affordable)

        if position_size > 0:
            self.ctx.buy(bar.symbol, position_size)

    def on_stop(self):
        pass
```

### 15.4 网格交易策略

```python
class GridStrategy(Strategy):
    def on_init(self):
        self.grid_size = Decimal(str(self.ctx.params.get("grid_size", "100")))
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.001")))
        self.num_grids = self.ctx.params.get("num_grids", 5)
        self.base_price = None
        self.buy_orders = {}   # grid_level → order_id
        self.sell_orders = {}

    def on_bar(self, bar):
        if self.base_price is None:
            self.base_price = bar.close
            self._place_grid_orders(bar)
            return

        # 检查已成交的订单，并在对侧补单
        for level, oid in list(self.buy_orders.items()):
            order = self.ctx.get_order(oid)
            if order and order.status == "filled":
                # 买入成交 → 在上方放卖出限价单
                sell_price = self.base_price + (level + 1) * self.grid_size
                sell_id = self.ctx.sell(bar.symbol, self.amount, price=sell_price)
                if sell_id:
                    self.sell_orders[level] = sell_id
                del self.buy_orders[level]

        for level, oid in list(self.sell_orders.items()):
            order = self.ctx.get_order(oid)
            if order and order.status == "filled":
                # 卖出成交 → 在下方放买入限价单
                buy_price = self.base_price - (level + 1) * self.grid_size
                buy_id = self.ctx.buy(bar.symbol, self.amount, price=buy_price)
                if buy_id:
                    self.buy_orders[level] = buy_id
                del self.sell_orders[level]

    def _place_grid_orders(self, bar):
        """初始化网格订单"""
        for i in range(1, self.num_grids + 1):
            # 下方挂买入限价单
            buy_price = self.base_price - i * self.grid_size
            buy_id = self.ctx.buy(bar.symbol, self.amount, price=buy_price)
            if buy_id:
                self.buy_orders[i] = buy_id

    def on_stop(self):
        self.ctx.log(f"网格策略停止, 基准价: {self.base_price}")
```

### 15.5 追踪止损

```python
class TrailingStopStrategy(Strategy):
    def on_init(self):
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))
        self.trail_pct = Decimal(str(self.ctx.params.get("trail_pct", "0.03")))
        self.highest_since_entry = None
        self.stop_order_id = None

    def on_bar(self, bar):
        pos = self.ctx.get_position(bar.symbol)

        if not pos:
            self.highest_since_entry = None
            self.stop_order_id = None

            # 简单入场信号
            closes = self.ctx.get_closes(10)
            if len(closes) >= 10:
                ma = sum(closes) / 10
                if bar.close > ma:
                    self.ctx.buy(bar.symbol, self.amount)
                    self.highest_since_entry = bar.close
            return

        # 更新最高价
        if self.highest_since_entry is None:
            self.highest_since_entry = bar.high
        else:
            self.highest_since_entry = max(self.highest_since_entry, bar.high)

        # 计算新的追踪止损价
        new_stop = self.highest_since_entry * (1 - self.trail_pct)

        # 更新止损单：取消旧的，创建新的
        if self.stop_order_id:
            old_order = self.ctx.get_order(self.stop_order_id)
            if old_order and old_order.status == "filled":
                # 止损已触发
                self.ctx.log(f"追踪止损触发 @ {old_order.avg_fill_price}")
                self.stop_order_id = None
                return

            # 只在止损价上移时更新（止损价只升不降）
            if old_order and old_order.stop_price and new_stop > old_order.stop_price:
                self.ctx.cancel_order(self.stop_order_id)
                self.stop_order_id = self.ctx.sell(
                    bar.symbol, pos.amount,
                    stop_price=new_stop,
                )
                self.ctx.log(f"追踪止损更新: {old_order.stop_price} → {new_stop}")
        else:
            self.stop_order_id = self.ctx.sell(
                bar.symbol, pos.amount,
                stop_price=new_stop,
            )

    def on_stop(self):
        pass
```

---

## 16. 注意事项与陷阱

### 16.1 市价单在回测中延迟一根K线成交

```python
# ❌ 错误认知
def on_bar(self, bar):
    self.ctx.buy(bar.symbol, Decimal("0.1"))
    # 不要期望立刻成交！此时 pending_orders 有一个新订单
    # 成交发生在下一根K线的 step 1
    pos = self.ctx.get_position(bar.symbol)  # 此时仍为 None！

# ✅ 正确做法
def on_bar(self, bar):
    if not self.ctx.has_position(bar.symbol):
        self.ctx.buy(bar.symbol, Decimal("0.1"))
    else:
        # 在后续K线中处理持仓
        pos = self.ctx.get_position(bar.symbol)
```

### 16.2 资金预留 — 多个挂单的资金冲突

```python
# ❌ 可能导致 ValueError: Insufficient cash
def on_bar(self, bar):
    # 第一个买入预留了大部分资金
    self.ctx.buy(bar.symbol, Decimal("0.5"), price=Decimal("49000"))
    # 第二个买入可能因资金不足而失败
    self.ctx.buy(bar.symbol, Decimal("0.5"), price=Decimal("48000"))

# ✅ 正确做法：合理分配资金
def on_bar(self, bar):
    per_order = self.ctx.cash * Decimal("0.4") / bar.close
    self.ctx.buy(bar.symbol, per_order, price=Decimal("49000"))
    self.ctx.buy(bar.symbol, per_order, price=Decimal("48000"))
```

### 16.3 卖出不能超过持仓

```python
# ❌ 同时挂两个卖出单，总量超过持仓
pos = self.ctx.get_position(bar.symbol)
if pos:
    self.ctx.sell(bar.symbol, pos.amount, stop_price=Decimal("48000"))
    self.ctx.sell(bar.symbol, pos.amount, price=Decimal("55000"))  # ValueError!

# ✅ 正确做法：分仓卖出
pos = self.ctx.get_position(bar.symbol)
if pos:
    half = pos.amount / 2
    self.ctx.sell(bar.symbol, half, stop_price=Decimal("48000"))
    self.ctx.sell(bar.symbol, half, price=Decimal("55000"))
```

### 16.4 Decimal 类型

```python
# ❌ 使用 float 会导致精度问题
amount = 0.1  # float!

# ✅ 始终使用 Decimal
amount = Decimal("0.1")

# ✅ 从参数转换
amount = Decimal(str(self.ctx.params.get("amount", "0.1")))
```

### 16.5 buy() 返回 None 不是异常

```python
# ❌ 忽略返回值
self.ctx.buy(bar.symbol, Decimal("0.00001"))  # 低于最小订单金额
# 订单被静默拒绝，但策略继续运行

# ✅ 检查返回值
order_id = self.ctx.buy(bar.symbol, amount)
if order_id is None:
    self.ctx.log("订单被拒绝（金额过小）")
```

### 16.6 权益快照在 on_bar 之前记录

权益曲线中的快照反映的是**策略决策之前**的状态。
这意味着当你在 `on_bar()` 中买入后，该笔订单的成交
不会反映在当前K线的权益快照中，而是在下一根。

### 16.7 止损/止盈配对管理

同时挂止损和止盈单时，一个成交后必须取消另一个，
否则可能导致意外交易。推荐使用 `on_order_done` 回调自动管理
（见[第 11 节](#11-订单生命周期)的 OCO 示例和[第 15.2 节](#152-带止损止盈的策略使用-on_fill--on_order_done)）。

---

## 17. 完整策略模板

```python
"""均线突破 + 追踪止损策略。

使用 ta 模块计算 EMA，突破时入场，on_fill 设置止损，
on_order_done 管理 OCO，on_bar 更新追踪止损。

参数:
    ema_period (int): EMA 周期，默认 20
    alloc_pct (str): 目标仓位比例，默认 "0.5"（50% 权益）
    trail_pct (str): 追踪止损百分比，默认 "0.03"（3%）
"""


class EMATrailingStrategy(Strategy):
    """EMA 突破 + 追踪止损策略。"""

    def on_init(self):
        """初始化：读取参数，设置状态变量。"""
        self.ema_period = self.ctx.params.get("ema_period", 20)
        self.alloc_pct = Decimal(str(self.ctx.params.get("alloc_pct", "0.5")))
        self.trail_pct = Decimal(str(self.ctx.params.get("trail_pct", "0.03")))

        self.stop_order_id = None
        self.highest_since_entry = None

    def on_fill(self, fill):
        """买入成交后立即设置初始止损。"""
        if fill.side == OrderSide.BUY:
            self.highest_since_entry = fill.price
            stop_price = fill.price * (1 - self.trail_pct)
            self.stop_order_id = self.ctx.sell(
                fill.symbol, fill.amount, stop_price=stop_price,
            )
            self.ctx.log(f"入场 @ {fill.price}, 初始止损 @ {stop_price}")

    def on_order_done(self, order):
        """止损触发后重置状态。"""
        if order.id == self.stop_order_id:
            if order.status == OrderStatus.FILLED:
                self.ctx.log(f"止损触发 @ {order.filled_price}")
            self.stop_order_id = None
            self.highest_since_entry = None

    def on_bar(self, bar):
        """核心逻辑：EMA 趋势判断 + 追踪止损更新。"""
        closes = self.ctx.get_closes(self.ema_period + 1)
        if len(closes) < self.ema_period:
            return

        ema_val = ta.ema(closes, self.ema_period)
        if ema_val is None:
            return

        pos = self.ctx.get_position(bar.symbol)

        if not pos:
            # 无持仓 → EMA 突破买入
            if bar.close > ema_val and self.stop_order_id is None:
                self.ctx.target_percent(bar.symbol, self.alloc_pct)
        else:
            # 有持仓 → 更新追踪止损
            if self.highest_since_entry is not None:
                self.highest_since_entry = max(self.highest_since_entry, bar.high)
                new_stop = self.highest_since_entry * (1 - self.trail_pct)

                if self.stop_order_id:
                    old = self.ctx.get_order(self.stop_order_id)
                    if old and old.stop_price and new_stop > old.stop_price:
                        self.ctx.cancel_order(self.stop_order_id)
                        self.stop_order_id = self.ctx.sell(
                            bar.symbol, pos.amount, stop_price=new_stop,
                        )

            # EMA 跌破 → 直接平仓
            if bar.close < ema_val:
                if self.stop_order_id:
                    self.ctx.cancel_order(self.stop_order_id)
                    self.stop_order_id = None
                self.ctx.close_position(bar.symbol)
                self.ctx.log(f"趋势反转平仓 @ {bar.close}")

    def on_stop(self):
        """策略停止：输出最终统计。"""
        self.ctx.log(f"最终权益: {self.ctx.equity}")
        self.ctx.log(f"收益率: {self.ctx.return_pct:.2%}")
        self.ctx.log(f"最大回撤: {self.ctx.max_drawdown:.2%}")
```

---

## 18. 绩效指标

回测和模拟交易完成后，系统自动计算以下绩效指标：

| 指标 | 说明 |
|------|------|
| **总收益 / 收益率** | 最终权益 vs 初始资金 |
| **年化收益率** | CAGR（需 ≥ 7 天数据） |
| **最大回撤** | 峰值到谷底的最大跌幅 |
| **最大回撤持续时间** | 从峰值到恢复的最长时间 |
| **夏普比率** | 年化风险调整收益（无风险利率 2%） |
| **索提诺比率** | 只考虑下行波动的风险调整收益 |
| **卡玛比率** | 年化收益 / 最大回撤 |
| **波动率** | 年化收益标准差 |
| **胜率** | 盈利交易占比 |
| **盈亏比** | 总盈利 / 总亏损 |
| **平均持仓时间** | 每笔交易的平均持续时间 |
| **最大连续亏损** | 最长连亏笔数 |
| **最大单笔盈利/亏损** | 最好/最差的单笔交易 |
