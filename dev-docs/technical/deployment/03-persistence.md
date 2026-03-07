# 数据持久化

> **关联文档**: [Docker 配置](./01-docker.md), [TimescaleDB](../data-model/03-timescaledb.md)

## 1. Volume 配置

```yaml
# docker-compose.yml volumes 详细配置
volumes:
  # PostgreSQL 数据
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DATA_PATH:-./data}/postgres

  # Redis 数据
  redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DATA_PATH:-./data}/redis

  # 策略文件
  strategy_files:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DATA_PATH:-./data}/strategies

  # 应用日志
  logs:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${DATA_PATH:-./data}/logs
```

## 2. 数据目录结构

```
data/
├── postgres/           # PostgreSQL 数据文件
├── redis/              # Redis AOF 持久化文件
├── strategies/         # 用户策略文件
│   ├── user_strategies/    # 用户上传的策略
│   └── builtin/            # 内置策略模板
├── logs/               # 应用日志
│   ├── squant.log          # 主应用日志
│   ├── strategy/           # 策略运行日志
│   └── trade/              # 交易日志
└── backups/            # 备份文件
    ├── db/                 # 数据库备份
    └── strategies/         # 策略备份
```

## 3. TimescaleDB 数据保留策略

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
