# 风控模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/risk/rules

获取风控规则列表。

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "uuid",
                "name": "单笔限额",
                "type": "order_limit",
                "params": {"max_amount_usdt": 1000},
                "enabled": true
            }
        ]
    }
}
```

---

## POST /api/v1/risk/rules

创建风控规则。

**请求体**：

```json
{
    "name": "单笔限额",
    "type": "order_limit",
    "params": {"max_amount_usdt": 1000}
}
```

---

## PUT /api/v1/risk/rules/{id}

更新风控规则。

---

## DELETE /api/v1/risk/rules/{id}

删除风控规则。

---

## POST /api/v1/risk/circuit-breaker

触发熔断（停止所有策略）。

---

## POST /api/v1/risk/close-all

一键平仓。

---

## GET /api/v1/risk/triggers

获取风控触发记录。
