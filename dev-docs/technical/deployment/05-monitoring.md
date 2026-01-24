# 监控与日志

> **关联文档**: [Docker 配置](./01-docker.md)

## 1. 日志配置

```python
# squant/core/logging.py
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import structlog

def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """配置结构化日志"""

    # 基础处理器
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # 文件处理器
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    # 配置 structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准库 logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
        format="%(message)s",
    )
```

## 2. 健康检查端点

```python
# squant/api/endpoints/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(tags=["Health"])

class HealthStatus(BaseModel):
    status: str
    timestamp: datetime
    version: str
    components: dict[str, dict]

class ComponentHealth(BaseModel):
    status: str
    latency_ms: float | None = None
    message: str | None = None

@router.get("/health", response_model=HealthStatus)
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> HealthStatus:
    """系统健康检查"""
    components = {}
    overall_status = "healthy"

    # 检查数据库
    try:
        start = datetime.now()
        await db.execute("SELECT 1")
        latency = (datetime.now() - start).total_seconds() * 1000
        components["database"] = {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as e:
        overall_status = "unhealthy"
        components["database"] = {
            "status": "unhealthy",
            "message": str(e),
        }

    # 检查 Redis
    try:
        start = datetime.now()
        await redis.ping()
        latency = (datetime.now() - start).total_seconds() * 1000
        components["redis"] = {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as e:
        overall_status = "unhealthy"
        components["redis"] = {
            "status": "unhealthy",
            "message": str(e),
        }

    return HealthStatus(
        status=overall_status,
        timestamp=datetime.now(),
        version="1.0.0",
        components=components,
    )

@router.get("/health/live")
async def liveness_probe():
    """Kubernetes liveness probe"""
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness_probe(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Kubernetes readiness probe"""
    await db.execute("SELECT 1")
    await redis.ping()
    return {"status": "ready"}
```

## 3. 应用指标

```python
# squant/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from functools import wraps
import time

# HTTP 请求指标
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# 策略指标
active_strategies = Gauge(
    "active_strategies",
    "Number of active strategies",
    ["mode"],  # backtest, paper, live
)

strategy_orders_total = Counter(
    "strategy_orders_total",
    "Total orders placed by strategies",
    ["strategy_id", "side", "status"],
)

# 系统指标
websocket_connections = Gauge(
    "websocket_connections",
    "Number of active WebSocket connections",
)

# 中间件
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        endpoint = request.url.path
        method = request.method
        status = response.status_code

        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status,
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        return response
```

## 4. 日志查看命令

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f backend

# 查看最近 100 行日志
docker compose logs --tail=100 backend

# 使用 jq 解析 JSON 日志
docker compose logs backend | jq -r 'select(.level=="ERROR")'

# 查看策略日志
tail -f ./data/logs/strategy/*.log
```
