"""
行情数据 API

提供实时价格、K线数据和自选币种管理的端点。
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timezone
from typing import List

from app.db.database import get_db
from app.models.market_data import UserWatchlist
from app.schemas.market import (
    TickerResponse,
    CandleResponse,
    WatchlistCreate,
    WatchlistUpdate,
    WatchlistResponse,
    MarketOverviewResponse,
)
from app.market.data_fetcher import MarketDataFetcher
from app.core.ratelimit import limiter, RATE_LIMITS


router = APIRouter()


# ==================== 热门币种 ====================


@router.get("/tickers", response_model=List[TickerResponse])
@limiter.limit(RATE_LIMITS["market_read"])
async def get_top_tickers(request: Request):
    """
    获取热门币种的实时价格（24 小时成交量排序）。

    速率限制：100 请求/分钟/IP

    Returns:
        List[TickerResponse]: 热门币种价格列表
    """
    result = await MarketDataFetcher.get_top_tickers()

    if not result:
        return []

    # 转换为响应格式
    tickers = []
    for ticker in result:
        tickers.append(
            TickerResponse(
                exchange="okx",
                symbol=ticker["symbol"],
                price=ticker["price"],
                open_price=ticker["open_price"],
                price_change=ticker["price_change"],
                price_change_percent=ticker["price_change_percent"],
                high_price=ticker["high_price"],
                low_price=ticker["low_price"],
                volume=ticker["volume"],
                quote_volume=ticker["quote_volume"],
                timestamp=datetime.now(timezone.utc),
            )
        )

    return tickers


@router.get("/ticker/{symbol}", response_model=TickerResponse)
@limiter.limit(RATE_LIMITS["market_read"])
async def get_ticker(symbol: str, request: Request):
    """
    获取单个币种的实时价格。

    速率限制：100 请求/分钟/IP

    Args:
        symbol: 交易对，如 BTCUSDT

    Returns:
        TickerResponse: 价格数据
    """
    result = await MarketDataFetcher.get_ticker(symbol.upper())

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"获取价格失败: {result['message']}",
        )

    ticker_data = result["data"]

    return TickerResponse(
        exchange="okx",
        symbol=ticker_data["symbol"],
        price=ticker_data["price"],
        open_price=ticker_data["open_price"],
        price_change=ticker_data["price_change"],
        price_change_percent=ticker_data["price_change_percent"],
        high_price=ticker_data["high_price"],
        low_price=ticker_data["low_price"],
        volume=ticker_data["volume"],
        quote_volume=ticker_data["quote_volume"],
        timestamp=datetime.now(timezone.utc),
    )


# ==================== K线数据 ====================


@router.get("/candles/{symbol}", response_model=List[CandleResponse])
@limiter.limit(RATE_LIMITS["market_read"])
async def get_candles(
    symbol: str,
    request: Request,
    timeframe: str = Query(
        "1h",
        description="时间周期：1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 3d, 1w, 1M",
    ),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
):
    """
    获取 K 线数据。

    速率限制：100 请求/分钟/IP

    Args:
        symbol: 交易对，如 BTCUSDT
        timeframe: 时间周期，默认 1h
        limit: 返回条数，默认 100，最大 1000

    Returns:
        List[CandleResponse]: K线数据列表
    """
    # 验证时间周期
    valid_timeframes = MarketDataFetcher.TIMEFRAMES
    if timeframe not in valid_timeframes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的时间周期: {timeframe}。有效值: {', '.join(valid_timeframes)}",
        )

    result = await MarketDataFetcher.get_klines(symbol.upper(), timeframe, limit)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"获取K线数据失败: {result['message']}",
        )

    # 转换为响应格式
    candles = []
    for kline in result["data"]:
        candles.append(
            CandleResponse(
                exchange=result["exchange"],
                symbol=result["symbol"],
                timeframe=result["timeframe"],
                open_time=kline["open_time"],
                close_time=kline["close_time"],
                open_price=str(kline["open_price"]),
                high_price=str(kline["high_price"]),
                low_price=str(kline["low_price"]),
                close_price=str(kline["close_price"]),
                volume=str(kline["volume"]),
                quote_volume=str(kline["quote_volume"])
                if kline["quote_volume"]
                else None,
                trades_count=kline["trades_count"],
            )
        )

    return candles


# ==================== 自选币种 ====================


@router.get("/watchlist", response_model=List[WatchlistResponse])
@limiter.limit(RATE_LIMITS["read"])
async def get_watchlist(
    request: Request,
    user_id: int = 1,  # TODO: 从认证上下文获取
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的自选币种列表。

    速率限制：100 请求/分钟/IP

    Returns:
        List[WatchlistResponse]: 自选币种列表
    """
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.sort_order),
    )
    watchlist = result.scalars().all()
    return watchlist


@router.post(
    "/watchlist", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(RATE_LIMITS["write"])
async def create_watchlist(
    request: Request,
    watchlist: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    添加自选币种。

    速率限制：20 请求/分钟/IP

    Args:
        watchlist: 自选币种信息

    Returns:
        WatchlistResponse: 创建的自选币种
    """
    # TODO: 获取真实用户 ID
    user_id = 1

    # 检查是否已存在
    result = await db.execute(
        select(UserWatchlist).where(
            (UserWatchlist.user_id == user_id)
            & (UserWatchlist.symbol == watchlist.symbol.upper())
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"自选币种 {watchlist.symbol} 已存在",
        )

    db_watchlist = UserWatchlist(
        user_id=user_id,
        exchange=watchlist.exchange,
        symbol=watchlist.symbol.upper(),
        label=watchlist.label,
        sort_order=watchlist.sort_order,
    )

    db.add(db_watchlist)
    await db.commit()
    await db.refresh(db_watchlist)

    return db_watchlist


@router.put("/watchlist/{watchlist_id}", response_model=WatchlistResponse)
@limiter.limit(RATE_LIMITS["write"])
async def update_watchlist(
    watchlist_id: int,
    request: Request,
    watchlist_update: WatchlistUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    更新自选币种。

    速率限制：20 请求/分钟/IP

    Args:
        watchlist_id: 自选币种 ID
        watchlist_update: 更新数据

    Returns:
        WatchlistResponse: 更新后的自选币种
    """
    result = await db.execute(
        select(UserWatchlist).where(UserWatchlist.id == watchlist_id),
    )
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"自选币种 ID {watchlist_id} 不存在",
        )

    # 更新字段
    if watchlist_update.label is not None:
        watchlist.label = watchlist_update.label  # type: ignore[assignment]
    if watchlist_update.sort_order is not None:
        watchlist.sort_order = watchlist_update.sort_order  # type: ignore[assignment]

    await db.commit()
    await db.refresh(watchlist)

    return watchlist


@router.delete("/watchlist/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(RATE_LIMITS["write"])
async def delete_watchlist(
    watchlist_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    删除自选币种。

    速率限制：20 请求/分钟/IP

    Args:
        watchlist_id: 自选币种 ID
    """
    result = await db.execute(
        delete(UserWatchlist).where(UserWatchlist.id == watchlist_id),
    )

    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"自选币种 ID {watchlist_id} 不存在",
        )

    await db.commit()


# ==================== 市场概览 ====================


@router.get("/overview", response_model=MarketOverviewResponse)
@limiter.limit(RATE_LIMITS["market_read"])
async def get_market_overview(
    request: Request,
    user_id: int = 1,  # TODO: 从认证上下文获取
    db: AsyncSession = Depends(get_db),
):
    """
    获取市场概览（热门币种 + 自选列表）。

    速率限制：100 请求/分钟/IP

    Returns:
        MarketOverviewResponse: 市场概览
    """
    # 获取热门币种
    tickers = await get_top_tickers(request)

    # 获取自选列表
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.sort_order),
    )
    watchlist = result.scalars().all()

    return MarketOverviewResponse(tickers=tickers, watchlist=watchlist)  # type: ignore[arg-type]
