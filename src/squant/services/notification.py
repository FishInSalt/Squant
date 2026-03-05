"""Notification service for alert delivery and management."""

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from squant.config import get_settings
from squant.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Alert notification service.

    Handles notification creation, persistence, webhook delivery,
    and real-time push via Redis pub/sub.
    """

    # In-memory cooldown cache: event_type -> last_send_time (monotonic)
    _cooldown_cache: dict[str, float] = {}
    # Counter for periodic history pruning (avoid checking DB every call)
    _notify_count: int = 0

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings().notification

    async def notify(
        self,
        level: str,
        event_type: str,
        title: str,
        message: str,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Notification:
        """Create notification, push via WebSocket, fire webhook.

        This method persists the notification to DB synchronously,
        then fires WebSocket push and webhook delivery as background tasks.
        """
        if not self._settings.enabled:
            record = Notification(
                level=level,
                event_type=event_type,
                title=title,
                message=message,
                details=details or {},
                run_id=run_id,
                status="skipped",
            )
            self._session.add(record)
            await self._session.flush()
            return record

        # Rate-limit check
        now = time.monotonic()
        last_sent = self._cooldown_cache.get(event_type, 0.0)
        is_rate_limited = (now - last_sent) < self._settings.cooldown_seconds

        status = "skipped" if is_rate_limited else "pending"

        # Update cooldown cache before await to prevent race condition:
        # without this, a concurrent coroutine could pass the rate-limit
        # check while this coroutine is yielded at flush().
        if not is_rate_limited:
            self._cooldown_cache[event_type] = now

        record = Notification(
            level=level,
            event_type=event_type,
            title=title,
            message=message,
            details=details or {},
            run_id=run_id,
            status=status,
        )
        self._session.add(record)
        await self._session.flush()

        if is_rate_limited:
            return record

        # Build payload for WebSocket and webhook
        payload = {
            "id": record.id,
            "level": record.level,
            "event_type": record.event_type,
            "title": record.title,
            "message": record.message,
            "details": record.details,
            "run_id": record.run_id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

        # Fire-and-forget WebSocket push
        asyncio.create_task(_push_to_websocket(payload))

        # Fire-and-forget webhook delivery
        if self._settings.webhook_url:
            asyncio.create_task(
                _deliver_webhook(
                    notification_id=record.id,
                    payload=payload,
                    url=self._settings.webhook_url,
                    timeout=self._settings.webhook_timeout_seconds,
                    max_retries=self._settings.webhook_max_retries,
                )
            )

        # Periodically prune old notifications beyond max_history
        NotificationService._notify_count += 1
        if NotificationService._notify_count % 50 == 0:
            asyncio.create_task(_prune_old_notifications(self._settings.max_history))

        return record

    async def list_notifications(
        self,
        offset: int = 0,
        limit: int = 20,
        level: str | None = None,
        is_read: bool | None = None,
        event_type: str | None = None,
    ) -> tuple[list[Notification], int]:
        """List notifications with filters and pagination."""
        query = select(Notification)
        count_query = select(func.count()).select_from(Notification)

        if level is not None:
            query = query.where(Notification.level == level)
            count_query = count_query.where(Notification.level == level)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
            count_query = count_query.where(Notification.is_read == is_read)
        if event_type is not None:
            query = query.where(Notification.event_type == event_type)
            count_query = count_query.where(Notification.event_type == event_type)

        total = (await self._session.execute(count_query)).scalar() or 0

        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        query = (
            select(func.count()).select_from(Notification).where(Notification.is_read == False)  # noqa: E712
        )
        return (await self._session.execute(query)).scalar() or 0

    async def mark_read(self, notification_ids: list[str] | None = None) -> int:
        """Mark notifications as read. None = mark all unread as read."""
        stmt = (
            update(Notification).where(Notification.is_read == False)  # noqa: E712
        )
        if notification_ids is not None:
            stmt = stmt.where(Notification.id.in_(notification_ids))
        stmt = stmt.values(is_read=True)

        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def delete_notification(self, notification_id: str) -> bool:
        """Delete a single notification."""
        record = await self._session.get(Notification, notification_id)
        if record is None:
            return False
        await self._session.delete(record)
        return True


# ---------------------------------------------------------------------------
# Module-level helpers (for use in engine code)
# ---------------------------------------------------------------------------


async def emit_notification(
    level: str,
    event_type: str,
    title: str,
    message: str,
    details: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    """Fire-and-forget notification emission for use in engine code.

    Opens its own DB session so callers don't need to manage one.
    """
    try:
        from squant.infra.database import get_session_context

        async with get_session_context() as session:
            service = NotificationService(session)
            await service.notify(level, event_type, title, message, details, run_id)
    except Exception:
        logger.warning("Failed to emit notification", exc_info=True)


async def _prune_old_notifications(max_history: int) -> None:
    """Delete oldest notifications beyond max_history limit."""
    try:
        from squant.infra.database import get_session_context

        async with get_session_context() as session:
            # Find the cutoff: get created_at of the Nth newest record
            cutoff_query = (
                select(Notification.created_at)
                .order_by(Notification.created_at.desc())
                .offset(max_history)
                .limit(1)
            )
            result = await session.execute(cutoff_query)
            cutoff = result.scalar()
            if cutoff is not None:
                from sqlalchemy import delete as sa_delete

                stmt = sa_delete(Notification).where(Notification.created_at < cutoff)
                deleted = await session.execute(stmt)
                await session.commit()
                if deleted.rowcount:
                    logger.info(
                        "Pruned %d old notifications (max_history=%d)",
                        deleted.rowcount,
                        max_history,
                    )
    except Exception:
        logger.warning("Failed to prune old notifications", exc_info=True)


async def _push_to_websocket(payload: dict[str, Any]) -> None:
    """Publish notification to Redis for WebSocket gateway."""
    try:
        from squant.infra.redis import get_redis_client

        redis = get_redis_client()
        message = json.dumps(
            {
                "type": "notification",
                "channel": "notifications",
                "data": payload,
            },
            default=str,
        )
        await redis.publish("squant:ws:notifications", message)
    except Exception:
        logger.warning("Failed to push notification to WebSocket", exc_info=True)


async def _deliver_webhook(
    notification_id: str,
    payload: dict[str, Any],
    url: str,
    timeout: int,
    max_retries: int,
) -> None:
    """Deliver webhook with retry and exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                await _update_webhook_status(
                    notification_id, "delivered", status_code=response.status_code
                )
                return
        except httpx.HTTPStatusError as e:
            if attempt < max_retries:
                await asyncio.sleep(2**attempt)
                continue
            await _update_webhook_status(
                notification_id,
                "failed",
                status_code=e.response.status_code,
                error=str(e),
                retry_count=attempt + 1,
            )
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(2**attempt)
                continue
            await _update_webhook_status(
                notification_id, "failed", error=str(e), retry_count=attempt + 1
            )


async def _update_webhook_status(
    notification_id: str,
    status: str,
    status_code: int | None = None,
    error: str | None = None,
    retry_count: int = 0,
) -> None:
    """Update notification delivery status in DB (opens its own session)."""
    try:
        from squant.infra.database import get_session_context

        async with get_session_context() as session:
            stmt = (
                update(Notification)
                .where(Notification.id == notification_id)
                .values(
                    status=status,
                    webhook_status_code=status_code,
                    webhook_error=error[:500] if error else None,
                    retry_count=retry_count,
                )
            )
            await session.execute(stmt)
    except Exception:
        logger.warning(f"Failed to update notification {notification_id} status", exc_info=True)
