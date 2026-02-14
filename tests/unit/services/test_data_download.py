"""Unit tests for DataDownloadService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.infra.exchange.types import Candlestick
from squant.services.data_download import (
    TIMEFRAME_MS,
    DataDownloadService,
    DownloadStatus,
    DownloadTaskInfo,
    get_download_service,
)


# ============================================================================
# DownloadTaskInfo Tests
# ============================================================================


class TestDownloadTaskInfo:
    """Tests for DownloadTaskInfo dataclass."""

    def test_to_dict_basic(self):
        """Test serialization with all fields."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        task = DownloadTaskInfo(
            id="test-id",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 6, 1, tzinfo=UTC),
            status=DownloadStatus.DOWNLOADING,
            progress=50.0,
            total_candles=3624,
            downloaded_candles=1812,
            created_at=now,
        )

        result = task.to_dict()

        assert result["id"] == "test-id"
        assert result["exchange"] == "binance"
        assert result["symbol"] == "BTC/USDT"
        assert result["timeframe"] == "1h"
        assert result["status"] == "downloading"
        assert result["progress"] == 50.0
        assert result["total_candles"] == 3624
        assert result["downloaded_candles"] == 1812
        assert result["error"] is None
        assert result["completed_at"] is None
        assert "2024-01-01" in result["start_date"]
        assert "2024-06-01" in result["end_date"]

    def test_to_dict_with_error(self):
        """Test serialization with error state."""
        completed_at = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)
        task = DownloadTaskInfo(
            id="err-id",
            exchange="okx",
            symbol="ETH/USDT",
            timeframe="1d",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 6, 1, tzinfo=UTC),
            status=DownloadStatus.FAILED,
            error="Rate limit exceeded",
            completed_at=completed_at,
        )

        result = task.to_dict()
        assert result["status"] == "failed"
        assert result["error"] == "Rate limit exceeded"
        assert result["completed_at"] is not None

    def test_to_dict_progress_rounding(self):
        """Test that progress is rounded to 1 decimal place."""
        task = DownloadTaskInfo(
            id="round-id",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 6, 1, tzinfo=UTC),
            progress=33.33333,
        )

        result = task.to_dict()
        assert result["progress"] == 33.3


# ============================================================================
# DataDownloadService Task Management Tests
# ============================================================================


class TestDataDownloadServiceTaskManagement:
    """Tests for task creation, listing, and cancellation."""

    @pytest.mark.asyncio
    async def test_start_download_creates_task(self):
        """Test that start_download creates a task with correct attributes."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task = service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )

        assert task.exchange == "binance"
        assert task.symbol == "BTC/USDT"
        assert task.timeframe == "1h"
        assert task.status == DownloadStatus.PENDING
        assert task.total_candles is not None
        assert task.total_candles > 0
        assert task.id in service._tasks

    def test_start_download_invalid_timeframe(self):
        """Test validation rejects invalid timeframe."""
        service = DataDownloadService()

        with pytest.raises(ValueError, match="Invalid timeframe"):
            service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="2h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )

    def test_start_download_invalid_date_range(self):
        """Test validation rejects end_date <= start_date."""
        service = DataDownloadService()

        with pytest.raises(ValueError, match="end_date must be after start_date"):
            service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 6, 1, tzinfo=UTC),
                end_date=datetime(2024, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_start_download_exchange_lowercased(self):
        """Test that exchange is lowercased."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task = service.start_download(
                exchange="BINANCE",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )

        assert task.exchange == "binance"

    @pytest.mark.asyncio
    async def test_start_download_naive_datetime_gets_utc(self):
        """Test that naive datetimes are treated as UTC."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task = service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1),  # naive
                end_date=datetime(2024, 2, 1),  # naive
            )

        assert task.start_date.tzinfo is not None
        assert task.end_date.tzinfo is not None
        assert task.start_date == datetime(2024, 1, 1, tzinfo=UTC)
        assert task.end_date == datetime(2024, 2, 1, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_start_download_estimates_total_candles(self):
        """Test total candle estimation based on timeframe."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task = service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 1, 2, tzinfo=UTC),
            )

        # 24 hours = 24 one-hour candles
        assert task.total_candles == 24

    @pytest.mark.asyncio
    async def test_get_task_found(self):
        """Test retrieving an existing task."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task = service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )

        result = service.get_task(task.id)
        assert result is task

    def test_get_task_not_found(self):
        """Test retrieving a non-existent task returns None."""
        service = DataDownloadService()
        assert service.get_task("nonexistent") is None

    def test_list_tasks_empty(self):
        """Test listing tasks when none exist."""
        service = DataDownloadService()
        assert service.list_tasks() == []

    @pytest.mark.asyncio
    async def test_list_tasks_ordered_by_created_at_desc(self):
        """Test tasks are listed most recent first."""
        service = DataDownloadService()

        with patch.object(service, "_download_worker", new_callable=AsyncMock):
            task1 = service.start_download(
                exchange="binance",
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )
            # Force different created_at
            task1.created_at = datetime(2024, 1, 1, tzinfo=UTC)

            task2 = service.start_download(
                exchange="binance",
                symbol="ETH/USDT",
                timeframe="1h",
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 2, 1, tzinfo=UTC),
            )
            task2.created_at = datetime(2024, 6, 1, tzinfo=UTC)

        tasks = service.list_tasks()
        assert len(tasks) == 2
        assert tasks[0].id == task2.id  # Most recent first

    def test_cancel_task_not_found(self):
        """Test cancelling a non-existent task returns None."""
        service = DataDownloadService()
        assert service.cancel_task("nonexistent") is None

    def test_cancel_task_downloading(self):
        """Test cancelling a downloading task."""
        service = DataDownloadService()

        task_info = DownloadTaskInfo(
            id="cancel-me",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.DOWNLOADING,
        )
        mock_task = MagicMock()
        task_info._task = mock_task
        service._tasks["cancel-me"] = task_info

        result = service.cancel_task("cancel-me")

        assert result is not None
        mock_task.cancel.assert_called_once()

    def test_cancel_task_already_completed(self):
        """Test cancelling a completed task doesn't call cancel."""
        service = DataDownloadService()

        task_info = DownloadTaskInfo(
            id="already-done",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.COMPLETED,
        )
        mock_task = MagicMock()
        task_info._task = mock_task
        service._tasks["already-done"] = task_info

        result = service.cancel_task("already-done")

        assert result is not None
        mock_task.cancel.assert_not_called()

    def test_remove_task_not_found(self):
        """Test removing a non-existent task returns None."""
        service = DataDownloadService()
        assert service.remove_task("nonexistent") is None

    def test_remove_task_completed(self):
        """Test removing a completed task succeeds."""
        service = DataDownloadService()

        task_info = DownloadTaskInfo(
            id="done-task",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.COMPLETED,
        )
        service._tasks["done-task"] = task_info

        result = service.remove_task("done-task")
        assert result is task_info
        assert "done-task" not in service._tasks

    def test_remove_task_failed(self):
        """Test removing a failed task succeeds."""
        service = DataDownloadService()

        task_info = DownloadTaskInfo(
            id="failed-task",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.FAILED,
        )
        service._tasks["failed-task"] = task_info

        result = service.remove_task("failed-task")
        assert result is task_info
        assert "failed-task" not in service._tasks

    def test_remove_task_active_rejected(self):
        """Test removing an active (downloading) task is rejected."""
        service = DataDownloadService()

        task_info = DownloadTaskInfo(
            id="active-task",
            exchange="binance",
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 2, 1, tzinfo=UTC),
            status=DownloadStatus.DOWNLOADING,
        )
        service._tasks["active-task"] = task_info

        result = service.remove_task("active-task")
        assert result is None
        assert "active-task" in service._tasks  # Not removed


# ============================================================================
# Upsert Candles Tests
# ============================================================================


class TestUpsertCandles:
    """Tests for _upsert_candles static method."""

    @pytest.mark.asyncio
    async def test_upsert_empty_list(self):
        """Test that empty candle list is a no-op."""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()

        await DataDownloadService._upsert_candles(
            mock_session, "binance", "BTC/USDT", "1h", []
        )

        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_builds_correct_params(self):
        """Test that candles are converted to correct SQL params."""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()

        candles = [
            Candlestick(
                timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                open=Decimal("42000"),
                high=Decimal("42500"),
                low=Decimal("41500"),
                close=Decimal("42200"),
                volume=Decimal("100.5"),
            ),
            Candlestick(
                timestamp=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
                open=Decimal("42200"),
                high=Decimal("42800"),
                low=Decimal("42000"),
                close=Decimal("42600"),
                volume=Decimal("150.3"),
            ),
        ]

        await DataDownloadService._upsert_candles(
            mock_session, "binance", "BTC/USDT", "1h", candles
        )

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1]  # Second positional arg is the params list

        assert len(params) == 2
        assert params[0]["exchange"] == "binance"
        assert params[0]["symbol"] == "BTC/USDT"
        assert params[0]["timeframe"] == "1h"
        assert params[0]["open"] == Decimal("42000")
        assert params[1]["close"] == Decimal("42600")

    @pytest.mark.asyncio
    async def test_upsert_sql_contains_on_conflict(self):
        """Test that SQL uses ON CONFLICT for upsert."""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()

        candles = [
            Candlestick(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("42000"),
                high=Decimal("42500"),
                low=Decimal("41500"),
                close=Decimal("42200"),
                volume=Decimal("100"),
            ),
        ]

        await DataDownloadService._upsert_candles(
            mock_session, "binance", "BTC/USDT", "1h", candles
        )

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "ON CONFLICT" in sql_text
        assert "DO UPDATE SET" in sql_text


# ============================================================================
# Singleton Tests
# ============================================================================


class TestGetDownloadService:
    """Tests for the singleton accessor."""

    def test_returns_same_instance(self):
        """Test that get_download_service returns the same instance."""
        import squant.services.data_download as module

        # Reset singleton
        module._download_service = None

        svc1 = get_download_service()
        svc2 = get_download_service()
        assert svc1 is svc2

        # Cleanup
        module._download_service = None


# ============================================================================
# TIMEFRAME_MS Constants Tests
# ============================================================================


class TestTimeframeConstants:
    """Tests for timeframe duration constants."""

    def test_all_timeframes_present(self):
        """Test all expected timeframes are defined."""
        expected = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}
        assert set(TIMEFRAME_MS.keys()) == expected

    def test_durations_are_positive(self):
        """Test all durations are positive milliseconds."""
        for tf, ms in TIMEFRAME_MS.items():
            assert ms > 0, f"Timeframe {tf} has non-positive duration"

    def test_1h_duration(self):
        """Test 1h is 3600000 ms."""
        assert TIMEFRAME_MS["1h"] == 3_600_000
