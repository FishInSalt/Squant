## 7. 认证和授权API (可选)

### 7.1 用户注册

```http
POST /api/v1/auth/register
```

**请求体:**

```json
{
  "username": "user123",
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

---

### 7.2 用户登录

```http
POST /api/v1/auth/login
```

**请求体:**

```json
{
  "username": "user123",
  "password": "SecurePass123!"
}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "登录成功",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 604800,
    "user": {
      "id": "uuid",
      "username": "user123",
      "email": "user@example.com"
    }
  },
  "timestamp": 1706073600
}
```

---

### 7.3 刷新令牌

```http
POST /api/v1/auth/refresh
```

---

### 7.4 用户登出

```http
POST /api/v1/auth/logout
```

**请求头:**

```
Authorization: Bearer {access_token}
```

---

## 8. 健康检查和系统API
