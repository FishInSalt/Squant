"""
行情数据获取模块

支持从 OKX 获取实时价格和 K 线数据。
使用 Redis 缓存减少 API 调用次数。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.core.http_client import get_with_retry
from app.models.okx_api import (
    OKXTickersResponse,
    validate_okx_response,
    validate_okx_ticker_data,
    validate_okx_kline_data,
)
from app.core.cache_manager import cache_manager, CacheKeys, CacheTTL

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """行情数据获取器"""

    # OKX API 基础 URL
    BASE_URL = "https://www.okx.com/api/v5"

    # 热门币种列表（按 24 小时成交量排序）
    TOP_SYMBOLS = [
        "BTC-USDT",
        "ETH-USDT",
        "BNB-USDT",
        "SOL-USDT",
        "XRP-USDT",
        "ADA-USDT",
        "DOGE-USDT",
        "DOT-USDT",
        "MATIC-USDT",
        "LINK-USDT",
        "AVAX-USDT",
        "UNI-USDT",
        "ATOM-USDT",
        "LTC-USDT",
        "TRX-USDT",
    ]

    # 支持的时间周期（与 OKX API 保持一致）
    # 分钟周期：小写 m (如 1m, 5m)
    # 其他周期：小写单位 (如 1h, 1d, 1w, 1M)
    TIMEFRAMES = [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    ]

    @staticmethod
    def _transform_okx_ticker(okx_ticker: Any) -> Optional[Dict[str, Any]]:
        """
        转换 OKX ticker 数据为我们需要的格式

        Args:
            okx_ticker: OKX Ticker 数据（已验证）

        Returns:
            Dict: 转换后的 ticker 数据
        """
        try:
            # okx_ticker 现在可能是 OKXTicker 对象或字典
            if hasattr(okx_ticker, "model_fields"):
                # Pydantic 模型
                inst_id = okx_ticker.instId
                last_price = float(okx_ticker.last)
                open24h = float(okx_ticker.open24h)
                high24h = float(okx_ticker.high24h)
                low24h = float(okx_ticker.low24h)
                volume24h = okx_ticker.volCcy24h
            else:
                # 字典（兼容性）
                inst_id = okx_ticker.get("instId", "")
                last_price = float(okx_ticker.get("last", 0))
                open24h = float(okx_ticker.get("open24h", 0))
                high24h = float(okx_ticker.get("high24h", 0))
                low24h = float(okx_ticker.get("low24h", 0))
                volume24h = okx_ticker.get("volCcy24h", "0")

            # 计算 24 小时涨跌
            price_change = last_price - open24h
            price_change_percent = (price_change / open24h * 100) if open24h != 0 else 0

            return {
                "exchange": "okx",
                "symbol": inst_id,
                "price": str(last_price),
                "open_price": str(open24h),
                "price_change": str(price_change),
                "price_change_percent": str(round(price_change_percent, 2)),
                "high_price": str(high24h),
                "low_price": str(low24h),
                "volume": volume24h,
                "quote_volume": okx_ticker.get("vol24h", "0")
                if not hasattr(okx_ticker, "model_fields")
                else "0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"转换 OKX ticker 数据失败: {str(e)}", exc_info=True)
            return None

    @staticmethod
    async def get_okx_ticker(symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 OKX 实时价格。

        使用全局 HTTP 客户端（带连接池和重试机制）。
        使用 Pydantic 模型验证 API 响应。

        Args:
            symbol: 交易对，如 BTC-USDT，如果为 None 则返回所有

        Returns:
            Dict: 价格数据
        """
        try:
            if symbol:
                url = f"{MarketDataFetcher.BASE_URL}/market/ticker?instId={symbol}"
            else:
                url = f"{MarketDataFetcher.BASE_URL}/market/tickers?instType=SPOT"

            logger.info(f"Fetching OKX ticker: {symbol or 'all'}")

            # 使用全局客户端（带自动重试）
            response = await get_with_retry(url)

            if response.status_code != 200:
                logger.error(f"OKX API HTTP 错误: {response.status_code}")
                return {
                    "success": False,
                    "message": f"OKX API HTTP 错误: {response.status_code}",
                }

            # 验证JSON格式
            try:
                response_data = response.json()
            except Exception as e:
                logger.error(f"OKX API JSON 解析失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API JSON 解析失败: {str(e)}",
                }

            # 验证OKX API响应结构
            try:
                validated_response = validate_okx_response(
                    response_data, expected_fields=["code", "msg", "data"]
                )
            except ValueError as e:
                logger.error(f"OKX API 响应验证失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API 响应格式无效: {str(e)}",
                }

            # 检查响应码
            if not validated_response.is_success():
                msg = validated_response.get_error_message()
                logger.error(f"OKX API 错误: {msg}")
                return {"success": False, "message": msg}

            # 验证并获取数据
            try:
                if isinstance(validated_response.data, list):
                    # Tickers响应
                    validated_tickers_response = OKXTickersResponse(**response_data)
                    return {"success": True, "data": validated_tickers_response.data}
                elif isinstance(validated_response.data, dict):
                    # 单个Ticker响应
                    validated_ticker = validate_okx_ticker_data(validated_response.data)
                    return {"success": True, "data": [validated_ticker]}
                else:
                    logger.error(
                        f"OKX API data type invalid: {type(validated_response.data)}"
                    )
                    return {"success": False, "message": "OKX API data type invalid"}
            except ValueError as e:
                logger.error(f"OKX API ticker 数据验证失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API ticker 数据验证失败: {str(e)}",
                }

        except Exception as e:
            logger.error(f"OKX API 请求异常: {str(e)}", exc_info=True)
            return {"success": False, "message": f"OKX API 请求失败: {str(e)}"}

    @staticmethod
    async def get_okx_klines(
        symbol: str, timeframe: str, limit: int = 100
    ) -> Dict[str, Any]:
        """
        获取 OKX K 线数据。

        使用全局 HTTP 客户端（带连接池和重试机制）。
        使用 Pydantic 模型验证 API 响应。

        Args:
            symbol: 交易对，如 BTC-USDT
            timeframe: 时间周期，如1m, 5m, 1h, 1d
            limit: 返回条数，默认 100，最大 300

        Returns:
            Dict: K线数据
        """
        try:
            # OKX API bar 参数格式要求：
            # - 分钟周期：小写 m (如 1m, 5m)
            # - 其他周期：大写 (如 1H, 4H, 1D, 1W, 1M)
            if timeframe.endswith("m"):
                bar_param = timeframe  # 保持小写
            else:
                # 转换为大写单位
                bar_param = timeframe.upper()

            url = f"{MarketDataFetcher.BASE_URL}/market/candles"
            params = {
                "instId": symbol.upper(),
                "bar": bar_param,
                "limit": str(min(limit, 300)),
            }

            logger.info(f"Fetching OKX klines: {symbol} {timeframe} limit={limit}")

            # 使用全局客户端（带自动重试）
            response = await get_with_retry(url, params=params)

            if response.status_code != 200:
                logger.error(f"OKX API HTTP 错误: {response.status_code}")
                return {
                    "success": False,
                    "message": f"OKX API HTTP 错误: {response.status_code}",
                }

            # 验证JSON格式
            try:
                response_data = response.json()
            except Exception as e:
                logger.error(f"OKX API JSON 解析失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API JSON 解析失败: {str(e)}",
                }

            # 验证OKX API响应结构
            try:
                validated_response = validate_okx_response(
                    response_data, expected_fields=["code", "msg", "data"]
                )
            except ValueError as e:
                logger.error(f"OKX API 响应验证失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API 响应格式无效: {str(e)}",
                }

            # 检查响应码
            if not validated_response.is_success():
                msg = validated_response.get_error_message()
                logger.error(f"OKX API 错误: {msg}")
                return {"success": False, "message": msg}

            # 验证并转换K线数据
            try:
                # OKX返回的data是二维数组列表
                raw_klines = validated_response.data

                if not isinstance(raw_klines, list):
                    logger.error(f"OKX API data type invalid: {type(raw_klines)}")
                    return {
                        "success": False,
                        "message": f"OKX API data type invalid: expected list, got {type(raw_klines).__name__}",
                    }

                # 转换为我们的格式
                formatted_klines = []
                for i, kline_data in enumerate(raw_klines):
                    try:
                        validated_kline = validate_okx_kline_data(kline_data)

                        formatted_klines.append(
                            {
                                "open_time": datetime.fromtimestamp(
                                    int(validated_kline.timestamp) / 1000,
                                    tz=timezone.utc,
                                ),
                                "open_price": float(validated_kline.open_price),
                                "high_price": float(validated_kline.high_price),
                                "low_price": float(validated_kline.low_price),
                                "close_price": float(validated_kline.close_price),
                                "volume": float(validated_kline.volume),
                                "close_time": datetime.fromtimestamp(
                                    int(validated_kline.timestamp) / 1000,
                                    tz=timezone.utc,
                                ),
                                "quote_volume": float(validated_kline.volCcy)
                                if validated_kline.volCcy
                                else 0.0,
                                "trades_count": None,  # OKX 不提供此数据
                            }
                        )
                    except ValueError as e:
                        logger.warning(
                            f"Failed to validate kline at index {i}: {str(e)}"
                        )
                        # 跳过无效的K线数据
                        continue
                    except Exception as e:
                        logger.error(
                            f"Unexpected error processing kline at index {i}: {str(e)}",
                            exc_info=True,
                        )
                        continue

                logger.info(
                    f"Successfully parsed {len(formatted_klines)} klines for {symbol} {timeframe}"
                )

                return {
                    "success": True,
                    "data": formatted_klines,
                    "exchange": "okx",
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                }

            except ValueError as e:
                logger.error(f"OKX API K线数据验证失败: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"OKX API K线数据验证失败: {str(e)}",
                }

        except Exception as e:
            logger.error(f"OKX API 请求异常: {str(e)}", exc_info=True)
            return {"success": False, "message": f"OKX API 请求失败: {str(e)}"}

    @staticmethod
    async def get_top_tickers() -> List[Dict[str, Any]]:
        """
        获取热门币种的实时价格。

        使用 Redis 缓存，缓存时间 60 秒。

        Returns:
            List: 价格数据列表，API失败时返回空列表
        """
        # 尝试从缓存获取
        cache_key = CacheKeys.MARKET_TICKERS
        cached_data = await cache_manager.get(cache_key)

        if cached_data is not None:
            logger.info("从缓存获取热门币种列表")
            return cached_data

        logger.info("Starting get_top_tickers() - Cache MISS")

        result = await MarketDataFetcher.get_okx_ticker()
        logger.info(f"get_okx_ticker result: {result}")
        logger.info(f"get_okx_ticker result type: {type(result)}")
        logger.info(f"get_okx_ticker result.get('success'): {result.get('success')}")

        if not result.get("success"):
            logger.warning(f"获取热门币种失败: {result.get('message')}")
            return []

        # OKX 返回数据格式转换
        okx_data = result.get("data")
        logger.info(f"okx_data type: {type(okx_data)}")

        if not okx_data:
            logger.error("okx_data is None or empty, returning empty list")
            return []

        # OKX 数据类型检查
        transformed = []

        if isinstance(okx_data, list):
            logger.info(f"Processing list with {len(okx_data)} items")
            for ticker in okx_data:
                transformed_item = MarketDataFetcher._transform_okx_ticker(ticker)
                if transformed_item:
                    transformed.append(transformed_item)
            logger.info(f"Transformed {len(transformed)} tickers")
        elif isinstance(okx_data, dict):
            logger.info("Processing single dict item")
            transformed_item = MarketDataFetcher._transform_okx_ticker(okx_data)
            if transformed_item:
                transformed.append(transformed_item)
            logger.info("Returning single transformed ticker")
        else:
            logger.error(
                f"Unsupported okx_data type: {type(okx_data)}, returning empty list"
            )

        # 过滤热门币种
        if len(transformed) > 0:
            # 按 24 小时成交量排序
            filtered_tickers = []
            for ticker in transformed:
                if ticker["symbol"] in MarketDataFetcher.TOP_SYMBOLS:
                    filtered_tickers.append(ticker)

            # 按成交量排序（TOP_SYMBOLS 列表已经是有序的）
            # 重新排序以匹配 TOP_SYMBOLS 的顺序
            sorted_tickers = []
            for symbol in MarketDataFetcher.TOP_SYMBOLS:
                for ticker in filtered_tickers:
                    if ticker["symbol"] == symbol:
                        sorted_tickers.append(ticker)
                        break

            # 缓存结果
            await cache_manager.set(
                cache_key, sorted_tickers, ttl=CacheTTL.TICKERS, tags=["tickers"]
            )

            logger.info(
                f"已缓存 {len(sorted_tickers)} 个热门币种，TTL: {CacheTTL.TICKERS}s"
            )
            return sorted_tickers

        return []

    @staticmethod
    async def get_ticker(symbol: str) -> Dict[str, Any]:
        """
        获取单个币种的实时价格。

        使用 Redis 缓存，缓存时间 30 秒。

        Args:
            symbol: 交易对，如 BTC-USDT

        Returns:
            Dict: 价格数据或错误信息
        """
        # 尝试从缓存获取
        cache_key = CacheKeys.ticker_key(symbol)
        cached_data = await cache_manager.get(cache_key)

        if cached_data is not None:
            logger.info(f"从缓存获取 {symbol} 价格数据")
            return {"success": True, "data": cached_data}

        logger.info(f"从 API 获取 {symbol} 价格数据 - Cache MISS")

        result = await MarketDataFetcher.get_okx_ticker(symbol)

        if not result.get("success"):
            logger.warning(f"获取 {symbol} 价格失败: {result.get('message')}")
            return result

        # OKX 返回单个交易对数据，需要转换格式
        data = result.get("data")

        # OKX 单个交易对返回格式：{"code": "0", "data": [{...}]}
        # 所以 data 是一个包含一个元素的列表（即使是单个交易对）
        if isinstance(data, list) and len(data) > 0:
            transformed = MarketDataFetcher._transform_okx_ticker(data[0])
            if transformed:
                # 缓存结果
                await cache_manager.set(
                    cache_key, transformed, ttl=CacheTTL.TICKER, tags=["ticker"]
                )
                logger.info(f"已缓存 {symbol} 价格数据，TTL: {CacheTTL.TICKER}s")
                return {"success": True, "data": transformed}

        return result

    @staticmethod
    async def get_klines(
        symbol: str, timeframe: str, limit: int = 100
    ) -> Dict[str, Any]:
        """
        获取 K 线数据。

        使用 Redis 缓存，缓存时间根据时间周期动态调整。

        Args:
            symbol: 交易对，如 BTC-USDT
            timeframe: 时间周期，如 1m, 5m, 1h, 1d
            limit: 返回条数，默认 100，最大 300

        Returns:
            Dict: K线数据，API失败时返回错误信息
        """
        # 尝试从缓存获取
        cache_key = CacheKeys.kline_key(symbol, timeframe)
        cached_data = await cache_manager.get(cache_key)

        if cached_data is not None:
            logger.info(f"从缓存获取 {symbol} {timeframe} K线数据")
            return cached_data

        logger.info(f"从 API 获取 {symbol} {timeframe} K线数据 - Cache MISS")

        result = await MarketDataFetcher.get_okx_klines(symbol, timeframe, limit)

        if not result.get("success"):
            logger.warning(f"获取 {symbol} K线数据失败: {result.get('message')}")
            return result

        # 缓存结果
        ttl = CacheTTL.get_kline_ttl(timeframe)
        await cache_manager.set(
            cache_key, result, ttl=ttl, tags=["kline", f"kline:{timeframe}"]
        )
        logger.info(f"已缓存 {symbol} {timeframe} K线数据，TTL: {ttl}s")

        return result
