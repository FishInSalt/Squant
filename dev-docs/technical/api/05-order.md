# 订单模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/orders

获取订单列表。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| run_id | string | 否 | 按策略筛选 |
| status | string | 否 | pending,submitted,partial,filled,cancelled,rejected |
| symbol | string | 否 | 按交易对筛选 |
| start | string | 否 | 开始时间 |
| end | string | 否 | 结束时间 |

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "uuid",
                "run_id": "uuid",
                "strategy_name": "双均线策略",
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "side": "buy",
                "type": "limit",
                "price": "67000.00",
                "amount": "0.01",
                "filled": "0.01",
                "avg_price": "66998.50",
                "status": "filled",
                "created_at": "2025-01-24T12:00:00Z"
            }
        ],
        "total": 100
    }
}
```

---

## POST /api/v1/orders/{id}/cancel

取消订单。
