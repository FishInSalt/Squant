# API 契约对齐：后端 Schema 改造需求

## 背景

前端已建立 API 契约测试基础设施（openapi-typescript 自动生成类型 + CI 漂移检测）。但 9 个前端 API 文件中，只有 `market.ts` 能迁移到生成类型，其余 7 个因后端 schema 与前端预期不兼容而无法迁移。

本文档记录每个不兼容接口的**具体差异、改动内容和改动原因**，供后端评估。

---

## 通用问题

### GP-001: Decimal 字段序列化为 string

**现状**：后端 Pydantic schema 中所有 `Decimal` 类型字段序列化为 JSON string（如 `"100.5"` 而非 `100.5`）。

**影响范围**：`account`, `order`, `backtest`, `paper`, `live` 模块中的价格、数量、资金字段。

**改动建议**：配置 FastAPI/Pydantic 的 JSON encoder，将 Decimal 序列化为 number。或者在 schema 中使用 `float` 替代 `Decimal`。

**原因**：前端所有价格/数量字段都是 `number` 类型。当前 string 序列化导致每个模块都需要手动 `parseFloat()`，且生成的 TypeScript 类型为 `string` 而非 `number`，丧失类型安全。JSON 规范原生支持浮点数，无需用 string 传递。

---

## 按模块分类

### 1. backtest（不可迁移）

#### BT-001: `BacktestRunResponse` 缺少 `strategy_name` 字段

**现状**：`BacktestRunResponse` 不返回策略名称，只有 `strategy_id`。

**改动**：在 `BacktestRunResponse` 中添加 `strategy_name: str` 字段（join strategy 表获取）。

**原因**：前端回测列表页、回测详情页都需要展示策略名称。当前前端额外请求策略详情来获取名称，增加了不必要的 API 调用。

#### BT-002: `BacktestRunResponse` 缺少 `progress` 字段

**现状**：异步回测运行中，前端无法获取进度。

**改动**：在 `BacktestRunResponse` 中添加 `progress: float` 字段（0.0-1.0）。

**原因**：前端回测页面需要展示进度条。轮询 status 时需要知道当前执行进度，否则用户只能看到"运行中"而不知道还需要等多久。

#### BT-003: `BacktestRunResponse.config` 嵌套 vs 扁平

**现状**：后端将 config 字段（`backtest_start`, `backtest_end`, `initial_capital` 等）扁平化到顶层。前端期望 `config: BacktestConfig` 嵌套对象。

**改动**：两种方案任选：
- A）后端添加 `config: BacktestConfig` 嵌套字段（推荐，语义更清晰）
- B）前端适配扁平结构（前端改动）

**原因**：前端表单提交用 `BacktestConfig` 对象，回显时也需要同结构。扁平结构导致请求和响应的字段命名不一致（`start_date` vs `backtest_start`）。

#### BT-004: `BacktestDetailResponse.result` 是 `dict[str, Any]`（无类型）

**现状**：回测详情的 `result` 字段返回 `dict[str, Any]`，生成的 TypeScript 类型为 `Record<string, unknown>`，没有字段级类型安全。

**改动**：定义强类型 schema：
```python
class BacktestMetricsResponse(BaseModel):
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    # ... 其他指标

class BacktestDetailResponse(BaseModel):
    run: BacktestRunResponse
    metrics: BacktestMetricsResponse  # 替代 result: dict
    trades: list[TradeRecordResponse]  # 新增
    equity_curve: list[EquityCurvePoint]
    drawdown_curve: list[DrawdownPoint]  # 新增
    total_bars: int | None
```

**原因**：`dict[str, Any]` 意味着 openapi-typescript 只能生成 `Record<string, unknown>`，前端无法获得任何字段提示或类型检查。回测指标（收益率、最大回撤、夏普比率等）是核心展示数据，必须有强类型保证。

#### BT-005: `EquityCurvePoint` 字段名和类型不匹配

**现状**：
- 时间字段：后端 `time: str`（ISO），前端期望 `timestamp: number`（unix ms）
- 数值字段：后端 `equity: str`, `cash: str`，前端期望 `equity: number`, `cash: number`

**改动**：参见 GP-001（Decimal→number）。时间字段命名统一为 `timestamp`，或前端适配 `time`。

**原因**：前端图表库（ECharts）需要 number 类型的时间戳和数值来绘制权益曲线。string 类型需要逐个 parse，增加不必要的运行时开销和出错风险。

---

### 2. strategy（不可迁移）

#### ST-001: `StrategyResponse` 缺少 `author`, `filename`, `class_name` 字段

**现状**：后端 `StrategyResponse` 不返回这三个字段。

**改动**：在 `StrategyResponse` 中添加：
```python
author: str | None = None
filename: str
class_name: str
```

**原因**：前端策略详情页需要展示作者信息、文件名和类名。这些信息在后端 Strategy model 中已存在，只是 response schema 没有暴露。

#### ST-002: `StrategyResponse` 缺少 `is_valid` 字段

**现状**：后端使用 `status: str` 表示策略状态，前端使用 `is_valid: boolean`。

**改动**：两种方案：
- A）后端添加 `is_valid: bool` 计算字段（`status == 'active'`）
- B）前端使用 `status` 字段判断（前端改动）

**原因**：前端策略列表需要快速区分有效/无效策略来显示不同的 UI 状态（如禁用运行按钮）。

#### ST-003: `ValidationResultResponse` 缺少 `strategy_info` 嵌套对象

**现状**：后端 `ValidationResultResponse` 只有 `valid`, `errors`, `warnings`。前端期望额外返回 `strategy_info: { name, class_name, params_schema }`。

**改动**：在 `ValidationResultResponse` 中添加 `strategy_info` 嵌套字段。

**原因**：策略校验通过后，前端需要展示解析出的策略信息（名称、类名、参数 schema），让用户确认上传的策略是否正确。当前需要额外请求策略详情才能获取这些信息。

---

### 3. account（不可迁移）

#### AC-001: `BalanceItem` 数值字段为 string

**现状**：`BalanceItem` 的 `available`, `frozen`, `total` 都是 string 类型。

**改动**：参见 GP-001。

**原因**：前端资产页面需要对余额进行排序、汇总、格式化展示，全部需要 number 类型。

#### AC-002: `BalanceItem` 字段命名不一致

**现状**：
- 后端：`currency`, `available`, `frozen`
- 前端：`asset`, `free`, `locked`

**改动**：两种方案：
- A）后端改用前端命名：`asset`, `free`, `locked`（更符合交易所通用术语）
- B）前端适配后端命名（前端改动）

**原因**：`free`/`locked` 是 CCXT 和主流交易所 API 的标准命名。统一命名减少团队理解成本。

#### AC-003: `BalanceResponse` 缺少 `account_id`, `account_name`, `total_usd_value`

**现状**：后端 `BalanceResponse` 只有 `exchange`, `balances`, `timestamp`，没有关联的账户信息和汇总值。

**改动**：添加字段：
```python
account_id: str
account_name: str
total_usd_value: float | None = None
```

**原因**：前端多账户管理场景下，需要知道余额属于哪个账户。`total_usd_value` 用于资产概览页的汇总展示，避免前端自行计算（需要额外获取汇率数据）。

---

### 4. order（不可迁移）

#### OD-001: `OrderDetail` 数值字段为 string

**现状**：`price`, `amount`, `filled`, `avg_price` 都是 string 类型。

**改动**：参见 GP-001。

**原因**：同上，前端订单列表需要对价格、数量进行排序和格式化，string 类型不可直接运算。

#### OD-002: `OrderDetail` 字段命名不一致

**现状**：
| 后端 | 前端 | 通用术语 |
|------|------|---------|
| `amount` | `quantity` | quantity 更通用 |
| `filled` | `filled_quantity` | filled_quantity 更明确 |
| `avg_price` | `avg_fill_price` | avg_fill_price 更明确 |

**改动**：建议统一命名，或前端适配。

**原因**：`amount` 在金融语境中既可指数量也可指金额，易歧义。`quantity`/`filled_quantity` 语义更明确。

#### OD-003: `OrderDetail` 缺少字段

**现状**：缺少 `stop_price`, `remaining_quantity`, `commission`, `commission_asset`, `strategy_name`, `filled_at`。

**改动**：按需添加：
```python
stop_price: float | None = None       # 止损/止盈触发价
remaining_quantity: float | None       # 可计算，但方便前端
commission: float | None = None        # 手续费
commission_asset: str | None = None    # 手续费币种
strategy_name: str | None = None       # join 策略表
filled_at: str | None = None           # 完全成交时间
```

**原因**：
- `stop_price`：条件单展示需要
- `commission`/`commission_asset`：订单详情页需要展示手续费信息，是用户关注的核心数据
- `strategy_name`：订单列表关联策略展示
- `filled_at`：订单历史分析需要精确成交时间

#### OD-004: `OrderStatus` 枚举不一致

**现状**：后端使用 `submitted`，前端使用 `open`；前端有 `expired`，后端没有。

**改动**：统一枚举值。建议后端添加 `expired` 状态，`submitted` 改为 `open`（或前端适配 `submitted`）。

**原因**：`open` 是交易所 API 的标准术语（CCXT、Binance、OKX 都用 `open`）。`expired` 是限价单/条件单超时的常见状态。

---

### 5. risk（不可迁移）

#### RK-001: `RiskRuleResponse` 缺少 `description`, `status`, `action`, `last_triggered`

**现状**：后端返回的风控规则信息很少，只有 `id`, `name`, `type`, `params`, `enabled`, `created_at`, `updated_at`。

**改动**：添加：
```python
description: str | None = None
status: str                    # active/inactive/triggered
action: str                    # warn/block/halt
last_triggered: str | None     # 最近触发时间
```

**原因**：
- `description`：风控规则列表需要展示规则说明，让用户理解每条规则的作用
- `action`：用户需要知道触发后会执行什么动作（警告/阻止/熔断）
- `last_triggered`：帮助用户评估规则是否有效、触发频率

#### RK-002: `CircuitBreakerStatusResponse` 结构完全不同

**现状**：
- 后端：`is_active`, `triggered_at`, `trigger_type`, `trigger_reason`, `cooldown_until`, `active_live_sessions`, `active_paper_sessions`
- 前端期望：`global_halt`, `halt_reason`, `halted_at`, `halted_by`, `auto_halt_conditions[]`, `active_sessions_count`, `pending_orders_count`

**改动**：扩展后端返回，添加 `auto_halt_conditions` 数组和 `pending_orders_count`：
```python
class AutoHaltCondition(BaseModel):
    id: str
    name: str
    enabled: bool
    condition_type: str  # total_loss/consecutive_losses/drawdown/error_rate
    threshold: float
    time_window_minutes: int | None
    current_value: float

class CircuitBreakerStatusResponse(BaseModel):
    is_active: bool
    trigger_reason: str | None
    triggered_at: str | None
    triggered_by: str | None
    auto_halt_conditions: list[AutoHaltCondition]
    active_sessions_count: int  # live + paper 合计
    pending_orders_count: int
    cooldown_until: str | None
```

**原因**：前端熔断器页面是关键的风控监控界面，需要：
- `auto_halt_conditions`：展示自动熔断条件列表及当前值 vs 阈值的对比
- `pending_orders_count`：紧急情况下用户需要知道还有多少待处理订单
- `triggered_by`：审计需要，知道是谁触发的熔断

#### RK-003: `RiskTriggerListItem` 信息严重不足

**现状**：只有 `id`, `time`, `rule_id`, `run_id`, `trigger_type`。

**改动**：补充详细信息：
```python
class RiskTriggerListItem(BaseModel):
    id: str
    rule_id: str
    rule_name: str           # join 规则表
    rule_type: str
    run_id: str | None
    strategy_name: str | None  # join 策略表
    exchange: str | None
    symbol: str | None
    trigger_value: Any
    threshold_value: Any
    action_taken: str         # warn/block/halt
    message: str
    created_at: str
```

**原因**：风控触发记录是用户排查问题的核心数据。只有 `id` 和 `time` 无法让用户理解发生了什么、为什么触发、触发了什么动作。详细信息避免了前端需要额外 N 次 API 调用来拼凑完整信息。

---

### 6. paper（不可迁移）

#### PP-001: `PaperTradingRunResponse` 缺少 `strategy_name`

**现状**：只有 `strategy_id`，没有策略名称。

**改动**：添加 `strategy_name: str`（join 策略表）。

**原因**：同 BT-001。模拟交易列表页需要展示策略名称，避免额外 API 调用。

#### PP-002: `PaperTradingStatusResponse` 缺少 PNL 字段

**现状**：状态响应有 `cash`, `equity`, `initial_capital`，但缺少 `unrealized_pnl`, `realized_pnl`。

**改动**：添加：
```python
unrealized_pnl: float
realized_pnl: float
```

**原因**：PNL 是模拟交易监控页面最核心的指标。`unrealized_pnl` 可以从 equity - cash - initial_capital 推算，但让前端计算容易出错且语义不明确。后端直接返回更可靠。

#### PP-003: `PositionInfo` 结构差异大

**现状**：后端 `positions: Record<symbol, PositionInfo>`，其中 `PositionInfo` 只有 `amount`, `avg_entry_price`（都是 string）。前端期望 `Position[]` 数组，包含 `side`, `current_price`, `unrealized_pnl`, `unrealized_pnl_percent`。

**改动**：扩展 `PositionInfo`：
```python
class PositionInfo(BaseModel):
    symbol: str
    side: str           # long/short
    amount: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
```
返回格式改为 `positions: list[PositionInfo]`。

**原因**：持仓信息是交易监控的核心展示。只有数量和均价无法让用户评估当前持仓盈亏状态。`current_price` 和 PNL 数据后端已有（用于权益计算），直接返回避免前端重复获取行情数据来计算。

---

### 7. live（不可迁移）

#### LV-001: `LiveTradingRunResponse` 缺少 `strategy_name` 和 `account_id`

**现状**：只有 `strategy_id`，没有策略名称和关联账户。

**改动**：添加 `strategy_name: str` 和 `account_id: str`。

**原因**：实盘交易列表需要同时展示策略名称和使用的交易所账户，这是用户区分不同实盘会话的关键信息。

#### LV-002: `LiveTradingStatusResponse` 缺少 PNL 字段

**改动和原因**：同 PP-002。

#### LV-003: `RiskConfigRequest` vs `RiskConfig` 响应不一致

**现状**：后端有 `RiskConfigRequest`（请求用）但没有 `RiskConfigResponse`。实盘状态中 `risk_state` 字段结构与前端 `RiskConfig` 不同。

**改动**：添加 `RiskConfigResponse`（和 request 结构一致但为 response），并在实盘详情中返回。

**原因**：前端需要回显实盘的风控配置。编辑/查看风控设置时需要知道当前值。

#### LV-004: Position 结构差异

**改动和原因**：同 PP-003。

---

## 优先级建议

| 优先级 | 改动项 | 影响 |
|--------|--------|------|
| **P0** | GP-001: Decimal→number 序列化 | 解决所有模块的数值类型不匹配，影响面最广 |
| **P1** | BT-004: 回测结果强类型化 | 核心功能，无类型安全 |
| **P1** | BT-001/PP-001/LV-001: 添加 strategy_name | 多处列表展示需要 |
| **P2** | PP-003/LV-004: 扩展 PositionInfo | 交易监控核心展示 |
| **P2** | RK-002: 熔断器状态扩展 | 风控监控页面 |
| **P2** | OD-003: 订单字段补全 | 订单详情展示 |
| **P3** | ST-001/ST-003: 策略字段补全 | 策略详情页 |
| **P3** | AC-002/OD-002/OD-004: 命名统一 | 可由前端适配，非阻塞 |

---

## 迁移状态汇总

| API 文件 | 状态 | 阻塞项 |
|---------|------|--------|
| `market.ts` | **已迁移** | — |
| `system.ts` | **无需迁移**（无对应生成类型） | — |
| `backtest.ts` | 待后端改造 | GP-001, BT-001~005 |
| `strategy.ts` | 待后端改造 | ST-001~003 |
| `account.ts` | 待后端改造 | GP-001, AC-001~003 |
| `order.ts` | 待后端改造 | GP-001, OD-001~004 |
| `risk.ts` | 待后端改造 | RK-001~003 |
| `paper.ts` | 待后端改造 | GP-001, PP-001~003 |
| `live.ts` | 待后端改造 | GP-001, LV-001~004 |
