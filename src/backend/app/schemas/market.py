"""
行情相关的 Pydantic schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ==================== Ticker (实时价格）====================

class TickerResponse(BaseModel):
    """实时价格响应"""
    exchange: str
    symbol: str
    price: str
    price_change: str
    price_change_percent: str
    high_price: str
    low_price: str
    volume: str
    quote_volume: str
    timestamp: datetime


# ==================== K线数据 ====================

class CandleResponse(BaseModel):
    """K线数据响应"""
    exchange: str
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: Optional[datetime]
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    quote_volume: Optional[str]
    trades_count: Optional[int]


# ==================== 自选币种 ====================

class WatchlistCreate(BaseModel):
    """添加自选币种的请求"""
    exchange: str = Field(..., description="交易所")
    symbol: str = Field(..., description="交易对，如 BTCUSDT")
    label: Optional[str] = Field(None, max_length=100, description="自定义标签")
    sort_order: int = Field(0, description="排序")


class WatchlistUpdate(BaseModel):
    """更新自选币种的请求"""
    label: Optional[str] = Field(None, max_length=100)
    sort_order: Optional[int] = None


class WatchlistResponse(BaseModel):
    """自选币种响应"""
    id: int
    user_id: int
    exchange: str
    symbol: str
    label: Optional[str]
    sort_order: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==================== 市场概览 ====================

class MarketOverviewResponse(BaseModel):
    """市场概览响应"""
    tickers: list[TickerResponse]
    watchlist: list[WatchlistResponse]
