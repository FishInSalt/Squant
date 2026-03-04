"""Unit tests for notification service (LIVE-011)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from squant.models.notification import Notification
from squant.services.notification import (
    NotificationService,
    _deliver_webhook,
    _prune_old_notifications,
    _push_to_websocket,
    emit_notification,
)


@pytest.fixture(autouse=True)
def _reset_class_state():
    """Clear class-level state before each test."""
    NotificationService._cooldown_cache.clear()
    NotificationService._notify_count = 0
    yield
    NotificationService._cooldown_cache.clear()
    NotificationService._notify_count = 0


@pytest.fixture
def mock_settings():
    """Create mock notification settings."""
    settings = MagicMock()
    settings.enabled = True
    settings.cooldown_seconds = 60
    settings.webhook_url = None
    settings.webhook_timeout_seconds = 10
    settings.webhook_max_retries = 3
    settings.max_history = 1000
    return settings


@pytest.fixture
def mock_session():
    """Create mock async DB session."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def service(mock_session, mock_settings):
    """Create NotificationService with mocks."""
    with patch("squant.services.notification.get_settings") as mock_get:
        mock_get.return_value.notification = mock_settings
        svc = NotificationService(mock_session)
    return svc


class TestNotificationServiceNotify:
    """Tests for NotificationService.notify() core method."""

    async def test_notify_creates_record(self, service, mock_session):
        """Normal path: creates record with status=pending, calls add+flush."""
        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="critical",
                event_type="engine_crashed",
                title="Engine Crashed",
                message="Something went wrong",
                details={"error": "test"},
                run_id="run-123",
            )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        added_record = mock_session.add.call_args[0][0]
        assert isinstance(added_record, Notification)
        assert added_record.level == "critical"
        assert added_record.event_type == "engine_crashed"
        assert added_record.status == "pending"
        assert added_record.run_id == "run-123"
        assert added_record.details == {"error": "test"}

    async def test_notify_disabled(self, mock_session, mock_settings):
        """When notifications disabled, status=skipped and no WS/webhook tasks."""
        mock_settings.enabled = False
        with patch("squant.services.notification.get_settings") as mock_get:
            mock_get.return_value.notification = mock_settings
            svc = NotificationService(mock_session)

        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await svc.notify(
                level="info",
                event_type="test",
                title="Test",
                message="msg",
            )

        added = mock_session.add.call_args[0][0]
        assert added.status == "skipped"
        mock_asyncio.create_task.assert_not_called()

    async def test_notify_rate_limited(self, service, mock_session):
        """Second call for same event_type within cooldown → skipped."""
        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="warning",
                event_type="position_mismatch",
                title="T1",
                message="M1",
            )

        # Second call with same event_type
        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="warning",
                event_type="position_mismatch",
                title="T2",
                message="M2",
            )

        # Second add call should have status=skipped
        second_record = mock_session.add.call_args_list[1][0][0]
        assert second_record.status == "skipped"

    async def test_notify_rate_limit_different_event_types(self, service, mock_session):
        """Different event_types are independent for cooldown."""
        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="critical",
                event_type="type_a",
                title="T1",
                message="M1",
            )
            await service.notify(
                level="critical",
                event_type="type_b",
                title="T2",
                message="M2",
            )

        # Both should be pending (different types)
        first = mock_session.add.call_args_list[0][0][0]
        second = mock_session.add.call_args_list[1][0][0]
        assert first.status == "pending"
        assert second.status == "pending"

    async def test_notify_fires_websocket_task(self, service, mock_session):
        """Verify WebSocket push task is created."""
        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="info",
                event_type="test",
                title="T",
                message="M",
            )

        # At least one create_task call for _push_to_websocket
        assert mock_asyncio.create_task.call_count >= 1

    async def test_notify_fires_webhook_task(self, service, mock_session):
        """When webhook_url is set, webhook task is created."""
        service._settings.webhook_url = "https://example.com/hook"

        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="critical",
                event_type="test",
                title="T",
                message="M",
            )

        # 2 tasks: WS push + webhook
        assert mock_asyncio.create_task.call_count >= 2

    async def test_notify_no_webhook_when_url_empty(self, service, mock_session):
        """No webhook task when webhook_url is None."""
        service._settings.webhook_url = None

        with (
            patch(
                "squant.services.notification._push_to_websocket",
                new_callable=AsyncMock,
            ),
            patch("squant.services.notification.asyncio") as mock_asyncio,
        ):
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="info",
                event_type="test",
                title="T",
                message="M",
            )

        # Only 1 task: WS push (no webhook)
        assert mock_asyncio.create_task.call_count == 1

    async def test_notify_triggers_prune_every_50(self, service, mock_session):
        """Prune task fires when _notify_count reaches 50."""
        NotificationService._notify_count = 49

        with patch("squant.services.notification.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            await service.notify(
                level="info",
                event_type="test",
                title="T",
                message="M",
            )

        # WS push (1) + prune (1) = at least 2
        assert mock_asyncio.create_task.call_count >= 2


class TestNotificationServiceCRUD:
    """Tests for list/count/mark/delete methods."""

    async def test_list_notifications(self, service, mock_session):
        """List returns items and total count."""
        mock_items = [MagicMock(), MagicMock()]
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = mock_items

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_items_result])

        items, total = await service.list_notifications(offset=0, limit=20)
        assert len(items) == 2
        assert total == 5

    async def test_list_notifications_with_filters(self, service, mock_session):
        """List with level and is_read filters."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [MagicMock()]

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_items_result])

        items, total = await service.list_notifications(
            offset=0, limit=10, level="critical", is_read=False
        )
        assert total == 1
        assert len(items) == 1

    async def test_get_unread_count(self, service, mock_session):
        """Get unread count returns integer."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await service.get_unread_count()
        assert count == 42

    async def test_mark_all_read(self, service, mock_session):
        """Mark all unread as read when ids=None."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_result)

        updated = await service.mark_read(notification_ids=None)
        assert updated == 5
        mock_session.execute.assert_awaited_once()

    async def test_mark_specific_read(self, service, mock_session):
        """Mark specific notification ids as read."""
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute = AsyncMock(return_value=mock_result)

        updated = await service.mark_read(notification_ids=["id-1", "id-2"])
        assert updated == 2

    async def test_delete_existing(self, service, mock_session):
        """Delete existing notification returns True."""
        mock_session.get = AsyncMock(return_value=MagicMock())
        result = await service.delete_notification("some-id")
        assert result is True
        mock_session.delete.assert_awaited_once()

    async def test_delete_nonexistent(self, service, mock_session):
        """Delete nonexistent notification returns False."""
        mock_session.get = AsyncMock(return_value=None)
        result = await service.delete_notification("bad-id")
        assert result is False
        mock_session.delete.assert_not_awaited()


class TestEmitNotification:
    """Tests for module-level emit_notification helper."""

    async def test_emit_notification_success(self):
        """emit_notification opens session and calls service.notify."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with (
            patch(
                "squant.infra.database.get_session_context",
                new=mock_session_ctx,
            ),
            patch.object(NotificationService, "notify", new_callable=AsyncMock) as mock_notify,
            patch("squant.services.notification.get_settings") as mock_get,
        ):
            mock_get.return_value.notification = MagicMock(enabled=True)
            await emit_notification(
                level="critical",
                event_type="test",
                title="Test",
                message="msg",
            )
            mock_notify.assert_awaited_once()

    async def test_emit_notification_swallows_exceptions(self):
        """emit_notification does not raise on DB errors."""
        with patch(
            "squant.infra.database.get_session_context",
            side_effect=RuntimeError("DB down"),
        ):
            # Should not raise
            await emit_notification(
                level="critical",
                event_type="test",
                title="Test",
                message="msg",
            )


class TestDeliverWebhook:
    """Tests for _deliver_webhook function."""

    async def test_deliver_success_200(self):
        """Successful 200 response marks as delivered."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()  # no-op for 200

        with (
            patch("squant.services.notification.httpx.AsyncClient") as mock_client_cls,
            patch(
                "squant.services.notification._update_webhook_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _deliver_webhook(
                notification_id="n-1",
                payload={"test": True},
                url="https://example.com/hook",
                timeout=10,
                max_retries=0,
            )

            mock_update.assert_awaited_once_with("n-1", "delivered", status_code=200)

    async def test_deliver_retries_on_5xx(self):
        """5xx response triggers retry and eventually marks as failed."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_request = MagicMock()
        error = httpx.HTTPStatusError("Server Error", request=mock_request, response=mock_response)
        mock_response.raise_for_status = MagicMock(side_effect=error)

        with (
            patch("squant.services.notification.httpx.AsyncClient") as mock_client_cls,
            patch(
                "squant.services.notification._update_webhook_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _deliver_webhook(
                notification_id="n-1",
                payload={"test": True},
                url="https://example.com/hook",
                timeout=10,
                max_retries=0,  # No retry, fail immediately
            )

            mock_update.assert_awaited_once()
            call_args = mock_update.call_args
            assert call_args[0][0] == "n-1"
            assert call_args[0][1] == "failed"
            assert call_args[1]["status_code"] == 500

    async def test_deliver_retries_on_connection_error(self):
        """Connection error triggers retry and eventually marks as failed."""
        with (
            patch("squant.services.notification.httpx.AsyncClient") as mock_client_cls,
            patch(
                "squant.services.notification._update_webhook_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _deliver_webhook(
                notification_id="n-1",
                payload={"test": True},
                url="https://example.com/hook",
                timeout=10,
                max_retries=0,
            )

            mock_update.assert_awaited_once()
            assert mock_update.call_args[0][1] == "failed"

    async def test_deliver_no_retry_on_first_success(self):
        """Successful first call does not retry."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with (
            patch("squant.services.notification.httpx.AsyncClient") as mock_client_cls,
            patch(
                "squant.services.notification._update_webhook_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _deliver_webhook(
                notification_id="n-1",
                payload={},
                url="https://example.com/hook",
                timeout=10,
                max_retries=3,
            )

            # Only one POST call
            mock_client.post.assert_awaited_once()
            mock_update.assert_awaited_once_with("n-1", "delivered", status_code=200)


class TestPushToWebsocket:
    """Tests for _push_to_websocket function."""

    async def test_publishes_to_redis(self):
        """Publishes JSON to correct Redis channel."""
        mock_redis = AsyncMock()

        with patch(
            "squant.infra.redis.get_redis_client",
            return_value=mock_redis,
        ):
            await _push_to_websocket({"id": "n-1", "title": "Test"})

        mock_redis.publish.assert_awaited_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == "squant:ws:notifications"

    async def test_swallows_errors(self):
        """Redis errors do not propagate."""
        with patch(
            "squant.infra.redis.get_redis_client",
            side_effect=RuntimeError("Redis down"),
        ):
            # Should not raise
            await _push_to_websocket({"id": "n-1"})


class TestPruneOldNotifications:
    """Tests for _prune_old_notifications function."""

    async def test_prune_deletes_old(self):
        """Prunes records beyond max_history."""
        mock_session = AsyncMock()
        cutoff_result = MagicMock()
        cutoff_result.scalar.return_value = datetime(2024, 1, 1, tzinfo=UTC)
        delete_result = MagicMock()
        delete_result.rowcount = 10
        mock_session.execute = AsyncMock(side_effect=[cutoff_result, delete_result])
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_ctx():
            yield mock_session

        with patch(
            "squant.infra.database.get_session_context",
            new=mock_ctx,
        ):
            await _prune_old_notifications(max_history=100)

        assert mock_session.execute.await_count == 2
        mock_session.commit.assert_awaited_once()

    async def test_prune_no_op_under_limit(self):
        """No delete when under max_history limit."""
        mock_session = AsyncMock()
        cutoff_result = MagicMock()
        cutoff_result.scalar.return_value = None  # no cutoff = under limit
        mock_session.execute = AsyncMock(return_value=cutoff_result)

        @asynccontextmanager
        async def mock_ctx():
            yield mock_session

        with patch(
            "squant.infra.database.get_session_context",
            new=mock_ctx,
        ):
            await _prune_old_notifications(max_history=1000)

        # Only the cutoff query, no delete
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_not_awaited()

    async def test_prune_swallows_errors(self):
        """DB errors do not propagate."""
        with patch(
            "squant.infra.database.get_session_context",
            side_effect=RuntimeError("DB down"),
        ):
            await _prune_old_notifications(max_history=100)
