# 核心表结构

> **关联文档**: [ER 图](./01-er-diagram.md)

## 1. 交易所账户表 (exchange_accounts)

存储用户配置的交易所 API 密钥。

```sql
CREATE TABLE exchange_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exchange        VARCHAR(32) NOT NULL,       -- binance, okx
    name            VARCHAR(64) NOT NULL,       -- 用户自定义名称
    api_key_enc     BYTEA NOT NULL,             -- AES-256-GCM 加密
    api_secret_enc  BYTEA NOT NULL,             -- AES-256-GCM 加密
    passphrase_enc  BYTEA,                      -- OKX 需要，可空
    nonce           BYTEA NOT NULL,             -- 加密 nonce
    testnet         BOOLEAN DEFAULT FALSE,      -- 是否测试网
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (exchange, name)
);

CREATE INDEX idx_exchange_accounts_exchange ON exchange_accounts(exchange);
```

## 2. 策略表 (strategies)

存储用户上传的策略代码和配置。

```sql
CREATE TABLE strategies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL UNIQUE,
    version         VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    description     TEXT,
    code            TEXT NOT NULL,              -- Python 源代码
    params_schema   JSONB NOT NULL DEFAULT '{}', -- 参数定义 JSON Schema
    default_params  JSONB NOT NULL DEFAULT '{}', -- 默认参数值
    status          VARCHAR(16) DEFAULT 'active', -- active, archived
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategies_status ON strategies(status);
```

### params_schema 示例

```json
{
  "type": "object",
  "properties": {
    "fast_period": {
      "type": "integer",
      "title": "快线周期",
      "default": 10,
      "minimum": 1,
      "maximum": 100
    },
    "slow_period": {
      "type": "integer",
      "title": "慢线周期",
      "default": 30,
      "minimum": 1,
      "maximum": 200
    }
  },
  "required": ["fast_period", "slow_period"]
}
```

## 3. 策略运行表 (strategy_runs)

记录策略的每次运行（回测/模拟/实盘）。

```sql
CREATE TYPE run_mode AS ENUM ('backtest', 'paper', 'live');
CREATE TYPE run_status AS ENUM ('pending', 'running', 'stopped', 'error', 'completed');

CREATE TABLE strategy_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id     UUID NOT NULL REFERENCES strategies(id),
    account_id      UUID REFERENCES exchange_accounts(id), -- 实盘必须，回测可空
    mode            run_mode NOT NULL,
    symbol          VARCHAR(32) NOT NULL,       -- BTC/USDT
    exchange        VARCHAR(32) NOT NULL,       -- binance
    timeframe       VARCHAR(8) NOT NULL,        -- 1m, 5m, 1h, 1d
    params          JSONB NOT NULL DEFAULT '{}', -- 运行时参数

    -- 回测专用
    backtest_start  TIMESTAMPTZ,
    backtest_end    TIMESTAMPTZ,
    initial_capital DECIMAL(20, 8),
    commission_rate DECIMAL(10, 8) DEFAULT 0.001,

    -- 运行状态
    status          run_status DEFAULT 'pending',
    process_id      VARCHAR(64),                -- 进程 PID 或容器 ID
    error_message   TEXT,

    -- 回测结果（回测完成后填充）
    result          JSONB,                      -- 回测报告 JSON

    started_at      TIMESTAMPTZ,
    stopped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategy_runs_strategy ON strategy_runs(strategy_id);
CREATE INDEX idx_strategy_runs_status ON strategy_runs(status);
CREATE INDEX idx_strategy_runs_mode ON strategy_runs(mode);
```

### result 字段示例（回测完成后）

```json
{
  "total_return": 0.2534,
  "annual_return": 0.4521,
  "sharpe_ratio": 1.85,
  "max_drawdown": -0.1234,
  "win_rate": 0.62,
  "profit_factor": 2.1,
  "total_trades": 156,
  "avg_holding_period": "4h 32m"
}
```

## 4. 订单表 (orders)

存储所有订单（策略订单和手动订单）。

```sql
CREATE TYPE order_side AS ENUM ('buy', 'sell');
CREATE TYPE order_type AS ENUM ('market', 'limit');
CREATE TYPE order_status AS ENUM ('pending', 'submitted', 'partial', 'filled', 'cancelled', 'rejected');

CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES strategy_runs(id), -- 策略订单关联，手动订单为空
    account_id      UUID NOT NULL REFERENCES exchange_accounts(id),
    exchange_oid    VARCHAR(64),                -- 交易所订单 ID

    symbol          VARCHAR(32) NOT NULL,
    side            order_side NOT NULL,
    type            order_type NOT NULL,
    price           DECIMAL(20, 8),             -- 限价单价格，市价单为空
    amount          DECIMAL(20, 8) NOT NULL,    -- 委托数量
    filled          DECIMAL(20, 8) DEFAULT 0,   -- 已成交数量
    avg_price       DECIMAL(20, 8),             -- 平均成交价

    status          order_status DEFAULT 'pending',
    reject_reason   TEXT,                       -- 拒绝原因

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_run ON orders(run_id);
CREATE INDEX idx_orders_account ON orders(account_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at DESC);
```

## 5. 成交表 (trades)

记录订单的每笔成交明细。

```sql
CREATE TABLE trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES orders(id),
    exchange_tid    VARCHAR(64),                -- 交易所成交 ID

    price           DECIMAL(20, 8) NOT NULL,
    amount          DECIMAL(20, 8) NOT NULL,
    fee             DECIMAL(20, 8) DEFAULT 0,
    fee_currency    VARCHAR(16),                -- BTC, USDT 等

    timestamp       TIMESTAMPTZ NOT NULL        -- 成交时间
);

CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
```

## 6. 风控规则表 (risk_rules)

```sql
CREATE TYPE risk_rule_type AS ENUM (
    'order_limit',      -- 单笔限额
    'position_limit',   -- 持仓限制
    'daily_loss_limit', -- 日亏损限制
    'total_loss_limit', -- 总亏损限制
    'frequency_limit',  -- 频率限制
    'volatility_break'  -- 波动熔断
);

CREATE TABLE risk_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(64) NOT NULL,
    type            risk_rule_type NOT NULL,
    params          JSONB NOT NULL,             -- 规则参数
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### params 示例

```json
// order_limit
{"max_amount_usdt": 1000}

// position_limit
{"max_position_pct": 0.3}

// daily_loss_limit
{"max_loss_pct": 0.05}

// frequency_limit
{"max_orders_per_minute": 10}
```

## 7. 自选列表表 (watchlist)

```sql
CREATE TABLE watchlist (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exchange        VARCHAR(32) NOT NULL,
    symbol          VARCHAR(32) NOT NULL,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (exchange, symbol)
);
```

## 8. 系统日志表 (system_logs)

```sql
CREATE TYPE log_level AS ENUM ('debug', 'info', 'warning', 'error', 'critical');

CREATE TABLE system_logs (
    id              BIGSERIAL PRIMARY KEY,
    level           log_level NOT NULL,
    module          VARCHAR(64),                -- squant.engine, squant.api 等
    message         TEXT NOT NULL,
    context         JSONB,                      -- 附加上下文
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_system_logs_level ON system_logs(level);
CREATE INDEX idx_system_logs_created ON system_logs(created_at DESC);
```
