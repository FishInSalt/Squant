# 数据模型设计

> **文档版本**: v1.0
> **最后更新**: 2025-01-24

## 文档索引

| 文档 | 描述 |
|------|------|
| [01-er-diagram.md](./01-er-diagram.md) | 实体关系图 |
| [02-core-tables.md](./02-core-tables.md) | 核心表结构 (账户、策略、订单) |
| [03-timescaledb.md](./03-timescaledb.md) | TimescaleDB 时序表设计 |
| [04-indexes.md](./04-indexes.md) | 索引设计与迁移策略 |
| [05-redis.md](./05-redis.md) | Redis 缓存设计 |

## 数据库选型

| 组件 | 用途 |
|------|------|
| PostgreSQL 16 | 主数据库，存储业务数据 |
| TimescaleDB | 时序数据扩展，存储 K 线、权益曲线 |
| Redis 7 | 缓存、消息队列、进程间通信 |
