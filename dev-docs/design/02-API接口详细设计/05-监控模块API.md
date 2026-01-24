## 6. 监控模块API (monitoring-module)

### 6.1 获取策略运行监控

```http
GET /api/v1/monitoring/strategies/{execution_id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "execution_id": "uuid",
    "strategy_id": "uuid",
    "strategy_name": "双均线策略",
    "run_mode": "paper",
    "status": "running",
    "start_time": "2024-01-24T10:00:00Z",
    "runtime": "3600",
    "connected_symbols": [
      {
        "symbol": "BTCUSDT",
        "current_price": "45000.50",
        "price_change": "+2.5%"
      }
    ],
    "orders": {
      "total": 10,
      "filled": 8,
      "canceled": 2,
      "recent_orders": [
        {
          "id": "123456789",
          "symbol": "BTCUSDT",
          "side": "buy",
          "price": "45000.00",
          "quantity": "0.001",
          "status": "filled",
          "created_at": "2024-01-24T10:00:00Z"
        }
      ]
    },
    "positions": [
      {
        "symbol": "BTCUSDT",
        "side": "long",
        "quantity": "0.001",
        "entry_price": "44000.00",
        "current_price": "45000.00",
        "unrealized_pnl": "10.00"
      }
    ],
    "pnl": {
      "realized_pnl": "50.50",
      "unrealized_pnl": "10.00",
      "total_pnl": "60.50"
    },
    "resource_usage": {
      "cpu_usage": "12.5",
      "memory_usage": "256"
    }
  },
  "timestamp": 1706073600
}
```

---

### 6.2 获取策略日志

```http
GET /api/v1/monitoring/strategies/{execution_id}/logs
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| level | string | 否 | 日志级别过滤 (debug, info, warning, error) |
| limit | int | 否 | 返回数量,默认100 |
| offset | int | 否 | 偏移量,默认0 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 1000,
    "items": [
      {
        "id": "uuid",
        "level": "info",
        "message": "买入信号: BTCUSDT, 短期MA=44000.00, 长期MA=43900.00",
        "context": {
          "short_ma": 44000.00,
          "long_ma": 43900.00
        },
        "created_at": "2024-01-24T10:00:00Z"
      },
      {
        "id": "uuid",
        "level": "warning",
        "message": "下单失败: 余额不足",
        "context": {
          "required_balance": "50.00",
          "available_balance": "40.00"
        },
        "created_at": "2024-01-24T10:00:01Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 6.3 获取策略订单

```http
GET /api/v1/monitoring/strategies/{execution_id}/orders
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 订单状态过滤 |
| symbol | string | 否 | 交易对过滤 |
| limit | int | 否 | 返回数量,默认20 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 10,
    "items": [
      {
        "id": "123456789",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "price": "45000.00",
        "quantity": "0.001",
        "filled_quantity": "0.001",
        "status": "filled",
        "is_simulation": true,
        "created_at": "2024-01-24T10:00:00Z",
        "updated_at": "2024-01-24T10:00:01Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 6.4 获取策略盈亏

```http
GET /api/v1/monitoring/strategies/{execution_id}/pnl
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "execution_id": "uuid",
    "initial_balance": "10000.00",
    "current_balance": "10060.50",
    "realized_pnl": "50.50",
    "unrealized_pnl": "10.00",
    "total_pnl": "60.50",
    "pnl_percent": "0.605%",
    "total_trades": 10,
    "win_trades": 6,
    "loss_trades": 4,
    "win_rate": "60%",
    "max_drawdown": "-2.5%",
    "equity_curve": [
      {
        "timestamp": "2024-01-24T10:00:00Z",
        "balance": "10000.00"
      },
      {
        "timestamp": "2024-01-24T11:00:00Z",
        "balance": "10060.50"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 6.5 获取告警列表

```http
GET /api/v1/monitoring/alerts
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| execution_id | string | 否 | 策略执行ID过滤 |
| type | string | 否 | 告警类型过滤 (error, warning, info) |
| is_read | boolean | 否 | 是否已读过滤 |
| limit | int | 否 | 返回数量,默认20 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 5,
    "unread_count": 2,
    "items": [
      {
        "id": "uuid",
        "execution_id": "uuid",
        "type": "error",
        "severity": "high",
        "title": "订单执行失败",
        "message": "订单123456789执行失败: 余额不足",
        "is_read": false,
        "created_at": "2024-01-24T10:00:00Z"
      },
      {
        "id": "uuid",
        "execution_id": "uuid",
        "type": "warning",
        "severity": "medium",
        "title": "策略资源使用率过高",
        "message": "CPU使用率达到85%,请检查策略性能",
        "is_read": false,
        "created_at": "2024-01-24T10:00:00Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 6.6 标记告警为已读

```http
PUT /api/v1/monitoring/alerts/{alert_id}/read
```

---

### 6.7 WebSocket订阅策略实时监控

```http
WS /ws/v1/monitoring/strategies/{execution_id}
```

**服务器推送消息类型:**

```json
// 1. 行情更新
{
  "event": "market_data",
  "data": {
    "symbol": "BTCUSDT",
    "price": "45000.50",
    "timestamp": 1706073600
  }
}

// 2. 订单更新
{
  "event": "order_update",
  "data": {
    "id": "123456789",
    "symbol": "BTCUSDT",
    "status": "filled",
    "filled_quantity": "0.001"
  }
}

// 3. 持仓更新
{
  "event": "position_update",
  "data": {
    "symbol": "BTCUSDT",
    "quantity": "0.001",
    "unrealized_pnl": "10.00"
  }
}

// 4. 日志更新
{
  "event": "log",
  "data": {
    "level": "info",
    "message": "买入信号: BTCUSDT",
    "timestamp": 1706073600
  }
}

// 5. 盈亏更新
{
  "event": "pnl_update",
  "data": {
    "realized_pnl": "50.50",
    "unrealized_pnl": "10.00",
    "total_pnl": "60.50"
  }
}

// 6. 告警
{
  "event": "alert",
  "data": {
    "type": "error",
    "severity": "high",
    "title": "订单执行失败",
    "message": "余额不足",
    "timestamp": 1706073600
  }
}
```

---

## 7. 认证和授权API (可选)
