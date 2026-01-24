# Docker Compose 配置

> **关联文档**: [技术选型](../overview/01-tech-stack.md), [系统架构](../architecture/01-overview.md)

## 1. 服务编排

```yaml
# docker-compose.yml
version: '3.8'

services:
  # PostgreSQL + TimescaleDB
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: squant-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER:-squant}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Database password required}
      POSTGRES_DB: ${DB_NAME:-squant}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-squant} -d ${DB_NAME:-squant}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - squant-network

  # Redis
  redis:
    image: redis:7-alpine
    container_name: squant-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:?Redis password required}
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - squant-network

  # Backend API
  backend:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: squant-backend
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://${DB_USER:-squant}:${DB_PASSWORD}@postgres:5432/${DB_NAME:-squant}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
    volumes:
      - strategy_files:/app/strategies
      - logs:/app/logs
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - squant-network

  # Frontend (Nginx serving static files)
  frontend:
    image: nginx:alpine
    container_name: squant-frontend
    restart: unless-stopped
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./nginx/frontend.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "127.0.0.1:3000:80"
    depends_on:
      - backend
    networks:
      - squant-network

  # Caddy (Reverse Proxy with Auto HTTPS)
  caddy:
    image: caddy:2-alpine
    container_name: squant-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
      - frontend
    networks:
      - squant-network

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  strategy_files:
    driver: local
  logs:
    driver: local
  caddy_data:
    driver: local
  caddy_config:
    driver: local

networks:
  squant-network:
    driver: bridge
```

## 2. Backend Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim AS base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============ 开发阶段 ============
FROM base AS development

# 安装开发工具
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装所有依赖（包括开发依赖）
RUN uv sync --frozen

# 复制源代码
COPY . .

CMD ["uv", "run", "uvicorn", "squant.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============ 构建阶段 ============
FROM base AS builder

RUN pip install uv

COPY pyproject.toml uv.lock ./

# 只安装生产依赖
RUN uv sync --frozen --no-dev

# ============ 生产阶段 ============
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# 从构建阶段复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 设置 PATH
ENV PATH="/app/.venv/bin:$PATH"

# 复制应用代码
COPY --chown=appuser:appuser squant/ ./squant/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./

# 创建必要目录
RUN mkdir -p /app/strategies /app/logs && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "squant.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 3. Caddy 配置

```caddyfile
# Caddyfile
{
    email {$ACME_EMAIL:admin@example.com}
}

# 本地开发使用 localhost
localhost {
    # API 代理
    handle /api/* {
        reverse_proxy backend:8000
    }

    # WebSocket 代理
    handle /ws/* {
        reverse_proxy backend:8000
    }

    # 前端静态文件
    handle {
        reverse_proxy frontend:80
    }
}

# 生产环境使用实际域名
# squant.yourdomain.com {
#     # API 代理
#     handle /api/* {
#         reverse_proxy backend:8000
#     }
#
#     # WebSocket 代理
#     handle /ws/* {
#         reverse_proxy backend:8000
#     }
#
#     # 前端静态文件
#     handle {
#         reverse_proxy frontend:80
#     }
# }
```

## 4. Nginx 前端配置

```nginx
# nginx/frontend.conf
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
    }
}
```
