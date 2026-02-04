"""
E2E测试数据种子脚本

在E2E测试环境中插入测试用的历史K线数据
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.database import get_session
from squant.models.market import Kline


async def generate_klines(
    exchange: str,
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    base_price: Decimal = Decimal("50000.0"),
) -> list[Kline]:
    """
    生成测试K线数据

    生成简单的随机游走价格数据，用于测试
    """
    klines = []
    current_time = start_date
    current_price = base_price

    # 根据timeframe确定时间间隔
    if timeframe == "1m":
        delta = timedelta(minutes=1)
    elif timeframe == "5m":
        delta = timedelta(minutes=5)
    elif timeframe == "15m":
        delta = timedelta(minutes=15)
    elif timeframe == "1h":
        delta = timedelta(hours=1)
    elif timeframe == "4h":
        delta = timedelta(hours=4)
    elif timeframe == "1d":
        delta = timedelta(days=1)
    else:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    while current_time < end_date:
        # 生成简单的随机游走价格（上下波动 0.5%）
        import random

        change_pct = Decimal(str(random.uniform(-0.005, 0.005)))
        price_change = current_price * change_pct

        # 计算OHLC
        open_price = current_price
        close_price = current_price + price_change
        high_price = max(open_price, close_price) * Decimal("1.002")
        low_price = min(open_price, close_price) * Decimal("0.998")

        # 生成随机成交量
        volume = Decimal(str(random.uniform(100, 1000)))

        kline = Kline(
            time=current_time,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )
        klines.append(kline)

        # 更新当前价格和时间
        current_price = close_price
        current_time += delta

    return klines


async def seed_test_data(session: AsyncSession):
    """插入E2E测试数据"""

    # 生成8天的BTC/USDT 1h K线数据（比测试请求的7天多1天作为缓冲）
    # 添加额外的1天缓冲，避免因 seed_data.py 和 E2E 测试执行时间差异
    # 导致 is_complete 检查失败
    end_date = datetime.now() + timedelta(hours=1)  # 多生成1小时数据
    start_date = end_date - timedelta(days=8)  # 从8天前开始

    print("生成测试K线数据: okx:BTC/USDT:1h")
    print(f"时间范围: {start_date} 到 {end_date}")
    print("(包含1天缓冲以应对时间差异)")

    klines = await generate_klines(
        exchange="okx",
        symbol="BTC/USDT",
        timeframe="1h",
        start_date=start_date,
        end_date=end_date,
        base_price=Decimal("50000.0"),
    )

    print(f"生成了 {len(klines)} 条K线数据")

    # 批量插入
    session.add_all(klines)
    await session.commit()

    print(f"✅ 成功插入 {len(klines)} 条K线数据")


async def clear_test_data(session: AsyncSession):
    """清理测试数据"""

    print("清理现有测试数据...")

    # 删除测试交易所的K线数据
    await session.execute(text("DELETE FROM klines WHERE exchange = 'okx' AND symbol = 'BTC/USDT'"))
    await session.commit()

    print("✅ 测试数据已清理")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="E2E测试数据种子脚本")
    parser.add_argument("--clear", action="store_true", help="清理现有测试数据")
    args = parser.parse_args()

    async for session in get_session():
        try:
            if args.clear:
                await clear_test_data(session)
            else:
                await seed_test_data(session)
        except Exception as e:
            print(f"❌ 错误: {e}")
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
