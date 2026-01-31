# 集成测试指南

本文档介绍如何在Squant项目中编写和运行集成测试。

## 目录

- [什么是集成测试](#什么是集成测试)
- [测试环境设置](#测试环境设置)
- [编写集成测试](#编写集成测试)
- [运行集成测试](#运行集成测试)
- [最佳实践](#最佳实践)
- [常见问题](#常见问题)

---

## 什么是集成测试

### 单元测试 vs 集成测试

| 特性 | 单元测试 | 集成测试 |
|------|---------|---------|
| **范围** | 单个函数/类 | 多个组件协作 |
| **依赖** | Mock外部依赖 | 真实的数据库、Redis等 |
| **速度** | 快（毫秒级） | 较慢（秒级） |
| **隔离性** | 完全隔离 | 部分隔离 |
| **环境** | 不需要外部服务 | 需要Docker环境 |

### 何时使用集成测试

✅ **适合集成测试的场景**:
- 数据库查询和ORM操作
- Redis缓存行为
- API端点的完整流程（请求 → 处理 → 持久化 → 响应）
- WebSocket连接和消息传递
- 多个服务的协作
- 事务和并发控制

❌ **不适合集成测试的场景**:
- 纯业务逻辑计算（用单元测试）
- 简单的数据转换（用单元测试）
- 已有大量单元测试覆盖的代码

---

## 测试环境设置

### 1. 使用Docker Compose启动测试环境

项目提供了专门的测试环境配置：

```bash
# 启动测试环境（PostgreSQL + Redis）
./scripts/test-env.sh start

# 查看服务状态
./scripts/test-env.sh status

# 查看日志
./scripts/test-env.sh logs

# 停止测试环境
./scripts/test-env.sh stop

# 完全清理测试环境（包括数据卷）
./scripts/test-env.sh down
```

### 2. 测试环境配置

测试环境使用不同的端口，避免与开发环境冲突：

| 服务 | 开发环境 | 测试环境 |
|------|---------|---------|
| PostgreSQL | localhost:5433 | localhost:5433 |
| Redis | localhost:6380 | localhost:6380 |
| API (E2E) | localhost:8000 | localhost:8001 |

**连接信息**:
```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test

# Redis
REDIS_URL=redis://localhost:6380/0
```

### 3. 数据库迁移

测试环境需要运行数据库迁移：

```bash
# test-env.sh start 会自动运行迁移
# 手动运行迁移：
export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
uv run alembic upgrade head

# 重置数据库
./scripts/test-env.sh reset-db
```

---

## 编写集成测试

### 目录结构

```
tests/integration/
├── conftest.py              # 集成测试fixtures
├── database/                # 数据库相关测试
│   └── test_strategy_repository.py
├── services/                # 服务层集成测试
│   └── test_redis_cache.py
├── api/                     # API集成测试
│   └── test_strategy_api.py
└── websocket/              # WebSocket集成测试
    └── test_websocket_streaming.py
```

### 使用Fixtures

集成测试可以使用以下fixtures（定义在`tests/integration/conftest.py`）：

#### 1. 数据库Fixtures

```python
import pytest
from sqlalchemy import select
from squant.models.strategy import Strategy


@pytest.mark.asyncio
async def test_create_strategy(db_session):
    """
    db_session: 每个测试独立的数据库session
    测试结束后自动回滚事务
    """
    strategy = Strategy(
        id=uuid4(),
        name="Test Strategy",
        code="def initialize(context): pass",
    )
    db_session.add(strategy)
    await db_session.commit()
    await db_session.refresh(strategy)

    assert strategy.id is not None
    assert strategy.created_at is not None
```

**可用的数据库fixtures**:
- `db_session`: 每个测试独立的session，自动回滚
- `clean_db_session`: 不自动回滚的session，用于需要真实提交的场景
- `engine`: 数据库引擎（session级别）

#### 2. Redis Fixtures

```python
import pytest


@pytest.mark.asyncio
async def test_redis_cache(redis):
    """
    redis: Redis客户端
    测试结束后自动清空数据
    """
    await redis.set("test_key", "test_value")
    value = await redis.get("test_key")

    assert value == "test_value"
```

**可用的Redis fixtures**:
- `redis`: 每个测试独立的Redis客户端，自动清理
- `redis_client`: Session级别的Redis客户端

#### 3. 测试数据Fixtures

```python
import pytest


@pytest.mark.asyncio
async def test_with_sample_data(sample_strategy):
    """
    sample_strategy: 预创建的示例策略
    """
    assert sample_strategy.name == "Test MA Strategy"
    # 使用示例数据进行测试
```

**可用的测试数据fixtures**:
- `sample_strategy`: 示例策略
- `sample_exchange_account`: 示例交易所账户
- `sample_backtest_run`: 示例回测运行

### API集成测试

```python
import pytest
from fastapi.testclient import TestClient
from squant.main import app
from squant.api.deps import get_session


@pytest.fixture
def client(db_session):
    """创建测试客户端，使用真实数据库"""
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()


def test_create_strategy_api(client, db_session):
    """测试API创建策略的完整流程"""
    # Arrange
    strategy_data = {
        "name": "API Test Strategy",
        "code": "def initialize(context): pass",
    }

    # Act - API请求
    response = client.post("/api/v1/strategies", json=strategy_data)

    # Assert - 验证响应
    assert response.status_code == 200
    created = response.json()
    assert created["name"] == strategy_data["name"]

    # Assert - 验证数据库持久化
    import asyncio
    from sqlalchemy import select
    from squant.models.strategy import Strategy

    async def verify():
        result = await db_session.execute(
            select(Strategy).where(Strategy.id == created["id"])
        )
        db_strategy = result.scalar_one()
        assert db_strategy.name == strategy_data["name"]

    asyncio.run(verify())
```

### WebSocket集成测试

```python
import pytest
import asyncio


@pytest.mark.asyncio
async def test_websocket_subscribe(redis, websocket_manager):
    """测试WebSocket订阅功能"""
    # Arrange
    received_messages = []

    async def message_handler(message):
        received_messages.append(message)

    # Act - 订阅频道
    await websocket_manager.subscribe("ticker:BTCUSDT", message_handler)

    # 发布消息
    await redis.publish("ticker:BTCUSDT", '{"price": 50000}')

    # 等待消息传递
    await asyncio.sleep(0.1)

    # Assert
    assert len(received_messages) > 0
    assert "price" in received_messages[0]
```

---

## 运行集成测试

### 基本命令

```bash
# 1. 启动测试环境
./scripts/test-env.sh start

# 2. 运行所有集成测试
./scripts/test-env.sh test -v

# 或者使用pytest直接运行
export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
export REDIS_URL="redis://localhost:6380/0"
uv run pytest tests/integration -v

# 3. 停止测试环境
./scripts/test-env.sh stop
```

### 选择性运行

```bash
# 只运行数据库测试
./scripts/test-env.sh test tests/integration/database -v

# 只运行API测试
./scripts/test-env.sh test tests/integration/api -v

# 运行特定测试文件
./scripts/test-env.sh test tests/integration/api/test_strategy_api.py -v

# 运行特定测试方法
./scripts/test-env.sh test tests/integration/api/test_strategy_api.py::TestStrategyAPIIntegration::test_create_strategy_end_to_end -v
```

### 带覆盖率报告

```bash
./scripts/test-env.sh test --cov=src/squant --cov-report=html
```

### 调试集成测试

```bash
# 显示print输出
./scripts/test-env.sh test -s

# 进入调试器
./scripts/test-env.sh test --pdb

# 只运行失败的测试
./scripts/test-env.sh test --lf
```

---

## 最佳实践

### 1. 测试隔离

✅ **好的做法**:
```python
@pytest.mark.asyncio
async def test_isolated(db_session):
    """每个测试在独立事务中运行"""
    strategy = Strategy(id=uuid4(), name="Test", code="...")
    db_session.add(strategy)
    await db_session.commit()

    # 测试结束后自动回滚，不影响其他测试
```

❌ **避免**:
```python
async def test_not_isolated(clean_db_session):
    """使用clean_db_session会影响其他测试"""
    # 数据会持久化，可能导致测试顺序依赖
```

### 2. 清理资源

✅ **好的做法**:
```python
@pytest.mark.asyncio
async def test_with_cleanup(redis):
    """redis fixture自动清理"""
    await redis.set("test_key", "value")
    # 测试结束后自动清理
```

使用fixture的yield语法:
```python
@pytest_asyncio.fixture
async def my_resource():
    resource = await create_resource()
    yield resource
    # 清理
    await resource.cleanup()
```

### 3. 避免测试顺序依赖

❌ **避免**:
```python
def test_step_1(db_session):
    """创建数据"""
    # 创建策略ID=1

def test_step_2(db_session):
    """依赖test_step_1的数据"""
    # 假设策略ID=1存在 - 错误！
```

✅ **好的做法**:
```python
def test_complete_scenario(db_session):
    """在单个测试中完成整个流程"""
    # 1. 创建数据
    strategy = create_strategy(db_session)

    # 2. 测试操作
    result = operate_on_strategy(strategy)

    # 3. 验证结果
    assert result is not None
```

或使用fixtures:
```python
@pytest_asyncio.fixture
async def existing_strategy(db_session):
    strategy = Strategy(...)
    db_session.add(strategy)
    await db_session.commit()
    return strategy

async def test_with_fixture(existing_strategy):
    # 使用fixture提供的数据
    assert existing_strategy.id is not None
```

### 4. 合理使用标记

```python
# 标记慢速测试
@pytest.mark.slow
async def test_performance():
    pass

# 标记需要交易所凭证的测试
@pytest.mark.exchange
async def test_real_exchange():
    pass

# 运行时跳过慢速测试
# pytest tests/integration -v -m "not slow"
```

### 5. 事务控制

```python
@pytest.mark.asyncio
async def test_transaction_commit(db_session):
    """测试需要提交才能看到的效果"""
    strategy = Strategy(...)
    db_session.add(strategy)
    await db_session.commit()  # 显式提交

    # 刷新获取最新数据
    await db_session.refresh(strategy)
    assert strategy.created_at is not None


@pytest.mark.asyncio
async def test_transaction_rollback(db_session):
    """测试回滚"""
    strategy = Strategy(...)
    db_session.add(strategy)

    await db_session.rollback()  # 回滚

    # 策略不应该存在
    result = await db_session.execute(
        select(Strategy).where(Strategy.name == strategy.name)
    )
    assert result.scalar_one_or_none() is None
```

### 6. 异步测试注意事项

```python
# ✅ 正确使用asyncio
@pytest.mark.asyncio
async def test_async_operation(db_session):
    result = await some_async_function()
    assert result is not None


# ❌ 不要在同步测试中使用async/await
def test_sync_with_async(db_session):
    # 错误！不能在同步函数中await
    result = await some_async_function()


# ✅ 如果必须在同步上下文中运行异步代码
def test_sync_context(db_session):
    import asyncio

    async def async_work():
        return await some_async_function()

    result = asyncio.run(async_work())
    assert result is not None
```

---

## 常见问题

### 1. 数据库连接错误

**问题**: `psycopg.OperationalError: could not connect to server`

**解决**:
```bash
# 检查测试环境是否启动
./scripts/test-env.sh status

# 检查PostgreSQL健康状态
docker compose -f docker-compose.test.yml exec postgres-test pg_isready

# 查看PostgreSQL日志
./scripts/test-env.sh logs postgres-test

# 重启测试环境
./scripts/test-env.sh restart
```

### 2. 测试数据污染

**问题**: 测试A通过，但测试B失败，因为有测试A的残留数据

**解决**:
```bash
# 重置数据库
./scripts/test-env.sh reset-db

# 或者确保使用db_session fixture（自动回滚）
@pytest.mark.asyncio
async def test_isolated(db_session):  # 使用db_session
    # 测试代码
    pass
```

### 3. Redis数据未清理

**问题**: Redis中有之前测试的数据

**解决**:
```bash
# 清空Redis
./scripts/test-env.sh clear-redis

# 或者在代码中使用redis fixture（自动清理）
@pytest.mark.asyncio
async def test_redis(redis):  # 使用redis fixture
    # 测试代码
    pass
```

### 4. 测试超时

**问题**: 测试一直运行不结束

**解决**:
```python
# 添加超时限制
@pytest.mark.timeout(30)  # 30秒超时
async def test_long_running():
    pass
```

### 5. 端口冲突

**问题**: `port is already allocated`

**解决**:
```bash
# 检查端口占用
lsof -i :5433
lsof -i :6380

# 停止占用端口的服务
./scripts/dev.sh stop  # 停止开发环境

# 或者修改docker-compose.test.yml使用不同端口
```

---

## 进阶话题

### 并行运行集成测试

```bash
# 安装pytest-xdist
uv add --dev pytest-xdist

# 并行运行（注意：可能导致数据库竞争）
./scripts/test-env.sh test -n 4

# 使用loadgroup避免并发访问同一资源
pytest tests/integration -n auto --dist loadgroup
```

### 测试覆盖率分析

```bash
# 生成覆盖率报告
./scripts/test-env.sh test --cov=src/squant --cov-report=html

# 查看报告
open htmlcov/index.html

# 只看集成测试覆盖的代码
./scripts/test-env.sh test --cov=src/squant --cov-report=term-missing
```

### 性能基准测试

```python
import pytest
import time


@pytest.mark.slow
@pytest.mark.asyncio
async def test_bulk_insert_performance(db_session):
    """测试批量插入性能"""
    start = time.time()

    # 插入1000条记录
    strategies = [
        Strategy(id=uuid4(), name=f"Strategy {i}", code="...")
        for i in range(1000)
    ]
    for s in strategies:
        db_session.add(s)
    await db_session.commit()

    duration = time.time() - start

    # 应该在合理时间内完成
    assert duration < 5.0  # 5秒内
    print(f"Inserted 1000 records in {duration:.2f}s")
```

---

## 相关文档

- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 测试最佳实践
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - 问题排查
- [CI_SETUP.md](./CI_SETUP.md) - CI/CD集成

---

**最后更新**: 2026-01-30
**维护者**: Development Team
