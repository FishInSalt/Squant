"""Market data models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDMixin


class Watchlist(Base, UUIDMixin):
    """User watchlist item."""

    __tablename__ = "watchlist"

    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_watchlist_exchange_symbol"),)

    def __repr__(self) -> str:
        return f"<Watchlist(exchange={self.exchange}, symbol={self.symbol})>"


class Kline(Base):
    """K-line (OHLCV) data - TimescaleDB hypertable."""

    __tablename__ = "klines"

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    exchange: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True, nullable=False)

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)

    __table_args__ = (Index("idx_klines_symbol_time", "exchange", "symbol", "timeframe", "time"),)

    def __repr__(self) -> str:
        return f"<Kline({self.exchange}:{self.symbol}:{self.timeframe} @ {self.time})>"
