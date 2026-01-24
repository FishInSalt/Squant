"""Metrics and snapshot models - TimescaleDB hypertables."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EquityCurve(Base):
    """Equity curve snapshot - TimescaleDB hypertable."""

    __tablename__ = "equity_curves"

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    position_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), default=Decimal("0"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EquityCurve(run_id={self.run_id}, time={self.time}, equity={self.equity})>"


class BalanceSnapshot(Base):
    """Account balance snapshot - TimescaleDB hypertable."""

    __tablename__ = "balance_snapshots"

    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("exchange_accounts.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(16), primary_key=True, nullable=False)

    free: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    locked: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    usd_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    def __repr__(self) -> str:
        return f"<BalanceSnapshot(account_id={self.account_id}, currency={self.currency}, time={self.time})>"
