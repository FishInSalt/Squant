"""Session manager for live trading engines.

Manages all active live trading sessions and handles candle distribution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from squant.engine.live.engine import LiveTradingEngine
    from squant.infra.exchange.okx.ws_types import WSCandle, WSOrderUpdate

logger = logging.getLogger(__name__)


class LiveSessionManager:
    """Manages all active live trading sessions.

    This is a singleton that:
    - Tracks all running live trading engines
    - Routes candle data to relevant engines
    - Routes order updates to engines
    - Handles graceful shutdown of all sessions
    """

    def __init__(self) -> None:
        """Initialize session manager."""
        # Active sessions: run_id -> engine
        self._sessions: dict[UUID, LiveTradingEngine] = {}

        # Subscription tracking: (symbol, timeframe) -> set of run_ids
        self._subscriptions: dict[tuple[str, str], set[UUID]] = {}

        # Order subscription tracking: symbol -> set of run_ids
        self._order_subscriptions: dict[str, set[UUID]] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    @property
    def session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._sessions)

    async def register(self, engine: LiveTradingEngine) -> None:
        """Register a new live trading engine.

        Args:
            engine: Live trading engine to register.
        """
        async with self._lock:
            run_id = engine.run_id
            key = (engine.symbol, engine.timeframe)

            if run_id in self._sessions:
                logger.warning(f"Engine {run_id} already registered")
                return

            self._sessions[run_id] = engine

            # Track candle subscription
            if key not in self._subscriptions:
                self._subscriptions[key] = set()
            self._subscriptions[key].add(run_id)

            # Track order subscription
            if engine.symbol not in self._order_subscriptions:
                self._order_subscriptions[engine.symbol] = set()
            self._order_subscriptions[engine.symbol].add(run_id)

            logger.info(
                f"Registered live engine {run_id} for {engine.symbol}:{engine.timeframe}, "
                f"total sessions: {len(self._sessions)}"
            )

    async def unregister(self, run_id: UUID) -> None:
        """Unregister a live trading engine.

        Args:
            run_id: Run ID of the engine to unregister.
        """
        async with self._lock:
            engine = self._sessions.pop(run_id, None)
            if engine is None:
                logger.warning(f"Engine {run_id} not found for unregistration")
                return

            # Remove from candle subscription tracking
            key = (engine.symbol, engine.timeframe)
            if key in self._subscriptions:
                self._subscriptions[key].discard(run_id)
                if not self._subscriptions[key]:
                    del self._subscriptions[key]

            # Remove from order subscription tracking
            if engine.symbol in self._order_subscriptions:
                self._order_subscriptions[engine.symbol].discard(run_id)
                if not self._order_subscriptions[engine.symbol]:
                    del self._order_subscriptions[engine.symbol]

            logger.info(
                f"Unregistered live engine {run_id}, remaining sessions: {len(self._sessions)}"
            )

    def get(self, run_id: UUID) -> LiveTradingEngine | None:
        """Get a live trading engine by run ID.

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
                except Exception as e:
                    logger.exception(f"Error dispatching candle to live engine {run_id}: {e}")

    def dispatch_order_update(self, update: WSOrderUpdate) -> None:
        """Dispatch an order update to relevant engines.

        Args:
            update: WebSocket order update data.
        """
        symbol = update.symbol

        # Get subscribed run IDs (copy to avoid modification during iteration)
        run_ids = self._order_subscriptions.get(symbol, set()).copy()

        if not run_ids:
            return

        # Dispatch to each engine
        for run_id in run_ids:
            engine = self._sessions.get(run_id)
            if engine and engine.is_running:
                try:
                    engine.on_order_update(update)
                except Exception as e:
                    logger.exception(f"Error dispatching order update to live engine {run_id}: {e}")

    async def stop_all(self, reason: str = "shutdown") -> None:
        """Stop all active sessions.

        Args:
            reason: Reason for stopping (for logging/error message).
        """
        logger.info(f"Stopping all live trading sessions: {reason}")

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
                    logger.exception(f"Error stopping live engine {run_id}: {e}")
            await self.unregister(run_id)

        logger.info(f"Stopped {len(run_ids)} live trading sessions")

    def get_subscribed_symbols(self) -> list[tuple[str, str]]:
        """Get list of (symbol, timeframe) pairs with active subscriptions.

        Returns:
            List of (symbol, timeframe) tuples.
        """
        return list(self._subscriptions.keys())

    def get_order_subscribed_symbols(self) -> list[str]:
        """Get list of symbols with order update subscriptions.

        Returns:
            List of symbol strings.
        """
        return list(self._order_subscriptions.keys())

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

    async def cleanup_stale_sessions(
        self, timeout_seconds: int = 300
    ) -> tuple[list[UUID], list[tuple[str, str]], list[str]]:
        """Stop and unregister stale sessions.

        Args:
            timeout_seconds: Maximum seconds since last activity.

        Returns:
            Tuple of (cleaned run_ids, candle keys to unsubscribe,
            ticker symbols to unsubscribe).
        """
        unhealthy = await self.check_health(timeout_seconds)
        cleaned: list[UUID] = []
        keys_to_unsub: list[tuple[str, str]] = []
        for run_id in unhealthy:
            engine = self._sessions.get(run_id)
            if engine:
                logger.warning(f"Cleaning up stale live session {run_id}")
                key = (engine.symbol, engine.timeframe)
                await engine.stop(error="Session timeout: no activity detected")
                await self.unregister(run_id)
                cleaned.append(run_id)
                # Check if this was the last subscriber for this key
                if key not in self._subscriptions:
                    keys_to_unsub.append(key)
        # Live sessions don't use ticker subscriptions
        return cleaned, keys_to_unsub, []


# Global live session manager instance
_live_session_manager: LiveSessionManager | None = None


def get_live_session_manager() -> LiveSessionManager:
    """Get the global live session manager instance.

    Returns:
        LiveSessionManager singleton.
    """
    global _live_session_manager
    if _live_session_manager is None:
        _live_session_manager = LiveSessionManager()
    return _live_session_manager
