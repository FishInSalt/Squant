# Squant 开发指南

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- Docker & Docker Compose
- Conda

### 1. 启动基础设施

```bash
cd /home/li416/Squant_oc
docker compose up -d postgres redis
```

### 2. 激活 Python 环境

```bash
conda activate squant
```

### 3. 初始化数据库

```bash
cd src/backend
alembic upgrade head
```

### 4. 启动后端服务

```bash
cd src/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 启动前端服务

```bash
cd src/frontend
npm run dev
```

## 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| **后端 API** | http://localhost:8000 | FastAPI 服务 |
| **API 文档** | http://localhost:8000/docs | Swagger UI |
| **前端应用** | http://localhost:5173 | Vue 3 应用 |

## 数据库迁移

### 生成新迁移

```bash
cd src/backend
alembic revision --autogenerate -m "描述迁移内容"
```

### 执行迁移

```bash
alembic upgrade head
```

### 回滚一个版本

```bash
alembic downgrade -1
```

### 查看当前版本

```bash
alembic current
```

### 查看迁移历史

```bash
alembic history
```

## 项目结构

```
Squant_oc/
├── src/
│   ├── backend/          # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/       # API 路由
│   │   │   ├── auth/      # 认证模块
│   │   │   ├── core/      # 核心配置
│   │   │   ├── db/        # 数据库配置
│   │   │   ├── market/    # 行情模块
│   │   │   ├── models/    # 数据模型
│   │   │   ├── monitoring/ # 监控模块
│   │   │   ├── runtime/    # 运行时模块
│   │   │   ├── schemas/   # Pydantic schemas
│   │   │   ├── strategy/  # 策略模块
│   │   │   ├── trading/   # 交易模块
│   │   │   └── utils/     # 工具函数
│   │   ├── alembic/          # 数据库迁移
│   │   ├── tests/            # 测试
│   │   ├── scripts/          # 脚本
│   │   ├── requirements.txt   # Python 依赖
│   │   └── Dockerfile
│   └── frontend/         # Vue 3 前端
│       ├── src/
│       ├── package.json
│       └── vite.config.ts
├── dev-docs/              # 开发文档
├── docker-compose.yml       # Docker 编排
└── README.md
```

## 开发工具

### 后端

| 工具 | 命令 | 用途 |
|------|--------|------|
| **uvicorn** | `uvicorn app.main:app --reload` | 开发服务器 |
| **alembic** | `alembic revision/upgrade` | 数据库迁移 |
| **pytest** | `pytest` | 运行测试 |
| **black** | `black .` | 代码格式化 |
| **ruff** | `ruff check .` | 代码检查 |
| **mypy** | `mypy .` | 类型检查 |

### 前端

| 工具 | 命令 | 用途 |
|------|--------|------|
| **vite** | `npm run dev` | 开发服务器 |
| **vite build** | `npm run build` | 生产构建 |
| **npm test** | `npm test` | 运行测试 |

## 环境变量

后端环境变量配置文件：`src/backend/.env`

```bash
APP_NAME=Squant
APP_ENV=development
DEBUG=True
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/squant
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-jwt-secret-key-change-this
```

## 常见问题

### PostgreSQL 连接失败

```bash
# 检查 Docker 服务状态
docker compose ps

# 重启服务
docker compose restart postgres
```

### 端口被占用

```bash
# 查找占用端口的进程
lsof -i :8000
lsof -i :5432
lsof -i :6379

# 杀死进程
kill -9 <PID>
```

### Python 包未找到

```bash
# 确认激活了 conda 环境
conda activate squant

# 重新安装依赖
pip install -r requirements.txt
```

## 停止服务

```bash
# 停止 Docker 服务
docker compose down

# 停止后端（按 Ctrl+C）
```

---

**最后更新**: 2026-01-24
**版本**: 0.1.0
