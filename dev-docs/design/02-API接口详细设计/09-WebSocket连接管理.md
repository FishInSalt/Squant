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
