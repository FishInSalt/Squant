#!/bin/bash
set -e

# Squant 部署脚本
# 使用方式: ./scripts/deploy.sh [dev|prod]

MODE=${1:-prod}
COMPOSE_FILE="docker-compose.yml"

echo "=========================================="
echo "  Squant 部署脚本"
echo "  模式: $MODE"
echo "=========================================="

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "错误: .env 文件不存在"
    echo "请复制 .env.example 并配置必要的环境变量:"
    echo "  cp .env.example .env"
    echo "  vim .env"
    exit 1
fi

# 开发模式
if [ "$MODE" = "dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
    echo "启动开发环境..."

    # 启动数据库服务
    docker compose -f $COMPOSE_FILE up -d postgres redis

    echo ""
    echo "数据库服务已启动:"
    echo "  - PostgreSQL: localhost:5433"
    echo "  - Redis: localhost:6380"
    echo ""
    echo "启动后端 (在另一个终端):"
    echo "  cd $(pwd) && uv run uvicorn squant.main:app --reload"
    echo ""
    echo "启动前端 (在另一个终端):"
    echo "  cd $(pwd)/frontend && npm run dev"
    exit 0
fi

# 生产模式
echo "构建并启动生产环境..."

# 构建镜像
echo "1. 构建 Docker 镜像..."
docker compose -f $COMPOSE_FILE build

# 运行数据库迁移
echo "2. 启动数据库服务..."
docker compose -f $COMPOSE_FILE up -d postgres redis
sleep 10  # 等待数据库就绪

echo "3. 运行数据库迁移..."
docker compose -f $COMPOSE_FILE run --rm backend alembic upgrade head

# 启动所有服务
echo "4. 启动所有服务..."
docker compose -f $COMPOSE_FILE up -d

echo ""
echo "=========================================="
echo "  部署完成!"
echo "=========================================="
echo ""
echo "服务状态:"
docker compose -f $COMPOSE_FILE ps
echo ""
echo "访问地址:"
echo "  - 前端: http://localhost (通过 Caddy)"
echo "  - API:  http://localhost/api"
echo "  - 直接访问前端: http://localhost:3000"
echo "  - 直接访问 API: http://localhost:8000"
echo ""
echo "查看日志: docker compose logs -f [service]"
echo "停止服务: docker compose down"
