#!/bin/bash

# 测试环境管理脚本
# 用于启动、停止和管理集成测试环境

set -e

COMPOSE_FILE="docker-compose.test.yml"
PROJECT_NAME="squant-test"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否运行
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# 启动测试环境
start() {
    print_info "Starting test environment..."
    check_docker

    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d postgres-test redis-test

    print_info "Waiting for services to be ready..."
    sleep 5

    # 检查PostgreSQL
    if docker compose -f $COMPOSE_FILE -p $PROJECT_NAME exec -T postgres-test pg_isready -U squant_test > /dev/null 2>&1; then
        print_info "PostgreSQL is ready"
    else
        print_error "PostgreSQL failed to start"
        exit 1
    fi

    # 检查Redis
    if docker compose -f $COMPOSE_FILE -p $PROJECT_NAME exec -T redis-test redis-cli ping > /dev/null 2>&1; then
        print_info "Redis is ready"
    else
        print_error "Redis failed to start"
        exit 1
    fi

    print_info "Running database migrations..."
    export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
    export REDIS_URL="redis://localhost:6380/0"
    uv run alembic upgrade head

    print_info "Test environment is ready!"
    print_info "PostgreSQL: localhost:5433 (user: squant_test, password: squant_test, db: squant_test)"
    print_info "Redis: localhost:6380"
}

# 停止测试环境
stop() {
    print_info "Stopping test environment..."
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME stop
    print_info "Test environment stopped"
}

# 停止并删除测试环境（包括数据卷）
down() {
    print_warn "Stopping and removing test environment (including volumes)..."
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME down -v
    print_info "Test environment removed"
}

# 重启测试环境
restart() {
    print_info "Restarting test environment..."
    stop
    start
}

# 查看测试环境状态
status() {
    print_info "Test environment status:"
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME ps
}

# 查看日志
logs() {
    service=$1
    if [ -z "$service" ]; then
        docker compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f
    else
        docker compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f $service
    fi
}

# 重置数据库（删除所有表并重新创建）
reset_db() {
    print_warn "Resetting test database..."
    export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"

    print_info "Dropping all tables..."
    uv run alembic downgrade base

    print_info "Creating all tables..."
    uv run alembic upgrade head

    print_info "Database reset complete"
}

# 清空Redis数据
clear_redis() {
    print_warn "Clearing Redis data..."
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME exec -T redis-test redis-cli FLUSHALL
    print_info "Redis data cleared"
}

# 运行集成测试
run_tests() {
    print_info "Running integration tests..."

    # 设置测试环境变量
    export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
    export REDIS_URL="redis://localhost:6380/0"
    export SECRET_KEY="test-secret-key-for-integration-testing-min-32-chars"
    export ENCRYPTION_KEY="test-encryption-key-32-chars!!"

    # 运行测试
    uv run pytest tests/integration "$@"
}

# 运行E2E测试（启动完整应用栈）
run_e2e() {
    print_info "Starting E2E test environment..."
    check_docker

    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME --profile e2e up -d

    print_info "Waiting for application to be ready..."
    sleep 10

    # 设置测试环境变量
    export API_URL="http://localhost:8000"
    export DATABASE_URL="postgresql+asyncpg://squant_test:squant_test@localhost:5433/squant_test"
    export REDIS_URL="redis://localhost:6380/0"

    print_info "Running E2E tests..."
    uv run pytest tests/e2e "$@"

    print_info "Stopping E2E environment..."
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME --profile e2e down
}

# 进入PostgreSQL shell
psql() {
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME exec postgres-test \
        psql -U squant_test -d squant_test
}

# 进入Redis CLI
redis_cli() {
    docker compose -f $COMPOSE_FILE -p $PROJECT_NAME exec redis-test redis-cli
}

# 显示帮助信息
usage() {
    cat << EOF
Usage: $0 <command> [options]

Commands:
    start           启动测试环境 (PostgreSQL + Redis)
    stop            停止测试环境
    down            停止并删除测试环境（包括数据卷）
    restart         重启测试环境
    status          查看测试环境状态
    logs [service]  查看日志（可选指定服务名）

    reset-db        重置数据库（删除所有表并重新创建）
    clear-redis     清空Redis数据

    test [args]     运行集成测试
    e2e [args]      运行E2E测试（启动完整应用栈）

    psql            进入PostgreSQL shell
    redis-cli       进入Redis CLI

Examples:
    $0 start                    # 启动测试环境
    $0 test -v                  # 运行集成测试（详细输出）
    $0 test -k test_order       # 运行包含test_order的测试
    $0 logs postgres-test       # 查看PostgreSQL日志
    $0 reset-db                 # 重置数据库
    $0 down                     # 完全清理测试环境

EOF
}

# 主逻辑
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    down)
        down
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    reset-db)
        reset_db
        ;;
    clear-redis)
        clear_redis
        ;;
    test)
        shift
        run_tests "$@"
        ;;
    e2e)
        shift
        run_e2e "$@"
        ;;
    psql)
        psql
        ;;
    redis-cli)
        redis_cli
        ;;
    *)
        usage
        exit 1
        ;;
esac
