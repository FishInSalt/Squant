"""
交易所账户数据模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class ExchangeType(str, enum.Enum):
    """支持的交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    HUOBI = "huobi"


class ExchangeAccount(Base):
    """交易所账户表"""
    __tablename__ = "exchange_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # 用户 ID（预留）
    exchange = Column(Enum(ExchangeType), nullable=False)  # 交易所类型
    label = Column(String(100), nullable=False)  # 账户标签/昵称
    api_key = Column(String(500), nullable=False)  # 加密后的 API Key
    api_secret = Column(String(500), nullable=False)  # 加密后的 API Secret
    passphrase = Column(String(500))  # 加密后的 API Passphrase（某些交易所需要，如 OKX）
    is_active = Column(Boolean, default=True)  # 是否激活
    is_validated = Column(Boolean, default=False)  # 是否已验证
    last_validated_at = Column(DateTime(timezone=True))  # 最后验证时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
