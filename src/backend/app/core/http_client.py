"""
HTTP 客户端管理模块

提供全局的 HTTP 客户端实例，支持连接池和重试机制。
"""

import httpx
import asyncio
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


# ========== 配置常量 ==========

HTTP_CONFIG = {
    # 连接池配置
    "max_connections": 100,  # 最大连接数
    "max_keepalive_connections": 20,  # 保持活动的最大连接数
    "keepalive_expiry": 30.0,  # 连接保持活跃时间（秒）
    # 超时配置
    "timeout_connect": 10.0,  # 连接超时（秒）
    "timeout_read": 30.0,  # 读取超时（秒）
    "timeout_write": 10.0,  # 写入超时（秒）
    "timeout": 30.0,  # 默认超时（秒）
    # 重试配置
    "max_retries": 3,  # 最大重试次数
    "retry_backoff_factor": 1.0,  # 退避因子（秒）
    "retry_status_codes": [408, 429, 500, 502, 503, 504],  # 需要重试的状态码
    "retry_exceptions": [
        httpx.TimeoutException,
        httpx.ConnectTimeout,
        httpx.ConnectError,
    ],  # 需要重试的异常
    # 其他配置
    "http2": True,  # 启用 HTTP/2
    "verify": True,  # 验证 SSL 证书
    "follow_redirects": True,  # 自动跟随重定向
    "max_redirects": 5,  # 最大重定向次数
}


# ========== 全局 HTTP 客户端 ==========

_global_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """
    获取全局 HTTP 客户端实例

    Returns:
        httpx.AsyncClient: 全局客户端实例
    """
    global _global_client

    if _global_client is None:
        _global_client = create_http_client()
        logger.info("Created global HTTP client with connection pool")

    return _global_client


def create_http_client(
    max_connections: int = HTTP_CONFIG["max_connections"],
    max_keepalive_connections: int = HTTP_CONFIG["max_keepalive_connections"],
    http2: bool = HTTP_CONFIG["http2"],
    verify: bool = HTTP_CONFIG["verify"],
) -> httpx.AsyncClient:
    """
    创建 HTTP 客户端实例（带连接池）

    Args:
        max_connections: 最大连接数
        max_keepalive_connections: 保持活动的最大连接数
        http2: 是否启用 HTTP/2
        verify: 是否验证 SSL 证书

    Returns:
        httpx.AsyncClient: HTTP 客户端实例
    """
    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive_connections,
        keepalive_expiry=HTTP_CONFIG["keepalive_expiry"],
    )

    timeout = httpx.Timeout(
        connect=HTTP_CONFIG["timeout_connect"],
        read=HTTP_CONFIG["timeout_read"],
        write=HTTP_CONFIG["timeout_write"],
        pool=HTTP_CONFIG["timeout"],
    )

    client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        http2=http2,
        verify=verify,
        follow_redirects=HTTP_CONFIG["follow_redirects"],
        max_redirects=HTTP_CONFIG["max_redirects"],
    )

    return client


async def close_http_client():
    """关闭全局 HTTP 客户端"""
    global _global_client

    if _global_client is not None:
        await _global_client.aclose()
        _global_client = None
        logger.info("Closed global HTTP client")


# ========== 重试机制 ==========


async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = HTTP_CONFIG["max_retries"],
    backoff_factor: float = HTTP_CONFIG["retry_backoff_factor"],
    retry_status_codes: list = HTTP_CONFIG["retry_status_codes"],
    retry_exceptions: list = HTTP_CONFIG["retry_exceptions"],
    **kwargs: Any,
) -> httpx.Response:
    """
    带重试机制的 HTTP 请求

    Args:
        method: HTTP 方法（GET, POST, PUT, DELETE等）
        url: 请求 URL
        max_retries: 最大重试次数
        backoff_factor: 退避因子（秒）
        retry_status_codes: 需要重试的HTTP状态码
        retry_exceptions: 需要重试的异常类型
        **kwargs: 其他传递给 client.request 的参数

    Returns:
        httpx.Response: HTTP 响应

    Raises:
        最后一次请求的异常
    """
    client = get_http_client()

    for attempt in range(max_retries + 1):
        try:
            logger.debug(
                f"HTTP {method} {url} (attempt {attempt + 1}/{max_retries + 1})"
            )

            response = await client.request(method, url, **kwargs)

            # 检查是否需要重试
            if response.status_code in retry_status_codes:
                if attempt < max_retries:
                    wait_time = backoff_factor * (2**attempt)
                    logger.warning(
                        f"HTTP {method} {url} returned {response.status_code}, "
                        f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"HTTP {method} {url} returned {response.status_code} after {max_retries} retries"
                    )

            # 成功或不再重试
            logger.debug(
                f"HTTP {method} {url} completed with status {response.status_code} "
                f"(attempt {attempt + 1})"
            )
            return response

        except Exception as e:
            # 检查是否需要重试
            should_retry = any(isinstance(e, exc_type) for exc_type in retry_exceptions)

            if should_retry and attempt < max_retries:
                wait_time = backoff_factor * (2**attempt)
                logger.warning(
                    f"HTTP {method} {url} raised {type(e).__name__}: {e}, "
                    f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(
                    f"HTTP {method} {url} raised {type(e).__name__}: {e} "
                    f"after {attempt + 1} attempts"
                )
                raise


async def get_with_retry(url: str, **kwargs: Any) -> httpx.Response:
    """
    GET 请求（带重试）

    Args:
        url: 请求 URL
        **kwargs: 其他参数

    Returns:
        httpx.Response: HTTP 响应
    """
    return await request_with_retry("GET", url, **kwargs)


async def post_with_retry(url: str, **kwargs: Any) -> httpx.Response:
    """
    POST 请求（带重试）

    Args:
        url: 请求 URL
        **kwargs: 其他参数

    Returns:
        httpx.Response: HTTP 响应
    """
    return await request_with_retry("POST", url, **kwargs)


async def put_with_retry(url: str, **kwargs: Any) -> httpx.Response:
    """
    PUT 请求（带重试）

    Args:
        url: 请求 URL
        **kwargs: 其他参数

    Returns:
        httpx.Response: HTTP 响应
    """
    return await request_with_retry("PUT", url, **kwargs)


async def delete_with_retry(url: str, **kwargs: Any) -> httpx.Response:
    """
    DELETE 请求（带重试）

    Args:
        url: 请求 URL
        **kwargs: 其他参数

    Returns:
        httpx.Response: HTTP 响应
    """
    return await request_with_retry("DELETE", url, **kwargs)


# ========== 上下文管理器 ==========


@asynccontextmanager
async def http_request(
    method: str,
    url: str,
    **kwargs: Any,
):
    """
    HTTP 请求上下文管理器

    使用示例：
        async with http_request("GET", "https://api.example.com/data") as response:
            data = response.json()

    Args:
        method: HTTP 方法
        url: 请求 URL
        **kwargs: 其他参数

    Yields:
        httpx.Response: HTTP 响应
    """
    response = await request_with_retry(method, url, **kwargs)
    try:
        yield response
    finally:
        # 可以在这里添加响应后处理逻辑
        pass


# ========== 生命周期管理 ==========


async def init_http_client():
    """初始化 HTTP 客户端（应用启动时调用）"""
    global _global_client

    if _global_client is None:
        _global_client = create_http_client()
        logger.info("Initialized global HTTP client")

    return _global_client


async def shutdown_http_client():
    """关闭 HTTP 客户端（应用关闭时调用）"""
    await close_http_client()


# ========== 工具函数 ==========


def get_client_stats() -> Dict[str, Any]:
    """
    获取 HTTP 客户端统计信息

    Returns:
        Dict: 客户端统计信息
    """
    global _global_client

    if _global_client is None:
        return {"status": "not_initialized"}

    return {
        "status": "initialized",
        "is_closed": _global_client.is_closed,
        "max_connections": HTTP_CONFIG["max_connections"],
        "max_keepalive_connections": HTTP_CONFIG["max_keepalive_connections"],
    }


def update_http_config(**kwargs: Any):
    """
    更新 HTTP 配置

    Args:
        **kwargs: 要更新的配置项
    """
    for key, value in kwargs.items():
        if key in HTTP_CONFIG:
            HTTP_CONFIG[key] = value
            logger.info(f"Updated HTTP config: {key} = {value}")
        else:
            logger.warning(f"Unknown HTTP config key: {key}")


# ========== 导出 ==========

__all__ = [
    # 配置
    "HTTP_CONFIG",
    # 客户端管理
    "get_http_client",
    "create_http_client",
    "close_http_client",
    # 重试机制
    "request_with_retry",
    "get_with_retry",
    "post_with_retry",
    "put_with_retry",
    "delete_with_retry",
    # 上下文管理器
    "http_request",
    # 生命周期管理
    "init_http_client",
    "shutdown_http_client",
    # 工具函数
    "get_client_stats",
    "update_http_config",
]
