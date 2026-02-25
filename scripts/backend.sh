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
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="${LOG_DIR}/backend.out"
LOG_FILE_PREV="${LOG_DIR}/backend.out.1"
PID_FILE="/tmp/squant_backend.pid"

# Server settings
HOST="0.0.0.0"
PORT="8000"
APP_MODULE="squant.main:app"

# Timeouts
GRACEFUL_TIMEOUT=5
READY_TIMEOUT=15      # seconds (0.5s per attempt)
READY_INTERVAL=0.5
PORT_RELEASE_TIMEOUT=3

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

# Check if a command exists
check_command() {
    command -v "$1" &> /dev/null
}

# Check if port is in use
is_port_in_use() {
    if check_command ss; then
        ss -tlnp 2>/dev/null | grep -q ":${PORT} " && return 0
    elif check_command lsof; then
        lsof -iTCP:"${PORT}" -sTCP:LISTEN &>/dev/null && return 0
    else
        # Fallback: try to connect
        (echo > /dev/tcp/localhost/"${PORT}") 2>/dev/null && return 0
    fi
    return 1
}

# Wait for port to be released
wait_for_port_release() {
    local timeout=$PORT_RELEASE_TIMEOUT
    while [ $timeout -gt 0 ] && is_port_in_use; do
        sleep 1
        timeout=$((timeout - 1))
    done
    if is_port_in_use; then
        return 1
    fi
    return 0
}

# Get the process group ID (PGID) from PID file
get_pgid() {
    if [ -f "$PID_FILE" ]; then
        local pgid
        pgid=$(cat "$PID_FILE")
        # Verify the process group still exists
        if ps -o pgid= -p "$pgid" &>/dev/null 2>&1 || \
           kill -0 -- -"$pgid" 2>/dev/null; then
            echo "$pgid"
            return 0
        fi
    fi
    return 1
}

# Check if the backend is running (by PID file or port)
is_running() {
    if get_pgid &>/dev/null; then
        return 0
    fi
    # Fallback: check if our port is occupied by uvicorn
    if is_port_in_use; then
        pgrep -f "uvicorn ${APP_MODULE}" &>/dev/null && return 0
    fi
    return 1
}

# Kill an entire process group
kill_process_group() {
    local pgid="$1"
    local signal="${2:-TERM}"
    # kill -- -PGID sends signal to entire process group
    kill -"$signal" -- -"$pgid" 2>/dev/null || true
}

# Wait for service to be ready via health check
wait_for_ready() {
    local max_attempts=$(( READY_TIMEOUT * 2 ))  # 0.5s intervals
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "http://localhost:${PORT}/api/v1/health" > /dev/null 2>&1; then
            return 0
        fi
        sleep "$READY_INTERVAL"
        attempt=$((attempt + 1))
    done
    return 1
}

# Rotate log file (keep one previous version)
rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        local size
        size=$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
        # Only rotate if log file is non-empty
        if [ "$size" -gt 0 ]; then
            mv -f "$LOG_FILE" "$LOG_FILE_PREV"
        fi
    fi
}

# =============================================================================
# Commands
# =============================================================================

cmd_start() {
    cd "$PROJECT_ROOT"

    # Check if already running
    if is_running; then
        log_warn "Backend already running"
        cmd_status
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

    # Check port availability
    if is_port_in_use; then
        log_error "Port ${PORT} is already in use"
        log_error "Run: ss -tlnp | grep :${PORT}  to see what's using it"
        exit 1
    fi

    # Ensure log directory exists
    mkdir -p "$LOG_DIR"

    # Rotate log before starting
    rotate_log

    log_info "Starting backend server..."

    # Start in a new session (setsid) so we get a dedicated process group.
    # This ensures 'kill -- -PGID' cleanly stops the entire process tree:
    #   setsid → uv → uvicorn reloader → uvicorn worker
    setsid uv run uvicorn "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        >> "$LOG_FILE" 2>&1 &

    local new_pid=$!
    # With setsid, the new PID is also the PGID
    echo "$new_pid" > "$PID_FILE"

    # Wait for service to be ready
    log_info "Waiting for service to be ready..."
    if wait_for_ready; then
        log_info "Backend started successfully (PGID: $new_pid)"
        log_info "API docs: http://localhost:${PORT}/api/v1/docs"
        log_info "Log file: $LOG_FILE"
    else
        log_error "Backend failed to start within ${READY_TIMEOUT}s"
        # Clean up the failed process
        kill_process_group "$new_pid"
        sleep 1
        kill_process_group "$new_pid" 9
        rm -f "$PID_FILE"
        log_error "Check logs: tail -50 $LOG_FILE"
        echo ""
        tail -20 "$LOG_FILE" 2>/dev/null || true
        exit 1
    fi
}

cmd_stop() {
    log_info "Stopping backend server..."

    local pgid
    pgid=$(get_pgid) || true

    if [ -z "$pgid" ]; then
        # No PID file or stale PID — try to find by process name
        local orphan_pid
        orphan_pid=$(pgrep -f "uvicorn ${APP_MODULE}" 2>/dev/null | head -1 || true)
        if [ -n "$orphan_pid" ]; then
            log_warn "Found orphan uvicorn process (PID: $orphan_pid), killing..."
            kill "$orphan_pid" 2>/dev/null || true
            sleep 2
            kill -9 "$orphan_pid" 2>/dev/null || true
        else
            log_warn "Backend is not running"
        fi
        rm -f "$PID_FILE"
        return 0
    fi

    # Phase 1: Graceful shutdown — SIGTERM to entire process group
    log_info "Sending SIGTERM to process group $pgid..."
    kill_process_group "$pgid" TERM

    # Wait for graceful shutdown
    local timeout=$GRACEFUL_TIMEOUT
    while [ $timeout -gt 0 ]; do
        if ! kill -0 -- -"$pgid" 2>/dev/null; then
            break
        fi
        sleep 1
        timeout=$((timeout - 1))
    done

    # Phase 2: Force kill if still running
    if kill -0 -- -"$pgid" 2>/dev/null; then
        log_warn "Process group did not stop within ${GRACEFUL_TIMEOUT}s, force killing..."
        kill_process_group "$pgid" 9
        sleep 1
    fi

    rm -f "$PID_FILE"
    log_info "Backend stopped"
}

cmd_restart() {
    cmd_stop

    # Wait for port to be released before starting
    if is_port_in_use; then
        log_info "Waiting for port ${PORT} to be released..."
        if ! wait_for_port_release; then
            log_error "Port ${PORT} still in use after ${PORT_RELEASE_TIMEOUT}s"
            log_error "Run: ss -tlnp | grep :${PORT}  to see what's using it"
            exit 1
        fi
    fi

    cmd_start
}

cmd_status() {
    if ! is_running; then
        log_error "Backend is not running"
        return 1
    fi

    local pgid
    pgid=$(get_pgid) || pgid="unknown"
    log_info "Backend is running (PGID: $pgid)"

    # Health check
    if curl -sf "http://localhost:${PORT}/api/v1/health" > /dev/null 2>&1; then
        local health
        health=$(curl -sf "http://localhost:${PORT}/api/v1/health")
        log_info "Health: $health"
    else
        log_warn "Health check failed - service may be starting up"
    fi

    # Show all processes in the group
    if [ "$pgid" != "unknown" ]; then
        echo ""
        log_info "Process tree:"
        ps -o pid,ppid,%cpu,%mem,etime,args --no-headers -g "$pgid" 2>/dev/null \
            || ps -o pid,ppid,%cpu,%mem,etime,args --no-headers -p "$pgid" 2>/dev/null \
            || true
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
