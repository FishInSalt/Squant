# 测试模板使用指南

本目录包含标准化的测试模板，帮助快速创建结构清晰、覆盖全面的测试文件。

## 可用模板

### 1. `service_template.py` - 服务层测试模板

用于测试 `src/squant/services/` 中的业务逻辑服务。

**使用步骤**:
```bash
# 1. 复制模板到目标位置
cp tests/templates/service_template.py tests/unit/services/test_my_service.py

# 2. 在编辑器中打开
code tests/unit/services/test_my_service.py

# 3. 全局搜索替换:
#    - <ServiceClass> → 实际服务类名 (如 OrderService)
#    - <service_instance> → fixture名称 (如 order_service)
#    - <business_method> → 实际方法名

# 4. 删除不需要的测试类
# 5. 根据服务实际依赖调整fixtures
# 6. 添加服务特定的测试用例
```

**包含的测试类**:
- `Test<ServiceClass>Init` - 初始化测试
- `Test<ServiceClass>CRUD` - CRUD操作测试
- `Test<ServiceClass>BusinessLogic` - 业务逻辑测试
- `Test<ServiceClass>Cache` - Redis缓存测试
- `Test<ServiceClass>ErrorHandling` - 错误处理测试
- `Test<ServiceClass>Parametrized` - 参数化测试示例

**示例**: 测试 `OrderService`

```python
# 搜索替换:
# <ServiceClass> → OrderService
# <service_instance> → order_service

# 修改后的代码:
@pytest.fixture
def order_service(mock_session, mock_redis):
    return OrderService(session=mock_session, redis=mock_redis)

class TestOrderServiceInit:
    def test_init_with_valid_dependencies(self, mock_session, mock_redis):
        service = OrderService(session=mock_session, redis=mock_redis)
        assert service.session == mock_session
```

---

### 2. `api_template.py` - API端点测试模板

用于测试 `src/squant/api/v1/` 中的FastAPI路由端点。

**使用步骤**:
```bash
# 1. 复制模板
cp tests/templates/api_template.py tests/unit/api/v1/test_my_endpoint.py

# 2. 全局搜索替换:
#    - <ResourceName> → 资源名称 (如 Order, Strategy)
#    - <endpoint_path> → API路径 (如 /api/v1/orders)

# 3. 调整 client fixture 的 dependency_overrides
# 4. 配置有效的请求数据 fixtures
# 5. 根据端点实际行为添加/删除测试
```

**包含的测试类**:
- `TestGet<ResourceName>List` - GET列表端点
- `TestGet<ResourceName>ById` - GET单个资源
- `TestCreate<ResourceName>` - POST创建
- `TestUpdate<ResourceName>` - PUT/PATCH更新
- `TestDelete<ResourceName>` - DELETE删除
- `Test<ResourceName>Validation` - 数据验证
- `Test<ResourceName>Authorization` - 权限控制
- `Test<ResourceName>ErrorHandling` - 错误处理

**示例**: 测试 `/api/v1/strategies` 端点

```python
# 搜索替换:
# <ResourceName> → Strategy
# <endpoint_path> → /api/v1/strategies

@pytest.fixture
def client(mock_session) -> TestClient:
    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()

class TestGetStrategyList:
    def test_get_list_success(self, client, mock_session):
        # Arrange
        mock_strategies = [
            MagicMock(id=uuid4(), name="MA Strategy"),
            MagicMock(id=uuid4(), name="RSI Strategy"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_strategies
        mock_session.execute.return_value = mock_result

        # Act
        response = client.get("/api/v1/strategies")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
```

---

## 最佳实践

### 1. 命名约定

遵循项目的测试命名规范:
```python
# 测试文件名
tests/unit/services/test_order.py

# 测试类名
class TestOrderServiceCreate:

# 测试方法名
def test_create_order_success(self):
def test_create_order_with_invalid_amount_raises_error(self):
```

格式: `test_<function>_<scenario>_<expected_result>`

### 2. Fixture组织

**全局fixtures** (`tests/conftest.py`):
- 数据库连接
- Redis连接
- 配置对象

**模块fixtures** (`tests/unit/services/conftest.py`):
- Mock依赖（session, redis, exchange）
- 测试数据工厂

**文件fixtures** (测试文件内):
- 服务/客户端实例
- 请求数据

### 3. Mock配置

```python
# ✅ 好的做法 - 使用AsyncMock for异步方法
mock_service.get_data = AsyncMock(return_value={"key": "value"})

# ✅ 配置side_effect处理多次调用
mock_service.create = AsyncMock(side_effect=[
    {"id": 1},
    Exception("Second call fails")
])

# ❌ 避免 - 不要mock asyncio核心原语
with patch('asyncio.sleep'):  # 危险！
    ...
```

### 4. 测试数据

使用工厂模式创建测试数据:
```python
class OrderFactory:
    _counter = 0

    @classmethod
    def create(cls, **overrides):
        cls._counter += 1
        defaults = {
            "id": uuid4(),
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": Decimal("0.1"),
        }
        defaults.update(overrides)
        return Order(**defaults)

# 使用
order1 = OrderFactory.create()
order2 = OrderFactory.create(side="sell")
```

### 5. 断言

```python
# ✅ 具体的断言
assert order.status == OrderStatus.FILLED
assert order.filled_amount == Decimal("0.1")

# ✅ 验证Mock调用
mock_exchange.create_order.assert_called_once_with(
    symbol="BTC/USDT",
    side="buy",
    amount=0.1
)

# ✅ 验证异常
with pytest.raises(ValueError, match="Invalid amount"):
    service.create_order(amount=-1)

# ❌ 避免 - 过于宽泛的断言
assert order is not None
assert len(orders) > 0
```

---

## 常见场景示例

### 场景1: 测试异步服务方法

```python
@pytest.mark.asyncio
async def test_create_order_success(self, order_service, mock_session):
    # Arrange
    order_data = {
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": "0.1",
    }
    mock_order = MagicMock()
    mock_order.id = uuid4()
    mock_session.refresh.side_effect = lambda obj: setattr(obj, 'id', mock_order.id)

    # Act
    result = await order_service.create(order_data)

    # Assert
    assert result.id == mock_order.id
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
```

### 场景2: 测试带枚举的API请求

```python
def test_create_order_with_valid_enum(self, client):
    # Arrange - 注意枚举值是小写
    payload = {
        "symbol": "BTC/USDT",
        "side": "buy",     # OrderSide.BUY = "buy"
        "type": "limit",   # OrderType.LIMIT = "limit"
        "amount": "0.1",
        "price": "50000"
    }

    # Act
    response = client.post("/api/v1/orders", json=payload)

    # Assert
    assert response.status_code == 200
```

### 场景3: 测试Decimal字段

```python
def test_balance_returns_decimal_as_string(self, client, mock_exchange):
    # Arrange
    mock_exchange.fetch_balance.return_value = {
        "BTC": {"free": 1.5, "used": 0.0, "total": 1.5}
    }

    # Act
    response = client.get("/api/v1/account/balance")

    # Assert
    assert response.status_code == 200
    data = response.json()
    # Decimal序列化为字符串
    assert isinstance(data["BTC"]["free"], str)
    assert float(data["BTC"]["free"]) == pytest.approx(1.5)
```

### 场景4: 测试错误处理

```python
@pytest.mark.asyncio
async def test_create_order_with_insufficient_balance(self, order_service, mock_exchange):
    # Arrange
    mock_exchange.create_order.side_effect = Exception("Insufficient balance")

    # Act & Assert
    with pytest.raises(Exception, match="Insufficient balance"):
        await order_service.create_order({
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": "100"
        })
```

---

## 快速参考

### pytest命令

```bash
# 运行单个测试文件
uv run pytest tests/unit/services/test_order.py -v

# 运行单个测试
uv run pytest tests/unit/services/test_order.py::TestOrderServiceCreate::test_create_success -v

# 运行带标记的测试
uv run pytest -m "not integration" -v

# 生成覆盖率报告
uv run pytest --cov=src/squant --cov-report=html

# 显示print输出
uv run pytest -s

# 在第一个失败处停止
uv run pytest -x
```

### Mock快速参考

```python
from unittest.mock import MagicMock, AsyncMock, patch

# 创建Mock
mock_obj = MagicMock()
mock_obj.method.return_value = "result"

# 异步Mock
mock_obj.async_method = AsyncMock(return_value="result")

# 多次调用
mock_obj.method = AsyncMock(side_effect=["first", "second"])

# Patch
with patch('module.function') as mock_func:
    mock_func.return_value = "mocked"

# 验证调用
mock_obj.method.assert_called_once()
mock_obj.method.assert_called_with(arg1="value")
assert mock_obj.method.call_count == 2
```

---

## 相关文档

- [TESTING_GUIDE.md](../../dev-docs/technical/testing/TESTING_GUIDE.md) - 完整测试指南
- [TROUBLESHOOTING.md](../../dev-docs/technical/testing/TROUBLESHOOTING.md) - 问题排查
- [TEST_COVERAGE_REPORT.md](../../dev-docs/technical/testing/TEST_COVERAGE_REPORT.md) - 覆盖率报告

---

**维护者**: Development Team
**最后更新**: 2026-01-30
