# 测试问题排查指南

本文档记录了Squant项目测试过程中遇到的常见问题及解决方案。

## 目录

- [严重问题 🚨](#严重问题-)
- [异步测试问题](#异步测试问题)
- [Mock相关问题](#mock相关问题)
- [Fixture问题](#fixture问题)
- [数据库测试问题](#数据库测试问题)
- [API测试问题](#api测试问题)
- [覆盖率相关](#覆盖率相关)

---

## 严重问题 🚨

### 问题1: 测试导致系统内存溢出崩溃

**症状**:
- 运行测试时系统完全卡死
- 内存使用率迅速飙升至100%
- Linux系统崩溃，需要硬重启
- 测试进程无法被kill

**发生时间**: 2026-01-30，Phase 10 WebSocket测试期间，发生两次

**根本原因**:

测试代码错误地mock了`asyncio.sleep()`，导致后台异步任务中的`while`循环变成无限快速循环：

```python
# ❌ 危险的测试代码
async def test_gateway_run():
    with patch("squant.websocket.handlers.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.return_value = None  # sleep立即返回
        await gateway.run()  # 启动3个后台任务

# 在 websocket/handlers.py 中的实际代码:
async def _receive_from_redis(self):
    while self._running:  # 永远为True
        message = await self._pubsub.get_message()
        if message is None:
            await asyncio.sleep(0.1)  # 被mock为立即返回！
            continue  # 无限快速循环，CPU和内存飙升
```

**为什么如此危险**:

1. `asyncio.sleep(0.1)`在生产代码中用于限流，防止循环占用过多CPU
2. Mock使其立即返回后，循环每秒执行数百万次
3. 三个后台任务同时进入无限循环
4. 内存不断分配但无法及时回收
5. 系统OOM (Out of Memory) killer来不及介入

**解决方案**:

1. **立即删除所有此类测试**：
   ```python
   # 删除以下测试类和方法
   - TestWebSocketGatewayRun (整个类)
   - TestWebSocketGatewayHeartbeat (大部分测试)
   - 任何调用 gateway.run() 的测试
   - 任何测试 _redis_heartbeat() 的测试
   ```

2. **安全的测试方法**：
   ```python
   # ✅ 测试前先启动任务，然后立即取消
   async def test_gateway_safe():
       task = asyncio.create_task(gateway.run())
       await asyncio.sleep(0.01)  # 让任务启动
       task.cancel()
       try:
           await task
       except asyncio.CancelledError:
           pass  # 预期的取消

   # ✅ 或者只测试单个迭代，不测试循环
   async def test_receive_single_message():
       # Mock pubsub.get_message() 返回一次后抛出异常
       gateway._pubsub.get_message = AsyncMock(
           side_effect=[{"data": b"test"}, asyncio.CancelledError()]
       )
       # 测试会在第一次迭代后退出
   ```

3. **使用集成测试代替单元测试**：
   - WebSocket长期运行任务应该用集成测试
   - 在真实环境中测试连接、订阅、断线重连
   - 使用Docker容器隔离测试环境

**预防措施**:

- ✅ 代码审查时特别注意mock `asyncio.sleep()`
- ✅ 避免测试包含`while True`或`while self._running`的方法
- ✅ 测试异步任务前先评估风险
- ✅ 在虚拟机或容器中运行可疑测试
- ✅ 使用超时机制：`pytest.mark.timeout(5)`

**影响范围**:

- 直接影响：开发机器崩溃，未保存工作丢失
- 间接影响：数据库连接泄漏，需要重启PostgreSQL
- 时间损失：每次崩溃恢复需要5-10分钟

**教训总结**:

> 🚨 **永远不要mock核心异步原语**（sleep, wait, Lock等），它们的时间特性是代码正确性的一部分。

---

## 异步测试问题

### 问题2: RuntimeError: Event loop is closed

**症状**:
```
RuntimeError: Event loop is closed
Exception ignored in: <function _ProactorBasePipeTransport.__del__ at ...>
```

**原因**:
- pytest-asyncio配置错误
- 同一个event loop被多次使用
- Fixture作用域不匹配

**解决方案**:

1. 检查`pytest.ini`配置：
   ```ini
   [pytest]
   asyncio_mode = auto
   asyncio_default_fixture_loop_scope = function
   ```

2. 确保async fixture作用域正确：
   ```python
   # ✅ Function scope - 每个测试独立
   @pytest.fixture
   async def async_client():
       async with httpx.AsyncClient() as client:
           yield client

   # ❌ Session scope - 会导致loop问题
   @pytest.fixture(scope="session")  # 不要用session
   async def async_client():
       ...
   ```

3. 避免手动创建event loop：
   ```python
   # ❌ 不要这样
   loop = asyncio.new_event_loop()
   asyncio.set_event_loop(loop)

   # ✅ 让pytest-asyncio管理
   async def test_something():
       await async_operation()
   ```

### 问题3: 测试超时但不报错

**症状**:
- 测试一直运行不结束
- 没有错误信息
- 需要手动Ctrl+C终止

**原因**:
- 异步任务没有正确清理
- 后台任务仍在运行
- WebSocket连接未关闭

**解决方案**:

1. 使用超时装饰器：
   ```python
   import pytest

   @pytest.mark.timeout(5)  # 5秒超时
   async def test_long_operation():
       await some_operation()
   ```

2. 正确清理资源：
   ```python
   @pytest.fixture
   async def gateway():
       gw = WebSocketGateway(...)
       yield gw
       # 清理
       if gw._running:
           gw._running = False
       # 取消所有任务
       for task in gw._tasks:
           if not task.done():
               task.cancel()
       await asyncio.gather(*gw._tasks, return_exceptions=True)
   ```

3. 使用上下文管理器：
   ```python
   async def test_with_cleanup():
       async with create_gateway() as gateway:
           # 测试代码
           pass
       # 自动清理
   ```

---

## Mock相关问题

### 问题4: Mock没有生效

**症状**:
- 测试仍然调用真实方法
- 断言失败：`mock_method.assert_called_once()` → AssertionError

**原因**:
- Mock路径错误
- 在错误的位置patch
- Import顺序问题

**解决方案**:

1. **在使用的地方patch，不是定义的地方**：
   ```python
   # models/order.py
   from datetime import datetime

   def create_order():
       return datetime.now()  # 使用 datetime.now

   # ❌ 错误 - patch定义的地方
   @patch('datetime.datetime')
   def test_create_order(mock_dt):
       ...

   # ✅ 正确 - patch使用的地方
   @patch('models.order.datetime')
   def test_create_order(mock_dt):
       mock_dt.now.return_value = datetime(2024, 1, 1)
       order = create_order()
       assert order == datetime(2024, 1, 1)
   ```

2. **检查import方式**：
   ```python
   # service.py
   from utils import helper  # 导入模块
   result = helper.process()  # 通过模块调用

   # ✅ 正确
   @patch('service.helper.process')  # patch service模块中的helper

   # ---

   # service.py
   from utils.helper import process  # 直接导入函数
   result = process()

   # ✅ 正确
   @patch('service.process')  # patch service模块中的process
   ```

3. **使用dependency_overrides替代patch**（FastAPI）：
   ```python
   # ✅ 推荐方式
   @pytest.fixture
   def client(mock_session):
       async def override_get_session():
           yield mock_session
       app.dependency_overrides[get_session] = override_get_session
       yield TestClient(app)
       app.dependency_overrides.clear()
   ```

### 问题5: AsyncMock调用后返回值错误

**症状**:
```python
mock_method.return_value = "expected"
result = await mock_method()  # result是一个coroutine，不是"expected"
```

**原因**:
- 使用了MagicMock而不是AsyncMock
- return_value和side_effect混用

**解决方案**:

1. **异步方法必须用AsyncMock**：
   ```python
   # ✅ 正确
   mock_service = MagicMock()
   mock_service.get_data = AsyncMock(return_value={"key": "value"})

   result = await mock_service.get_data()  # {"key": "value"}
   ```

2. **side_effect用于多次调用**：
   ```python
   mock_service.get_data = AsyncMock(
       side_effect=[
           {"first": "call"},
           {"second": "call"},
           Exception("third call fails")
       ]
   )

   result1 = await mock_service.get_data()  # {"first": "call"}
   result2 = await mock_service.get_data()  # {"second": "call"}
   with pytest.raises(Exception):
       await mock_service.get_data()  # 抛出异常
   ```

3. **检查是否正确await**：
   ```python
   # ❌ 错误 - 没有await
   result = mock_async_method()  # <coroutine object>

   # ✅ 正确
   result = await mock_async_method()
   ```

---

## Fixture问题

### 问题6: Fixture冲突或重复定义

**症状**:
```
fixture 'mock_session' not found
fixture 'mock_session' already defined
```

**原因**:
- Fixture在多个conftest.py中重复定义
- Fixture作用域冲突
- Import循环

**解决方案**:

1. **使用层级化的conftest.py**：
   ```
   tests/
   ├── conftest.py              # 全局fixtures (session, db, redis)
   ├── unit/
   │   ├── conftest.py         # 单元测试fixtures (mocks)
   │   ├── api/
   │   │   ├── conftest.py    # API测试fixtures (client)
   │   │   └── v1/
   │   │       └── test_*.py
   │   └── services/
   │       ├── conftest.py    # Service测试fixtures
   │       └── test_*.py
   ```

2. **避免fixture重复定义**：
   ```python
   # conftest.py - 只定义一次
   @pytest.fixture
   def mock_exchange():
       mock = MagicMock()
       # 配置mock
       return mock

   # test文件中使用，不要重新定义
   def test_something(mock_exchange):
       # 直接使用
       pass
   ```

3. **使用fixture参数化而不是重复定义**：
   ```python
   @pytest.fixture(params=["okx", "binance", "bybit"])
   def exchange_name(request):
       return request.param

   def test_exchange(exchange_name):
       # 测试会运行3次，每次不同参数
       pass
   ```

### 问题7: Fixture清理不当导致状态泄漏

**症状**:
- 测试A通过，但测试B失败
- 改变测试顺序后结果不同
- Mock被之前的测试修改

**原因**:
- Fixture没有正确清理
- 使用module或class scope但未重置状态
- app.dependency_overrides未清理

**解决方案**:

1. **使用yield进行清理**：
   ```python
   @pytest.fixture
   def client(mock_session):
       # Setup
       app.dependency_overrides[get_session] = lambda: mock_session
       client = TestClient(app)

       yield client

       # Teardown - 清理
       app.dependency_overrides.clear()
       mock_session.reset_mock()
   ```

2. **autouse fixture自动清理**：
   ```python
   @pytest.fixture(autouse=True)
   def reset_overrides():
       """每个测试后自动清理dependency overrides"""
       yield
       app.dependency_overrides.clear()
   ```

3. **检查module/class scope fixture**：
   ```python
   @pytest.fixture(scope="class")
   def shared_resource():
       resource = SomeResource()
       resource.reset()  # 初始化状态
       yield resource
       resource.cleanup()  # 清理
   ```

---

## 数据库测试问题

### 问题8: 数据库连接泄漏

**症状**:
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached
too many clients already
```

**原因**:
- Session未关闭
- 事务未提交或回滚
- 连接池配置太小

**解决方案**:

1. **正确使用async session**：
   ```python
   @pytest.fixture
   async def session():
       async with async_session_maker() as session:
           async with session.begin():
               yield session
               await session.rollback()  # 测试后回滚
   ```

2. **Mock session时确保异步方法**：
   ```python
   @pytest.fixture
   def mock_session():
       session = MagicMock()
       session.execute = AsyncMock()
       session.commit = AsyncMock()
       session.rollback = AsyncMock()
       session.close = AsyncMock()
       session.__aenter__ = AsyncMock(return_value=session)
       session.__aexit__ = AsyncMock()
       return session
   ```

3. **集成测试中使用事务回滚**：
   ```python
   @pytest.fixture
   async def db_session():
       async with engine.begin() as conn:
           async with AsyncSession(bind=conn) as session:
               # 开启嵌套事务
               await conn.begin_nested()

               yield session

               # 测试后回滚
               await session.rollback()
   ```

### 问题9: 数据库测试数据冲突

**症状**:
```
IntegrityError: duplicate key value violates unique constraint
```

**原因**:
- 测试间共享数据
- 未清理前一个测试的数据
- UUID或ID冲突

**解决方案**:

1. **使用事务隔离**：
   ```python
   @pytest.fixture(autouse=True)
   async def reset_db():
       """每个测试后清空表"""
       yield
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.drop_all)
           await conn.run_sync(Base.metadata.create_all)
   ```

2. **使用唯一ID**：
   ```python
   import uuid

   @pytest.fixture
   def unique_strategy_id():
       return uuid.uuid4()

   def test_create_strategy(unique_strategy_id):
       strategy = Strategy(id=unique_strategy_id, name="Test")
       ...
   ```

3. **使用工厂模式**：
   ```python
   class StrategyFactory:
       _counter = 0

       @classmethod
       def create(cls, **kwargs):
           cls._counter += 1
           defaults = {
               "name": f"Strategy_{cls._counter}",
               "id": uuid.uuid4(),
           }
           defaults.update(kwargs)
           return Strategy(**defaults)

   def test_create():
       s1 = StrategyFactory.create()
       s2 = StrategyFactory.create()  # 不会冲突
   ```

---

## API测试问题

### 问题10: TestClient返回422 Unprocessable Entity

**症状**:
```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "side"],
      "msg": "Input should be 'buy' or 'sell'"
    }
  ]
}
```

**原因**:
- 请求数据不符合Pydantic schema
- Enum值大小写错误
- 缺少必需字段

**解决方案**:

1. **检查Enum定义和使用**：
   ```python
   # models/enums.py
   class OrderSide(str, Enum):
       BUY = "buy"   # 值是小写
       SELL = "sell"

   # ❌ 错误 - 使用大写
   payload = {"side": "BUY"}  # 422错误

   # ✅ 正确 - 使用小写
   payload = {"side": "buy"}
   ```

2. **使用schema验证测试数据**：
   ```python
   from schemas.order import OrderCreateRequest

   @pytest.fixture
   def valid_order_request():
       # 先用schema验证
       data = {
           "symbol": "BTC/USDT",
           "side": "buy",
           "type": "limit",
           "amount": "0.1",
           "price": "50000"
       }
       # 确保能通过验证
       OrderCreateRequest(**data)
       return data
   ```

3. **检查响应帮助调试**：
   ```python
   response = client.post("/api/v1/orders", json=payload)
   if response.status_code != 200:
       print(response.json())  # 打印详细错误
   assert response.status_code == 200
   ```

### 问题11: Decimal序列化问题

**症状**:
```python
assert response.json()["available"] == 1.5
# AssertionError: assert '1.5' == 1.5
```

**原因**:
- Pydantic Decimal字段被序列化为字符串（默认行为）
- 直接比较字符串和数字

**解决方案**:

1. **转换为float比较**：
   ```python
   data = response.json()
   assert float(data["available"]) == 1.5
   assert float(data["total"]) == pytest.approx(2.5)
   ```

2. **配置schema序列化**：
   ```python
   from pydantic import BaseModel, ConfigDict

   class BalanceResponse(BaseModel):
       model_config = ConfigDict(
           json_encoders={Decimal: float}  # Decimal序列化为float
       )

       available: Decimal
       total: Decimal
   ```

3. **使用字符串比较**：
   ```python
   assert data["available"] == "1.5"
   assert Decimal(data["available"]) == Decimal("1.5")
   ```

---

## 覆盖率相关

### 问题12: 覆盖率报告不准确

**症状**:
- 明明测试通过，但覆盖率显示0%
- 某些文件没有出现在报告中

**原因**:
- 源码路径配置错误
- .coveragerc配置问题
- 并行测试导致覆盖率合并失败

**解决方案**:

1. **检查.coveragerc配置**：
   ```ini
   [run]
   source = src/squant
   omit =
       */tests/*
       */migrations/*
       */__pycache__/*

   [report]
   exclude_lines =
       pragma: no cover
       def __repr__
       raise AssertionError
       raise NotImplementedError
       if TYPE_CHECKING:
   ```

2. **运行覆盖率测试**：
   ```bash
   # 生成覆盖率报告
   uv run pytest --cov=src/squant --cov-report=html

   # 查看详细报告
   open htmlcov/index.html

   # 只看某个模块
   uv run pytest tests/unit/services/ --cov=src/squant/services
   ```

3. **并行测试覆盖率**：
   ```bash
   # 使用pytest-xdist并行测试
   uv run pytest -n auto --cov=src/squant --cov-report=html

   # 合并覆盖率数据
   coverage combine
   coverage report
   ```

### 问题13: 达到100%覆盖率但代码仍有bug

**问题**:
- 覆盖率100%不代表测试质量高
- 可能只是执行了代码，没有验证行为

**解决方案**:

1. **关注分支覆盖率**：
   ```bash
   uv run pytest --cov=src/squant --cov-branch --cov-report=term-missing
   ```

2. **测试边界条件和异常情况**：
   ```python
   # ❌ 只测试happy path
   def test_divide():
       assert divide(10, 2) == 5

   # ✅ 测试异常情况
   def test_divide_by_zero():
       with pytest.raises(ZeroDivisionError):
           divide(10, 0)

   def test_divide_negative():
       assert divide(-10, 2) == -5
   ```

3. **使用mutation testing检查测试质量**：
   ```bash
   # 安装mutmut
   pip install mutmut

   # 运行mutation testing
   mutmut run --paths-to-mutate=src/squant/services
   ```

---

## 调试技巧

### 使用pytest调试选项

```bash
# 显示print输出
pytest -s

# 在第一个失败处停止
pytest -x

# 显示最详细的错误信息
pytest -vv

# 只运行失败的测试
pytest --lf

# 运行上次失败和新修改的测试
pytest --ff

# 显示测试执行时间
pytest --durations=10

# 进入调试器
pytest --pdb
```

### 在测试中使用调试器

```python
def test_something():
    result = complex_operation()

    # 进入调试器
    import pdb; pdb.set_trace()

    assert result == expected
```

### 查看Mock调用

```python
def test_with_mock_inspection():
    mock_service.method.return_value = "result"

    # 调用
    do_something(mock_service)

    # 检查调用
    print(mock_service.method.call_count)
    print(mock_service.method.call_args_list)
    print(mock_service.method.called)

    # 断言
    mock_service.method.assert_called_once_with(arg1="value")
```

---

## 快速参考

### 常见错误快速查找

| 错误信息 | 可能原因 | 章节 |
|---------|---------|------|
| RuntimeError: Event loop is closed | pytest-asyncio配置 | [问题2](#问题2-runtimeerror-event-loop-is-closed) |
| 测试超时不结束 | 资源未清理 | [问题3](#问题3-测试超时但不报错) |
| Mock没有生效 | Patch路径错误 | [问题4](#问题4-mock没有生效) |
| fixture not found | Conftest位置错误 | [问题6](#问题6-fixture冲突或重复定义) |
| QueuePool limit reached | 连接泄漏 | [问题8](#问题8-数据库连接泄漏) |
| 422 Unprocessable Entity | Schema验证失败 | [问题10](#问题10-testclient返回422-unprocessable-entity) |
| assert '1.5' == 1.5 | Decimal序列化 | [问题11](#问题11-decimal序列化问题) |
| 系统崩溃 | Mock asyncio.sleep | [问题1](#问题1-测试导致系统内存溢出崩溃) |

---

## 获取帮助

如果遇到本文档未涵盖的问题：

1. 查看[TESTING_GUIDE.md](./TESTING_GUIDE.md)了解最佳实践
2. 运行`pytest --fixtures`查看可用的fixtures
3. 使用`pytest -vv`获取详细错误信息
4. 检查[pytest官方文档](https://docs.pytest.org/)
5. 搜索项目issue或创建新issue

---

**最后更新**: 2026-01-30
**维护者**: Development Team
