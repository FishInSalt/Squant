# 账户模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/accounts

获取交易所账户列表。

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "uuid",
                "exchange": "binance",
                "name": "主账户",
                "testnet": false,
                "is_active": true,
                "created_at": "2025-01-24T12:00:00Z"
            }
        ]
    }
}
```

---

## POST /api/v1/accounts

添加交易所账户。

**请求体**：

```json
{
    "exchange": "binance",
    "name": "主账户",
    "api_key": "xxx",
    "api_secret": "xxx",
    "passphrase": "",
    "testnet": false
}
```

---

## POST /api/v1/accounts/{id}/test

测试 API 连接。

**响应**：

```json
{
    "code": 0,
    "data": {
        "success": true,
        "permissions": ["read", "spot_trade"],
        "message": "连接成功"
    }
}
```

---

## DELETE /api/v1/accounts/{id}

删除账户。

---

## GET /api/v1/accounts/{id}/balance

获取账户余额。

**响应**：

```json
{
    "code": 0,
    "data": {
        "total_usd": "15234.56",
        "balances": [
            {"currency": "USDT", "free": "10000.00", "locked": "500.00"},
            {"currency": "BTC", "free": "0.1", "locked": "0"}
        ]
    }
}
```
