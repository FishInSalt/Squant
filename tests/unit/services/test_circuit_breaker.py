"""Unit tests for circuit breaker service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squant.services.circuit_breaker import (
    CIRCUIT_BREAKER_STATE_KEY,
    CircuitBreakerAlreadyActiveError,
    CircuitBreakerCooldownError,
    CircuitBreakerOperationInProgressError,
    CircuitBreakerService,
    CircuitBreakerState,
)


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState dataclass."""

    def test_default_state(self) -> None:
        """Test default state is inactive."""
        state = CircuitBreakerState()
        assert state.is_active is False
        assert state.triggered_at is None
        assert state.trigger_type is None
        assert state.trigger_reason is None
        assert state.cooldown_until is None

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(UTC)
        state = CircuitBreakerState(
            is_active=True,
            triggered_at=now,
            trigger_type="manual",
            trigger_reason="Test reason",
            cooldown_until=now,
        )
        result = state.to_dict()
        assert result["is_active"] is True
        assert result["triggered_at"] == now.isoformat()
        assert result["trigger_type"] == "manual"
        assert result["trigger_reason"] == "Test reason"
        assert result["cooldown_until"] == now.isoformat()

    def test_to_dict_with_none_values(self) -> None:
        """Test conversion with None values."""
        state = CircuitBreakerState()
        result = state.to_dict()
        assert result["triggered_at"] is None
        assert result["cooldown_until"] is None

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(UTC)
        data = {
            "is_active": True,
            "triggered_at": now.isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test",
            "cooldown_until": now.isoformat(),
        }
        state = CircuitBreakerState.from_dict(data)
        assert state.is_active is True
        assert state.trigger_type == "manual"
        assert state.trigger_reason == "Test"

    def test_from_dict_empty(self) -> None:
        """Test creation from empty dictionary."""
        state = CircuitBreakerState.from_dict({})
        assert state.is_active is False
        assert state.triggered_at is None


class TestCircuitBreakerService:
    """Tests for CircuitBreakerService."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create mock Redis client."""
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock()
        redis.eval = AsyncMock()  # For Lua script in _release_lock
        return redis

    @pytest.fixture
    def service(
        self, mock_session: MagicMock, mock_redis: MagicMock
    ) -> CircuitBreakerService:
        """Create service with mocks."""
        return CircuitBreakerService(mock_session, mock_redis)

    @pytest.mark.asyncio
    async def test_get_state_empty(self, service: CircuitBreakerService) -> None:
        """Test getting state when Redis is empty."""
        state = await service.get_state()
        assert state.is_active is False
        service.redis.get.assert_called_once_with(CIRCUIT_BREAKER_STATE_KEY)

    @pytest.mark.asyncio
    async def test_get_state_with_data(self, service: CircuitBreakerService) -> None:
        """Test getting state with existing data."""
        now = datetime.now(UTC)
        state_data = {
            "is_active": True,
            "triggered_at": now.isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test",
            "cooldown_until": now.isoformat(),
        }
        service.redis.get = AsyncMock(return_value=json.dumps(state_data))

        state = await service.get_state()

        assert state.is_active is True
        assert state.trigger_type == "manual"

    @pytest.mark.asyncio
    async def test_get_state_invalid_json(
        self, service: CircuitBreakerService
    ) -> None:
        """Test getting state with invalid JSON."""
        service.redis.get = AsyncMock(return_value="invalid json")

        state = await service.get_state()

        assert state.is_active is False

    @pytest.mark.asyncio
    async def test_trigger_success(self, service: CircuitBreakerService) -> None:
        """Test successful circuit breaker trigger."""
        with patch(
            "squant.services.circuit_breaker.get_live_session_manager"
        ) as mock_live_mgr:
            mock_live = MagicMock()
            mock_live.session_count = 2
            mock_live.stop_all = AsyncMock()
            mock_live_mgr.return_value = mock_live

            with patch(
                "squant.services.circuit_breaker.get_session_manager"
            ) as mock_paper_mgr:
                mock_paper = MagicMock()
                mock_paper.session_count = 3
                mock_paper.stop_all = AsyncMock()
                mock_paper_mgr.return_value = mock_paper

                result = await service.trigger(
                    reason="Test trigger",
                    cooldown_minutes=30,
                )

                assert result["status"] == "triggered"
                assert result["live_sessions_stopped"] == 2
                assert result["paper_sessions_stopped"] == 3
                assert result["errors"] == []

                mock_live.stop_all.assert_called_once()
                mock_paper.stop_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_already_active(
        self, service: CircuitBreakerService
    ) -> None:
        """Test trigger when already active."""
        state_data = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Previous trigger",
            "cooldown_until": None,
        }
        service.redis.get = AsyncMock(return_value=json.dumps(state_data))

        with pytest.raises(CircuitBreakerAlreadyActiveError):
            await service.trigger(reason="Test")

    @pytest.mark.asyncio
    async def test_trigger_lock_conflict(
        self, service: CircuitBreakerService
    ) -> None:
        """Test trigger when lock cannot be acquired."""
        service.redis.set = AsyncMock(return_value=False)  # Lock not acquired

        with pytest.raises(CircuitBreakerOperationInProgressError):
            await service.trigger(reason="Test")

    @pytest.mark.asyncio
    async def test_trigger_with_errors(
        self, service: CircuitBreakerService
    ) -> None:
        """Test trigger when sessions fail to stop."""
        with patch(
            "squant.services.circuit_breaker.get_live_session_manager"
        ) as mock_live_mgr:
            mock_live = MagicMock()
            mock_live.session_count = 1
            mock_live.stop_all = AsyncMock(side_effect=Exception("Live error"))
            mock_live_mgr.return_value = mock_live

            with patch(
                "squant.services.circuit_breaker.get_session_manager"
            ) as mock_paper_mgr:
                mock_paper = MagicMock()
                mock_paper.session_count = 1
                mock_paper.stop_all = AsyncMock()
                mock_paper_mgr.return_value = mock_paper

                result = await service.trigger(reason="Test")

                assert len(result["errors"]) == 1
                assert "Live sessions" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_close_all_positions(
        self, service: CircuitBreakerService
    ) -> None:
        """Test close all positions."""
        from uuid import uuid4

        test_run_id = str(uuid4())

        with patch(
            "squant.services.circuit_breaker.get_live_session_manager"
        ) as mock_live_mgr:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.emergency_close = AsyncMock(
                return_value={"positions_closed": 2, "orders_cancelled": 3, "errors": []}
            )

            mock_live = MagicMock()
            mock_live.list_sessions.return_value = [{"run_id": test_run_id}]
            mock_live.get.return_value = mock_engine
            mock_live_mgr.return_value = mock_live

            with patch(
                "squant.services.circuit_breaker.get_session_manager"
            ) as mock_paper_mgr:
                mock_paper = MagicMock()
                mock_paper.session_count = 2
                mock_paper.stop_all = AsyncMock()
                mock_paper_mgr.return_value = mock_paper

                result = await service.close_all_positions()

                assert result["live_positions_closed"] == 2
                assert result["orders_cancelled"] == 3
                assert result["paper_positions_reset"] == 2

    @pytest.mark.asyncio
    async def test_close_all_positions_with_errors(
        self, service: CircuitBreakerService
    ) -> None:
        """Test close all positions with errors."""
        from uuid import uuid4

        test_run_id = str(uuid4())

        with patch(
            "squant.services.circuit_breaker.get_live_session_manager"
        ) as mock_live_mgr:
            mock_engine = MagicMock()
            mock_engine.is_running = True
            mock_engine.emergency_close = AsyncMock(
                side_effect=Exception("Close failed")
            )

            mock_live = MagicMock()
            mock_live.list_sessions.return_value = [{"run_id": test_run_id}]
            mock_live.get.return_value = mock_engine
            mock_live_mgr.return_value = mock_live

            with patch(
                "squant.services.circuit_breaker.get_session_manager"
            ) as mock_paper_mgr:
                mock_paper = MagicMock()
                mock_paper.session_count = 0
                mock_paper.stop_all = AsyncMock()
                mock_paper_mgr.return_value = mock_paper

                result = await service.close_all_positions()

                assert len(result["errors"]) == 1
                assert "Close failed" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_reset_not_active(self, service: CircuitBreakerService) -> None:
        """Test reset when not active."""
        result = await service.reset()
        assert result["status"] == "not_active"

    @pytest.mark.asyncio
    async def test_reset_success(self, service: CircuitBreakerService) -> None:
        """Test successful reset after cooldown."""
        past = datetime(2020, 1, 1, tzinfo=UTC)
        state_data = {
            "is_active": True,
            "triggered_at": past.isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test",
            "cooldown_until": past.isoformat(),
        }
        service.redis.get = AsyncMock(return_value=json.dumps(state_data))

        result = await service.reset()

        assert result["status"] == "reset"
        service.redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_reset_in_cooldown(self, service: CircuitBreakerService) -> None:
        """Test reset during cooldown period."""
        from datetime import timedelta

        future = datetime.now(UTC) + timedelta(hours=1)
        state_data = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test",
            "cooldown_until": future.isoformat(),
        }
        service.redis.get = AsyncMock(return_value=json.dumps(state_data))

        with pytest.raises(CircuitBreakerCooldownError) as exc_info:
            await service.reset()

        assert exc_info.value.remaining_minutes > 0

    @pytest.mark.asyncio
    async def test_reset_force(self, service: CircuitBreakerService) -> None:
        """Test forced reset during cooldown."""
        from datetime import timedelta

        future = datetime.now(UTC) + timedelta(hours=1)
        state_data = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test",
            "cooldown_until": future.isoformat(),
        }
        service.redis.get = AsyncMock(return_value=json.dumps(state_data))

        result = await service.reset(force=True)

        assert result["status"] == "reset"

    @pytest.mark.asyncio
    async def test_get_status(self, service: CircuitBreakerService) -> None:
        """Test getting status."""
        with patch(
            "squant.services.circuit_breaker.get_live_session_manager"
        ) as mock_live_mgr:
            mock_live = MagicMock()
            mock_live.session_count = 5
            mock_live_mgr.return_value = mock_live

            with patch(
                "squant.services.circuit_breaker.get_session_manager"
            ) as mock_paper_mgr:
                mock_paper = MagicMock()
                mock_paper.session_count = 3
                mock_paper_mgr.return_value = mock_paper

                status = await service.get_status()

                assert status["is_active"] is False
                assert status["active_live_sessions"] == 5
                assert status["active_paper_sessions"] == 3


class TestCircuitBreakerErrors:
    """Tests for circuit breaker error classes."""

    def test_already_active_error(self) -> None:
        """Test CircuitBreakerAlreadyActiveError."""
        error = CircuitBreakerAlreadyActiveError()
        assert "already active" in str(error)

    def test_cooldown_error(self) -> None:
        """Test CircuitBreakerCooldownError."""
        error = CircuitBreakerCooldownError(30.5)
        assert error.remaining_minutes == 30.5
        assert "30.5" in str(error)
