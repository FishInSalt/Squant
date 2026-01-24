# 系统模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## GET /api/v1/system/status

获取系统状态。

**响应**：

```json
{
    "code": 0,
    "data": {
        "version": "1.0.0",
        "uptime": 86400,
        "exchanges": {
            "binance": {"status": "connected", "latency_ms": 50},
            "okx": {"status": "connected", "latency_ms": 80}
        },
        "running_strategies": 3,
        "database": "healthy",
        "redis": "healthy"
    }
}
```

---

## POST /api/v1/system/data/download

下载历史数据。

**请求体**：

```json
{
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "start": "2024-01-01",
    "end": "2024-12-31"
}
```

---

## GET /api/v1/system/logs

获取系统日志。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| level | string | 否 | debug,info,warning,error |
| module | string | 否 | 模块名 |
| start | string | 否 | 开始时间 |
| limit | int | 否 | 数量 |
