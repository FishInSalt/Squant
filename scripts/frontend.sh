#!/bin/bash
# Squant Frontend Service Management Script
# Usage: ./frontend.sh {start|stop|restart|status|logs|build}

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

# Auto-detect project root (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Runtime files
LOG_FILE="/tmp/squant_frontend.log"
PID_FILE="/tmp/squant_frontend.pid"

# Server settings
PORT="5175"

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
    # Fallback: find by process name (main vite process)
    pgrep -f "node.*vite" 2>/dev/null | head -1 || true
}

# Wait for service to be ready
wait_for_ready() {
    local max_attempts=20
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "http://localhost:${PORT}/" > /dev/null 2>&1; then
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
    cd "$FRONTEND_DIR"

    # Check if already running
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ]; then
        log_warn "Frontend already running (PID: $pid)"
        return 0
    fi

    # Verify npm is available
    if ! check_command npm; then
        log_error "npm not found. Please install Node.js first."
        exit 1
    fi

    # Check if node_modules exists
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_info "Installing dependencies..."
        npm install
    fi

    log_info "Starting frontend dev server..."

    # Start vite in background with explicit port
    nohup npm run dev -- --port "$PORT" > "$LOG_FILE" 2>&1 &

    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # Wait for service to be ready
    log_info "Waiting for service to be ready..."
    if wait_for_ready; then
        log_info "Frontend started successfully (PID: $new_pid)"
        log_info "URL: http://localhost:${PORT}/"
        log_info "Log file: $LOG_FILE"
    else
        log_error "Frontend failed to start within timeout"
        log_error "Check logs: tail -50 $LOG_FILE"
        # Show last few lines of log
        echo ""
        tail -20 "$LOG_FILE" 2>/dev/null || true
        rm -f "$PID_FILE"
        exit 1
    fi
}

cmd_stop() {
    log_info "Stopping frontend server..."

    local pid
    pid=$(get_pid)

    if [ -z "$pid" ]; then
        log_warn "Frontend is not running"
        rm -f "$PID_FILE"
        # Clean up any orphan vite processes
        pkill -f "node.*vite" 2>/dev/null || true
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

    # Clean up any remaining vite processes
    pkill -f "node.*vite" 2>/dev/null || true

    rm -f "$PID_FILE"
    log_info "Frontend stopped"
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
        log_error "Frontend is not running"
        return 1
    fi

    log_info "Frontend is running (PID: $pid)"

    # Health check
    if curl -sf "http://localhost:${PORT}/" > /dev/null 2>&1; then
        log_info "URL: http://localhost:${PORT}/"
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

cmd_build() {
    cd "$FRONTEND_DIR"

    log_info "Building frontend for production..."

    # Check if node_modules exists
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_info "Installing dependencies..."
        npm install
    fi

    npm run build

    if [ $? -eq 0 ]; then
        log_info "Build completed successfully"
        log_info "Output: $FRONTEND_DIR/dist/"
    else
        log_error "Build failed"
        exit 1
    fi
}

cmd_help() {
    echo "Squant Frontend Service Management"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start    Start the frontend dev server in background"
    echo "  stop     Stop the frontend dev server"
    echo "  restart  Restart the frontend dev server"
    echo "  status   Check if frontend is running"
    echo "  logs     Tail the log file"
    echo "  build    Build frontend for production"
    echo "  help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start     # Start dev server"
    echo "  $0 restart   # Restart dev server"
    echo "  $0 logs      # Watch logs"
    echo "  $0 build     # Build for production"
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
    build)   cmd_build ;;
    help|-h|--help) cmd_help ;;
    *)
        log_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
