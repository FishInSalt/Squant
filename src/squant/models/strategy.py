"""Strategy and StrategyRun models."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin
from .enums import RunMode, RunStatus, StrategyStatus

if TYPE_CHECKING:
    from .exchange import ExchangeAccount
    from .order import Order


class Strategy(Base, UUIDMixin, TimestampMixin):
    """Strategy definition with code and parameters."""

    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    params_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    default_params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[StrategyStatus] = mapped_column(
        String(16), default=StrategyStatus.ACTIVE, nullable=False
    )

    # Relationships
    runs: Mapped[list["StrategyRun"]] = relationship(
        back_populates="strategy", lazy="selectin"
    )

    __table_args__ = (Index("idx_strategies_status", "status"),)

    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name={self.name}, version={self.version})>"


class StrategyRun(Base, UUIDMixin):
    """Strategy run instance (backtest, paper, or live)."""

    __tablename__ = "strategy_runs"

    strategy_id: Mapped[str] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("exchange_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    mode: Mapped[RunMode] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Backtest specific
    backtest_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backtest_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    initial_capital: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 8), default=Decimal("0.001"), nullable=False
    )
    slippage: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 8), nullable=True
    )

    # Run state
    status: Mapped[RunStatus] = mapped_column(
        String(16), default=RunStatus.PENDING, nullable=False
    )
    process_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Backtest result
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="runs")
    account: Mapped["ExchangeAccount | None"] = relationship(
        back_populates="strategy_runs"
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="run", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_strategy_runs_strategy", "strategy_id"),
        Index("idx_strategy_runs_status", "status"),
        Index("idx_strategy_runs_mode", "mode"),
    )

    def __repr__(self) -> str:
        return f"<StrategyRun(id={self.id}, mode={self.mode}, status={self.status})>"
