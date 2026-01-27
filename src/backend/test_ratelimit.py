"""
测试速率限制功能

测试各个端点的速率限制是否正常工作。
"""

import asyncio
import httpx
import time
from typing import List


BASE_URL = "http://localhost:8000"


async def test_rate_limit_health_check():
    """测试健康检查端点的速率限制"""
    print("\n=== 测试健康检查端点速率限制 ===")
    print("限制：60 请求/分钟")

    async with httpx.AsyncClient() as client:
        success_count = 0
        fail_count = 0

        # 发送100个请求（超过限制）
        for i in range(100):
            try:
                response = await client.get(f"{BASE_URL}/health")
                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:
                    fail_count += 1
                    print(f"✓ 第 {i + 1} 个请求被限速 (429)")
            except Exception as e:
                print(f"✗ 第 {i + 1} 个请求失败: {e}")

        print(f"\n结果：成功 {success_count} 个，失败 {fail_count} 个")
        print(f"预期：前60个成功，后40个被限速")


async def test_rate_limit_market_read():
    """测试市场数据读取端点的速率限制"""
    print("\n=== 测试市场数据端点速率限制 ===")
    print("限制：100 请求/分钟")

    async with httpx.AsyncClient() as client:
        success_count = 0
        fail_count = 0

        # 发送150个请求（超过限制）
        for i in range(150):
            try:
                response = await client.get(f"{BASE_URL}/api/v1/market/tickers")
                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:
                    fail_count += 1
                    if fail_count == 1:
                        print(f"✓ 第 {i + 1} 个请求开始被限速 (429)")
            except Exception as e:
                print(f"✗ 第 {i + 1} 个请求失败: {e}")

        print(f"\n结果：成功 {success_count} 个，失败 {fail_count} 个")
        print(f"预期：前100个成功，后50个被限速")


async def test_rate_limit_write():
    """测试写操作端点的速率限制"""
    print("\n=== 测试写操作端点速率限制 ===")
    print("限制：20 请求/分钟")

    async with httpx.AsyncClient() as client:
        success_count = 0
        fail_count = 0

        # 发送30个请求（超过限制）
        for i in range(30):
            try:
                response = await client.get(f"{BASE_URL}/api/v1/accounts")
                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:
                    fail_count += 1
                    if fail_count == 1:
                        print(f"✓ 第 {i + 1} 个请求开始被限速 (429)")
            except Exception as e:
                print(f"✗ 第 {i + 1} 个请求失败: {e}")

        print(f"\n结果：成功 {success_count} 个，失败 {fail_count} 个")
        print(f"预期：前20个成功，后10个被限速")


async def test_rate_limit_account_validate():
    """测试账户验证端点的速率限制"""
    print("\n=== 测试账户验证端点速率限制 ===")
    print("限制：10 请求/分钟")

    async with httpx.AsyncClient() as client:
        success_count = 0
        fail_count = 0

        # 发送20个请求（超过限制）
        for i in range(20):
            try:
                payload = {
                    "exchange": "okx",
                    "api_key": "test_key",
                    "api_secret": "test_secret",
                }
                response = await client.post(
                    f"{BASE_URL}/api/v1/accounts/validate", json=payload
                )
                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:
                    fail_count += 1
                    if fail_count == 1:
                        print(f"✓ 第 {i + 1} 个请求开始被限速 (429)")
            except Exception as e:
                print(f"✗ 第 {i + 1} 个请求失败: {e}")

        print(f"\n结果：成功 {success_count} 个，失败 {fail_count} 个")
        print(f"预期：前10个成功，后10个被限速")


async def test_rate_limit_headers():
    """测试速率限制响应头"""
    print("\n=== 测试速率限制响应头 ===")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")

        print("\n响应头:")
        print(f"X-RateLimit-Limit: {response.headers.get('X-RateLimit-Limit')}")
        print(f"X-RateLimit-Remaining: {response.headers.get('X-RateLimit-Remaining')}")
        print(f"X-RateLimit-Reset: {response.headers.get('X-RateLimit-Reset')}")
        print(f"Retry-After: {response.headers.get('Retry-After')}")


async def test_concurrent_requests():
    """测试并发请求"""
    print("\n=== 测试并发请求 ===")
    print("限制：100 请求/分钟")

    async with httpx.AsyncClient() as client:
        # 同时发送100个请求
        tasks = []
        for i in range(100):
            task = client.get(f"{BASE_URL}/api/v1/market/tickers")
            tasks.append(task)

        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time

        success_count = sum(
            1
            for r in responses
            if not isinstance(r, Exception) and r.status_code == 200
        )
        rate_limited_count = sum(
            1
            for r in responses
            if not isinstance(r, Exception) and r.status_code == 429
        )

        print(f"\n并发100个请求，耗时：{duration:.2f}秒")
        print(f"成功：{success_count} 个")
        print(f"被限速：{rate_limited_count} 个")
        print(f"预期：前100个成功（因为是并发），后续请求会被限速")


async def main():
    """主测试函数"""
    print("=" * 60)
    print("Squant API 速率限制测试")
    print("=" * 60)

    # 测试健康检查
    await test_rate_limit_health_check()

    # 测试市场数据读取
    await test_rate_limit_market_read()

    # 测试写操作
    await test_rate_limit_write()

    # 测试账户验证
    await test_rate_limit_account_validate()

    # 测试响应头
    await test_rate_limit_headers()

    # 测试并发请求
    await test_concurrent_requests()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
