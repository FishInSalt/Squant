"""Order and Trade models."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin
from .enums import OrderSide, OrderStatus, OrderType

if TYPE_CHECKING:
    from .exchange import ExchangeAccount
    from .strategy import StrategyRun


class Order(Base, UUIDMixin, TimestampMixin):
    """Order record."""

    __tablename__ = "orders"

    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("strategy_runs.id", ondelete="RESTRICT"), nullable=True
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("exchange_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    exchange_oid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[OrderSide] = mapped_column(String(8), nullable=False)
    type: Mapped[OrderType] = mapped_column(String(8), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    filled: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), nullable=False)
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    status: Mapped[OrderStatus] = mapped_column(
        String(16), default=OrderStatus.PENDING, nullable=False
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["StrategyRun | None"] = relationship(back_populates="orders")
    account: Mapped["ExchangeAccount"] = relationship(back_populates="orders")
    trades: Mapped[list["Trade"]] = relationship(back_populates="order", lazy="selectin")

    __table_args__ = (
        Index("idx_orders_run", "run_id"),
        Index("idx_orders_account", "account_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"
        )


class Trade(Base, UUIDMixin):
    """Trade execution record."""

    __tablename__ = "trades"

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    exchange_tid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"), nullable=False)
    fee_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="trades")

    __table_args__ = (
        Index("idx_trades_order", "order_id"),
        Index("idx_trades_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Trade(id={self.id}, price={self.price}, amount={self.amount})>"
