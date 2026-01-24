"""
行情数据模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Numeric
from sqlalchemy.sql import func
from app.db.database import Base


class Candle(Base):
    """K 线数据表"""
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(50), nullable=False, index=True)  # 交易所
    symbol = Column(String(50), nullable=False, index=True)  # 交易对，如 BTCUSDT
    timeframe = Column(String(20), nullable=False, index=True)  # 时间周期，如 1m, 5m, 15m, 1h, 4h, 1d
    open_time = Column(DateTime(timezone=True), nullable=False, index=True)  # 开盘时间
    close_time = Column(DateTime(timezone=True))  # 收盘时间
    open_price = Column(Numeric(20, 8), nullable=False)  # 开盘价
    high_price = Column(Numeric(20, 8), nullable=False)  # 最高价
    low_price = Column(Numeric(20, 8), nullable=False)  # 最低价
    close_price = Column(Numeric(20, 8), nullable=False)  # 收盘价
    volume = Column(Numeric(20, 8), nullable=False)  # 成交量
    quote_volume = Column(Numeric(20, 8))  # 成交额（USDT）
    trades_count = Column(Integer)  # 成交笔数
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 创建复合索引
    __table_args__ = (
        {'comment': 'K线数据表'},
    )


class UserWatchlist(Base):
    """用户自选币种表"""
    __tablename__ = "user_watchlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # 用户 ID
    exchange = Column(String(50), nullable=False)  # 交易所
    symbol = Column(String(50), nullable=False, index=True)  # 交易对
    label = Column(String(100))  # 自定义标签
    sort_order = Column(Integer, default=0)  # 排序
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        {'comment': '用户自选币种表'},
    )
