"""Unit tests for background task manager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.services.background import BackgroundTaskManager, get_task_manager


class TestBackgroundTaskManagerInit:
    """Tests for BackgroundTaskManager initialization."""

    def test_initial_state(self) -> None:
        """Test manager starts in correct initial state."""
        manager = BackgroundTaskManager()

        assert manager.is_running is False
        assert len(manager._tasks) == 0

    def test_singleton_pattern(self) -> None:
        """Test get_task_manager returns singleton."""
        # Reset singleton for test
        import squant.services.background as bg_module

        bg_module._task_manager = None

        manager1 = get_task_manager()
        manager2 = get_task_manager()

        assert manager1 is manager2

        # Cleanup
        bg_module._task_manager = None


class TestBackgroundTaskManagerLifecycle:
    """Tests for BackgroundTaskManager start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        """Test that start sets running flag."""
        manager = BackgroundTaskManager()

        manager.start(persist_interval=10, health_check_interval=20)

        assert manager.is_running is True
        assert len(manager._tasks) == 2

        # Cleanup
        await manager.stop()

    @pytest.mark.asyncio
    async def test_double_start_no_duplicate_tasks(self) -> None:
        """Test that starting twice doesn't create duplicate tasks."""
        manager = BackgroundTaskManager()

        manager.start(persist_interval=10, health_check_interval=20)
        manager.start(persist_interval=10, health_check_interval=20)

        assert len(manager._tasks) == 2

        # Cleanup
        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_tasks(self) -> None:
        """Test that stop clears all tasks."""
        manager = BackgroundTaskManager()

        manager.start(persist_interval=10, health_check_interval=20)
        await manager.stop()

        assert manager.is_running is False
        assert len(manager._tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """Test that stop works when not running."""
        manager = BackgroundTaskManager()

        await manager.stop()  # Should not raise

        assert manager.is_running is False


class TestPeriodicTaskExecution:
    """Tests for periodic task execution."""

    @pytest.mark.asyncio
    async def test_persist_snapshots_called(self) -> None:
        """Test that persist_snapshots is called periodically."""
        manager = BackgroundTaskManager()

        with patch.object(manager, "_persist_snapshots", new_callable=AsyncMock) as mock_persist:
            manager.start(persist_interval=0.1, health_check_interval=100)

            # Wait enough time for the task to run (just over interval)
            await asyncio.sleep(0.15)
            await manager.stop()

            mock_persist.assert_called()

    @pytest.mark.asyncio
    async def test_health_check_called(self) -> None:
        """Test that health_check is called periodically."""
        manager = BackgroundTaskManager()

        with patch.object(manager, "_health_check", new_callable=AsyncMock) as mock_health:
            manager.start(persist_interval=100, health_check_interval=0.1)

            # Wait enough time for the task to run (just over interval)
            await asyncio.sleep(0.15)
            await manager.stop()

            mock_health.assert_called()

    @pytest.mark.asyncio
    async def test_periodic_task_handles_exception(self) -> None:
        """Test that exceptions in periodic tasks don't stop the manager."""
        manager = BackgroundTaskManager()

        call_count = 0

        async def failing_task():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Test error")

        with patch.object(manager, "_persist_snapshots", failing_task):
            with patch.object(manager, "_health_check", AsyncMock()):
                manager.start(persist_interval=0.1, health_check_interval=100)
                # Wait for multiple task executions (3 intervals: 0.3s total)
                await asyncio.sleep(0.35)
                await manager.stop()

        # Should have been called multiple times despite exceptions
        assert call_count >= 2


class TestPersistSnapshots:
    """Tests for _persist_snapshots method."""

    @pytest.mark.asyncio
    async def test_persist_snapshots_with_no_sessions(self) -> None:
        """Test persist_snapshots with no active sessions."""
        manager = BackgroundTaskManager()

        mock_session_manager = MagicMock()
        mock_session_manager.get_sessions_needing_persistence.return_value = []

        with patch(
            "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
        ):
            # Should not raise
            await manager._persist_snapshots()

    @pytest.mark.asyncio
    async def test_persist_snapshots_filters_by_should_persist(self) -> None:
        """Test that only sessions that should persist are processed."""
        manager = BackgroundTaskManager()

        mock_session_manager = MagicMock()
        # Only 'run-1' needs persistence (via public API)
        mock_session_manager.get_sessions_needing_persistence.return_value = ["run-1"]

        mock_service = MagicMock()
        mock_service.persist_snapshots = AsyncMock(return_value=5)

        mock_db_session = AsyncMock()

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.infra.database.get_session_context") as mock_get_session,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_db_session
            with patch(
                "squant.services.paper_trading.PaperTradingService", return_value=mock_service
            ):
                await manager._persist_snapshots()

        # Only run-1 should be persisted
        mock_service.persist_snapshots.assert_called_once_with("run-1")

    @pytest.mark.asyncio
    async def test_persist_snapshots_handles_exception(self) -> None:
        """Test that exceptions during persist_snapshots are handled."""
        manager = BackgroundTaskManager()

        mock_session_manager = MagicMock()
        mock_session_manager.get_sessions_needing_persistence.return_value = ["run-1", "run-2"]

        mock_service = MagicMock()
        # First call raises exception, second succeeds
        mock_service.persist_snapshots = AsyncMock(side_effect=[Exception("Database error"), 3])

        mock_db_session = AsyncMock()

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.infra.database.get_session_context") as mock_get_session,
            patch("squant.services.background.logger") as mock_logger,
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_db_session
            with patch(
                "squant.services.paper_trading.PaperTradingService", return_value=mock_service
            ):
                await manager._persist_snapshots()

        # Should have tried both runs
        assert mock_service.persist_snapshots.call_count == 2
        # Should have logged the error
        mock_logger.error.assert_called_once()
        assert "run-1" in mock_logger.error.call_args[0][0]


class TestHealthCheck:
    """Tests for _health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_skips_cleanup_when_no_unhealthy(self) -> None:
        """Test that health_check skips cleanup when no unhealthy sessions."""
        manager = BackgroundTaskManager()

        mock_session_manager = AsyncMock()
        mock_session_manager.check_health = AsyncMock(return_value=[])
        mock_session_manager.cleanup_stale_sessions = AsyncMock(return_value=[])

        mock_settings = MagicMock()
        mock_settings.paper_session_timeout_seconds = 300

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
        ):
            await manager._health_check()

        # No unhealthy sessions means cleanup is not called (early return)
        mock_session_manager.cleanup_stale_sessions.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_check_calls_cleanup_for_unhealthy(self) -> None:
        """Test that health_check calls cleanup when unhealthy sessions exist."""
        manager = BackgroundTaskManager()

        unhealthy_id = uuid4()
        mock_session_manager = AsyncMock()
        mock_session_manager.check_health = AsyncMock(return_value=[unhealthy_id])
        mock_session_manager.cleanup_stale_sessions = AsyncMock(return_value=[unhealthy_id])
        mock_session_manager.get = MagicMock(return_value=None)

        mock_settings = MagicMock()
        mock_settings.paper_session_timeout_seconds = 300

        mock_service = AsyncMock()
        mock_db_session = AsyncMock()

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.infra.database.get_session_context") as mock_ctx,
            patch(
                "squant.services.paper_trading.PaperTradingService",
                return_value=mock_service,
            ),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await manager._health_check()

        mock_session_manager.cleanup_stale_sessions.assert_called_once_with(300)

    @pytest.mark.asyncio
    async def test_health_check_logs_cleanup_count(self) -> None:
        """Test that health_check logs when sessions are cleaned up."""
        manager = BackgroundTaskManager()

        cleaned_ids = [uuid4(), uuid4()]
        mock_session_manager = AsyncMock()
        mock_session_manager.check_health = AsyncMock(return_value=cleaned_ids)
        mock_session_manager.cleanup_stale_sessions = AsyncMock(return_value=cleaned_ids)
        mock_session_manager.get = MagicMock(return_value=None)

        mock_settings = MagicMock()
        mock_settings.paper_session_timeout_seconds = 300

        mock_service = AsyncMock()
        mock_db_session = AsyncMock()

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.infra.database.get_session_context") as mock_ctx,
            patch(
                "squant.services.paper_trading.PaperTradingService",
                return_value=mock_service,
            ),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("squant.services.background.logger") as mock_logger:
                await manager._health_check()

                mock_logger.warning.assert_called_once()
                assert "2" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_health_check_captures_engine_state(self) -> None:
        """Test that health_check captures engine state snapshots before cleanup."""
        manager = BackgroundTaskManager()

        unhealthy_id = uuid4()
        mock_engine = MagicMock()
        mock_engine.get_state_snapshot.return_value = {
            "cash": "10000",
            "equity": "10500",
            "total_fees": "50",
            "bar_count": 100,
            "realized_pnl": "500",
            "unrealized_pnl": "0",
            "positions": {},
            "trades": [],
            "completed_orders_count": 5,
            "trades_count": 3,
            "logs": [],
        }

        mock_session_manager = AsyncMock()
        mock_session_manager.check_health = AsyncMock(return_value=[unhealthy_id])
        mock_session_manager.cleanup_stale_sessions = AsyncMock(return_value=[unhealthy_id])
        mock_session_manager.get = MagicMock(return_value=mock_engine)

        mock_settings = MagicMock()
        mock_settings.paper_session_timeout_seconds = 300

        mock_service = AsyncMock()
        mock_db_session = AsyncMock()

        with (
            patch(
                "squant.engine.paper.manager.get_session_manager", return_value=mock_session_manager
            ),
            patch("squant.config.get_settings", return_value=mock_settings),
            patch("squant.infra.database.get_session_context") as mock_ctx,
            patch(
                "squant.services.paper_trading.PaperTradingService",
                return_value=mock_service,
            ),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await manager._health_check()

        # Should have captured engine state
        mock_engine.get_state_snapshot.assert_called_once()
        # Should have passed result to mark_session_interrupted
        mock_service.mark_session_interrupted.assert_called_once()
        call_kwargs = mock_service.mark_session_interrupted.call_args
        assert call_kwargs[1].get("result") or (len(call_kwargs[0]) > 2 and call_kwargs[0][2])
