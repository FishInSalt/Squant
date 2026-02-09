# 错误处理

> **关联文档**: [架构概览](./01-overview.md)

## 错误分类

| 类别 | 示例 | 处理方式 |
|------|------|----------|
| **业务错误** | 余额不足、参数无效 | 返回明确错误码，前端展示 |
| **系统错误** | 数据库连接失败 | 记录日志，返回通用错误 |
| **交易所错误** | API 限频、网络超时 | 重试机制，通知用户 |
| **策略错误** | 策略代码异常 | 隔离到进程内，记录日志 |

## 错误码设计

```python
class ErrorCode(IntEnum):
    # 通用错误 1xxx
    SUCCESS = 0
    UNKNOWN_ERROR = 1000
    INVALID_PARAMS = 1001
    UNAUTHORIZED = 1002

    # 行情错误 2xxx
    MARKET_DATA_UNAVAILABLE = 2001
    SYMBOL_NOT_FOUND = 2002

    # 策略错误 3xxx
    STRATEGY_NOT_FOUND = 3001
    STRATEGY_VALIDATION_FAILED = 3002
    STRATEGY_ALREADY_RUNNING = 3003

    # 交易错误 4xxx
    INSUFFICIENT_BALANCE = 4001
    ORDER_REJECTED = 4002
    ORDER_NOT_FOUND = 4003

    # 风控错误 5xxx
    RISK_LIMIT_EXCEEDED = 5001
    CIRCUIT_BREAKER_TRIGGERED = 5002

    # 账户错误 6xxx
    EXCHANGE_NOT_CONFIGURED = 6001
    API_KEY_INVALID = 6002
```

## 错误码范围

| 范围 | 模块 | 示例 |
|------|------|------|
| 0 | 成功 | 0 = SUCCESS |
| 1000-1999 | 通用错误 | 1001 = INVALID_PARAMS |
| 2000-2999 | 行情模块 | 2001 = MARKET_DATA_UNAVAILABLE |
| 3000-3999 | 策略模块 | 3001 = STRATEGY_NOT_FOUND |
| 4000-4999 | 交易模块 | 4001 = INSUFFICIENT_BALANCE |
| 5000-5999 | 风控模块 | 5001 = RISK_LIMIT_EXCEEDED |
| 6000-6999 | 账户模块 | 6001 = EXCHANGE_NOT_CONFIGURED |

## 重试策略

```python
# 交易所 API 调用重试配置
RETRY_CONFIG = {
    "max_retries": 3,
    "backoff_factor": 1.5,  # 指数退避
    "retry_on": [
        "NetworkError",
        "RateLimitExceeded",
        "ExchangeNotAvailable"
    ],
    "no_retry_on": [
        "InsufficientFunds",
        "InvalidOrder",
        "AuthenticationError"
    ]
}
```

### 重试时间计算

```
第 1 次重试: 1.5^0 = 1 秒后
第 2 次重试: 1.5^1 = 1.5 秒后
第 3 次重试: 1.5^2 = 2.25 秒后
```

## 异常处理示例

```python
from fastapi import HTTPException
from squant.core.errors import ErrorCode

class BusinessException(Exception):
    def __init__(self, code: ErrorCode, message: str = None):
        self.code = code
        self.message = message or code.name
        super().__init__(self.message)

# 使用
async def create_order(order: OrderCreate):
    if balance < order.amount * order.price:
        raise BusinessException(
            ErrorCode.INSUFFICIENT_BALANCE,
            "余额不足，无法下单"
        )
```
