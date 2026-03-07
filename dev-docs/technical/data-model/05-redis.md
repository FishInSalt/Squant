# Redis 缓存设计

> **关联文档**: [进程间通信](../architecture/04-ipc.md)

## 1. Key 命名规范

```
squant:{domain}:{identifier}:{field}

例如：
squant:ticker:binance:BTC/USDT          # 最新行情
squant:depth:binance:BTC/USDT           # 深度数据
squant:process:status:{process_id}      # 进程状态
squant:rate_limit:api:{account_id}      # API 限频计数
```

## 2. 数据结构选择

| 数据 | Redis 类型 | TTL | 说明 |
|---|---|---|---|
| 最新行情 | Hash | 5s | 价格、涨跌幅等 |
| 深度数据 | String (JSON) | 1s | 买卖盘口 |
| 进程心跳 | String | 30s | 进程存活检测 |
| 限频计数 | String + INCR | 60s | 滑动窗口计数 |
| 订阅关系 | Set | - | WebSocket 订阅管理 |

## 3. 使用示例

### 行情缓存

```python
# 写入行情
await redis.hset("squant:ticker:binance:BTC/USDT", mapping={
    "price": "67234.56",
    "change_24h": "2.34",
    "volume_24h": "12500000000",
    "timestamp": "1706097600"
})
await redis.expire("squant:ticker:binance:BTC/USDT", 5)

# 读取行情
ticker = await redis.hgetall("squant:ticker:binance:BTC/USDT")
```

### 进程心跳

```python
# 策略进程定期发送心跳
await redis.set(f"squant:process:heartbeat:{process_id}", "1", ex=30)

# 主进程检查进程是否存活
is_alive = await redis.exists(f"squant:process:heartbeat:{process_id}")
```

### 订阅管理

```python
# 添加订阅
await redis.sadd("squant:ws:subscriptions:ticker:binance:BTC/USDT", connection_id)

# 获取订阅者
subscribers = await redis.smembers("squant:ws:subscriptions:ticker:binance:BTC/USDT")

# 移除订阅
await redis.srem("squant:ws:subscriptions:ticker:binance:BTC/USDT", connection_id)
```

### API 限频

```python
async def check_rate_limit(account_id: str, limit: int = 10) -> bool:
    """检查 API 调用频率"""
    key = f"squant:rate_limit:api:{account_id}"
    current = await redis.incr(key)

    if current == 1:
        await redis.expire(key, 60)  # 60秒窗口

    return current <= limit
```

## 4. Pub/Sub 频道

| 频道 | 用途 |
|------|------|
| `squant:control:{process_id}` | 控制命令（启动、停止） |
| `squant:status:{process_id}` | 状态上报（心跳、异常） |
| `squant:order:{process_id}` | 订单事件 |
| `squant:market:{symbol}` | 行情推送 |

### 发布消息

```python
await redis.publish(
    f"squant:control:{process_id}",
    json.dumps({"action": "stop"})
)
```

### 订阅消息

```python
pubsub = redis.pubsub()
await pubsub.subscribe(f"squant:control:{process_id}")

async for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        handle_command(data)
```

## 5. 连接配置

```python
from redis.asyncio import Redis

redis = Redis.from_url(
    "redis://:password@localhost:6379/0",
    encoding="utf-8",
    decode_responses=True,
)
```
