"""
缓存管理模块

使用 Redis 实现数据缓存，减少对外部 API 的调用。

缓存策略：
- Ticker 数据：30秒缓存（频繁更新的价格数据）
- KLine 数据：5-15分钟缓存（根据时间周期）
- Tickers 列表：60秒缓存
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class CacheManager:
    """Redis 缓存管理器"""

    def __init__(self):
        """初始化 Redis 连接"""
        self._redis_client: Optional[redis.Redis] = None

    async def get_client(self) -> redis.Redis:
        """获取 Redis 客户端（单例模式）"""
        if self._redis_client is None:
            try:
                # 解析 Redis URL
                redis_url = settings.redis_url
                password = settings.redis_password

                # 创建 Redis 客户端
                if password:
                    self._redis_client = redis.from_url(
                        redis_url,
                        password=password,
                        encoding="utf-8",
                        decode_responses=True,
                    )
                else:
                    self._redis_client = redis.from_url(
                        redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                    )

                # 测试连接
                await self._redis_client.ping()
                logger.info("Redis 连接成功")

            except Exception as e:
                logger.error(f"Redis 连接失败: {str(e)}", exc_info=True)
                # 返回一个空的客户端（会自动降级为无缓存模式）
                self._redis_client = None

        return self._redis_client

    async def get(self, key: str) -> Optional[Any]:
        """
        从缓存获取数据

        Args:
            key: 缓存键

        Returns:
            缓存的数据，不存在返回 None
        """
        try:
            client = await self.get_client()
            if client is None:
                logger.debug(f"Redis 客户端不可用，跳过缓存读取: {key}")
                return None

            data = await client.get(key)
            if data:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(data)
            else:
                logger.debug(f"Cache MISS: {key}")
                return None
        except Exception as e:
            logger.error(f"从缓存读取失败 {key}: {str(e)}", exc_info=True)
            return None

    async def set(
        self, key: str, value: Any, ttl: int = 60, tags: Optional[list[str]] = None
    ) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值（会被自动序列化为 JSON）
            ttl: 过期时间（秒）
            tags: 标签列表（用于批量删除）

        Returns:
            是否设置成功
        """
        try:
            client = await self.get_client()
            if client is None:
                logger.debug(f"Redis 客户端不可用，跳过缓存写入: {key}")
                return False

            # 序列化数据
            serialized_data = json.dumps(value, ensure_ascii=False)

            # 设置缓存
            success = await client.setex(key, ttl, serialized_data)

            # 如果有标签，添加到标签集合
            if tags:
                for tag in tags:
                    tag_key = f"tag:{tag}"
                    await client.sadd(tag_key, key)
                    # 标签集合也需要过期时间
                    await client.expire(tag_key, ttl + 10)  # 多给10秒缓冲

            if success:
                logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            else:
                logger.warning(f"Cache SET 失败: {key}")

            return success

        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {str(e)}", exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            client = await self.get_client()
            if client is None:
                return False

            result = await client.delete(key)
            if result:
                logger.debug(f"Cache DELETE: {key}")

            return bool(result)

        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {str(e)}", exc_info=True)
            return False

    async def delete_by_tag(self, tag: str) -> int:
        """
        按标签批量删除缓存

        Args:
            tag: 标签名

        Returns:
            删除的缓存数量
        """
        try:
            client = await self.get_client()
            if client is None:
                return 0

            tag_key = f"tag:{tag}"
            keys = await client.smembers(tag_key)

            if not keys:
                return 0

            # 删除所有相关缓存
            deleted_count = 0
            for key in keys:
                if await client.delete(key):
                    deleted_count += 1

            # 删除标签集合
            await client.delete(tag_key)

            logger.info(f"按标签 {tag} 删除了 {deleted_count} 个缓存")
            return deleted_count

        except Exception as e:
            logger.error(f"按标签删除缓存失败 {tag}: {str(e)}", exc_info=True)
            return 0

    async def delete_pattern(self, pattern: str) -> int:
        """
        按模式批量删除缓存

        Args:
            pattern: 匹配模式（如 market:tickers:*）

        Returns:
            删除的缓存数量
        """
        try:
            client = await self.get_client()
            if client is None:
                return 0

            # 查找匹配的键
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if not keys:
                return 0

            # 批量删除
            deleted_count = 0
            if keys:
                deleted_count = await client.delete(*keys)

            logger.info(f"按模式 {pattern} 删除了 {deleted_count} 个缓存")
            return deleted_count

        except Exception as e:
            logger.error(f"按模式删除缓存失败 {pattern}: {str(e)}", exc_info=True)
            return 0

    async def close(self):
        """关闭 Redis 连接"""
        if self._redis_client:
            await self._redis_client.close()
            logger.info("Redis 连接已关闭")


# 全局缓存管理器实例
cache_manager = CacheManager()


class CacheKeys:
    """缓存键命名常量"""

    # 市场数据
    MARKET_TICKER = "market:ticker"
    MARKET_TICKERS = "market:tickers"
    MARKET_KLINE = "market:kline"

    @staticmethod
    def ticker_key(symbol: str) -> str:
        """生成 Ticker 缓存键"""
        return f"{CacheKeys.MARKET_TICKER}:{symbol}"

    @staticmethod
    def kline_key(symbol: str, timeframe: str) -> str:
        """生成 KLine 缓存键"""
        return f"{CacheKeys.MARKET_KLINE}:{symbol}:{timeframe}"


class CacheTTL:
    """缓存过期时间常量（秒）"""

    # 市场数据
    TICKER = 30  # 30秒（价格数据更新频繁）
    TICKERS = 60  # 60秒（热门币种列表）
    KLINE_1M = 60  # 1分钟K线：1分钟
    KLINE_5M = 180  # 5分钟K线：3分钟
    KLINE_15M = 300  # 15分钟K线：5分钟
    KLINE_1H = 600  # 1小时K线：10分钟
    KLINE_4H = 1200  # 4小时K线：20分钟
    KLINE_1D = 1800  # 1天K线：30分钟
    KLINE_DEFAULT = 300  # 默认：5分钟

    @staticmethod
    def get_kline_ttl(timeframe: str) -> int:
        """
        根据时间周期获取K线缓存时间

        Args:
            timeframe: 时间周期（1m, 5m, 1h, 1d等）

        Returns:
            缓存时间（秒）
        """
        ttl_map = {
            "1m": CacheTTL.KLINE_1M,
            "3m": 120,  # 2分钟
            "5m": CacheTTL.KLINE_5M,
            "15m": CacheTTL.KLINE_15M,
            "30m": 420,  # 7分钟
            "1h": CacheTTL.KLINE_1H,
            "2h": 900,  # 15分钟
            "4h": CacheTTL.KLINE_4H,
            "6h": 1500,  # 25分钟
            "12h": 2100,  # 35分钟
            "1d": CacheTTL.KLINE_1D,
            "3d": 3600,  # 1小时
            "1w": 7200,  # 2小时
            "1M": 14400,  # 4小时
        }

        return ttl_map.get(timeframe, CacheTTL.KLINE_DEFAULT)
