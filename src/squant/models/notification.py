"""Notification models."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDMixin


class Notification(Base, UUIDMixin, TimestampMixin):
    """Alert notification record.

    Tracks notifications sent via webhook and displayed in the frontend.
    """

    __tablename__ = "notifications"

    level: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    webhook_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    webhook_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_level", "level"),
        Index("idx_notifications_event_type", "event_type"),
        Index("idx_notifications_is_read", "is_read"),
        Index("idx_notifications_run_id", "run_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, level={self.level}, "
            f"event_type={self.event_type}, status={self.status})>"
        )
