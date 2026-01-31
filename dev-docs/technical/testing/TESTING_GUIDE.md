# Squant测试编写指南

## 目录
- [测试分类](#测试分类)
- [危险操作清单](#危险操作清单)
- [Mock最佳实践](#mock最佳实践)
- [测试fixture指南](#测试fixture指南)
- [测试命名规范](#测试命名规范)
- [断言最佳实践](#断言最佳实践)
- [常用测试模式](#常用测试模式)

## 测试分类

### 单元测试 (Unit Tests)
- **位置**: `tests/unit/`
- **目的**: 测试单个函数/类的行为
- **特点**: 快速、隔离、无外部依赖
- **运行**: `uv run pytest tests/unit/`

**示例**:
```python
def test_calculate_profit():
    """测试利润计算函数"""
    result = calculate_profit(buy_price=100, sell_price=110, amount=10)
    assert result == 100
```

### 集成测试 (Integration Tests)
- **位置**: `tests/integration/`
- **目的**: 测试模块间交互
- **特点**: 需要真实依赖（数据库、Redis）
- **运行**: `uv run pytest tests/integration/`

**示例**:
```python
@pytest.mark.integration
async def test_order_service_with_database(db_session):
    """测试订单服务与数据库交互"""
    service = OrderService(db_session, mock_exchange)
    order = await service.create_order(...)

    # 验证数据已持久化
    fetched = await service.get_order(order.id)
    assert fetched.id == order.id
```

### 端到端测试 (E2E Tests)
- **位置**: `tests/e2e/`
- **目的**: 测试完整业务流程
- **特点**: 运行完整系统、真实API调用
- **运行**: `uv run pytest tests/e2e/`

**示例**:
```python
@pytest.mark.e2e
async def test_complete_backtest_flow(api_client):
    """测试从创建策略到完成回测的完整流程"""
    # 1. 创建策略
    strategy = await create_strategy(api_client)
    # 2. 启动回测
    run = await start_backtest(api_client, strategy.id)
    # 3. 等待完成
    result = await wait_for_completion(api_client, run.id)
    # 4. 验证结果
    assert result.status == "completed"
```

## 危险操作清单 🚨

### 绝对禁止的操作

#### ❌ 1. Mock asyncio.sleep()

**错误示例**:
```python
# 🔥 危险！会导致无限循环和系统崩溃
async def test_heartbeat():
    with patch('asyncio.sleep', return_value=None):
        await gateway._redis_heartbeat()  # while循环无限快速执行
```

**原因**: 当`asyncio.sleep()`被mock为立即返回时，包含`while`循环的异步任务会变成CPU密集型无限循环，瞬间耗尽系统资源。

**正确做法**:
```python
# ✅ 安全：测试任务可以被取消
async def test_heartbeat_cancellation():
    task = asyncio.create_task(gateway._redis_heartbeat())
    await asyncio.sleep(0.01)  # 真实的sleep
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert task.done()
```

#### ❌ 2. 测试包含无限循环的方法

**危险方法特征**:
```python
async def _receive_from_redis(self):
    """⚠️ 包含无限循环 - 不要直接测试"""
    while self._running:
        message = await self._pubsub.get_message()
        if message is None:
            await asyncio.sleep(0.1)  # 如果被mock，循环失控
            continue
        # 处理消息...
```

**正确做法**: 不测试循环本身，而是测试循环内的逻辑：
```python
# ✅ 测试消息处理逻辑，而不是循环
async def test_message_handling():
    gateway = WebSocketGateway(mock_ws, mock_manager)

    # 直接测试处理逻辑
    message = {"type": "ticker", "data": {...}}
    await gateway._handle_message(message)

    # 验证处理结果
    mock_ws.send_json.assert_called_once()
```

#### ❌ 3. 调用启动后台任务的方法

**危险示例**:
```python
# ❌ 会创建多个不受控的后台任务
async def test_gateway_run():
    gateway = WebSocketGateway(mock_ws, mock_manager)
    await gateway.run()  # 启动3个后台任务！
```

**正确做法**: 使用集成测试而不是单元测试：
```python
# ✅ 在集成测试中测试完整流程
@pytest.mark.integration
async def test_gateway_connection_lifecycle():
    # 使用真实的WebSocket客户端连接
    async with websockets.connect("ws://localhost:8000/ws") as ws:
        await ws.send(json.dumps({"type": "subscribe", "channel": "ticker:BTC/USDT"}))
        response = await ws.recv()
        assert json.loads(response)["type"] == "subscribed"
```

#### ❌ 4. Mock整个异步行为

**错误示例**:
```python
# ❌ Mock了异步行为本身
mock_exchange.connect = AsyncMock()
# 如果connect内部有循环，仍然可能有问题
```

**正确做法**: 只mock返回值：
```python
# ✅ 只mock结果，不mock行为
mock_exchange.get_ticker = AsyncMock(
    return_value=Ticker(symbol="BTC/USDT", last=50000)
)
```

### 警告级别操作 ⚠️

这些操作可以做，但要特别小心：

#### ⚠️ 1. 测试WebSocket连接

```python
# 需要确保连接会被关闭
async def test_websocket_send():
    gateway = WebSocketGateway(mock_ws, mock_manager)
    # 设置短超时
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(gateway.run(), timeout=0.1)
```

#### ⚠️ 2. 测试定时任务

```python
# 使用真实但很短的间隔
async def test_periodic_task():
    task = PeriodicTask(interval=0.01)  # 10ms而不是10s
    await task.run_once()  # 只运行一次
```

## Mock最佳实践

### 1. Mock数据库操作

#### 基础Mock
```python
@pytest.fixture
def mock_session():
    """标准数据库session mock"""
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session
```

#### Mock查询结果
```python
async def test_list_orders(mock_session):
    # 设置查询返回值
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        mock_order1,
        mock_order2,
    ]
    mock_session.execute.return_value = mock_result

    # 执行测试
    service = OrderService(mock_session)
    orders = await service.list_orders()

    # 验证
    assert len(orders) == 2
```

#### Mock count查询
```python
async def test_count_orders(mock_session):
    # Mock count查询
    mock_result = MagicMock()
    mock_result.scalar.return_value = 42
    mock_session.execute.return_value = mock_result

    service = OrderService(mock_session)
    count = await service.count_orders()

    assert count == 42
```

### 2. Mock交易所API

#### 基础Mock
```python
@pytest.fixture
def mock_exchange():
    """标准交易所adapter mock"""
    exchange = MagicMock()
    exchange.get_ticker = AsyncMock()
    exchange.get_balance = AsyncMock()
    exchange.create_order = AsyncMock()
    exchange.cancel_order = AsyncMock()
    return exchange
```

#### Mock成功响应
```python
async def test_get_ticker_success(mock_exchange):
    # 设置返回值
    mock_exchange.get_ticker.return_value = Ticker(
        symbol="BTC/USDT",
        last=Decimal("50000"),
        bid=Decimal("49999"),
        ask=Decimal("50001"),
        volume=Decimal("1000"),
        timestamp=datetime.now(UTC),
    )

    service = MarketService(mock_exchange)
    ticker = await service.get_ticker("BTC/USDT")

    assert ticker.last == Decimal("50000")
```

#### Mock异常
```python
async def test_get_ticker_exchange_error(mock_exchange):
    # Mock抛出异常
    mock_exchange.get_ticker.side_effect = ExchangeAPIError("Rate limit")

    service = MarketService(mock_exchange)

    with pytest.raises(ExchangeAPIError):
        await service.get_ticker("BTC/USDT")
```

### 3. Mock时间相关

#### Mock datetime.now()
```python
from datetime import datetime, UTC

def test_create_with_timestamp():
    fixed_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    with patch('squant.services.order.datetime') as mock_dt:
        mock_dt.now.return_value = fixed_time
        mock_dt.UTC = UTC

        order = create_order(...)
        assert order.created_at == fixed_time
```

#### 不要Mock sleep
```python
# ❌ 错误
with patch('asyncio.sleep'):
    await long_running_task()

# ✅ 正确：使用真实但短的时间
await asyncio.sleep(0.01)  # 10ms
```

### 4. Mock Redis操作

```python
@pytest.fixture
def mock_redis():
    """标准Redis client mock"""
    redis = AsyncMock()
    redis.get = AsyncMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.publish = AsyncMock()
    return redis

async def test_cache_get(mock_redis):
    mock_redis.get.return_value = b'{"price": 50000}'

    cache = CacheService(mock_redis)
    price = await cache.get_price("BTC/USDT")

    assert price == 50000
```

## 测试Fixture指南

### Fixture作用域

```python
# 每个测试函数创建一次（默认）
@pytest.fixture
def mock_order():
    return create_mock_order()

# 每个测试类创建一次
@pytest.fixture(scope="class")
def shared_config():
    return load_config()

# 每个测试模块创建一次
@pytest.fixture(scope="module")
def database_connection():
    conn = create_connection()
    yield conn
    conn.close()

# 整个测试会话创建一次
@pytest.fixture(scope="session")
def test_environment():
    setup_environment()
    yield
    teardown_environment()
```

### Fixture依赖

```python
@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_exchange():
    return MagicMock()

@pytest.fixture
def order_service(mock_session, mock_exchange):
    """依赖其他fixtures"""
    account = MagicMock(id="test-account")
    return OrderService(mock_session, mock_exchange, account)

def test_create_order(order_service):
    """直接使用组合fixture"""
    order = await order_service.create_order(...)
```

### 参数化Fixture

```python
@pytest.fixture(params=["okx", "binance", "bybit"])
def exchange_name(request):
    """测试会针对每个参数运行一次"""
    return request.param

def test_exchange_adapter(exchange_name):
    """这个测试会运行3次"""
    adapter = create_adapter(exchange_name)
    assert adapter is not None
```

### Cleanup Fixture

```python
@pytest.fixture
def temp_strategy():
    """创建后自动清理"""
    strategy = create_strategy()
    yield strategy
    # cleanup代码在这里
    delete_strategy(strategy.id)
```

## 测试命名规范

### 测试函数命名

格式: `test_<功能>_<场景>_<预期结果>`

```python
# ✅ 好的命名
def test_create_order_with_valid_data_returns_order()
def test_create_order_with_invalid_symbol_raises_validation_error()
def test_list_orders_when_empty_returns_empty_list()
def test_cancel_order_when_already_filled_raises_error()

# ❌ 不好的命名
def test_order()  # 太模糊
def test_1()  # 无意义
def test_error()  # 不清楚什么错误
```

### 测试类命名

```python
# 按功能分组
class TestOrderCreation:
    def test_create_with_valid_data(self): ...
    def test_create_with_invalid_data(self): ...

class TestOrderCancellation:
    def test_cancel_open_order(self): ...
    def test_cancel_filled_order(self): ...

# 按API端点分组
class TestCreateEndpoint:
    def test_post_success(self): ...
    def test_post_validation_error(self): ...
```

## 断言最佳实践

### 基础断言

```python
# ✅ 明确的断言
assert order.status == OrderStatus.FILLED
assert order.amount == Decimal("0.1")
assert len(orders) == 3
assert response.status_code == 200

# ❌ 避免模糊断言
assert order  # 不清楚在检查什么
assert response  # 太模糊
```

### 浮点数比较

```python
# ✅ 使用近似比较
assert abs(price - 50000.0) < 0.01
# 或使用pytest.approx
assert price == pytest.approx(50000.0, rel=1e-4)

# ❌ 直接比较浮点数
assert price == 50000.0  # 可能因精度问题失败
```

### Decimal比较

```python
# ✅ Decimal精确比较
from decimal import Decimal
assert order.amount == Decimal("0.1")
assert order.price == Decimal("50000.00")

# ❌ 与float混用
assert order.amount == 0.1  # 可能精度问题
```

### 集合断言

```python
# ✅ 检查成员
assert "BTC/USDT" in symbols
assert order_id in [o.id for o in orders]

# ✅ 检查子集
assert set(result_ids).issubset(set(all_ids))

# ✅ 检查内容
assert set(symbols) == {"BTC/USDT", "ETH/USDT"}
```

### 异常断言

```python
# ✅ 检查异常类型和消息
with pytest.raises(ValidationError) as exc_info:
    create_order(invalid_data)

assert "symbol" in str(exc_info.value)

# ✅ 检查特定异常属性
with pytest.raises(OrderNotFoundError) as exc_info:
    get_order("invalid_id")

assert exc_info.value.order_id == "invalid_id"
```

### Mock调用断言

```python
# ✅ 验证调用
mock_exchange.create_order.assert_called_once()
mock_session.commit.assert_called()

# ✅ 验证参数
mock_exchange.create_order.assert_called_once_with(
    symbol="BTC/USDT",
    side=OrderSide.BUY,
    type=OrderType.LIMIT,
    amount=Decimal("0.1"),
)

# ✅ 验证未调用
mock_exchange.cancel_order.assert_not_called()
```

## 常用测试模式

### 1. Arrange-Act-Assert (AAA) 模式

```python
async def test_create_order():
    # Arrange (准备)
    service = OrderService(mock_session, mock_exchange, account)
    order_data = {
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "amount": Decimal("0.1"),
    }

    # Act (执行)
    order = await service.create_order(**order_data)

    # Assert (断言)
    assert order.id is not None
    assert order.symbol == "BTC/USDT"
    assert order.status == OrderStatus.SUBMITTED
```

### 2. Given-When-Then (BDD) 模式

```python
async def test_cancel_order():
    # Given: 有一个已提交的订单
    order = await create_order(status=OrderStatus.SUBMITTED)

    # When: 取消订单
    result = await service.cancel_order(order.id)

    # Then: 订单状态变为已取消
    assert result.status == OrderStatus.CANCELLED
```

### 3. 参数化测试

```python
@pytest.mark.parametrize("side,type,expected", [
    (OrderSide.BUY, OrderType.LIMIT, True),
    (OrderSide.BUY, OrderType.MARKET, True),
    (OrderSide.SELL, OrderType.LIMIT, True),
    (OrderSide.SELL, OrderType.MARKET, True),
])
def test_order_combinations(side, type, expected):
    result = is_valid_order(side, type)
    assert result == expected
```

### 4. 表格驱动测试

```python
test_cases = [
    # (input, expected_output, description)
    (100, 110, "profit"),
    (100, 100, "break even"),
    (100, 90, "loss"),
]

@pytest.mark.parametrize("buy,sell,expected", test_cases)
def test_pnl_calculation(buy, sell, expected):
    result = calculate_pnl(buy, sell)
    if expected == "profit":
        assert result > 0
    elif expected == "break even":
        assert result == 0
    else:
        assert result < 0
```

### 5. 测试数据构建器

```python
class OrderBuilder:
    """订单测试数据构建器"""

    def __init__(self):
        self.data = {
            "symbol": "BTC/USDT",
            "side": OrderSide.BUY,
            "type": OrderType.LIMIT,
            "amount": Decimal("0.1"),
            "price": Decimal("50000"),
        }

    def with_symbol(self, symbol: str):
        self.data["symbol"] = symbol
        return self

    def with_market_type(self):
        self.data["type"] = OrderType.MARKET
        self.data.pop("price", None)
        return self

    def build(self):
        return self.data

# 使用
def test_create_order():
    order_data = OrderBuilder().with_symbol("ETH/USDT").build()
    order = await service.create_order(**order_data)
```

## 测试组织

### 目录结构

```
tests/
├── unit/                    # 单元测试
│   ├── api/
│   ├── services/
│   ├── models/
│   └── utils/
├── integration/            # 集成测试
│   ├── test_database.py
│   └── test_redis.py
├── e2e/                    # 端到端测试
│   └── scenarios/
├── fixtures/               # 测试数据
│   ├── strategies/
│   └── market_data/
├── conftest.py            # 全局fixtures
└── templates/             # 测试模板
```

### conftest.py组织

```python
# tests/conftest.py - 全局fixtures

# tests/unit/conftest.py - 单元测试fixtures

# tests/unit/services/conftest.py - Services层fixtures
```

## 运行测试

### 基本命令

```bash
# 运行所有测试
uv run pytest

# 运行指定目录
uv run pytest tests/unit/

# 运行指定文件
uv run pytest tests/unit/services/test_order.py

# 运行指定测试
uv run pytest tests/unit/services/test_order.py::test_create_order

# 运行匹配名称的测试
uv run pytest -k "test_create"
```

### 有用的选项

```bash
# 显示详细输出
uv run pytest -v

# 显示打印语句
uv run pytest -s

# 失败时立即停止
uv run pytest -x

# 显示最慢的10个测试
uv run pytest --durations=10

# 只运行失败的测试
uv run pytest --lf

# 生成覆盖率报告
uv run pytest --cov=src/squant --cov-report=html
```

### 使用标记

```python
# 标记慢速测试
@pytest.mark.slow
def test_long_running():
    pass

# 标记集成测试
@pytest.mark.integration
def test_with_database():
    pass

# 跳过测试
@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    pass

# 预期失败
@pytest.mark.xfail
def test_known_bug():
    pass
```

```bash
# 运行特定标记的测试
uv run pytest -m "not slow"
uv run pytest -m "integration"
```

## 调试技巧

### 1. 使用pdb

```python
def test_debug():
    import pdb; pdb.set_trace()
    result = complex_function()
    assert result == expected
```

```bash
# 失败时自动进入调试器
uv run pytest --pdb
```

### 2. 打印调试

```python
def test_with_print(capsys):
    print("Debug info:", value)
    result = function()

    # 捕获输出
    captured = capsys.readouterr()
    assert "Debug info" in captured.out
```

### 3. 查看fixture值

```bash
# 显示所有可用fixtures
uv run pytest --fixtures

# 显示fixture设置过程
uv run pytest --setup-show
```

## 总结

### ✅ 好的测试特征
- 快速运行（单元测试 <100ms）
- 独立（可以任意顺序运行）
- 可重复（每次结果相同）
- 自我验证（不需要人工检查）
- 及时（与代码同步维护）

### ❌ 避免的测试反模式
- 测试实现细节而不是行为
- 过度Mock导致测试失去意义
- 测试之间有依赖关系
- 测试包含复杂的逻辑
- 不清晰的失败消息

### 🎯 记住
1. 先写测试，再写代码（TDD）
2. 一个测试只测一件事
3. 测试名称应该描述期望行为
4. 保持测试简单易懂
5. 定期运行测试

---

**需要帮助？**
- 查看 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) 解决常见问题
- 查看 `tests/templates/` 获取测试模板
- 查看现有测试代码作为示例
