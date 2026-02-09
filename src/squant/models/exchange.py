"""Exchange account model."""

from sqlalchemy import Boolean, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class ExchangeAccount(Base, UUIDMixin, TimestampMixin):
    """Exchange account with encrypted API credentials."""

    __tablename__ = "exchange_accounts"

    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    api_secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    passphrase_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    testnet: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    strategy_runs: Mapped[list["StrategyRun"]] = relationship(  # noqa: F821
        back_populates="account", lazy="selectin"
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        back_populates="account", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("exchange", "name", name="uq_exchange_account_name"),
        Index("idx_exchange_accounts_exchange", "exchange"),
    )

    def __repr__(self) -> str:
        return f"<ExchangeAccount(id={self.id}, exchange={self.exchange}, name={self.name})>"
