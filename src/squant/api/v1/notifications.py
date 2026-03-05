"""Notification API endpoints (LIVE-011)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from squant.api.utils import ApiResponse, PaginatedData, paginate_params
from squant.infra.database import get_session
from squant.schemas.notification import (
    MarkReadRequest,
    NotificationResponse,
    UnreadCountResponse,
)
from squant.services.notification import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ApiResponse[PaginatedData[NotificationResponse]])
async def list_notifications(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    level: str | None = Query(None, description="Filter by level: critical/warning/info"),
    is_read: bool | None = Query(None, description="Filter by read status"),
    event_type: str | None = Query(None, description="Filter by event type"),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[PaginatedData[NotificationResponse]]:
    """List notifications with pagination and filters."""
    service = NotificationService(session)
    offset, limit = paginate_params(page, page_size)

    items, total = await service.list_notifications(
        offset=offset,
        limit=limit,
        level=level,
        is_read=is_read,
        event_type=event_type,
    )

    return ApiResponse(
        data=PaginatedData(
            items=[NotificationResponse.model_validate(n) for n in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/unread-count", response_model=ApiResponse[UnreadCountResponse])
async def get_unread_count(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UnreadCountResponse]:
    """Get count of unread notifications."""
    service = NotificationService(session)
    count = await service.get_unread_count()
    return ApiResponse(data=UnreadCountResponse(count=count))


@router.post("/mark-read", response_model=ApiResponse[dict])
async def mark_read(
    request: MarkReadRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """Mark notifications as read."""
    service = NotificationService(session)
    updated = await service.mark_read(request.notification_ids)
    return ApiResponse(data={"updated": updated})


@router.delete("/{notification_id}", response_model=ApiResponse[dict])
async def delete_notification(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[dict]:
    """Delete a notification."""
    service = NotificationService(session)
    deleted = await service.delete_notification(notification_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
    return ApiResponse(data={"deleted": True})
