"""Unit tests for system API endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.database import get_session, get_session_readonly
from squant.main import app
from squant.services.data_download import (
    DataDownloadService,
    DownloadStatus,
    DownloadTaskInfo,
)


@pytest_asyncio.fixture
async def mock_session():
    """Create a mock async session."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest_asyncio.fixture
async def client(mock_session) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with mocked DB sessions."""

    async def override_get_session():
        yield mock_session

    async def override_get_session_readonly():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_session_readonly] = override_get_session_readonly

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# Data Download Endpoints
# ============================================================================


class TestStartDownload:
    """Tests for POST /api/v1/system/data/download."""

    @pytest.mark.asyncio
    async def test_success(self, client: AsyncClient) -> None:
        """Test starting a download task successfully."""
        task_info = DownloadTaskInfo(
            id="task-123",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.PENDING,
            total_candles=744,
        )

        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.start_download.return_value = task_info

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.post(
                "/api/v1/system/data/download",
                json={
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timeframe": "1h",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-02-01T00:00:00Z",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == "task-123"
        assert data["data"]["exchange"] == "binance"
        assert data["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_unsupported_exchange(self, client: AsyncClient) -> None:
        """Test rejection of unsupported exchange."""
        response = await client.post(
            "/api/v1/system/data/download",
            json={
                "exchange": "kraken",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-02-01T00:00:00Z",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_timeframe(self, client: AsyncClient) -> None:
        """Test rejection when service raises ValueError."""
        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.start_download.side_effect = ValueError("Invalid timeframe: 2h")

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.post(
                "/api/v1/system/data/download",
                json={
                    "exchange": "binance",
                    "symbol": "BTC/USDT",
                    "timeframe": "2h",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-02-01T00:00:00Z",
                },
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_date_range(self, client: AsyncClient) -> None:
        """Test rejection of end_date <= start_date via Pydantic validator."""
        response = await client.post(
            "/api/v1/system/data/download",
            json={
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "start_date": "2024-06-01T00:00:00Z",
                "end_date": "2024-01-01T00:00:00Z",
            },
        )

        assert response.status_code == 422


class TestListDownloadTasks:
    """Tests for GET /api/v1/system/data/download/tasks."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient) -> None:
        """Test listing when no tasks exist."""
        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.list_tasks.return_value = []

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.get("/api/v1/system/data/download/tasks")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, client: AsyncClient) -> None:
        """Test listing multiple tasks."""
        tasks = [
            DownloadTaskInfo(
                id=f"task-{i}",
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
                status=DownloadStatus.DOWNLOADING if i == 0 else DownloadStatus.COMPLETED,
            )
            for i in range(2)
        ]

        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.list_tasks.return_value = tasks

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.get("/api/v1/system/data/download/tasks")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2


class TestGetDownloadTask:
    """Tests for GET /api/v1/system/data/download/{task_id}."""

    @pytest.mark.asyncio
    async def test_found(self, client: AsyncClient) -> None:
        """Test getting an existing task."""
        task_info = DownloadTaskInfo(
            id="task-456",
            exchange="okx",
            symbol="ETH/USDT",
            timeframe="4h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 3, 1, tzinfo=UTC),
            status=DownloadStatus.COMPLETED,
            progress=100.0,
        )

        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.get_task.return_value = task_info

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.get("/api/v1/system/data/download/task-456")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == "task-456"
        assert data["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Test getting a non-existent task."""
        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.get_task.return_value = None

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.get("/api/v1/system/data/download/nonexistent")

        assert response.status_code == 404


class TestCancelDownloadTask:
    """Tests for POST /api/v1/system/data/download/{task_id}/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_success(self, client: AsyncClient) -> None:
        """Test cancelling a running task."""
        task_info = DownloadTaskInfo(
            id="task-cancel",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.FAILED,
            error="Cancelled by user",
        )

        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.cancel_task.return_value = task_info

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.post("/api/v1/system/data/download/task-cancel/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, client: AsyncClient) -> None:
        """Test cancelling a non-existent task."""
        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.cancel_task.return_value = None

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.post("/api/v1/system/data/download/nonexistent/cancel")

        assert response.status_code == 404


class TestRemoveDownloadTask:
    """Tests for DELETE /api/v1/system/data/download/{task_id}."""

    @pytest.mark.asyncio
    async def test_remove_success(self, client: AsyncClient) -> None:
        """Test removing a completed task."""
        task_info = DownloadTaskInfo(
            id="task-remove",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.COMPLETED,
        )

        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.remove_task.return_value = task_info

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.delete("/api/v1/system/data/download/task-remove")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_not_found(self, client: AsyncClient) -> None:
        """Test removing a non-existent or active task."""
        mock_service = MagicMock(spec=DataDownloadService)
        mock_service.remove_task.return_value = None

        with patch("squant.api.v1.system.get_download_service", return_value=mock_service):
            response = await client.delete("/api/v1/system/data/download/nonexistent")

        assert response.status_code == 404


# ============================================================================
# Historical Data Management Endpoints
# ============================================================================


class TestListHistoricalData:
    """Tests for GET /api/v1/system/data/list."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient) -> None:
        """Test listing when no data exists."""
        with patch("squant.api.v1.system.DataLoader") as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader.get_available_symbols = AsyncMock(return_value=[])
            mock_loader_class.return_value = mock_loader

            response = await client.get("/api/v1/system/data/list")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_list_with_data(self, client: AsyncClient) -> None:
        """Test listing available historical data."""
        symbols = [
            {
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "bar_count": 8760,
                "first_bar": "2024-01-01T00:00:00",
                "last_bar": "2024-12-31T23:00:00",
            },
        ]

        with patch("squant.api.v1.system.DataLoader") as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader.get_available_symbols = AsyncMock(return_value=symbols)
            mock_loader_class.return_value = mock_loader

            response = await client.get("/api/v1/system/data/list")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        item = data["data"][0]
        assert item["id"] == "binance:BTC/USDT:1h"
        assert item["candle_count"] == 8760
        assert item["exchange"] == "binance"

    @pytest.mark.asyncio
    async def test_list_with_symbol_filter(self, client: AsyncClient) -> None:
        """Test filtering by symbol."""
        symbols = [
            {
                "exchange": "binance",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "bar_count": 100,
                "first_bar": "2024-01-01T00:00:00",
                "last_bar": "2024-01-05T00:00:00",
            },
            {
                "exchange": "binance",
                "symbol": "ETH/USDT",
                "timeframe": "1h",
                "bar_count": 50,
                "first_bar": "2024-01-01T00:00:00",
                "last_bar": "2024-01-03T00:00:00",
            },
        ]

        with patch("squant.api.v1.system.DataLoader") as mock_loader_class:
            mock_loader = MagicMock()
            mock_loader.get_available_symbols = AsyncMock(return_value=symbols)
            mock_loader_class.return_value = mock_loader

            response = await client.get(
                "/api/v1/system/data/list", params={"symbol": "BTC/USDT"}
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["symbol"] == "BTC/USDT"


class TestDeleteHistoricalData:
    """Tests for DELETE /api/v1/system/data/{data_id}."""

    @pytest.mark.asyncio
    async def test_delete_success(self, client: AsyncClient, mock_session) -> None:
        """Test successful deletion."""
        mock_result = MagicMock()
        mock_result.rowcount = 1000
        mock_session.execute.return_value = mock_result

        response = await client.delete("/api/v1/system/data/binance:BTC/USDT:1h")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, mock_session) -> None:
        """Test deletion when no data exists."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        response = await client.delete("/api/v1/system/data/binance:BTC/USDT:1h")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_invalid_id_format(self, client: AsyncClient) -> None:
        """Test deletion with invalid data_id format (no colons)."""
        response = await client.delete("/api/v1/system/data/invalid-id")

        assert response.status_code == 400


# ============================================================================
# Symbol Listing Endpoint
# ============================================================================


class TestListExchangeSymbols:
    """Tests for GET /api/v1/system/symbols/{exchange_id}."""

    @pytest.mark.asyncio
    async def test_success(self, client: AsyncClient) -> None:
        """Test listing symbols for a supported exchange."""
        mock_adapter = MagicMock()
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}, "ETH/USDT": {}, "SOL/USDT": {}}
        mock_adapter._exchange = mock_exchange

        with patch(
            "squant.api.deps._get_or_create_exchange_adapter",
            new_callable=AsyncMock,
            return_value=mock_adapter,
        ):
            response = await client.get("/api/v1/system/symbols/binance")

        assert response.status_code == 200
        data = response.json()
        assert "BTC/USDT" in data["data"]
        assert "ETH/USDT" in data["data"]

    @pytest.mark.asyncio
    async def test_unsupported_exchange(self, client: AsyncClient) -> None:
        """Test rejection of unsupported exchange."""
        response = await client.get("/api/v1/system/symbols/kraken")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_adapter_failure(self, client: AsyncClient) -> None:
        """Test handling when adapter raises an exception."""
        with patch(
            "squant.api.deps._get_or_create_exchange_adapter",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            response = await client.get("/api/v1/system/symbols/binance")

        assert response.status_code == 502
