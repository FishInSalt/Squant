#!/bin/bash
# Squant Backend Service Management Script
# Usage: ./backend.sh {start|stop|restart|status|logs}

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

# Auto-detect project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Runtime files
LOG_FILE="/tmp/squant_backend.log"
PID_FILE="/tmp/squant_backend.pid"

# Server settings
HOST="0.0.0.0"
PORT="8000"
APP_MODULE="squant.main:app"

# =============================================================================
# Utility Functions
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

# Check if a command exists
check_command() {
    command -v "$1" &> /dev/null
}

# Get process ID if running
get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        fi
    fi
    # Fallback: find by process name
    pgrep -f "uvicorn ${APP_MODULE}" 2>/dev/null | head -1 || true
}

# Wait for service to be ready
wait_for_ready() {
    local max_attempts=20
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "http://localhost:${PORT}/api/v1/health" > /dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
        attempt=$((attempt + 1))
    done
    return 1
}

# =============================================================================
# Commands
# =============================================================================

cmd_start() {
    cd "$PROJECT_ROOT"

    # Check if already running
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ]; then
        log_warn "Backend already running (PID: $pid)"
        return 0
    fi

    # Verify uv is available
    if ! check_command uv; then
        log_error "uv not found. Please install uv first."
        exit 1
    fi

    # Verify .env file exists
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_error ".env file not found. Copy from .env.example and configure."
        exit 1
    fi

    log_info "Starting backend server..."

    # Start uvicorn in background using uv run
    nohup uv run uvicorn "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        > "$LOG_FILE" 2>&1 &

    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # Wait for service to be ready
    log_info "Waiting for service to be ready..."
    if wait_for_ready; then
        log_info "Backend started successfully (PID: $new_pid)"
        log_info "API docs: http://localhost:${PORT}/api/v1/docs"
        log_info "Log file: $LOG_FILE"
    else
        log_error "Backend failed to start within timeout"
        log_error "Check logs: tail -50 $LOG_FILE"
        # Show last few lines of log
        echo ""
        tail -20 "$LOG_FILE" 2>/dev/null || true
        rm -f "$PID_FILE"
        exit 1
    fi
}

cmd_stop() {
    log_info "Stopping backend server..."

    local pid
    pid=$(get_pid)

    if [ -z "$pid" ]; then
        log_warn "Backend is not running"
        rm -f "$PID_FILE"
        return 0
    fi

    # Graceful shutdown
    kill "$pid" 2>/dev/null || true

    # Wait for process to exit
    local timeout=10
    while [ $timeout -gt 0 ] && ps -p "$pid" > /dev/null 2>&1; do
        sleep 1
        timeout=$((timeout - 1))
    done

    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        log_warn "Process did not stop gracefully, force killing..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    # Clean up any remaining uvicorn processes
    pkill -f "uvicorn ${APP_MODULE}" 2>/dev/null || true

    rm -f "$PID_FILE"
    log_info "Backend stopped"
}

cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

cmd_status() {
    local pid
    pid=$(get_pid)

    if [ -z "$pid" ]; then
        log_error "Backend is not running"
        return 1
    fi

    log_info "Backend is running (PID: $pid)"

    # Health check
    if curl -sf "http://localhost:${PORT}/api/v1/health" > /dev/null 2>&1; then
        local health
        health=$(curl -sf "http://localhost:${PORT}/api/v1/health")
        log_info "Health: $health"
    else
        log_warn "Health check failed - service may be starting up"
    fi

    # Show resource usage
    if check_command ps; then
        echo ""
        log_info "Resource usage:"
        ps -p "$pid" -o pid,ppid,%cpu,%mem,etime,cmd --no-headers 2>/dev/null || true
    fi
}

cmd_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        log_error "Log file not found: $LOG_FILE"
        exit 1
    fi

    log_info "Tailing log file (Ctrl+C to exit)..."
    tail -f "$LOG_FILE"
}

cmd_help() {
    echo "Squant Backend Service Management"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start    Start the backend server in background"
    echo "  stop     Stop the backend server"
    echo "  restart  Restart the backend server"
    echo "  status   Check if backend is running"
    echo "  logs     Tail the log file"
    echo "  help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start     # Start server"
    echo "  $0 restart   # Restart server"
    echo "  $0 logs      # Watch logs"
}

# =============================================================================
# Main
# =============================================================================

case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    help|-h|--help) cmd_help ;;
    *)
        log_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
