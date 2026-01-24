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
