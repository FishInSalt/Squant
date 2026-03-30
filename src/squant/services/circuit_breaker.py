"""Circuit breaker service for emergency trading halt.

Provides global circuit breaker functionality to stop all trading
and optionally close all positions.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from squant.config import get_settings
from squant.engine.live.manager import get_live_session_manager
from squant.engine.paper.manager import get_session_manager
from squant.infra.repository import BaseRepository
from squant.models.enums import CircuitBreakerTriggerType
from squant.models.risk import CircuitBreakerEvent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Redis keys for circuit breaker state
CIRCUIT_BREAKER_STATE_KEY = "squant:circuit_breaker:state"
CIRCUIT_BREAKER_LOCK_KEY = "squant:circuit_breaker:lock"


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""

    pass


class CircuitBreakerAlreadyActiveError(CircuitBreakerError):
    """Circuit breaker is already active."""

    def __init__(self) -> None:
        super().__init__("Circuit breaker is already active")


class CircuitBreakerOperationInProgressError(CircuitBreakerError):
    """Another circuit breaker operation is in progress."""

    def __init__(self) -> None:
        super().__init__("Another circuit breaker operation is in progress")


class CircuitBreakerNotActiveError(CircuitBreakerError):
    """Circuit breaker is not active."""

    def __init__(self) -> None:
        super().__init__("Circuit breaker is not active")


class CircuitBreakerCooldownError(CircuitBreakerError):
    """Circuit breaker is in cooldown period."""

    def __init__(self, remaining_minutes: float) -> None:
        self.remaining_minutes = remaining_minutes
        super().__init__(
            f"Circuit breaker is in cooldown, {remaining_minutes:.1f} minutes remaining"
        )


@dataclass
class CircuitBreakerState:
    """Circuit breaker state stored in Redis."""

    is_active: bool = False
    triggered_at: datetime | None = None
    trigger_type: str | None = None
    trigger_reason: str | None = None
    cooldown_until: datetime | None = None
    trigger_session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "is_active": self.is_active,
            "triggered_at": (self.triggered_at.isoformat() if self.triggered_at else None),
            "trigger_type": self.trigger_type,
            "trigger_reason": self.trigger_reason,
            "cooldown_until": (self.cooldown_until.isoformat() if self.cooldown_until else None),
            "trigger_session_id": self.trigger_session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerState:
        """Create from Redis data."""
        triggered_at = None
        if data.get("triggered_at"):
            triggered_at = datetime.fromisoformat(data["triggered_at"])
            # Ensure timezone awareness (default to UTC if missing)
            if triggered_at.tzinfo is None:
                triggered_at = triggered_at.replace(tzinfo=UTC)

        cooldown_until = None
        if data.get("cooldown_until"):
            cooldown_until = datetime.fromisoformat(data["cooldown_until"])
            # Ensure timezone awareness (default to UTC if missing)
            if cooldown_until.tzinfo is None:
                cooldown_until = cooldown_until.replace(tzinfo=UTC)

        return cls(
            is_active=data.get("is_active", False),
            triggered_at=triggered_at,
            trigger_type=data.get("trigger_type"),
            trigger_reason=data.get("trigger_reason"),
            cooldown_until=cooldown_until,
            trigger_session_id=data.get("trigger_session_id"),
        )


class CircuitBreakerEventRepository(BaseRepository[CircuitBreakerEvent]):
    """Repository for CircuitBreakerEvent model."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CircuitBreakerEvent, session)


class CircuitBreakerService:
    """Service for global circuit breaker operations.

    Provides functionality to:
    - Trigger circuit breaker to stop all trading (RSK-010)
    - Close all open positions (RSK-011)
    - Track circuit breaker events for audit
    """

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        """Initialize circuit breaker service.

        Args:
            session: Database session.
            redis: Redis client.
        """
        self.session = session
        self.redis = redis
        self.event_repo = CircuitBreakerEventRepository(session)
        self._settings = get_settings()

    async def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state from Redis.

        Returns:
            Current circuit breaker state.
        """
        data = await self.redis.get(CIRCUIT_BREAKER_STATE_KEY)
        if data is None:
            return CircuitBreakerState()

        try:
            state_dict = json.loads(data)
            return CircuitBreakerState.from_dict(state_dict)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Invalid circuit breaker state in Redis: {e}")
            return CircuitBreakerState()

    async def _save_state(self, state: CircuitBreakerState) -> None:
        """Save circuit breaker state to Redis.

        Args:
            state: State to save.
        """
        await self.redis.set(
            CIRCUIT_BREAKER_STATE_KEY,
            json.dumps(state.to_dict()),
        )

    async def _release_lock(self, lock_id: str) -> None:
        """Release lock only if we own it.

        Uses Lua script for atomic check-and-delete.

        Args:
            lock_id: The unique lock identifier we used when acquiring.
        """
        # Lua script: only delete if the value matches our lock_id
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(lua_script, 1, CIRCUIT_BREAKER_LOCK_KEY, lock_id)

    async def trigger(
        self,
        reason: str,
        trigger_type: CircuitBreakerTriggerType = CircuitBreakerTriggerType.MANUAL,
        cooldown_minutes: int | None = None,
        trigger_source: str = "api",
        trigger_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger the circuit breaker to stop all trading.

        This is the main emergency stop function (RSK-010).

        Args:
            reason: Reason for triggering.
            trigger_type: Type of trigger (manual/auto).
            cooldown_minutes: Optional cooldown period.
            trigger_source: Source of the trigger (api/rule:xxx).
            trigger_session_id: Session that triggered the breaker (for auto triggers).

        Returns:
            Dict with trigger results.

        Raises:
            CircuitBreakerAlreadyActiveError: If already active.
            CircuitBreakerOperationInProgressError: If another operation is in progress.
        """
        # Generate unique lock identifier for this operation
        lock_id = str(uuid.uuid4())

        # Acquire distributed lock first (before checking state)
        lock_acquired = await self.redis.set(
            CIRCUIT_BREAKER_LOCK_KEY,
            lock_id,
            nx=True,
            ex=30,  # 30 second lock timeout
        )
        if not lock_acquired:
            # Another process is already handling an operation
            raise CircuitBreakerOperationInProgressError()

        try:
            # Double-check state after acquiring lock
            state = await self.get_state()
            if state.is_active:
                raise CircuitBreakerAlreadyActiveError()

            now = datetime.now(UTC)
            cooldown = cooldown_minutes or self._settings.circuit_breaker_cooldown_minutes
            cooldown_until = datetime.fromtimestamp(now.timestamp() + cooldown * 60, tz=UTC)

            # Stop all sessions
            live_manager = get_live_session_manager()
            paper_manager = get_session_manager()

            live_count = live_manager.session_count
            paper_count = paper_manager.session_count

            errors: list[str] = []

            # Stop live sessions
            try:
                await live_manager.stop_all(reason=f"Circuit breaker: {reason}")
            except Exception as e:
                logger.exception("Error stopping live sessions")
                errors.append(f"Live sessions: {e}")

            # Stop paper sessions
            try:
                await paper_manager.stop_all(reason=f"Circuit breaker: {reason}")
            except Exception as e:
                logger.exception("Error stopping paper sessions")
                errors.append(f"Paper sessions: {e}")

            # Update state
            new_state = CircuitBreakerState(
                is_active=True,
                triggered_at=now,
                trigger_type=trigger_type.value,
                trigger_reason=reason,
                cooldown_until=cooldown_until,
                trigger_session_id=trigger_session_id,
            )
            await self._save_state(new_state)

            # Record event to database
            await self.event_repo.create(
                time=now,
                trigger_type=trigger_type.value,
                trigger_source=trigger_source,
                reason=reason,
                details={
                    "cooldown_minutes": cooldown,
                    "errors": errors,
                },
                sessions_stopped=live_count + paper_count,
                positions_closed=0,  # Positions not automatically closed
            )
            await self.session.commit()

            # Log notification (RSK-013)
            logger.critical(
                f"CIRCUIT BREAKER TRIGGERED: {reason} | "
                f"Type: {trigger_type.value} | "
                f"Live sessions stopped: {live_count} | "
                f"Paper sessions stopped: {paper_count} | "
                f"Cooldown until: {cooldown_until.isoformat()}"
            )

            return {
                "status": "triggered",
                "triggered_at": now.isoformat(),
                "live_sessions_stopped": live_count,
                "paper_sessions_stopped": paper_count,
                "errors": errors,
            }

        finally:
            # Release lock only if we still own it
            await self._release_lock(lock_id)

    async def close_all_positions(self, reason: str = "Manual close all") -> dict[str, Any]:
        """Close all open positions across all sessions (RSK-011).

        Performs emergency close on all live sessions and resets paper sessions.

        Args:
            reason: Reason for closing positions.

        Returns:
            Dict with close operation results.
        """
        live_manager = get_live_session_manager()
        paper_manager = get_session_manager()

        results: dict[str, Any] = {
            "live_positions_closed": 0,
            "paper_positions_reset": 0,
            "orders_cancelled": 0,
            "errors": [],
        }

        # Close live positions
        for session_info in live_manager.list_sessions():
            run_id = session_info.get("run_id")
            if not run_id:
                continue

            from uuid import UUID

            engine = live_manager.get(UUID(run_id))
            if engine and engine.is_running:
                try:
                    close_result = await engine.emergency_close()
                    results["live_positions_closed"] += close_result.get("positions_closed", 0)
                    results["orders_cancelled"] += close_result.get("orders_cancelled", 0)
                    if close_result.get("errors"):
                        results["errors"].extend(
                            [{"run_id": run_id, "error": e} for e in close_result["errors"]]
                        )
                except Exception as e:
                    logger.exception(f"Error closing positions for {run_id}")
                    results["errors"].append({"run_id": run_id, "error": str(e)})

        # Stop paper sessions (no real positions to close)
        paper_count = paper_manager.session_count
        try:
            await paper_manager.stop_all(reason=reason)
            results["paper_positions_reset"] = paper_count
        except Exception as e:
            logger.exception("Error stopping paper sessions")
            results["errors"].append({"type": "paper", "error": str(e)})

        # Log notification (RSK-013)
        logger.critical(
            f"CLOSE ALL POSITIONS: {reason} | "
            f"Live positions closed: {results['live_positions_closed']} | "
            f"Orders cancelled: {results['orders_cancelled']} | "
            f"Paper sessions reset: {results['paper_positions_reset']}"
        )

        return results

    async def reset(self, force: bool = False) -> dict[str, Any]:
        """Reset the circuit breaker.

        Args:
            force: If True, ignore cooldown period.

        Returns:
            Dict with reset status.

        Raises:
            CircuitBreakerNotActiveError: If not active.
            CircuitBreakerCooldownError: If in cooldown and not forced.
            CircuitBreakerOperationInProgressError: If another operation is in progress.
        """
        # Acquire distributed lock to prevent TOCTOU race with concurrent
        # trigger() or reset() calls (ISSUE-109 fix)
        lock_id = str(uuid.uuid4())
        lock_acquired = await self.redis.set(
            CIRCUIT_BREAKER_LOCK_KEY,
            lock_id,
            nx=True,
            ex=30,
        )
        if not lock_acquired:
            raise CircuitBreakerOperationInProgressError()

        try:
            state = await self.get_state()

            if not state.is_active:
                raise CircuitBreakerNotActiveError()

            # Check cooldown unless forced
            if not force and state.cooldown_until:
                now = datetime.now(UTC)
                if now < state.cooldown_until:
                    remaining = (state.cooldown_until - now).total_seconds() / 60
                    raise CircuitBreakerCooldownError(remaining)

            # Reset state
            await self._save_state(CircuitBreakerState())

            logger.info("Circuit breaker reset")

            return {"status": "reset", "cooldown_remaining_minutes": None}
        finally:
            await self._release_lock(lock_id)

    async def get_status(self) -> dict[str, Any]:
        """Get current circuit breaker status.

        Returns:
            Dict with current status.
        """
        return await get_circuit_breaker_status(self.redis)


async def get_circuit_breaker_status(redis: Redis) -> dict[str, Any]:
    """Get current circuit breaker status (standalone function).

    This function does not require a database session, only Redis.

    Args:
        redis: Redis client.

    Returns:
        Dict with current status.
    """
    data = await redis.get(CIRCUIT_BREAKER_STATE_KEY)
    if data is None:
        state = CircuitBreakerState()
    else:
        try:
            state_dict = json.loads(data)
            state = CircuitBreakerState.from_dict(state_dict)
        except (json.JSONDecodeError, ValueError):
            state = CircuitBreakerState()

    live_manager = get_live_session_manager()
    paper_manager = get_session_manager()

    return {
        "is_active": state.is_active,
        "triggered_at": (state.triggered_at.isoformat() if state.triggered_at else None),
        "trigger_type": state.trigger_type,
        "trigger_reason": state.trigger_reason,
        "cooldown_until": (state.cooldown_until.isoformat() if state.cooldown_until else None),
        "active_live_sessions": live_manager.session_count,
        "active_paper_sessions": paper_manager.session_count,
    }
