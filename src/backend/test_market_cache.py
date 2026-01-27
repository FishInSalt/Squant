"""
市场数据缓存测试脚本

用于验证缓存功能是否正常工作。
"""

import asyncio
import sys
import time

# 添加项目路径
sys.path.insert(0, "/home/li416/Squant_oc/src/backend")

from app.market.data_fetcher import MarketDataFetcher
from app.core.cache_manager import cache_manager, CacheKeys


async def test_cache():
    """测试缓存功能"""

    print("=" * 60)
    print("市场数据缓存测试")
    print("=" * 60)
    print()

    # 测试 1: 获取热门币种列表（第一次 - Cache MISS）
    print("测试 1: 获取热门币种列表（第一次）")
    print("-" * 60)
    start = time.time()
    tickers_1 = await MarketDataFetcher.get_top_tickers()
    end = time.time()
    print(f"✓ 获取了 {len(tickers_1)} 个热门币种")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print("✓ 预期: Cache MISS（第一次调用）")
    print()

    # 测试 2: 获取热门币种列表（第二次 - Cache HIT）
    print("测试 2: 获取热门币种列表（第二次）")
    print("-" * 60)
    start = time.time()
    tickers_2 = await MarketDataFetcher.get_top_tickers()
    end = time.time()
    print(f"✓ 获取了 {len(tickers_2)} 个热门币种")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print("✓ 预期: Cache HIT（缓存未过期）")
    print()

    # 测试 3: 获取单个币种价格
    print("测试 3: 获取 BTC-USDT 价格")
    print("-" * 60)
    start = time.time()
    result_1 = await MarketDataFetcher.get_ticker("BTC-USDT")
    end = time.time()
    print(f"✓ 状态: {result_1['success']}")
    if result_1["success"]:
        print(f"✓ 价格: {result_1['data']['price']}")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print()

    # 测试 4: 再次获取单个币种价格
    print("测试 4: 再次获取 BTC-USDT 价格")
    print("-" * 60)
    start = time.time()
    result_2 = await MarketDataFetcher.get_ticker("BTC-USDT")
    end = time.time()
    print(f"✓ 状态: {result_2['success']}")
    if result_2["success"]:
        print(f"✓ 价格: {result_2['data']['price']}")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print("✓ 预期: Cache HIT（缓存未过期）")
    print()

    # 测试 5: 获取K线数据
    print("测试 5: 获取 BTC-USDT 1h K线数据")
    print("-" * 60)
    start = time.time()
    klines_1 = await MarketDataFetcher.get_klines("BTC-USDT", "1h", 10)
    end = time.time()
    print(f"✓ 状态: {klines_1['success']}")
    if klines_1["success"]:
        print(f"✓ 获取了 {len(klines_1['data'])} 条K线数据")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print()

    # 测试 6: 再次获取K线数据
    print("测试 6: 再次获取 BTC-USDT 1h K线数据")
    print("-" * 60)
    start = time.time()
    klines_2 = await MarketDataFetcher.get_klines("BTC-USDT", "1h", 10)
    end = time.time()
    print(f"✓ 状态: {klines_2['success']}")
    if klines_2["success"]:
        print(f"✓ 获取了 {len(klines_2['data'])} 条K线数据")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print("✓ 预期: Cache HIT（缓存未过期）")
    print()

    # 测试 7: 删除缓存
    print("测试 7: 删除 BTC-USDT ticker 缓存")
    print("-" * 60)
    cache_key = CacheKeys.ticker_key("BTC-USDT")
    deleted = await cache_manager.delete(cache_key)
    print(f"✓ 删除缓存: {deleted}")
    print()

    # 测试 8: 再次获取（应该Cache MISS）
    print("测试 8: 获取 BTC-USDT 价格（删除缓存后）")
    print("-" * 60)
    start = time.time()
    result_3 = await MarketDataFetcher.get_ticker("BTC-USDT")
    end = time.time()
    print(f"✓ 状态: {result_3['success']}")
    if result_3["success"]:
        print(f"✓ 价格: {result_3['data']['price']}")
    print(f"✓ 耗时: {(end - start) * 1000:.2f} ms")
    print("✓ 预期: Cache MISS（缓存已删除）")
    print()

    # 测试 9: 按标签删除所有ticker缓存
    print("测试 9: 按标签删除所有ticker缓存")
    print("-" * 60)
    deleted_count = await cache_manager.delete_by_tag("ticker")
    print(f"✓ 删除了 {deleted_count} 个ticker缓存")
    print()

    # 测试 10: 按模式删除所有市场数据缓存
    print("测试 10: 按模式删除所有市场数据缓存")
    print("-" * 60)
    deleted_count = await cache_manager.delete_pattern("market:*")
    print(f"✓ 删除了 {deleted_count} 个市场数据缓存")
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)

    # 关闭 Redis 连接
    await cache_manager.close()


if __name__ == "__main__":
    asyncio.run(test_cache())
