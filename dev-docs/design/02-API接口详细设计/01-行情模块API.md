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
