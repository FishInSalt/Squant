"""Notification schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Notification record response."""

    id: str
    level: str
    event_type: str
    title: str
    message: str
    details: dict[str, Any]
    run_id: str | None
    status: str
    is_read: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    """Unread notification count."""

    count: int


class MarkReadRequest(BaseModel):
    """Mark notifications as read."""

    notification_ids: list[str] | None = Field(
        default=None,
        description="Notification IDs to mark as read. None = mark all as read.",
    )
