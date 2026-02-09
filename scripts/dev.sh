#!/bin/bash
# Squant 开发环境脚本

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# 启动开发依赖
start_deps() {
    log_info "Starting development dependencies..."
    docker compose -f docker-compose.dev.yml up -d
    log_info "Waiting for services to be ready..."
    sleep 3
    log_info "Services started successfully"
}

# 停止开发依赖
stop_deps() {
    log_info "Stopping development dependencies..."
    docker compose -f docker-compose.dev.yml down
}

# 运行数据库迁移
migrate() {
    log_info "Running database migrations..."
    uv run alembic upgrade head
}

# 启动后端开发服务器
run_backend() {
    log_info "Starting backend development server..."
    uv run uvicorn squant.main:app --reload --host 0.0.0.0 --port 8000
}

# 启动前端开发服务器
run_frontend() {
    log_info "Starting frontend development server..."
    cd frontend && pnpm dev
}

# 运行测试
test() {
    log_info "Running tests..."
    uv run pytest -v
}

# 代码检查
lint() {
    log_info "Running linters..."
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy src/squant/
}

# 格式化代码
format() {
    log_info "Formatting code..."
    uv run ruff format .
    uv run ruff check --fix .
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
    echo "  format    Format code"
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
    format)
        format
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
