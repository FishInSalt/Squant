# 策略模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/strategies

获取策略列表。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | active, archived |
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |

**响应**：

```json
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "uuid",
                "name": "双均线策略",
                "version": "1.0.0",
                "description": "基于双均线交叉的趋势跟踪策略",
                "status": "active",
                "created_at": "2025-01-24T12:00:00Z"
            }
        ],
        "total": 10,
        "page": 1,
        "page_size": 20
    }
}
```

---

## GET /api/v1/strategies/{id}

获取策略详情。

**响应**：

```json
{
    "code": 0,
    "data": {
        "id": "uuid",
        "name": "双均线策略",
        "version": "1.0.0",
        "description": "...",
        "code": "class DualMA(Strategy): ...",
        "params_schema": {
            "type": "object",
            "properties": {
                "fast_period": {"type": "integer", "default": 10},
                "slow_period": {"type": "integer", "default": 30}
            }
        },
        "default_params": {
            "fast_period": 10,
            "slow_period": 30
        },
        "status": "active",
        "created_at": "2025-01-24T12:00:00Z"
    }
}
```

---

## POST /api/v1/strategies

上传策略。

**请求体** (multipart/form-data)：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | .py 策略文件 |

**响应**：

```json
{
    "code": 0,
    "data": {
        "id": "uuid",
        "name": "双均线策略",
        "validation": {
            "success": true,
            "warnings": []
        }
    }
}
```

**校验失败响应**：

```json
{
    "code": 3002,
    "message": "策略校验失败",
    "data": {
        "errors": [
            {"line": 10, "message": "必须继承 Strategy 基类"},
            {"line": 25, "message": "禁止导入 os 模块"}
        ]
    }
}
```

---

## DELETE /api/v1/strategies/{id}

删除策略。
