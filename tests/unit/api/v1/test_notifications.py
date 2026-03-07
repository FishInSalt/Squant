"""Unit tests for notification API endpoints (LIVE-011)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from squant.main import app


def _make_notification(**overrides) -> MagicMock:
    """Create a mock Notification object for testing."""
    now = datetime.now(UTC)
    defaults = {
        "id": "n-001",
        "level": "critical",
        "event_type": "engine_crashed",
        "title": "Engine Crashed",
        "message": "Something went wrong",
        "details": {},
        "run_id": None,
        "status": "pending",
        "is_read": False,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestListNotifications:
    """Tests for GET /api/v1/notifications."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncGenerator[AsyncClient, None]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_list_success(self, client: AsyncClient) -> None:
        """Returns paginated notification list."""
        items = [_make_notification(id="n-1"), _make_notification(id="n-2")]

        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.list_notifications = AsyncMock(return_value=(items, 2))
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["total"] == 2
        assert len(data["data"]["items"]) == 2
        assert data["data"]["items"][0]["id"] == "n-1"

    async def test_list_with_filters(self, client: AsyncClient) -> None:
        """Query params are passed to service."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.list_notifications = AsyncMock(return_value=([], 0))
            mock_cls.return_value = mock_svc

            response = await client.get(
                "/api/v1/notifications",
                params={"level": "critical", "is_read": "false", "page": 2, "page_size": 10},
            )

        assert response.status_code == 200
        call_kwargs = mock_svc.list_notifications.call_args[1]
        assert call_kwargs["level"] == "critical"
        assert call_kwargs["is_read"] is False
        assert call_kwargs["offset"] == 10  # page=2, page_size=10 → offset=10
        assert call_kwargs["limit"] == 10

    async def test_list_empty(self, client: AsyncClient) -> None:
        """Returns empty list when no notifications."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.list_notifications = AsyncMock(return_value=([], 0))
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []


class TestUnreadCount:
    """Tests for GET /api/v1/notifications/unread-count."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncGenerator[AsyncClient, None]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_unread_count(self, client: AsyncClient) -> None:
        """Returns unread notification count."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.get_unread_count = AsyncMock(return_value=7)
            mock_cls.return_value = mock_svc

            response = await client.get("/api/v1/notifications/unread-count")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["count"] == 7


class TestMarkRead:
    """Tests for POST /api/v1/notifications/mark-read."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncGenerator[AsyncClient, None]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_mark_all_read(self, client: AsyncClient) -> None:
        """Mark all as read when notification_ids is null."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.mark_read = AsyncMock(return_value=5)
            mock_cls.return_value = mock_svc

            response = await client.post(
                "/api/v1/notifications/mark-read",
                json={"notification_ids": None},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["updated"] == 5
        mock_svc.mark_read.assert_awaited_once_with(None)

    async def test_mark_specific(self, client: AsyncClient) -> None:
        """Mark specific notification ids as read."""
        ids = ["n-1", "n-2"]
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.mark_read = AsyncMock(return_value=2)
            mock_cls.return_value = mock_svc

            response = await client.post(
                "/api/v1/notifications/mark-read",
                json={"notification_ids": ids},
            )

        assert response.status_code == 200
        assert response.json()["data"]["updated"] == 2
        mock_svc.mark_read.assert_awaited_once_with(ids)


class TestDeleteNotification:
    """Tests for DELETE /api/v1/notifications/{id}."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncGenerator[AsyncClient, None]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_delete_success(self, client: AsyncClient) -> None:
        """Delete existing notification returns 200."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.delete_notification = AsyncMock(return_value=True)
            mock_cls.return_value = mock_svc

            response = await client.delete("/api/v1/notifications/n-1")

        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    async def test_delete_not_found(self, client: AsyncClient) -> None:
        """Delete nonexistent notification returns 404."""
        with patch("squant.api.v1.notifications.NotificationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.delete_notification = AsyncMock(return_value=False)
            mock_cls.return_value = mock_svc

            response = await client.delete("/api/v1/notifications/bad-id")

        assert response.status_code == 404
