# 备份策略

> **关联文档**: [数据持久化](./03-persistence.md)

## 1. 备份脚本

```bash
#!/bin/bash
# scripts/backup.sh

set -euo pipefail

# 配置
BACKUP_DIR="${BACKUP_DIR:-./data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# 创建备份目录
mkdir -p "${BACKUP_DIR}/db" "${BACKUP_DIR}/strategies"

# ============ 数据库备份 ============
backup_database() {
    log_info "Starting database backup..."

    local backup_file="${BACKUP_DIR}/db/squant_${TIMESTAMP}.sql.gz"

    docker compose exec -T postgres pg_dump \
        -U "${DB_USER:-squant}" \
        -d "${DB_NAME:-squant}" \
        --no-owner \
        --no-acl \
        | gzip > "${backup_file}"

    if [[ -f "${backup_file}" ]]; then
        local size=$(du -h "${backup_file}" | cut -f1)
        log_info "Database backup completed: ${backup_file} (${size})"
    else
        log_error "Database backup failed"
        return 1
    fi
}

# ============ 策略文件备份 ============
backup_strategies() {
    log_info "Starting strategies backup..."

    local backup_file="${BACKUP_DIR}/strategies/strategies_${TIMESTAMP}.tar.gz"

    tar -czf "${backup_file}" -C ./data strategies/

    if [[ -f "${backup_file}" ]]; then
        local size=$(du -h "${backup_file}" | cut -f1)
        log_info "Strategies backup completed: ${backup_file} (${size})"
    else
        log_error "Strategies backup failed"
        return 1
    fi
}

# ============ 清理旧备份 ============
cleanup_old_backups() {
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."

    find "${BACKUP_DIR}" -type f -mtime "+${RETENTION_DAYS}" -delete

    log_info "Cleanup completed"
}

# ============ 主流程 ============
main() {
    log_info "=== Squant Backup Started ==="

    backup_database
    backup_strategies
    cleanup_old_backups

    log_info "=== Squant Backup Completed ==="
}

main "$@"
```

## 2. 恢复脚本

```bash
#!/bin/bash
# scripts/restore.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./data/backups}"

log_info() { echo -e "\033[0;32m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[0;31m[ERROR]\033[0m $1" >&2; }

# 列出可用备份
list_backups() {
    log_info "Available database backups:"
    ls -lh "${BACKUP_DIR}/db/"*.sql.gz 2>/dev/null || echo "  No backups found"

    echo ""
    log_info "Available strategy backups:"
    ls -lh "${BACKUP_DIR}/strategies/"*.tar.gz 2>/dev/null || echo "  No backups found"
}

# 恢复数据库
restore_database() {
    local backup_file="$1"

    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi

    log_info "Restoring database from: ${backup_file}"
    log_info "WARNING: This will overwrite the current database!"
    read -p "Continue? (yes/no): " confirm

    if [[ "${confirm}" != "yes" ]]; then
        log_info "Restore cancelled"
        return 0
    fi

    # 停止后端服务
    docker compose stop backend

    # 恢复数据库
    gunzip -c "${backup_file}" | docker compose exec -T postgres psql \
        -U "${DB_USER:-squant}" \
        -d "${DB_NAME:-squant}"

    # 重启后端服务
    docker compose start backend

    log_info "Database restore completed"
}

# 恢复策略文件
restore_strategies() {
    local backup_file="$1"

    if [[ ! -f "${backup_file}" ]]; then
        log_error "Backup file not found: ${backup_file}"
        return 1
    fi

    log_info "Restoring strategies from: ${backup_file}"

    tar -xzf "${backup_file}" -C ./data/

    log_info "Strategies restore completed"
}

# 使用说明
usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  list                    List available backups"
    echo "  db <backup_file>        Restore database from backup"
    echo "  strategies <backup_file> Restore strategies from backup"
}

# 主流程
case "${1:-}" in
    list)
        list_backups
        ;;
    db)
        restore_database "${2:-}"
        ;;
    strategies)
        restore_strategies "${2:-}"
        ;;
    *)
        usage
        exit 1
        ;;
esac
```

## 3. 定时备份 (Cron)

```bash
# 添加到 crontab: crontab -e

# 每天凌晨 3 点执行完整备份
0 3 * * * cd /path/to/squant && ./scripts/backup.sh >> ./data/logs/backup.log 2>&1

# 每 6 小时执行数据库备份
0 */6 * * * cd /path/to/squant && ./scripts/backup.sh db >> ./data/logs/backup.log 2>&1
```
