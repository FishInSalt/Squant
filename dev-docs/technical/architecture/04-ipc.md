# 进程间通信

> **关联文档**: [架构概览](./01-overview.md)

## 通信架构

策略进程与主进程通过 Redis 通信：

```
┌─────────────────┐                    ┌─────────────────┐
│   Main Process  │                    │ Strategy Process│
│   (FastAPI)     │                    │   (Worker)      │
│                 │                    │                 │
│  ┌───────────┐  │     Redis          │  ┌───────────┐  │
│  │ Publisher │──┼──────Pub/Sub──────▶│  │Subscriber │  │
│  └───────────┘  │                    │  └───────────┘  │
│                 │                    │                 │
│  ┌───────────┐  │     Redis          │  ┌───────────┐  │
│  │Subscriber │◀─┼──────Pub/Sub───────┼──│ Publisher │  │
│  └───────────┘  │                    │  └───────────┘  │
└─────────────────┘                    └─────────────────┘
```

## Channel 设计

| Channel | 用途 | 方向 |
|---------|------|------|
| `squant:control:{process_id}` | 控制命令（启动、停止） | 主进程 → 策略进程 |
| `squant:status:{process_id}` | 状态上报（心跳、异常） | 策略进程 → 主进程 |
| `squant:order:{process_id}` | 订单事件 | 双向 |
| `squant:market:{symbol}` | 行情推送 | 主进程 → 策略进程 |

## 消息格式

### 控制消息

```python
{
    "type": "command",
    "action": "stop",  # start | stop | update_params
    "payload": {},
    "timestamp": "2025-01-24T12:00:00Z"
}
```

### 状态消息

```python
{
    "type": "status",
    "process_id": "uuid",
    "status": "running",  # running | stopped | error
    "metrics": {
        "cpu": 5.2,
        "memory": 128.5,
        "uptime": 3600
    },
    "timestamp": "2025-01-24T12:00:00Z"
}
```

### 订单消息

```python
{
    "type": "order",
    "action": "create",  # create | update | cancel
    "order": {
        "id": "uuid",
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "price": 67000.0,
        "amount": 0.01
    },
    "timestamp": "2025-01-24T12:00:00Z"
}
```

## WebSocket 推送

```
Client                    Server
   │                         │
   │── Subscribe(ticker) ───▶│
   │                         │
   │◀── Ticker Update ───────│ (每 100ms)
   │◀── Ticker Update ───────│
   │                         │
   │── Subscribe(kline) ────▶│
   │                         │
   │◀── Kline Update ────────│ (每根K线)
   │                         │
   │── Subscribe(order) ────▶│
   │                         │
   │◀── Order Update ────────│ (状态变化时)
   │                         │
```

### WebSocket 消息格式

```python
{
    "channel": "ticker",
    "symbol": "BTC/USDT",
    "data": {
        "price": 67234.56,
        "change": 2.34,
        "volume": 12500000000
    }
}
```
