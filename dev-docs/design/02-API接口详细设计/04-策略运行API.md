## 5. 策略运行模块API (runtime-module)

### 5.1 启动策略

```http
POST /api/v1/runtime/strategies/{strategy_id}/start
```

**请求体:**

```json
{
  "account_id": "uuid",
  "run_mode": "paper",
  "config": {
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "short_period": 5,
    "long_period": 20,
    "quantity": "0.001"
  },
  "stop_config": {
    "on_stop_action": "cancel_orders",
    "max_loss": "100.00"
  }
}
```

**参数说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_id | string | 否 | 交易所账户ID (实盘/模拟运行必填) |
| run_mode | string | 是 | 运行模式: backtest, paper, live |
| config | object | 是 | 策略参数配置 |
| stop_config | object | 否 | 停止配置 |

**stop_config说明:**

| 字段 | 类型 | 说明 |
|------|------|------|
| on_stop_action | string | 停止行为: cancel_orders(只撤单), close_positions(平仓), do_nothing(不做操作) |
| max_loss | string | 最大亏损(超过自动停止) |

**响应示例:**

```json
{
  "code": 0,
  "message": "策略启动成功",
  "data": {
    "execution_id": "uuid",
    "strategy_id": "uuid",
    "run_mode": "paper",
    "status": "running",
    "start_time": "2024-01-24T10:00:00Z",
    "container_id": "container_abc123"
  },
  "timestamp": 1706073600
}
```

---

### 5.2 停止策略

```http
POST /api/v1/runtime/strategies/{execution_id}/stop
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| force | boolean | 否 | 是否强制停止,默认false |

**响应示例:**

```json
{
  "code": 0,
  "message": "策略停止成功",
  "data": {
    "execution_id": "uuid",
    "status": "stopped",
    "stop_time": "2024-01-24T10:00:00Z",
    "orders_canceled": 2,
    "positions_closed": 1
  },
  "timestamp": 1706073600
}
```

---

### 5.3 获取运行中的策略列表

```http
GET /api/v1/runtime/strategies
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| run_mode | string | 否 | 运行模式过滤 |
| status | string | 否 | 状态过滤 (running, stopped, error) |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "execution_id": "uuid",
      "strategy_id": "uuid",
      "strategy_name": "双均线策略",
      "run_mode": "paper",
      "status": "running",
      "start_time": "2024-01-24T10:00:00Z",
      "runtime": "3600",  // 运行时长(秒)
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "cpu_usage": "12.5",
      "memory_usage": "256"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 5.4 获取策略运行详情

```http
GET /api/v1/runtime/strategies/{execution_id}
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
    "account_id": "uuid",
    "run_mode": "paper",
    "status": "running",
    "config": {
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "short_period": 5,
      "long_period": 20
    },
    "start_time": "2024-01-24T10:00:00Z",
    "end_time": null,
    "runtime": "3600",
    "container_id": "container_abc123",
    "performance": {
      "total_trades": 10,
      "win_trades": 6,
      "loss_trades": 4,
      "win_rate": "60%",
      "pnl": "50.50",
      "pnl_percent": "5.05%"
    },
    "positions": [
      {
        "symbol": "BTCUSDT",
        "side": "long",
        "quantity": "0.001",
        "entry_price": "44000.00",
        "unrealized_pnl": "10.00"
      }
    ],
    "resource_usage": {
      "cpu_usage": "12.5",
      "memory_usage": "256"
    },
    "last_log": {
      "level": "info",
      "message": "买入信号: BTCUSDT",
      "timestamp": "2024-01-24T10:00:00Z"
    }
  },
  "timestamp": 1706073600
}
```

---

### 5.5 启动回测

```http
POST /api/v1/runtime/strategies/{strategy_id}/backtest
```

**请求体:**

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "start_date": "2023-01-01",
  "end_date": "2024-01-01",
  "initial_balance": "10000.00",
  "config": {
    "short_period": 5,
    "long_period": 20,
    "quantity": "0.001"
  }
}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "回测启动成功",
  "data": {
    "execution_id": "uuid",
    "status": "running",
    "estimated_time": "60"
  },
  "timestamp": 1706073600
}
```

---

### 5.6 获取回测结果

```http
GET /api/v1/runtime/backtest-results/{execution_id}
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
    "backtest_config": {
      "symbol": "BTCUSDT",
      "interval": "1h",
      "start_date": "2023-01-01",
      "end_date": "2024-01-01",
      "initial_balance": "10000.00"
    },
    "results": {
      "total_return": "15.5%",
      "annual_return": "15.5%",
      "max_drawdown": "-8.2%",
      "sharpe_ratio": "1.8",
      "win_rate": "60%",
      "total_trades": 100,
      "profit_trades": 60,
      "loss_trades": 40,
      "avg_win": "20.00",
      "avg_loss": "-12.00",
      "profit_factor": "2.5"
    },
    "equity_curve": [
      {
        "date": "2023-01-01",
        "balance": "10000.00"
      },
      {
        "date": "2023-01-02",
        "balance": "10015.00"
      }
    ],
    "trade_history": [
      {
        "id": "1",
        "symbol": "BTCUSDT",
        "side": "buy",
        "entry_time": "2023-01-01T10:00:00Z",
        "exit_time": "2023-01-02T10:00:00Z",
        "entry_price": "44000.00",
        "exit_price": "44500.00",
        "quantity": "0.001",
        "pnl": "5.00"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 5.7 回测API使用说明

**⚠️ 重要: 回测是异步执行的**

由于回测可能耗时较长(秒级到分钟级),因此采用**异步执行 + 轮询查询**的模式。

**完整使用流程:**

```javascript
// 1. 启动回测
const startBacktest = async () => {
  const response = await fetch('/api/v1/runtime/strategies/strategy-123/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: 'BTCUSDT',
      interval: '1h',
      start_date: '2023-01-01',
      end_date: '2024-01-01',
      initial_balance: '10000.00',
      config: { short_period: 5, long_period: 20 }
    })
  })

  const result = await response.json()
  const executionId = result.data.execution_id

  console.log(`回测启动成功, execution_id: ${executionId}`)
  console.log(`预计耗时: ${result.data.estimated_time}秒`)

  return executionId
}

// 2. 轮询回测状态
const pollBacktestStatus = async (executionId) => {
  const maxAttempts = 60  // 最多轮询60次 (10分钟)
  const interval = 10000  // 每10秒查询一次

  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(`/api/v1/runtime/backtest-results/${executionId}`)
    const result = await response.json()

    if (result.data.status === 'completed') {
      console.log('回测完成')
      return result.data
    } else if (result.data.status === 'failed') {
      console.error('回测失败:', result.data.error_message)
      throw new Error('回测失败')
    }

    console.log(`回测中... (${i + 1}/${maxAttempts})`)
    await new Promise(resolve => setTimeout(resolve, interval))
  }

  throw new Error('回测超时')
}

// 3. 使用示例
const main = async () => {
  const executionId = await startBacktest()
  const results = await pollBacktestStatus(executionId)

  console.log('回测结果:', results.data)
  console.log('总收益率:', results.data.results.total_return)
  console.log('夏普比率:', results.data.results.sharpe_ratio)
}

main().catch(console.error)
```

**回测状态值:**

| 状态 | 说明 | 下一步操作 |
|------|------|-----------|
| `running` | 回测运行中 | 继续轮询 |
| `completed` | 回测完成 | 获取结果 |
| `failed` | 回测失败 | 查看error_message |

**回测参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 交易对 |
| interval | string | 是 | K线周期 (1m, 5m, 1h, 1d等) |
| start_date | string | 是 | 回测开始日期 (YYYY-MM-DD) |
| end_date | string | 是 | 回测结束日期 (YYYY-MM-DD) |
| initial_balance | string | 是 | 初始资金 |
| config | object | 是 | 策略参数 |

---

### 5.8 WebSocket连接管理

**⚠️ 重要: WebSocket连接需要execution_id**

要订阅策略的实时监控数据,需要先获取execution_id。

**完整使用流程:**

```javascript
// 1. 获取运行中的策略列表
const getRunningStrategies = async () => {
  const response = await fetch('/api/v1/runtime/strategies')
  const result = await response.json()
  return result.data  // 运行中的策略列表
}

// 2. 选择策略并订阅
const subscribeToStrategy = async (strategyId) => {
  // 2.1 先获取策略列表,找到对应的execution_id
  const strategies = await getRunningStrategies()
  const target = strategies.find(s => s.strategy_id === strategyId)

  if (!target) {
    console.error('策略未运行')
    return
  }

  const executionId = target.execution_id
  console.log(`订阅策略, execution_id: ${executionId}`)

  // 2.2 建立WebSocket连接
  // 注意: 需要在URL中携带access_token
  const token = localStorage.getItem('access_token')
  const ws = new WebSocket(`ws://localhost:8000/ws/v1/monitoring/strategies/${executionId}?token=${token}`)

  // 2.3 订阅不同类型的数据
  ws.onopen = () => {
    console.log('WebSocket连接已建立')

    // 订阅事件类型 (可选)
    ws.send(JSON.stringify({
      event: 'subscribe',
      data: ['market_data', 'order_update', 'position_update', 'pnl_update']
    }))
  }

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)

    switch (message.event) {
      case 'market_data':
        console.log('行情更新:', message.data)
        break
      case 'order_update':
        console.log('订单更新:', message.data)
        break
      case 'position_update':
        console.log('持仓更新:', message.data)
        break
      case 'pnl_update':
        console.log('盈亏更新:', message.data)
        break
      case 'alert':
        console.warn('告警:', message.data)
        break
      case 'log':
        console.log('策略日志:', message.data)
        break
      default:
        console.log('未知事件:', message)
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket错误:', error)
  }

  ws.onclose = () => {
    console.log('WebSocket连接已关闭')
    // 可选: 自动重连
    setTimeout(() => subscribeToStrategy(strategyId), 5000)
  }

  return ws
}

// 3. 使用示例
const main = async () => {
  const strategyId = 'strategy-123'
  const ws = await subscribeToStrategy(strategyId)

  // 可以取消订阅
  setTimeout(() => {
    ws.close()
  }, 60000)  // 60秒后关闭连接
}

main().catch(console.error)
```

**WebSocket事件类型:**

| 事件名 | 数据字段 | 说明 |
|--------|---------|------|
| `market_data` | symbol, price, price_change | 行情更新 |
| `order_update` | id, symbol, side, status | 订单状态更新 |
| `position_update` | symbol, quantity, unrealized_pnl | 持仓更新 |
| `pnl_update` | realized_pnl, unrealized_pnl, total_pnl | 盈亏更新 |
| `alert` | type, severity, title, message | 告警通知 |
| `log` | level, message, timestamp | 策略日志 |

**心跳保活:**

```javascript
// WebSocket需要定期发送心跳消息 (每30秒)
const keepAlive = (ws) => {
  const interval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event: 'ping' }))
    } else {
      clearInterval(interval)
    }
  }, 30000)
}
```

**错误处理:**

```javascript
// WebSocket错误码
ws.addEventListener('error', (event) => {
  console.error('WebSocket错误:', event)

  // 常见错误处理
  if (event.code === 1006) {
    console.error('连接异常关闭,尝试重连...')
  } else if (event.code === 1008) {
    console.error('策略停止,连接关闭')
  }
})
```

---

## 6. 监控模块API (monitoring-module)
