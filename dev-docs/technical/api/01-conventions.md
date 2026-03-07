# API 规范与约定

> **关联文档**: [系统架构](../architecture/01-overview.md), [数据模型](../data-model/01-er-diagram.md)

## 1. 基础约定

| 项目 | 约定 |
|------|------|
| 基础路径 | `/api/v1` |
| 协议 | HTTPS (生产环境) |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601 (`2025-01-24T12:00:00Z`) |
| 分页参数 | `page` (从1开始), `page_size` (默认20, 最大100) |

## 2. 请求格式

```http
POST /api/v1/strategies HTTP/1.1
Content-Type: application/json

{
    "name": "双均线策略",
    "code": "..."
}
```

## 3. 响应格式

### 成功响应

```json
{
    "code": 0,
    "message": "success",
    "data": { ... }
}
```

### 分页响应

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [ ... ],
        "total": 100,
        "page": 1,
        "page_size": 20
    }
}
```

### 错误响应

```json
{
    "code": 3001,
    "message": "策略不存在",
    "data": null
}
```

## 4. 错误码定义

| 范围 | 模块 | 示例 |
|------|------|------|
| 0 | 成功 | 0 = SUCCESS |
| 1000-1999 | 通用错误 | 1001 = INVALID_PARAMS |
| 2000-2999 | 行情模块 | 2001 = MARKET_DATA_UNAVAILABLE |
| 3000-3999 | 策略模块 | 3001 = STRATEGY_NOT_FOUND |
| 4000-4999 | 交易模块 | 4001 = INSUFFICIENT_BALANCE |
| 5000-5999 | 风控模块 | 5001 = RISK_LIMIT_EXCEEDED |
| 6000-6999 | 账户模块 | 6001 = EXCHANGE_NOT_CONFIGURED |

## 5. OpenAPI 文档

FastAPI 自动生成 OpenAPI 文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
