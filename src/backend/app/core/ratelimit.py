"""
速率限制配置

基于 slowapi 实现的 API 速率限制功能。

使用 Redis 作为存储后端，支持分布式部署。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Callable
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


# ========== 速率限制常量 ==========

"""
速率限制策略说明：

1. 全局限制（所有端点）：
   - 1000 请求/分钟 - 防止DDoS攻击

2. 市场数据端点（读操作）：
   - 100 请求/分钟/IP - 允许合理的查询频率
   - 适用于：GET /market/tickers, /market/ticker/{symbol}, /market/candles/{symbol}

3. 账户验证端点（高风险）：
   - 10 请求/分钟/IP - 防止暴力测试和滥用
   - 适用于：POST /accounts/validate, POST /accounts/{id}/validate

4. 写操作（POST/PUT/DELETE）：
   - 20 请求/分钟/IP - 防止数据破坏
   - 适用于：所有写操作端点

5. 读操作（GET）：
   - 100 请求/分钟/IP - 允许合理的查询
"""

RATE_LIMITS = {
    # 全局限制
    "global": "1000/minute",  # 1000 req/min
    # 市场数据端点（公共数据，可以适当放宽）
    "market_read": "100/minute",  # 100 req/min/IP
    # 账户验证端点（调用外部API，需要严格限制）
    "account_validate": "10/minute",  # 10 req/min/IP
    # 写操作（创建、更新、删除）
    "write": "20/minute",  # 20 req/min/IP
    # 读操作（查询）
    "read": "100/minute",  # 100 req/min/IP
}


# ========== 自定义速率限制处理器 ==========


def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """
    自定义速率限制超出处理器

    返回友好的错误提示和重试时间。
    """
    logger.warning(
        f"Rate limit exceeded for {request.client.host} "
        f"on {request.url.path}: {exc.detail}"
    )

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "请求过于频繁，请稍后再试",
            "message": "Rate limit exceeded",
            "retry_after": str(exc.retry_after) if exc.retry_after else "60",
            "limit": exc.detail,
            "error_code": "RATE_LIMIT_EXCEEDED",
        },
    )


# ========== 创建 Limiter 实例 ==========


def get_redis_key_func(key_func: Callable[[Request], str]) -> Callable[[Request], str]:
    """
    包装 key 函数，添加项目前缀

    Args:
        key_func: 原始的 key 函数

    Returns:
        包装后的 key 函数
    """

    def wrapped(request: Request) -> str:
        key = key_func(request)
        return f"squant:{settings.api_v1_prefix}:{key}"

    return wrapped


# 创建 Limiter 实例
limiter = Limiter(
    key_func=get_redis_key_func(get_remote_address),
    default_limits=[RATE_LIMITS["global"]],  # 全局限制
    storage_uri=settings.redis_url,  # Redis 连接字符串
    headers_enabled=True,  # 在响应头中包含限速信息
    strategy="fixed-window",  # 使用固定窗口策略
    # 可选：sliding-window（滑动窗口，更精确但开销更大）
)

# 覆盖默认的处理器
limiter.limiter._rate_limit_exceeded_handler = rate_limit_exceeded_handler


# ========== 速率限制装饰器 ==========
"""
使用示例：

from app.core.ratelimit import limiter, RATE_LIMITS

@router.get("/tickers")
@limiter.limit(RATE_LIMITS["market_read"])
async def get_tickers(request: Request):
    # ...

@router.post("/accounts/validate")
@limiter.limit(RATE_LIMITS["account_validate"])
async def validate_account(request: Request, data: ValidateRequest):
    # ...
"""


# ========== 辅助函数 ==========


def get_rate_limit_for_endpoint(method: str, path: str) -> str:
    """
    根据端点的 HTTP 方法和路径返回合适的速率限制

    Args:
        method: HTTP 方法（GET, POST, PUT, DELETE）
        path: 端点路径

    Returns:
        速率限制字符串
    """
    # 账户验证端点
    if "/accounts/validate" in path or "/validate" in path:
        return RATE_LIMITS["account_validate"]

    # 写操作
    if method in ["POST", "PUT", "DELETE", "PATCH"]:
        return RATE_LIMITS["write"]

    # 读操作
    if method == "GET":
        # 市场数据端点
        if "/market/" in path:
            return RATE_LIMITS["market_read"]

        return RATE_LIMITS["read"]

    # 默认使用全局限制
    return RATE_LIMITS["global"]


def get_client_ip(request: Request) -> str:
    """
    获取客户端真实IP地址

    考虑代理服务器（如 Nginx）的情况。

    Args:
        request: FastAPI 请求对象

    Returns:
        客户端IP地址
    """
    # 尝试从代理头获取
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For 可能包含多个IP，取第一个
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # 默认使用直接连接的IP
    if request.client:
        return request.client.host

    return "unknown"


# ========== 测试工具 ==========


async def test_redis_connection() -> bool:
    """
    测试 Redis 连接是否正常

    Returns:
        True 如果连接正常，否则 False
    """
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.close()
        logger.info("Redis connection successful for rate limiting")
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        logger.warning("Rate limiting will not work without Redis")
        return False


# ========== 速率限制状态 ==========


class RateLimitStatus:
    """速率限制状态信息"""

    def __init__(self, limit: str, remaining: int, reset: int, retry_after: int = 0):
        self.limit = limit
        self.remaining = remaining
        self.reset = reset
        self.retry_after = retry_after

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "reset": self.reset,
            "retry_after": self.retry_after,
        }


def get_rate_limit_info(request: Request) -> RateLimitStatus:
    """
    从请求响应头中获取速率限制信息

    Args:
        request: FastAPI 请求对象

    Returns:
        RateLimitStatus 对象
    """
    # 这些头由 slowapi 自动添加
    limit = request.headers.get("X-RateLimit-Limit", "unknown")
    remaining = request.headers.get("X-RateLimit-Remaining", "0")
    reset = request.headers.get("X-RateLimit-Reset", "0")
    retry_after = request.headers.get("Retry-After", "0")

    return RateLimitStatus(
        limit=limit,
        remaining=int(remaining),
        reset=int(reset),
        retry_after=int(retry_after),
    )


__all__ = [
    "limiter",
    "RATE_LIMITS",
    "rate_limit_exceeded_handler",
    "get_rate_limit_for_endpoint",
    "get_client_ip",
    "test_redis_connection",
    "get_rate_limit_info",
    "RateLimitStatus",
]
