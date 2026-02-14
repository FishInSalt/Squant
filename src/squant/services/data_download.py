"""Historical data download service.

Manages asynchronous download tasks that fetch OHLCV data from exchanges
via CCXT and store it in the Kline TimescaleDB hypertable.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.types import Candlestick, TimeFrame

logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 500  # Candles per CCXT API call
BATCH_DELAY = 0.5  # Seconds between API calls

# Timeframe durations in milliseconds (for cursor advancement)
TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


class DownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadTaskInfo:
    """In-memory download task state."""

    id: str
    exchange: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    total_candles: int | None = None
    downloaded_candles: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response dict."""
        return {
            "id": self.id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "status": self.status.value,
            "progress": round(self.progress, 1),
            "total_candles": self.total_candles,
            "downloaded_candles": self.downloaded_candles,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DataDownloadService:
    """Manages historical data download tasks.

    Tasks are tracked in memory. Each download runs as an asyncio.Task
    in the background, fetching OHLCV data via CCXT and upserting to
    the Kline table.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTaskInfo] = {}

    def start_download(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> DownloadTaskInfo:
        """Start a new download task.

        Args:
            exchange: Exchange ID (okx, binance, bybit).
            symbol: Trading pair (e.g., BTC/USDT).
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w).
            start_date: Start datetime (inclusive).
            end_date: End datetime (inclusive).

        Returns:
            DownloadTaskInfo with task ID and initial status.

        Raises:
            ValueError: If timeframe is invalid or date range is invalid.
        """
        if timeframe not in TIMEFRAME_MS:
            raise ValueError(f"Invalid timeframe: {timeframe}")
        if end_date <= start_date:
            raise ValueError("end_date must be after start_date")

        # Ensure timezone-aware (naive datetimes treated as UTC)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=UTC)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=UTC)

        task_id = str(uuid.uuid4())
        task_info = DownloadTaskInfo(
            id=task_id,
            exchange=exchange.lower(),
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        # Estimate total candles for progress tracking
        duration_ms = int((end_date - start_date).total_seconds() * 1000)
        tf_ms = TIMEFRAME_MS[timeframe]
        task_info.total_candles = max(1, duration_ms // tf_ms)

        # Create background asyncio task
        task_info._task = asyncio.create_task(
            self._download_worker(task_info),
            name=f"download-{task_id[:8]}",
        )

        self._tasks[task_id] = task_info
        return task_info

    def get_task(self, task_id: str) -> DownloadTaskInfo | None:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[DownloadTaskInfo]:
        """List all tasks (most recent first)."""
        return sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )

    def cancel_task(self, task_id: str) -> DownloadTaskInfo | None:
        """Cancel a running download task."""
        task_info = self._tasks.get(task_id)
        if task_info is None:
            return None

        if task_info.status == DownloadStatus.DOWNLOADING and task_info._task:
            task_info._task.cancel()
            # Status will be updated by the CancelledError handler in _download_worker

        return task_info

    def remove_task(self, task_id: str) -> DownloadTaskInfo | None:
        """Remove a finished task from the task list.

        Only completed or failed tasks can be removed.
        Returns the removed task, or None if not found.
        """
        task_info = self._tasks.get(task_id)
        if task_info is None:
            return None

        if task_info.status in (DownloadStatus.DOWNLOADING, DownloadStatus.PENDING):
            return None  # Cannot remove active tasks

        return self._tasks.pop(task_id)

    async def _download_worker(self, task_info: DownloadTaskInfo) -> None:
        """Background worker that fetches candles and upserts to DB.

        1. Create a dedicated CCXTRestAdapter (public, no credentials)
        2. Loop: fetch BATCH_SIZE candles starting from cursor
        3. Upsert each batch to Kline table via ON CONFLICT
        4. Update progress
        5. Sleep BATCH_DELAY between batches
        6. Close adapter when done
        """
        from squant.infra.database import get_session_context

        task_info.status = DownloadStatus.DOWNLOADING
        adapter = CCXTRestAdapter(task_info.exchange, None)

        try:
            await adapter.connect()

            tf_enum = TimeFrame(task_info.timeframe)
            cursor_ms = int(task_info.start_date.timestamp() * 1000)
            end_ms = int(task_info.end_date.timestamp() * 1000)

            while cursor_ms < end_ms:
                candles = await adapter.get_candlesticks(
                    symbol=task_info.symbol,
                    timeframe=tf_enum,
                    limit=BATCH_SIZE,
                    start_time=cursor_ms,
                )

                if not candles:
                    break

                # Filter candles to requested range
                raw_count = len(candles)
                candles = [c for c in candles if c.timestamp <= task_info.end_date]

                # All returned data is beyond end_date — download complete
                if raw_count > 0 and not candles:
                    break

                if candles:
                    async with get_session_context() as session:
                        await self._upsert_candles(
                            session,
                            task_info.exchange,
                            task_info.symbol,
                            task_info.timeframe,
                            candles,
                        )

                    task_info.downloaded_candles += len(candles)
                    if task_info.total_candles and task_info.total_candles > 0:
                        task_info.progress = min(
                            100.0,
                            (task_info.downloaded_candles / task_info.total_candles) * 100,
                        )

                # Advance cursor past the last candle
                last_ts_ms = int(candles[-1].timestamp.timestamp() * 1000) if candles else cursor_ms
                next_cursor = last_ts_ms + TIMEFRAME_MS[task_info.timeframe]

                # Safety: prevent infinite loop
                if next_cursor <= cursor_ms:
                    break
                cursor_ms = next_cursor

                await asyncio.sleep(BATCH_DELAY)

            task_info.status = DownloadStatus.COMPLETED
            task_info.progress = 100.0
            task_info.completed_at = datetime.now(UTC)
            logger.info(
                "Download completed: %s:%s %s - %d candles",
                task_info.exchange,
                task_info.symbol,
                task_info.timeframe,
                task_info.downloaded_candles,
            )

        except asyncio.CancelledError:
            task_info.status = DownloadStatus.FAILED
            task_info.error = "Cancelled by user"
            task_info.completed_at = datetime.now(UTC)
            logger.info("Download cancelled: %s", task_info.id)

        except Exception as e:
            task_info.status = DownloadStatus.FAILED
            task_info.error = str(e)
            task_info.completed_at = datetime.now(UTC)
            logger.exception("Download failed: %s: %s", task_info.id, e)

        finally:
            await adapter.close()

    @staticmethod
    async def _upsert_candles(
        session: Any,
        exchange: str,
        symbol: str,
        timeframe: str,
        candles: list[Candlestick],
    ) -> None:
        """Upsert candles to the Kline table using ON CONFLICT."""
        from sqlalchemy import text

        if not candles:
            return

        sql = text(
            "INSERT INTO klines (time, exchange, symbol, timeframe, "
            "open, high, low, close, volume) "
            "VALUES (:time, :exchange, :symbol, :timeframe, "
            ":open, :high, :low, :close, :volume) "
            "ON CONFLICT (time, exchange, symbol, timeframe) "
            "DO UPDATE SET "
            "open = EXCLUDED.open, high = EXCLUDED.high, "
            "low = EXCLUDED.low, close = EXCLUDED.close, "
            "volume = EXCLUDED.volume"
        )

        params = [
            {
                "time": c.timestamp,
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

        await session.execute(sql, params)


# Global singleton
_download_service: DataDownloadService | None = None


def get_download_service() -> DataDownloadService:
    """Get the global download service singleton."""
    global _download_service
    if _download_service is None:
        _download_service = DataDownloadService()
    return _download_service
