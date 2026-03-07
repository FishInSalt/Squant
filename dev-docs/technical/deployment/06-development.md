# 本地开发环境

> **关联文档**: [Docker 配置](./01-docker.md), [环境变量](./02-environment.md)

## 1. 开发环境 Docker Compose

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: squant-postgres-dev
    environment:
      POSTGRES_USER: squant
      POSTGRES_PASSWORD: devpassword
      POSTGRES_DB: squant
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    container_name: squant-redis-dev
    command: redis-server --appendonly yes
    volumes:
      - redis_dev_data:/data
    ports:
      - "6379:6379"

volumes:
  postgres_dev_data:
  redis_dev_data:
```

## 2. 开发环境配置

```bash
# .env.development

APP_ENV=development
DEBUG=true
SECRET_KEY=dev-secret-key-not-for-production

# 本地数据库
DATABASE_URL=postgresql+asyncpg://squant:devpassword@localhost:5432/squant

# 本地 Redis (无密码)
REDIS_URL=redis://localhost:6379/0

# 开发用加密密钥
ENCRYPTION_KEY=dev-encryption-key-32-bytes-xx

# 日志
LOG_LEVEL=DEBUG
LOG_FORMAT=text

# 禁用沙箱 (开发环境)
STRATEGY_SANDBOX_ENABLED=false
```

## 3. 开发环境启动脚本

```bash
#!/bin/bash
# scripts/dev.sh

set -euo pipefail

# 启动开发依赖
start_deps() {
    echo "Starting development dependencies..."
    docker compose -f docker-compose.dev.yml up -d
    echo "Waiting for services to be ready..."
    sleep 3
}

# 停止开发依赖
stop_deps() {
    echo "Stopping development dependencies..."
    docker compose -f docker-compose.dev.yml down
}

# 运行数据库迁移
migrate() {
    echo "Running database migrations..."
    uv run alembic upgrade head
}

# 启动后端开发服务器
run_backend() {
    echo "Starting backend development server..."
    uv run uvicorn squant.main:app --reload --host 0.0.0.0 --port 8000
}

# 启动前端开发服务器
run_frontend() {
    echo "Starting frontend development server..."
    cd frontend && pnpm dev
}

# 运行测试
test() {
    echo "Running tests..."
    uv run pytest -v
}

# 代码检查
lint() {
    echo "Running linters..."
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy squant/
}

# 使用说明
usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start     Start development dependencies (postgres, redis)"
    echo "  stop      Stop development dependencies"
    echo "  migrate   Run database migrations"
    echo "  backend   Start backend development server"
    echo "  frontend  Start frontend development server"
    echo "  test      Run tests"
    echo "  lint      Run linters"
    echo "  all       Start deps, migrate, and run backend"
}

case "${1:-}" in
    start)
        start_deps
        ;;
    stop)
        stop_deps
        ;;
    migrate)
        migrate
        ;;
    backend)
        run_backend
        ;;
    frontend)
        run_frontend
        ;;
    test)
        test
        ;;
    lint)
        lint
        ;;
    all)
        start_deps
        migrate
        run_backend
        ;;
    *)
        usage
        exit 1
        ;;
esac
```

## 4. 快速开始指南

```bash
# 1. 克隆项目
git clone https://github.com/yourname/squant.git
cd squant

# 2. 安装 Python 依赖
uv sync

# 3. 复制环境变量配置
cp .env.example .env.development
cp .env.development .env

# 4. 启动开发环境
./scripts/dev.sh start

# 5. 运行数据库迁移
./scripts/dev.sh migrate

# 6. 启动后端服务
./scripts/dev.sh backend

# 7. 另开终端，启动前端 (可选)
cd frontend
pnpm install
pnpm dev

# 8. 访问应用
# - API: http://localhost:8000
# - API 文档: http://localhost:8000/docs
# - 前端: http://localhost:5173
```

## 5. VS Code 开发配置

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.analysis.typeCheckingMode": "basic",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.fixAll.ruff": "explicit",
        "source.organizeImports.ruff": "explicit"
    },
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff"
    },
    "ruff.lint.args": ["--config=pyproject.toml"],
    "files.exclude": {
        "**/__pycache__": true,
        "**/.pytest_cache": true,
        "**/.mypy_cache": true,
        "**/.ruff_cache": true
    }
}
```

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Backend: FastAPI",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": ["squant.main:app", "--reload", "--port", "8000"],
            "jinja": true,
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        },
        {
            "name": "Backend: Debug Tests",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["-v", "-s"],
            "jinja": true
        }
    ]
}
```

## 6. 部署检查清单

### 生产环境上线前检查

```markdown
## 安全检查
- [ ] 所有敏感信息通过环境变量配置
- [ ] SECRET_KEY 使用强随机值 (>= 32 字符)
- [ ] 数据库密码使用强密码
- [ ] Redis 设置密码保护
- [ ] API Key 加密存储
- [ ] 禁用 DEBUG 模式
- [ ] 配置 HTTPS (Caddy 自动)

## 数据库检查
- [ ] 运行所有数据库迁移
- [ ] 创建必要索引
- [ ] 配置 TimescaleDB 压缩策略
- [ ] 配置数据保留策略

## 备份检查
- [ ] 配置自动备份脚本
- [ ] 测试备份恢复流程
- [ ] 设置异地备份 (可选)

## 监控检查
- [ ] 健康检查端点正常
- [ ] 日志正确输出
- [ ] 配置日志轮转

## 性能检查
- [ ] 配置连接池大小
- [ ] 配置策略进程数限制
- [ ] 测试负载情况
```

## 7. 常用运维命令

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 查看服务状态
docker compose ps

# 重启单个服务
docker compose restart backend

# 查看日志
docker compose logs -f backend

# 进入容器
docker compose exec backend bash

# 运行数据库迁移
docker compose exec backend alembic upgrade head

# 备份数据库
./scripts/backup.sh

# 更新部署
git pull
docker compose build backend
docker compose up -d backend
```
