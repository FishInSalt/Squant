"""
行情数据获取模块

支持从 Binance 获取实时价格和 K 线数据。
"""
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime



class MarketDataFetcher:
    """行情数据获取器"""

    # 热门币种列表（按 24 小时成交量排序）
    TOP_SYMBOLS = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT",
        "AVAXUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "TRXUSDT"
    ]

    # 支持的时间周期
    TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]

    @staticmethod
    async def get_binance_ticker(symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 Binance 实时价格。

        Args:
            symbol: 交易对，如 BTCUSDT，如果为 None 则返回所有

        Returns:
            Dict: 价格数据
        """
        try:
            async with httpx.AsyncClient() as client:
                if symbol:
                    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
                else:
                    url = "https://api.binance.com/api/v3/ticker/24hr"

                response = await client.get(url, timeout=10.0)

                if response.status_code == 200:
                    if symbol:
                        return {
                            'success': True,
                            'data': response.json()
                        }
                    else:
                        return {
                            'success': True,
                            'data': response.json()
                        }
                else:
                    return {
                        'success': False,
                        'message': f'Binance API 错误: {response.status_code}'
                    }

        except httpx.TimeoutException:
            return {
                'success': False,
                'message': 'Binance API 连接超时'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Binance API 请求失败: {str(e)}'
            }

    @staticmethod
    async def get_binance_klines(
        symbol: str,
        timeframe: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        获取 Binance K 线数据。

        Args:
            symbol: 交易对，如 BTCUSDT
            timeframe: 时间周期，如 1m, 5m, 1h, 1d
            limit: 返回条数，默认 100，最大 1000

        Returns:
            Dict: K线数据
        """
        try:
            async with httpx.AsyncClient() as client:
                url = "https://api.binance.com/api/v3/klines"
                params: Dict[str, str | int] = {
                    "symbol": symbol.upper(),
                    "interval": timeframe.lower(),
                    "limit": str(min(limit, 1000))
                }

                response = await client.get(url, params=params, timeout=10.0)

                if response.status_code == 200:
                    klines = response.json()

                    # 格式化 K线数据
                    formatted_klines = []
                    for kline in klines:
                        formatted_klines.append({
                            'open_time': datetime.fromtimestamp(kline[0] / 1000),
                            'open_price': float(kline[1]),
                            'high_price': float(kline[2]),
                            'low_price': float(kline[3]),
                            'close_price': float(kline[4]),
                            'volume': float(kline[5]),
                            'close_time': datetime.fromtimestamp(kline[6] / 1000) if kline[6] else None,
                            'quote_volume': float(kline[7]),
                            'trades_count': int(kline[8]) if kline[8] else None
                        })

                    return {
                        'success': True,
                        'data': formatted_klines,
                        'exchange': 'binance',
                        'symbol': symbol.upper(),
                        'timeframe': timeframe
                    }
                else:
                    return {
                        'success': False,
                        'message': f'Binance API 错误: {response.status_code}'
                    }

        except httpx.TimeoutException:
            return {
                'success': False,
                'message': 'Binance API 连接超时'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Binance API 请求失败: {str(e)}'
            }

    @staticmethod
    async def get_top_tickers() -> List[Dict[str, Any]]:
        """
        获取热门币种的实时价格。

        Returns:
            List: 价格数据列表
        """
        result = await MarketDataFetcher.get_binance_ticker()

        if not result['success']:
            return []

        all_tickers = result['data']
        top_tickers = []

        for symbol in MarketDataFetcher.TOP_SYMBOLS:
            for ticker in all_tickers:
                if ticker['symbol'] == symbol:
                    top_tickers.append(ticker)
                    break

        return top_tickers

    @staticmethod
    async def get_ticker(symbol: str) -> Dict[str, Any]:
        """
        获取单个币种的实时价格。

        Args:
            symbol: 交易对，如 BTCUSDT

        Returns:
            Dict: 价格数据或错误信息
        """
        return await MarketDataFetcher.get_binance_ticker(symbol)
