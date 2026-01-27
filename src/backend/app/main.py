from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1 import accounts, market
from app.core.ratelimit import limiter, test_redis_connection, RATE_LIMITS
from app.core.http_client import init_http_client, shutdown_http_client
import logging

logger = logging.getLogger(__name__)


# ========== 应用生命周期 ==========


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时
    logger.info(f"Starting {settings.app_name} v0.1.0")

    # 初始化 HTTP 客户端（带连接池）
    _ = init_http_client()  # type: ignore
    logger.info("HTTP client initialized with connection pool")

    # 测试 Redis 连接（用于速率限制）
    redis_available = await test_redis_connection()
    if redis_available:
        logger.info("Rate limiting enabled with Redis backend")
    else:
        logger.warning("Rate limiting disabled (Redis not available)")

    yield

    # 关闭时
    logger.info(f"Shutting down {settings.app_name}")

    # 关闭 HTTP 客户端
    await shutdown_http_client()
    logger.info("HTTP client shutdown completed")


# ========== 创建应用 ==========

app = FastAPI(
    title=settings.app_name,
    description="Quantitative Trading System API",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# 添加速率限制到应用状态
app.state.limiter = limiter


# ========== 中间件 ==========

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 速率限制中间件（由 slowapi 自动处理）
# 不需要手动添加，limiter 会自动处理所有端点


# ========== 根路径 ==========


@app.get("/")
@limiter.limit(RATE_LIMITS["read"])
async def root(request: Request):
    """根路径，返回API信息"""
    return {"message": "Squant API", "version": "0.1.0", "status": "running"}


# ========== 健康检查 ==========


@app.get("/health")
@limiter.limit("60/minute")  # 健康检查允许每分钟60次
async def health_check(request: Request):
    """健康检查端点"""
    return {
        "status": "healthy",
        "rate_limiting": "enabled" if settings.redis_url else "disabled",
    }


# ========== 注册路由 ==========

# 注意：路由中的端点需要手动添加 @limiter.limit() 装饰器
# 速率限制在各个路由文件中单独配置

app.include_router(
    accounts.router, prefix=f"{settings.api_v1_prefix}/accounts", tags=["accounts"]
)
app.include_router(
    market.router, prefix=f"{settings.api_v1_prefix}/market", tags=["market"]
)
