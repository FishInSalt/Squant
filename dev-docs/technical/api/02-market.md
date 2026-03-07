# 行情模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/market/tickers

获取热门行情列表。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| exchange | string | 否 | 交易所筛选: binance, okx, 空=全部 |
| limit | int | 否 | 返回数量，默认20，最大50 |

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "price": "67234.56",
                "change_24h": "2.34",
                "volume_24h": "12500000000",
                "high_24h": "68000.00",
                "low_24h": "65000.00",
                "updated_at": "2025-01-24T12:00:00Z"
            }
        ]
    }
}
```

---

## GET /api/v1/market/klines

获取 K 线数据。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| exchange | string | 是 | 交易所 |
| symbol | string | 是 | 交易对，如 BTC/USDT |
| timeframe | string | 是 | 时间周期: 1m,5m,15m,1h,4h,1d,1w |
| start | string | 否 | 开始时间 ISO 8601 |
| end | string | 否 | 结束时间 ISO 8601 |
| limit | int | 否 | 返回数量，默认100，最大1000 |

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "time": "2025-01-24T12:00:00Z",
                "open": "67000.00",
                "high": "67500.00",
                "low": "66800.00",
                "close": "67234.56",
                "volume": "1234.56"
            }
        ]
    }
}
```

---

## GET /api/v1/market/watchlist

获取自选列表。

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "uuid",
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "price": "67234.56",
                "change_24h": "2.34"
            }
        ]
    }
}
```

---

## POST /api/v1/market/watchlist

添加自选。

**请求体**：

```json
{
    "exchange": "binance",
    "symbol": "ETH/USDT"
}
```

---

## DELETE /api/v1/market/watchlist/{id}

删除自选。
