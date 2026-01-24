"""System log model."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .enums import LogLevel


class SystemLog(Base):
    """System log entry."""

    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[LogLevel] = mapped_column(String(16), nullable=False)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_system_logs_level", "level"),
        Index("idx_system_logs_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SystemLog(id={self.id}, level={self.level}, module={self.module})>"
