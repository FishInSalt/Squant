# 端到端（E2E）测试

端到端测试验证完整的业务流程，从API调用到数据库持久化的完整链路。

## 测试范围

E2E测试专注于关键业务流程：

1. **回测流程** (`test_backtest_flow.py`)
   - 创建策略 → 配置回测 → 启动回测 → 查看结果

2. **模拟交易流程** (计划中)
   - 创建策略 → 启动模拟会话 → 接收实时数据 → 生成订单

3. **实盘交易流程** (计划中)
   - 配置交易所 → 创建策略 → 启动会话 → 订单生命周期

## 运行 E2E 测试

### 方式1: 使用 Docker（推荐）

```bash
# 1. 启动完整应用栈（Backend + Database + Redis）
docker compose -f docker-compose.test.yml --profile e2e up -d

# 2. 等待服务启动（约10-15秒）
sleep 15

# 3. 运行 E2E 测试
uv run pytest tests/e2e -v

# 4. 停止服务
docker compose -f docker-compose.test.yml --profile e2e down
```

### 方式2: 本地运行

如果你在本地运行 Backend 服务器：

```bash
# 1. 启动测试环境（只启动 Database + Redis）
./scripts/test-env.sh start

# 2. 在另一个终端启动 Backend
./scripts/dev.sh backend

# 3. 运行 E2E 测试
uv run pytest tests/e2e -v

# 4. 停止服务
./scripts/test-env.sh stop
```

## 测试标记

E2E 测试使用以下 pytest 标记：

- `@pytest.mark.e2e` - 所有E2E测试（自动添加）
- `@pytest.mark.slow` - 耗时较长的测试（>10秒）

运行特定标记的测试：

```bash
# 只运行非slow的E2E测试
uv run pytest tests/e2e -v -m "e2e and not slow"

# 只运行slow测试
uv run pytest tests/e2e -v -m "slow"
```

## 编写 E2E 测试

### 测试结构

```python
import pytest

pytestmark = pytest.mark.e2e

class TestSomeFlow:
    @pytest.mark.asyncio
    async def test_complete_workflow(self, api_client):
        # 1. 通过 API 创建资源
        response = await api_client.post("/api/v1/resource", json=data)
        assert response.status_code == 200

        # 2. 验证资源创建成功
        resource_id = response.json()["id"]

        # 3. 执行业务操作
        response = await api_client.post(f"/api/v1/resource/{resource_id}/action")
        assert response.status_code == 200

        # 4. 验证结果
        response = await api_client.get(f"/api/v1/resource/{resource_id}")
        assert response.json()["status"] == "expected_status"
```

### 可用的 Fixtures

#### HTTP Client
- `api_client` - AsyncClient，用于调用 API
- `api_base_url` - API 基础 URL

#### 测试数据
- `test_strategy_data` - 示例策略数据
- `test_backtest_config` - 回测配置
- `cleanup_strategies` - 自动清理创建的策略

#### 辅助函数
- `wait_for_backtest(api_client, run_id, timeout)` - 等待回测完成
- `assert_backtest_metrics(metrics)` - 验证回测指标

#### 数据库和 Redis（从集成测试继承）
- `db_session` - 数据库 session
- `redis` - Redis 客户端
- `test_settings` - 测试配置

## 最佳实践

### 1. 测试隔离

每个测试应该独立运行，不依赖其他测试的状态：

```python
@pytest.mark.asyncio
async def test_something(self, api_client, cleanup_strategies):
    # ✅ 创建自己需要的数据
    response = await api_client.post("/api/v1/strategies", json=data)
    strategy_id = response.json()["id"]
    cleanup_strategies(strategy_id)  # 注册清理

    # 执行测试...
```

### 2. 合理的超时

为长时间运行的操作设置合理的超时：

```python
# ✅ 设置足够的超时时间
completed_run = await wait_for_backtest(api_client, run_id, timeout=120.0)

# ❌ 避免无限等待
while True:
    await asyncio.sleep(1.0)  # 可能永远等待
```

### 3. 清晰的断言消息

提供清晰的错误信息，便于调试：

```python
# ✅ 包含上下文信息
assert response.status_code == 200, \
    f"Failed to create strategy: {response.text}"

# ❌ 缺少上下文
assert response.status_code == 200
```

### 4. 测试真实的业务场景

E2E 测试应该模拟真实用户操作：

```python
# ✅ 完整的业务流程
async def test_user_creates_and_runs_backtest(self, api_client):
    # 1. 用户创建策略
    # 2. 用户配置回测参数
    # 3. 用户启动回测
    # 4. 用户查看结果

# ❌ 测试单个API端点
async def test_create_strategy(self, api_client):
    response = await api_client.post(...)
    assert response.status_code == 200
```

## 调试技巧

### 1. 查看 API 响应

```python
response = await api_client.post("/api/v1/resource", json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
```

### 2. 使用 pytest 的详细输出

```bash
# 显示 print 输出
uv run pytest tests/e2e -v -s

# 显示完整的 traceback
uv run pytest tests/e2e -v --tb=long
```

### 3. 检查服务日志

```bash
# Docker 方式
docker compose -f docker-compose.test.yml --profile e2e logs app-test

# 本地方式
tail -f logs/app.log
```

### 4. 进入失败时的调试器

```bash
uv run pytest tests/e2e --pdb -s
```

## 性能考虑

E2E 测试比单元测试慢，因为它们涉及真实的网络调用和数据库操作。

### 预期耗时

- 简单测试（CRUD操作）: 1-3秒
- 回测流程: 10-60秒（取决于回测时长）
- 模拟/实盘交易: 30-120秒

### 优化建议

1. **并行运行**（谨慎）:
   ```bash
   # E2E测试通常不适合并行，因为共享数据库
   # 但可以在不同的环境中并行运行
   ```

2. **使用较短的时间范围**:
   ```python
   # ✅ 测试用7天数据
   start_time = end_time - timedelta(days=7)

   # ❌ 避免使用很长的时间范围
   start_time = end_time - timedelta(days=365)
   ```

3. **跳过 slow 测试**:
   ```bash
   # 快速验证
   uv run pytest tests/e2e -v -m "e2e and not slow"
   ```

## 故障排查

### 问题1: API server not available

**错误**: `pytest.skip: API server not available`

**解决**:
```bash
# 检查服务是否启动
docker compose -f docker-compose.test.yml --profile e2e ps

# 检查服务健康状态
curl http://localhost:8001/health
```

### 问题2: 测试超时

**错误**: `Task did not complete within 60s`

**解决**:
- 增加超时时间
- 检查回测配置（减少时间范围）
- 查看服务日志确认是否有错误

### 问题3: 数据库连接错误

**错误**: `Must use test database for E2E tests`

**解决**:
```bash
# 确保设置了正确的环境变量
export TESTING_DB_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
```

## 下一步

- [ ] 添加 Paper Trading 流程测试
- [ ] 添加 Live Trading 流程测试（使用测试网）
- [ ] 添加 WebSocket 实时数据流测试
- [ ] 集成到 CI/CD 流程
- [ ] 添加性能基准测试

---

**维护者**: Development Team
**最后更新**: 2026-01-30
