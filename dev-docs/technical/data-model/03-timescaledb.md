# TimescaleDB 时序表

> **关联文档**: [核心表结构](./02-core-tables.md)

## 1. K 线数据表 (klines)

存储历史和实时 K 线数据。

```sql
CREATE TABLE klines (
    time            TIMESTAMPTZ NOT NULL,
    exchange        VARCHAR(32) NOT NULL,
    symbol          VARCHAR(32) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,        -- 1m, 5m, 15m, 1h, 4h, 1d, 1w
    open            DECIMAL(20, 8) NOT NULL,
    high            DECIMAL(20, 8) NOT NULL,
    low             DECIMAL(20, 8) NOT NULL,
    close           DECIMAL(20, 8) NOT NULL,
    volume          DECIMAL(30, 8) NOT NULL,

    PRIMARY KEY (time, exchange, symbol, timeframe)
);

-- 转换为 TimescaleDB 超表
SELECT create_hypertable('klines', 'time', chunk_time_interval => INTERVAL '7 days');

-- 启用压缩（7天后自动压缩）
ALTER TABLE klines SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'exchange, symbol, timeframe'
);

SELECT add_compression_policy('klines', INTERVAL '7 days');

-- 数据保留策略（可选：保留2年）
-- SELECT add_retention_policy('klines', INTERVAL '2 years');
```

## 2. 风控触发记录表 (risk_triggers)

记录风控规则触发历史。

```sql
CREATE TABLE risk_triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    time            TIMESTAMPTZ NOT NULL,
    rule_id         UUID NOT NULL REFERENCES risk_rules(id),
    run_id          UUID REFERENCES strategy_runs(id),
    trigger_type    VARCHAR(32) NOT NULL,       -- blocked, warning
    details         JSONB NOT NULL              -- 触发详情
);

-- 时间索引（查询优化）
CREATE INDEX idx_risk_triggers_time ON risk_triggers(time DESC);

-- 规则索引（按规则查询触发记录）
CREATE INDEX idx_risk_triggers_rule_id ON risk_triggers(rule_id);

-- 策略运行索引（按策略查询触发记录）
CREATE INDEX idx_risk_triggers_run_id ON risk_triggers(run_id);
```

> **设计说明**: 使用 UUID 主键而非 `(time, rule_id)` 复合主键，避免同一规则在同一时刻触发多次时的主键冲突（尤其在回测场景）。

## 3. 权益曲线表 (equity_curves)

记录策略运行过程中的权益变化。

```sql
CREATE TABLE equity_curves (
    time            TIMESTAMPTZ NOT NULL,
    run_id          UUID NOT NULL REFERENCES strategy_runs(id),
    equity          DECIMAL(20, 8) NOT NULL,    -- 总权益
    cash            DECIMAL(20, 8) NOT NULL,    -- 现金余额
    position_value  DECIMAL(20, 8) NOT NULL,    -- 持仓价值
    unrealized_pnl  DECIMAL(20, 8) DEFAULT 0,   -- 未实现盈亏

    PRIMARY KEY (time, run_id)
);

SELECT create_hypertable('equity_curves', 'time', chunk_time_interval => INTERVAL '7 days');
```

## 4. 资产快照表 (balance_snapshots)

定期记录账户资产快照。

```sql
CREATE TABLE balance_snapshots (
    time            TIMESTAMPTZ NOT NULL,
    account_id      UUID NOT NULL REFERENCES exchange_accounts(id),
    currency        VARCHAR(16) NOT NULL,
    free            DECIMAL(20, 8) NOT NULL,
    locked          DECIMAL(20, 8) NOT NULL,
    usd_value       DECIMAL(20, 8),             -- 折算 USD 价值

    PRIMARY KEY (time, account_id, currency)
);

SELECT create_hypertable('balance_snapshots', 'time', chunk_time_interval => INTERVAL '30 days');
```

## 5. 数据保留策略

```sql
-- 自动数据压缩（7天后压缩）
SELECT add_compression_policy('klines', INTERVAL '7 days');
SELECT add_compression_policy('balance_snapshots', INTERVAL '7 days');
SELECT add_compression_policy('equity_curves', INTERVAL '7 days');

-- 数据保留策略（可选，根据存储需求配置）
-- 保留 1 年的 K 线数据
SELECT add_retention_policy('klines', INTERVAL '1 year');

-- 保留 2 年的资产快照
SELECT add_retention_policy('balance_snapshots', INTERVAL '2 years');

-- 保留 2 年的权益曲线
SELECT add_retention_policy('equity_curves', INTERVAL '2 years');
```

## 6. 数据量估算

```
BTC/USDT 1分钟 K 线 5 年:
= 5 × 365 × 24 × 60 = 2,628,000 条

单条 OHLCV 约 50 字节:
= 2,628,000 × 50 ≈ 125 MB（压缩后 ~15 MB）

支持 100 个交易对:
= 100 × 15 MB = 1.5 GB
```
