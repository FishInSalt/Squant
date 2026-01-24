# 量化交易系统 - API接口详细设计文档

---

## 文档信息

| 项目 | 内容 |
|------|------|
| 文档版本 | v1.1 |
| 创建日期 | 2026-01-24 |
| 关联文档 | 01-系统架构设计.md (v1.3) |

---

## 📋 MVP架构说明

### 重要声明

⚠️ **本文档是针对MVP单体应用的API设计**,不是微服务架构的API设计。

| 架构阶段 | 架构类型 | 文档对应 |
|---------|---------|----------|
| **MVP阶段** (当前) | 单体应用 (FastAPI) + Docker策略运行 | ✅ 本文档 |
| **成熟阶段** (未来) | 微服务架构 | ❌ 不适用 |

### MVP vs 微服务 API对比

| 方面 | MVP API (本系统) | 微服务 API |
|------|-----------------|-----------|
| **API Gateway** | FastAPI内置 | Kong/Traefik |
| **服务间通信** | 模块间函数调用(无需API) | gRPC |
| **前端通信** | REST API + WebSocket | REST API + WebSocket |
| **API数量** | 所有API在单体应用中 | 分布在多个微服务中 |
| **调用方式** | `/api/v1/{module}/{resource}` | `/api/v1/{service}/{resource}` |

### 章节组织说明

本文档按**功能模块**组织API:

| 章节 | 模块名 | 说明 |
|------|--------|------|
| 2. 行情服务API | market-module | 行情数据管理 |
| 3. 策略服务API | strategy-module | 策略库管理 |
| 4. 交易服务API | trading-module | 交易所交易管理 |
| 5. 策略运行服务API | runtime-module | 策略生命周期管理 |
| 6. 监控服务API | monitoring-module | 运行监控管理 |

⚠️ **注意**: 这里使用的"服务"一词是指单体应用中的**功能模块**,不是独立的微服务。在MVP阶段,所有这些模块都运行在同一个FastAPI进程中。

---

## 1. API设计原则

### 1.1 RESTful API设计规范

| 规范 | 说明 | 示例 |
|------|------|------|
| **资源命名** | 使用名词复数形式 | `/api/v1/strategies` 而非 `/api/v1/strategy` |
| **HTTP方法** | 语义化使用HTTP动词 | GET(查询), POST(创建), PUT(更新), DELETE(删除) |
| **版本控制** | URL中包含版本号 | `/api/v1/...` |
| **状态码** | 正确使用HTTP状态码 | 200(成功), 201(创建), 400(请求错误), 401(未认证), 500(服务器错误) |
| **分页** | 使用limit和offset参数 | `GET /api/v1/orders?limit=20&offset=0` |
| **过滤和排序** | 使用查询参数 | `GET /api/v1/orders?status=filled&sort=created_at:desc` |

### 1.2 通用响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "timestamp": 1706073600
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| code | int | 业务状态码,0表示成功 |
| message | string | 响应消息 |
| data | object/array | 响应数据 |
| timestamp | int | Unix时间戳(秒) |

### 1.3 错误响应格式

```json
{
  "code": 40001,
  "message": "策略校验失败: 缺少必需接口 on_bar",
  "errors": [
    {
      "field": "strategy_code",
      "message": "缺少必需接口 on_bar"
    }
  ],
  "timestamp": 1706073600
}
```

### 1.4 业务状态码定义

| 状态码 | 说明 | HTTP状态码 |
|--------|------|-----------|
| 0 | 成功 | 200 |
| 40001 | 参数错误 | 400 |
| 40002 | 资源不存在 | 404 |
| 40003 | 重复请求 | 409 |
| 40004 | 资源已存在 | 409 |
| 40005 | 权限不足 | 403 |
| 40006 | 认证失败 | 401 |
| 40007 | 策略校验失败 | 400 |
| 40008 | 余额不足 | 400 |
| 40009 | 订单失败 | 400 |
| 50001 | 服务器内部错误 | 500 |
| 50002 | 第三方服务错误 | 502 |
| 50003 | 服务不可用 | 503 |

---

## 2. 行情模块API (market-module)

### 2.1 获取热门币种列表

```http
GET /api/v1/markets/trending
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| exchange | string | 否 | 交易所,默认binance |
| limit | int | 否 | 返回数量,默认20,最大100 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "symbol": "BTCUSDT",
      "base_asset": "BTC",
      "quote_asset": "USDT",
      "price": "45000.50",
      "price_change": "+2.5%",
      "price_change_percent": 2.5,
      "volume_24h": "1234567890.12",
      "high_24h": "46000.00",
      "low_24h": "44000.00",
      "market_cap": "850000000000"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 2.2 获取自选币种列表

```http
GET /api/v1/markets/watchlist
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| exchange | string | 否 | 交易所,默认binance |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "symbol": "BTCUSDT",
      "exchange": "binance",
      "added_at": "2024-01-24T10:00:00Z",
      "ticker": {
        "price": "45000.50",
        "price_change": "+2.5%",
        "volume_24h": "1234567890.12"
      }
    }
  ],
  "timestamp": 1706073600
}
```

---

### 2.3 添加自选币种

```http
POST /api/v1/markets/watchlist
```

**请求体:**

```json
{
  "symbol": "ETHUSDT",
  "exchange": "binance"
}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "添加成功",
  "data": {
    "id": "uuid",
    "symbol": "ETHUSDT",
    "exchange": "binance",
    "added_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 2.4 删除自选币种

```http
DELETE /api/v1/markets/watchlist/{id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "删除成功",
  "data": null,
  "timestamp": 1706073600
}
```

---

### 2.5 获取单个币种行情

```http
GET /api/v1/markets/ticker/{symbol}
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 交易对,如 BTCUSDT |
| exchange | string | 否 | 交易所,默认binance |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "symbol": "BTCUSDT",
    "price": "45000.50",
    "price_change": "+2.5%",
    "price_change_percent": 2.5,
    "volume_24h": "1234567890.12",
    "high_24h": "46000.00",
    "low_24h": "44000.00",
    "ask_price": "45000.60",
    "bid_price": "45000.40",
    "timestamp": 1706073600
  },
  "timestamp": 1706073600
}
```

---

### 2.6 获取K线数据

```http
GET /api/v1/markets/kline/{symbol}
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| symbol | string | 是 | 交易对 |
| exchange | string | 否 | 交易所,默认binance |
| interval | string | 否 | K线周期,默认1m (1m, 5m, 15m, 1h, 4h, 1d, 1w) |
| limit | int | 否 | 返回数量,默认100,最大1000 |
| start_time | int | 否 | 开始时间(Unix时间戳,毫秒) |
| end_time | int | 否 | 结束时间(Unix时间戳,毫秒) |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "open_time": 1706073600000,
      "close_time": 1706073659999,
      "open": "45000.00",
      "high": "45050.00",
      "low": "44980.00",
      "close": "45020.00",
      "volume": "123.45",
      "quote_volume": "5555555.00",
      "trades_count": 1234
    }
  ],
  "timestamp": 1706073600
}
```

---

### 2.7 WebSocket订阅实时行情

```http
WS /ws/v1/markets/ticker
```

**客户端发送消息:**

```json
{
  "action": "subscribe",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "exchange": "binance"
}
```

**服务器推送消息:**

```json
{
  "event": "ticker",
  "data": {
    "symbol": "BTCUSDT",
    "price": "45000.50",
    "price_change": "+2.5%",
    "volume_24h": "1234567890.12",
    "timestamp": 1706073600
  }
}
```

---

## 3. 策略模块API (strategy-module)

### 3.1 上传策略文件

```http
POST /api/v1/strategies/upload
Content-Type: multipart/form-data
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 策略文件 (.py) |
| name | string | 是 | 策略名称 |
| description | string | 否 | 策略描述 |
| language | string | 否 | 编程语言,默认python |

**响应示例:**

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "uuid",
    "name": "双均线策略",
    "description": "基于5日和20日均线的趋势跟踪策略",
    "language": "python",
    "version": "1.0.0",
    "is_validated": true,
    "created_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 3.2 获取策略列表

```http
GET /api/v1/strategies
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| language | string | 否 | 编程语言过滤 |
| is_validated | boolean | 否 | 是否校验通过过滤 |
| limit | int | 否 | 返回数量,默认20 |
| offset | int | 否 | 偏移量,默认0 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 10,
    "items": [
      {
        "id": "uuid",
        "name": "双均线策略",
        "description": "基于5日和20日均线的趋势跟踪策略",
        "language": "python",
        "version": "1.0.0",
        "is_validated": true,
        "created_at": "2024-01-24T10:00:00Z",
        "updated_at": "2024-01-24T10:00:00Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 3.3 获取策略详情

```http
GET /api/v1/strategies/{strategy_id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "name": "双均线策略",
    "description": "基于5日和20日均线的趋势跟踪策略",
    "language": "python",
    "version": "1.0.0",
    "metadata": {
      "author": "User123",
      "parameters": [
        {
          "name": "short_period",
          "type": "int",
          "default": 5,
          "description": "短期均线周期"
        },
        {
          "name": "long_period",
          "type": "int",
          "default": 20,
          "description": "长期均线周期"
        }
      ]
    },
    "is_validated": true,
    "created_at": "2024-01-24T10:00:00Z",
    "updated_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 3.4 删除策略

```http
DELETE /api/v1/strategies/{strategy_id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "删除成功",
  "data": null,
  "timestamp": 1706073600
}
```

---

### 3.5 获取策略版本列表

```http
GET /api/v1/strategies/{strategy_id}/versions
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "version": "1.0.0",
      "changelog": "初始版本",
      "created_at": "2024-01-24T10:00:00Z"
    },
    {
      "id": "uuid",
      "version": "1.1.0",
      "changelog": "优化参数",
      "created_at": "2024-01-25T10:00:00Z"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 3.6 下载策略模板

```http
GET /api/v1/strategies/template
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| language | string | 否 | 编程语言,默认python |

**响应:** 文件下载 (strategy_template.py)

---

## 4. 交易模块API (trading-module)

### 4.1 添加交易所账户

```http
POST /api/v1/accounts
```

**请求体:**

```json
{
  "exchange": "binance",
  "account_name": "我的Binance账户",
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase"
}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "添加成功",
  "data": {
    "id": "uuid",
    "exchange": "binance",
    "account_name": "我的Binance账户",
    "api_key_preview": "abcd****efgh",
    "is_active": true,
    "created_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 4.2 获取账户列表

```http
GET /api/v1/accounts
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "exchange": "binance",
      "account_name": "我的Binance账户",
      "api_key_preview": "abcd****efgh",
      "is_active": true,
      "created_at": "2024-01-24T10:00:00Z"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 4.3 更新账户信息

```http
PUT /api/v1/accounts/{account_id}
```

**请求体:**

```json
{
  "account_name": "新的账户名",
  "api_key": "new_api_key",
  "api_secret": "new_api_secret"
}
```

---

### 4.4 删除账户

```http
DELETE /api/v1/accounts/{account_id}
```

---

### 4.5 查询账户余额

```http
GET /api/v1/accounts/{account_id}/balance
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "asset": "USDT",
      "free": "1000.50",
      "locked": "0.00",
      "total": "1000.50"
    },
    {
      "asset": "BTC",
      "free": "0.5",
      "locked": "0.1",
      "total": "0.6"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 4.6 查询持仓

```http
GET /api/v1/accounts/{account_id}/positions
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "symbol": "BTCUSDT",
      "side": "long",
      "quantity": "0.5",
      "entry_price": "44000.00",
      "current_price": "45000.00",
      "unrealized_pnl": "500.00",
      "pnl_percent": "2.27%"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 4.7 获取订单列表

```http
GET /api/v1/orders
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_id | string | 否 | 账户ID过滤 |
| execution_id | string | 否 | 策略执行ID过滤 |
| symbol | string | 否 | 交易对过滤 |
| status | string | 否 | 订单状态过滤 (new, partial_filled, filled, canceled, rejected) |
| is_simulation | boolean | 否 | 是否模拟订单 |
| limit | int | 否 | 返回数量,默认20 |
| offset | int | 否 | 偏移量,默认0 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 100,
    "items": [
      {
        "id": "123456789",
        "execution_id": "uuid",
        "account_id": "uuid",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "price": null,
        "quantity": "0.001",
        "filled_quantity": "0.001",
        "status": "filled",
        "is_simulation": false,
        "created_at": "2024-01-24T10:00:00Z",
        "updated_at": "2024-01-24T10:00:01Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 4.8 获取订单详情

```http
GET /api/v1/orders/{order_id}
```

---

### 4.9 取消订单

```http
POST /api/v1/orders/{order_id}/cancel
```

**响应示例:**

```json
{
  "code": 0,
  "message": "撤单成功",
  "data": {
    "id": "123456789",
    "status": "canceled"
  },
  "timestamp": 1706073600
}
```

---

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

### 7.1 用户注册

```http
POST /api/v1/auth/register
```

**请求体:**

```json
{
  "username": "user123",
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

---

### 7.2 用户登录

```http
POST /api/v1/auth/login
```

**请求体:**

```json
{
  "username": "user123",
  "password": "SecurePass123!"
}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "登录成功",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 604800,
    "user": {
      "id": "uuid",
      "username": "user123",
      "email": "user@example.com"
    }
  },
  "timestamp": 1706073600
}
```

---

### 7.3 刷新令牌

```http
POST /api/v1/auth/refresh
```

---

### 7.4 用户登出

```http
POST /api/v1/auth/logout
```

**请求头:**

```
Authorization: Bearer {access_token}
```

---

## 8. 健康检查和系统API

### 8.1 健康检查

```http
GET /health
```

**响应示例:**

```json
{
  "status": "healthy",
  "timestamp": "1706073600",
  "services": {
    "database": "up",
    "redis": "up",
    "docker": "up"
  }
}
```

---

### 8.2 就绪检查

```http
GET /ready
```

---

### 8.3 版本信息

```http
GET /version
```

**响应示例:**

```json
{
  "version": "1.0.0",
  "build_time": "2024-01-24T10:00:00Z",
  "git_commit": "abc123"
}
```

---

## 9. 错误处理

### 9.1 通用错误响应

所有API在发生错误时返回统一的错误格式:

```json
{
  "code": 40001,
  "message": "错误描述",
  "errors": [
    {
      "field": "参数名",
      "message": "具体错误信息"
    }
  ],
  "request_id": "uuid",
  "timestamp": 1706073600
}
```

### 9.2 常见错误码

| 错误码 | HTTP状态码 | 说明 |
|--------|-----------|------|
| 40001 | 400 | 请求参数错误 |
| 40002 | 404 | 资源不存在 |
| 40003 | 409 | 重复请求 |
| 40004 | 409 | 资源已存在 |
| 40005 | 403 | 权限不足 |
| 40006 | 401 | 认证失败 |
| 40007 | 400 | 策略校验失败 |
| 40008 | 400 | 余额不足 |
| 40009 | 400 | 订单失败 |
| 50001 | 500 | 服务器内部错误 |
| 50002 | 502 | 第三方服务错误 |
| 50003 | 503 | 服务不可用 |

---

## 10. 分页和排序

### 10.1 分页参数

所有列表API支持分页:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 20 | 每页数量,最大100 |
| offset | int | 0 | 偏移量 |

### 10.2 排序参数

| 参数 | 类型 | 说明 |
|------|------|------|
| sort | string | 排序字段,格式: `field:direction` |
| | | direction: `asc`(升序) 或 `desc`(降序) |
| | | 示例: `sort=created_at:desc` |

**示例:**

```http
GET /api/v1/orders?limit=50&offset=0&sort=created_at:desc&status=filled
```

---

## 11. 限流和配额

### 11.1 API限流

| 用户级别 | 限流规则 |
|----------|----------|
| 普通用户 | 100 requests / minute |
| 高级用户 | 500 requests / minute |

**限流响应头:**

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706073660
```

**超限响应:**

```json
{
  "code": 42901,
  "message": "API请求频率超限",
  "errors": [
    {
      "field": null,
      "message": "每分钟最多100次请求"
    }
  ],
  "timestamp": 1706073600
}
```

---

## 12. WebSocket连接管理

### 12.1 连接认证

WebSocket连接需要在URL中携带access_token:

```
WS /ws/v1/monitoring/strategies/{execution_id}?token={access_token}
```

### 12.2 心跳保活

客户端需定期发送心跳消息:

```json
{
  "event": "ping"
}
```

服务器响应:

```json
{
  "event": "pong"
}
```

### 12.3 连接超时

- 心跳间隔: 30秒
- 连接超时: 60秒(无心跳则断开连接)

---

## 附录: OpenAPI规范生成

所有API均支持通过FastAPI自动生成OpenAPI规范文档:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

**文档结束**
