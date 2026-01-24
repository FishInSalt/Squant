## 8. 健康检查和系统API

### 8.1 健康检查

```http
GET /health
```

**响应示例:**

```json
{
  "status": "healthy",
  "timestamp": "1706073600",
  "services": {
    "database": "up",
    "redis": "up",
    "docker": "up"
  }
}
```

---

### 8.2 就绪检查

```http
GET /ready
```

---

### 8.3 版本信息

```http
GET /version
```

**响应示例:**

```json
{
  "version": "1.0.0",
  "build_time": "2024-01-24T10:00:00Z",
  "git_commit": "abc123"
}
```

---

## 9. 错误处理
