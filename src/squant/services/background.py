"""Background tasks for paper trading.

Manages periodic tasks:
- Persist equity snapshots to database
- Health check and cleanup stale sessions
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks for paper trading.

    Runs periodic tasks for:
    - Persisting equity snapshots to database
    - Health checking and cleaning up stale sessions
    """

    def __init__(self) -> None:
        """Initialize background task manager."""
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if background tasks are running."""
        return self._running

    def start(self, persist_interval: float, health_check_interval: float) -> None:
        """Start background tasks.

        Args:
            persist_interval: Interval in seconds for snapshot persistence (supports sub-second intervals).
            health_check_interval: Interval in seconds for health checks (supports sub-second intervals).
        """
        if self._running:
            logger.warning("Background tasks already running")
            return

        self._running = True
        self._tasks.append(
            asyncio.create_task(self._run_periodic(self._persist_snapshots, persist_interval))
        )
        self._tasks.append(
            asyncio.create_task(self._run_periodic(self._health_check, health_check_interval))
        )
        logger.info(
            f"Background tasks started: persist_interval={persist_interval}s, "
            f"health_check_interval={health_check_interval}s"
        )

    async def stop(self) -> None:
        """Stop all background tasks."""
        if not self._running:
            return

        self._running = False
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        logger.info("Background tasks stopped")

    async def _run_periodic(
        self,
        func: Callable[[], Awaitable[None]],
        interval: float,
    ) -> None:
        """Run a function periodically.

        Args:
            func: Async function to run.
            interval: Interval in seconds between runs (supports sub-second intervals).
        """
        while self._running:
            try:
                await asyncio.sleep(interval)
                if self._running:  # Check again after sleep
                    await func()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in periodic task {func.__name__}: {e}")

    async def _persist_snapshots(self) -> None:
        """Persist pending snapshots for all active sessions."""
        from squant.engine.paper.manager import get_session_manager
        from squant.infra.database import get_session_context
        from squant.services.paper_trading import PaperTradingService

        session_manager = get_session_manager()

        # Get list of run_ids with pending snapshots via public API
        run_ids_to_persist = session_manager.get_sessions_needing_persistence()

        if not run_ids_to_persist:
            return

        async with get_session_context() as db_session:
            service = PaperTradingService(db_session)
            for run_id in run_ids_to_persist:
                try:
                    count = await service.persist_snapshots(run_id)
                    if count > 0:
                        logger.debug(f"Persisted {count} snapshots for run {run_id}")
                except Exception as e:
                    logger.error(f"Failed to persist snapshots for run {run_id}: {e}")

    async def _health_check(self) -> None:
        """Check and cleanup stale sessions."""
        from squant.config import get_settings
        from squant.engine.paper.manager import get_session_manager

        settings = get_settings()
        session_manager = get_session_manager()

        count = await session_manager.cleanup_stale_sessions(settings.paper_session_timeout_seconds)
        if count > 0:
            logger.warning(f"Cleaned up {count} stale paper trading sessions")


# Global instance
_task_manager: BackgroundTaskManager | None = None


def get_task_manager() -> BackgroundTaskManager:
    """Get the global background task manager.

    Returns:
        BackgroundTaskManager singleton.
    """
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
