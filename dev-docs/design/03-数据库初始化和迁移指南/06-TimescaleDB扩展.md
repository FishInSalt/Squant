## 8. TimescaleDB时序数据扩展

### 8.1 创建TimescaleDB超表

```sql
-- 连接到数据库
psql -U squant -d squant

-- 1. 安装TimescaleDB扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. 将klines表转换为超表 (按时间分区)
SELECT create_hypertable('klines', 'open_time', chunk_time_interval => INTERVAL '1 day');

-- 3. 创建压缩策略 (压缩30天前的数据)
ALTER TABLE klines SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, interval'
);

SELECT add_compression_policy('klines', INTERVAL '30 days');

-- 4. 创建数据保留策略 (删除1年前的数据)
SELECT add_retention_policy('klines', INTERVAL '365 days');
```

### 8.2 连续聚合 (自动计算)

```sql
-- 创建连续聚合,计算1小时K线
CREATE MATERIALIZED VIEW klines_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', open_time) AS bucket,
    exchange,
    symbol,
    interval,
    first(open_price, open_time) AS open_price,
    MAX(high_price) AS high_price,
    MIN(low_price) AS low_price,
    last(close_price, open_time) AS close_price,
    SUM(volume) AS volume,
    SUM(quote_volume) AS quote_volume
FROM klines
GROUP BY bucket, exchange, symbol, interval
WITH DATA;

-- 设置刷新策略 (每5分钟刷新一次)
SELECT add_continuous_aggregate_policy('klines_1h',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');
```

---

## 9. 数据库备份和恢复
