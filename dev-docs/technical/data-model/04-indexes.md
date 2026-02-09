# 索引设计

> **关联文档**: [核心表结构](./02-core-tables.md)

## 1. 索引策略

| 表 | 索引 | 类型 | 用途 |
|---|---|---|---|
| orders | (run_id) | B-tree | 按策略查订单 |
| orders | (created_at DESC) | B-tree | 按时间查订单 |
| orders | (status) | B-tree | 按状态筛选 |
| klines | (exchange, symbol, timeframe, time) | B-tree (复合) | K 线查询主键 |
| strategy_runs | (status, mode) | B-tree (复合) | 运行中策略列表 |

## 2. 部分索引

```sql
-- 只索引运行中的策略
CREATE INDEX idx_active_runs ON strategy_runs(status)
WHERE status IN ('pending', 'running');

-- 只索引未完成订单
CREATE INDEX idx_open_orders ON orders(account_id, status)
WHERE status IN ('pending', 'submitted', 'partial');
```

## 3. 数据迁移策略

### Alembic 配置

```python
# alembic/env.py
from squant.models import Base
from squant.config import settings

target_metadata = Base.metadata

def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    # ...
```

### 迁移命名规范

```
{序号}_{日期}_{描述}.py

例如：
001_20250124_initial_schema.py
002_20250125_add_risk_rules.py
003_20250126_add_equity_curves.py
```

### 迁移命令

```bash
# 创建新迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚一个版本
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史
alembic history
```

## 4. 数据备份

```bash
# 定时备份脚本
pg_dump -Fc squant > backup_$(date +%Y%m%d).dump

# 恢复
pg_restore -d squant backup_20250124.dump
```

## 5. 查询优化建议

### K 线查询

```sql
-- 推荐：使用时间范围 + 复合主键
SELECT * FROM klines
WHERE exchange = 'binance'
  AND symbol = 'BTC/USDT'
  AND timeframe = '1h'
  AND time >= '2024-01-01'
  AND time < '2024-02-01'
ORDER BY time;

-- 避免：全表扫描
SELECT * FROM klines WHERE symbol = 'BTC/USDT';
```

### 订单查询

```sql
-- 推荐：使用索引字段
SELECT * FROM orders
WHERE run_id = 'xxx'
  AND status IN ('submitted', 'partial')
ORDER BY created_at DESC
LIMIT 50;

-- 使用部分索引
SELECT * FROM orders
WHERE account_id = 'xxx'
  AND status = 'pending';  -- 命中 idx_open_orders
```
