## 3. 策略模块API (strategy-module)

### 3.1 上传策略文件

```http
POST /api/v1/strategies/upload
Content-Type: multipart/form-data
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 策略文件 (.py) |
| name | string | 是 | 策略名称 |
| description | string | 否 | 策略描述 |
| language | string | 否 | 编程语言,默认python |

**响应示例:**

```json
{
  "code": 0,
  "message": "上传成功",
  "data": {
    "id": "uuid",
    "name": "双均线策略",
    "description": "基于5日和20日均线的趋势跟踪策略",
    "language": "python",
    "version": "1.0.0",
    "is_validated": true,
    "created_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 3.2 获取策略列表

```http
GET /api/v1/strategies
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| language | string | 否 | 编程语言过滤 |
| is_validated | boolean | 否 | 是否校验通过过滤 |
| limit | int | 否 | 返回数量,默认20 |
| offset | int | 否 | 偏移量,默认0 |

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 10,
    "items": [
      {
        "id": "uuid",
        "name": "双均线策略",
        "description": "基于5日和20日均线的趋势跟踪策略",
        "language": "python",
        "version": "1.0.0",
        "is_validated": true,
        "created_at": "2024-01-24T10:00:00Z",
        "updated_at": "2024-01-24T10:00:00Z"
      }
    ]
  },
  "timestamp": 1706073600
}
```

---

### 3.3 获取策略详情

```http
GET /api/v1/strategies/{strategy_id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "uuid",
    "name": "双均线策略",
    "description": "基于5日和20日均线的趋势跟踪策略",
    "language": "python",
    "version": "1.0.0",
    "metadata": {
      "author": "User123",
      "parameters": [
        {
          "name": "short_period",
          "type": "int",
          "default": 5,
          "description": "短期均线周期"
        },
        {
          "name": "long_period",
          "type": "int",
          "default": 20,
          "description": "长期均线周期"
        }
      ]
    },
    "is_validated": true,
    "created_at": "2024-01-24T10:00:00Z",
    "updated_at": "2024-01-24T10:00:00Z"
  },
  "timestamp": 1706073600
}
```

---

### 3.4 删除策略

```http
DELETE /api/v1/strategies/{strategy_id}
```

**响应示例:**

```json
{
  "code": 0,
  "message": "删除成功",
  "data": null,
  "timestamp": 1706073600
}
```

---

### 3.5 获取策略版本列表

```http
GET /api/v1/strategies/{strategy_id}/versions
```

**响应示例:**

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": "uuid",
      "version": "1.0.0",
      "changelog": "初始版本",
      "created_at": "2024-01-24T10:00:00Z"
    },
    {
      "id": "uuid",
      "version": "1.1.0",
      "changelog": "优化参数",
      "created_at": "2024-01-25T10:00:00Z"
    }
  ],
  "timestamp": 1706073600
}
```

---

### 3.6 下载策略模板

```http
GET /api/v1/strategies/template
```

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| language | string | 否 | 编程语言,默认python |

**响应:** 文件下载 (strategy_template.py)

---

## 4. 交易模块API (trading-module)
