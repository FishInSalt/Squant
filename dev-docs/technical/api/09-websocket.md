# WebSocket API

> **关联文档**: [API 规范](./01-conventions.md)

## 1. 连接

```
ws://localhost:8000/api/v1/ws
```

## 2. 消息格式

### 客户端 → 服务端

```json
{
    "action": "subscribe",
    "channel": "ticker",
    "params": {
        "exchange": "binance",
        "symbol": "BTC/USDT"
    }
}
```

### 服务端 → 客户端

```json
{
    "channel": "ticker",
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "data": {
        "price": "67234.56",
        "change_24h": "2.34",
        "volume_24h": "12500000000"
    },
    "timestamp": "2025-01-24T12:00:00.123Z"
}
```

## 3. 频道列表

| 频道 | 参数 | 说明 | 推送频率 |
|------|------|------|----------|
| `ticker` | exchange, symbol | 最新价格 | ~100ms |
| `kline` | exchange, symbol, timeframe | K 线更新 | 每根K线 |
| `depth` | exchange, symbol | 深度数据 | ~100ms |
| `order` | run_id (可选) | 订单状态 | 状态变化时 |
| `strategy` | run_id (可选) | 策略状态 | 状态变化时 |

## 4. 操作类型

| Action | 说明 |
|--------|------|
| `subscribe` | 订阅频道 |
| `unsubscribe` | 取消订阅 |
| `ping` | 心跳检测 |

## 5. 示例

### 订阅行情

```json
{"action": "subscribe", "channel": "ticker", "params": {"exchange": "binance", "symbol": "BTC/USDT"}}
```

### 订阅 K 线

```json
{"action": "subscribe", "channel": "kline", "params": {"exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"}}
```

### 订阅订单更新

```json
{"action": "subscribe", "channel": "order", "params": {"run_id": "uuid"}}
```

### 心跳

```json
{"action": "ping"}
```

### 心跳响应

```json
{"action": "pong", "timestamp": "2025-01-24T12:00:00Z"}
```

## 6. 错误消息

```json
{
    "channel": "error",
    "code": 1001,
    "message": "无效的订阅参数"
}
```
