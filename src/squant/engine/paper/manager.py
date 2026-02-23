"""Session manager for paper trading engines.

Manages all active paper trading sessions and handles candle distribution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from squant.engine.paper.engine import PaperTradingEngine
    from squant.infra.exchange.okx.ws_types import WSCandle

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages all active paper trading sessions.

    This is a singleton that:
    - Tracks all running paper trading engines
    - Routes candle data to relevant engines
    - Handles graceful shutdown of all sessions
    """

    def __init__(self) -> None:
        """Initialize session manager."""
        # Active sessions: run_id -> engine
        self._sessions: dict[UUID, PaperTradingEngine] = {}

        # Subscription tracking: (symbol, timeframe) -> set of run_ids
        self._subscriptions: dict[tuple[str, str], set[UUID]] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Consecutive dispatch error tracking per session (PP-H02)
        self._consecutive_errors: dict[UUID, int] = {}
        self._dispatch_error_threshold: int = 5

    @property
    def session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)

    async def register(self, engine: PaperTradingEngine) -> None:
        """Register a new paper trading engine.

        Args:
            engine: Paper trading engine to register.
        """
        async with self._lock:
            run_id = engine.run_id
            key = (engine.symbol, engine.timeframe)

            if run_id in self._sessions:
                logger.warning(f"Engine {run_id} already registered")
                return

            self._sessions[run_id] = engine

            # Track subscription
            if key not in self._subscriptions:
                self._subscriptions[key] = set()
            self._subscriptions[key].add(run_id)

            logger.info(
                f"Registered engine {run_id} for {engine.symbol}:{engine.timeframe}, "
                f"total sessions: {len(self._sessions)}"
            )

    async def unregister(self, run_id: UUID) -> None:
        """Unregister a paper trading engine.

        Args:
            run_id: Run ID of the engine to unregister.
        """
        async with self._lock:
            engine = self._sessions.pop(run_id, None)
            if engine is None:
                logger.warning(f"Engine {run_id} not found for unregistration")
                return

            # Remove from subscription tracking
            key = (engine.symbol, engine.timeframe)
            if key in self._subscriptions:
                self._subscriptions[key].discard(run_id)
                if not self._subscriptions[key]:
                    del self._subscriptions[key]

            # Clean up error tracking (PP-H02)
            self._consecutive_errors.pop(run_id, None)

            logger.info(f"Unregistered engine {run_id}, remaining sessions: {len(self._sessions)}")

    async def unregister_and_check_subscription(self, run_id: UUID) -> tuple[str, str] | None:
        """Unregister an engine and atomically check if subscription can be removed.

        This is an atomic operation that prevents race conditions between
        unregistering a session and checking if other sessions need the subscription.

        Args:
            run_id: Run ID of the engine to unregister.

        Returns:
            Tuple of (symbol, timeframe) if subscription should be removed,
            None if other sessions still need it or engine not found.
        """
        async with self._lock:
            engine = self._sessions.pop(run_id, None)
            if engine is None:
                logger.warning(f"Engine {run_id} not found for unregistration")
                return None

            key = (engine.symbol, engine.timeframe)

            # Remove from subscription tracking
            if key in self._subscriptions:
                self._subscriptions[key].discard(run_id)
                if not self._subscriptions[key]:
                    # No other sessions need this subscription
                    del self._subscriptions[key]
                    # Clean up error tracking (PP-H02)
                    self._consecutive_errors.pop(run_id, None)
                    logger.info(f"Unregistered engine {run_id}, subscription {key} can be removed")
                    return key
                else:
                    logger.info(
                        f"Unregistered engine {run_id}, "
                        f"subscription {key} still needed by {len(self._subscriptions[key])} sessions"
                    )
                    # Clean up error tracking (PP-H02)
                    self._consecutive_errors.pop(run_id, None)
                    return None

            # Clean up error tracking (PP-H02)
            self._consecutive_errors.pop(run_id, None)
            logger.info(f"Unregistered engine {run_id}, remaining sessions: {len(self._sessions)}")
            return None

    def get(self, run_id: UUID) -> PaperTradingEngine | None:
        """Get a paper trading engine by run ID.

        Args:
            run_id: Run ID to look up.

        Returns:
            Engine if found, None otherwise.
        """
        return self._sessions.get(run_id)

    def list_sessions(self) -> list[dict]:
        """List all active sessions.

        Returns:
            List of session state snapshots.
        """
        return [engine.get_state_snapshot() for engine in self._sessions.values()]

    async def dispatch_candle(self, candle: WSCandle) -> None:
        """Dispatch a candle to all subscribed engines.

        Args:
            candle: WebSocket candle data.
        """
        key = (candle.symbol, candle.timeframe)

        # Get subscribed run IDs (snapshot to avoid holding lock during processing)
        async with self._lock:
            run_ids = self._subscriptions.get(key, set()).copy()

        if not run_ids:
            return

        # Dispatch to each engine
        for run_id in run_ids:
            engine = self._sessions.get(run_id)
            if engine and engine.is_running:
                try:
                    await engine.process_candle(candle)
                    # Reset error counter on success (PP-H02)
                    self._consecutive_errors.pop(run_id, None)
                except Exception as e:
                    logger.exception(f"Error dispatching candle to engine {run_id}: {e}")
                    # Track consecutive errors and auto-stop if threshold reached (PP-H02)
                    error_count = self._consecutive_errors.get(run_id, 0) + 1
                    self._consecutive_errors[run_id] = error_count
                    if error_count >= self._dispatch_error_threshold:
                        logger.error(
                            f"Engine {run_id} reached {error_count} consecutive dispatch errors, "
                            f"stopping automatically"
                        )
                        try:
                            await engine.stop(
                                error=f"Auto-stopped: {error_count} consecutive dispatch errors"
                            )
                        except Exception as stop_error:
                            logger.exception(f"Error auto-stopping engine {run_id}: {stop_error}")
                        self._consecutive_errors.pop(run_id, None)

    async def stop_all(self, reason: str = "shutdown") -> None:
        """Stop all active sessions.

        Args:
            reason: Reason for stopping (for logging/error message).
        """
        logger.info(f"Stopping all paper trading sessions: {reason}")

        # Get all run IDs (snapshot)
        async with self._lock:
            run_ids = list(self._sessions.keys())

        # Stop each session and unregister
        for run_id in run_ids:
            engine = self._sessions.get(run_id)
            if engine and engine.is_running:
                try:
                    await engine.stop(error=f"Session stopped: {reason}")
                except Exception as e:
                    logger.exception(f"Error stopping engine {run_id}: {e}")
            await self.unregister(run_id)

        logger.info(f"Stopped {len(run_ids)} paper trading sessions")

    def get_subscribed_symbols(self) -> list[tuple[str, str]]:
        """Get list of (symbol, timeframe) pairs with active subscriptions.

        Returns:
            List of (symbol, timeframe) tuples.
        """
        return list(self._subscriptions.keys())

    def get_sessions_needing_persistence(self) -> list[UUID]:
        """Get run_ids of sessions that need snapshot persistence.

        Returns:
            List of run_ids with pending snapshots exceeding batch size.
        """
        return [
            run_id for run_id, engine in self._sessions.items() if engine.should_persist_snapshots()
        ]

    async def check_health(self, timeout_seconds: int = 300) -> list[UUID]:
        """Check health of all sessions and return unhealthy run_ids.

        Args:
            timeout_seconds: Maximum seconds since last activity.

        Returns:
            List of unhealthy session run_ids.
        """
        unhealthy: list[UUID] = []
        async with self._lock:
            for run_id, engine in self._sessions.items():
                if not engine.is_healthy(timeout_seconds):
                    unhealthy.append(run_id)
        return unhealthy

    async def cleanup_stale_sessions(self, timeout_seconds: int = 300) -> list[UUID]:
        """Stop and unregister stale sessions.

        Args:
            timeout_seconds: Maximum seconds since last activity.

        Returns:
            List of run_ids that were actually cleaned up.
        """
        unhealthy = await self.check_health(timeout_seconds)
        cleaned: list[UUID] = []
        for run_id in unhealthy:
            engine = self._sessions.get(run_id)
            if engine:
                logger.warning(f"Cleaning up stale session {run_id}")
                await engine.stop(error="Session timeout: no activity detected")
                await self.unregister(run_id)
                cleaned.append(run_id)
        return cleaned


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager instance.

    Returns:
        SessionManager singleton.
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
