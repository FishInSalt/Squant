# 可扩展性设计

> **关联文档**: [模块划分](./02-modules.md)

## 1. 交易所扩展

### 适配器抽象基类

```python
from abc import ABC, abstractmethod

class ExchangeAdapter(ABC):
    """交易所适配器抽象基类"""

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取最新价格"""
        ...

    @abstractmethod
    async def get_klines(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[Kline]:
        """获取 K 线数据"""
        ...

    @abstractmethod
    async def create_order(self, order: OrderCreate) -> Order:
        """创建订单"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        ...

    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        """获取账户余额"""
        ...
```

### 添加新交易所

```python
# 只需实现接口即可
class BybitAdapter(ExchangeAdapter):
    def __init__(self, api_key: str, api_secret: str):
        self.client = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
        })

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self.client.fetch_ticker(symbol)
        return Ticker(
            symbol=symbol,
            price=data["last"],
            change_24h=data["percentage"],
            volume_24h=data["quoteVolume"],
        )

    # ... 实现其他方法
```

## 2. 通知渠道扩展

### 通知渠道抽象基类

```python
class NotificationChannel(ABC):
    """通知渠道抽象基类"""

    @abstractmethod
    async def send(self, message: str, level: str = "info") -> bool:
        """发送通知"""
        ...
```

### 添加新渠道

```python
class WeChatChannel(NotificationChannel):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, message: str, level: str = "info") -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                json={"msgtype": "text", "text": {"content": message}}
            )
            return response.status_code == 200
```

## 3. 策略指标扩展

策略可通过 `context.indicator()` 调用技术指标，新指标注册到指标库即可。

### 指标注册

```python
# 指标注册表
INDICATOR_REGISTRY = {}

def register_indicator(name: str):
    """指标注册装饰器"""
    def decorator(func):
        INDICATOR_REGISTRY[name] = func
        return func
    return decorator

@register_indicator("SMA")
def sma(data: list, period: int) -> float:
    """简单移动平均"""
    return sum(data[-period:]) / period

@register_indicator("EMA")
def ema(data: list, period: int) -> float:
    """指数移动平均"""
    multiplier = 2 / (period + 1)
    result = data[0]
    for price in data[1:]:
        result = (price - result) * multiplier + result
    return result
```

### 在策略中使用

```python
def on_bar(self, bar):
    closes = self.ctx.get_history("close", 30)

    # 使用注册的指标
    sma = self.ctx.indicator("SMA", closes, 20)
    ema = self.ctx.indicator("EMA", closes, 20)
    custom = self.ctx.indicator("MY_INDICATOR", closes, 14)
```

## 4. 扩展点总结

| 扩展点 | 接口 | 实现方式 |
|--------|------|----------|
| 交易所 | `ExchangeAdapter` | 继承基类，实现方法 |
| 通知渠道 | `NotificationChannel` | 继承基类，实现 send 方法 |
| 技术指标 | `@register_indicator` | 装饰器注册函数 |
| 风控规则 | `RiskRule` | 继承基类，实现 check 方法 |
| 数据源 | `DataSource` | 继承基类，实现 fetch 方法 |
