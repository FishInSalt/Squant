#!/usr/bin/env python3
"""
Mock 数据测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.market.mock_data import MockDataService


async def test_mock_data():
    """测试 Mock 数据服务"""
    print("\n" + "=" * 80)
    print(" Mock 数据测试")
    print("=" * 80)

    # 测试 1: 获取所有 Tickers
    print("\n【测试 1】获取所有 Tickers")
    tickers = MockDataService.get_mock_tickers()
    print(f"✅ 返回数量: {len(tickers)}")
    print(f"第一个币种: {tickers[0]['symbol']} - {tickers[0]['price']}")

    # 测试 2: 获取单个 Ticker
    print("\n【测试 2】获取单个 Ticker")
    ticker = MockDataService.get_mock_ticker("BTCUSDT")
    print(f"✅ 币种: {ticker['symbol']}")
    print(f"✅ 价格: {ticker['price']}")
    print(f"✅ 涨跌幅: {ticker['price_change_percent']}%")

    # 测试 3: 获取 K 线数据
    print("\n【测试 3】获取 K 线数据")
    klines = MockDataService.get_mock_klines("BTCUSDT", "1h", 10)
    print(f"✅ 返回数量: {len(klines)}")
    if klines:
        print(f"✅ 第一个K线时间: {klines[0]['open_time']}")
        print(f"✅ 第一个K线价格: {klines[0]['open_price']}")

    # 测试 4: 获取 Watchlist
    print("\n【测试 4】获取 Watchlist")
    watchlist = MockDataService.get_mock_watchlist()
    print(f"✅ 返回数量: {len(watchlist)}")
    if watchlist:
        print(f"✅ 第一个自选: {watchlist[0]['symbol']} - {watchlist[0]['label']}")

    print("\n" + "=" * 80)
    print(" 所有测试通过！✅")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_mock_data())
