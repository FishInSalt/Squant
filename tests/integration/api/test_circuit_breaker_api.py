"""Integration tests for Circuit Breaker API endpoints.

Tests the RSK-010 and RSK-011 acceptance criteria for emergency trading halt functionality.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestTriggerCircuitBreaker:
    """Test circuit breaker triggering (RSK-010)."""

    async def test_trigger_circuit_breaker_success(self, client):
        """Test RSK-010-1: Trigger circuit breaker to stop all trading."""
        mock_result = {
            "status": "triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
            "live_sessions_stopped": 2,
            "paper_sessions_stopped": 1,
            "errors": [],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request_data = {
                "reason": "Emergency stop - market volatility",
                "cooldown_minutes": 30,
            }
            response = await client.post("/api/v1/circuit-breaker/trigger", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "triggered"
        assert "triggered_at" in result
        assert result["live_sessions_stopped"] == 2
        assert result["paper_sessions_stopped"] == 1
        assert result["errors"] == []

    async def test_trigger_circuit_breaker_default_cooldown(self, client):
        """Test RSK-010-1: Trigger circuit breaker with default cooldown."""
        mock_result = {
            "status": "triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
            "live_sessions_stopped": 1,
            "paper_sessions_stopped": 0,
            "errors": [],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_trigger:
            request_data = {"reason": "Manual emergency stop"}
            response = await client.post("/api/v1/circuit-breaker/trigger", json=request_data)

            # Verify cooldown was not specified (service uses default)
            mock_trigger.assert_called_once()
            call_kwargs = mock_trigger.call_args.kwargs
            assert call_kwargs["reason"] == "Manual emergency stop"
            assert call_kwargs["cooldown_minutes"] is None

        assert response.status_code == 200

    async def test_trigger_circuit_breaker_already_active(self, client):
        """Test RSK-010-2: Cannot trigger if already active."""
        from squant.services.circuit_breaker import CircuitBreakerAlreadyActiveError

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            side_effect=CircuitBreakerAlreadyActiveError(),
        ):
            request_data = {"reason": "Emergency stop"}
            response = await client.post("/api/v1/circuit-breaker/trigger", json=request_data)

        assert response.status_code == 409
        assert "circuit breaker is already active" in response.json()["detail"].lower()

    async def test_trigger_circuit_breaker_operation_in_progress(self, client):
        """Test RSK-010-2: Cannot trigger if another operation in progress."""
        from squant.services.circuit_breaker import CircuitBreakerOperationInProgressError

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            side_effect=CircuitBreakerOperationInProgressError(),
        ):
            request_data = {"reason": "Emergency stop"}
            response = await client.post("/api/v1/circuit-breaker/trigger", json=request_data)

        assert response.status_code == 409
        assert "operation is in progress" in response.json()["detail"].lower()

    async def test_trigger_circuit_breaker_with_errors(self, client):
        """Test RSK-010-3: Show errors encountered during trigger."""
        mock_result = {
            "status": "triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
            "live_sessions_stopped": 1,
            "paper_sessions_stopped": 2,
            "errors": [
                "Failed to stop session abc123: Connection timeout",
                "Failed to stop session def456: Exchange unavailable",
            ],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request_data = {"reason": "Network issues"}
            response = await client.post("/api/v1/circuit-breaker/trigger", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "triggered"
        assert len(result["errors"]) == 2
        assert "Connection timeout" in result["errors"][0]

    async def test_trigger_circuit_breaker_validation(self, client):
        """Test request validation for trigger."""
        # Missing reason
        response = await client.post("/api/v1/circuit-breaker/trigger", json={})
        assert response.status_code == 422

        # Empty reason
        response = await client.post("/api/v1/circuit-breaker/trigger", json={"reason": ""})
        assert response.status_code == 422

        # Reason too long (> 256 chars)
        response = await client.post("/api/v1/circuit-breaker/trigger", json={"reason": "x" * 257})
        assert response.status_code == 422

        # Invalid cooldown (< 1)
        response = await client.post(
            "/api/v1/circuit-breaker/trigger",
            json={"reason": "Test", "cooldown_minutes": 0},
        )
        assert response.status_code == 422

        # Invalid cooldown (> 1440)
        response = await client.post(
            "/api/v1/circuit-breaker/trigger",
            json={"reason": "Test", "cooldown_minutes": 1441},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestCloseAllPositions:
    """Test emergency close all positions (RSK-011)."""

    async def test_close_all_positions_success(self, client):
        """Test RSK-011-1: Close all positions across all sessions."""
        mock_result = {
            "live_positions_closed": 3,
            "paper_positions_reset": 2,
            "orders_cancelled": 5,
            "errors": [],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.close_all_positions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request_data = {"reason": "Emergency close due to system failure"}
            response = await client.post(
                "/api/v1/circuit-breaker/close-all-positions", json=request_data
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["live_positions_closed"] == 3
        assert result["paper_positions_reset"] == 2
        assert result["orders_cancelled"] == 5
        assert result["errors"] == []

    async def test_close_all_positions_without_request_body(self, client):
        """Test RSK-011-1: Close all positions with default reason."""
        mock_result = {
            "live_positions_closed": 1,
            "paper_positions_reset": 1,
            "orders_cancelled": 2,
            "errors": [],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.close_all_positions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_close:
            # POST without request body
            response = await client.post("/api/v1/circuit-breaker/close-all-positions")

            # Verify default reason was used
            mock_close.assert_called_once()
            call_kwargs = mock_close.call_args.kwargs
            assert call_kwargs["reason"] == "Manual close all positions"

        assert response.status_code == 200

    async def test_close_all_positions_with_errors(self, client):
        """Test RSK-011-2: Show errors for positions that couldn't be closed."""
        mock_result = {
            "live_positions_closed": 2,
            "paper_positions_reset": 1,
            "orders_cancelled": 3,
            "errors": [
                {"session_id": "abc123", "error": "Exchange connection timeout"},
                {"session_id": "def456", "error": "Insufficient margin for close"},
            ],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.close_all_positions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request_data = {"reason": "Emergency close"}
            response = await client.post(
                "/api/v1/circuit-breaker/close-all-positions", json=request_data
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["errors"]) == 2
        assert result["errors"][0]["session_id"] == "abc123"
        assert "timeout" in result["errors"][0]["error"].lower()

    async def test_close_all_positions_partial_success(self, client):
        """Test RSK-011-2: Partial success when some positions fail to close."""
        mock_result = {
            "live_positions_closed": 1,  # Only 1 out of 3 closed
            "paper_positions_reset": 2,
            "orders_cancelled": 2,  # Only 2 out of 5 cancelled
            "errors": [
                {"session_id": "abc", "error": "Exchange API error"},
                {"session_id": "def", "error": "Order already filled"},
            ],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.close_all_positions",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            request_data = {"reason": "Partial close test"}
            response = await client.post(
                "/api/v1/circuit-breaker/close-all-positions", json=request_data
            )

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Even with errors, endpoint should return 200 with results
        assert result["live_positions_closed"] == 1
        assert result["orders_cancelled"] == 2
        assert len(result["errors"]) == 2


@pytest.mark.asyncio
class TestCircuitBreakerStatus:
    """Test circuit breaker status query."""

    async def test_get_status_active(self, client):
        """Test get status when circuit breaker is active."""
        mock_status = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Market volatility",
            "cooldown_until": datetime.now(UTC).isoformat(),
            "active_live_sessions": 0,
            "active_paper_sessions": 0,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get("/api/v1/circuit-breaker/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["is_active"] is True
        assert "triggered_at" in result
        assert result["trigger_type"] == "manual"
        assert result["trigger_reason"] == "Market volatility"
        assert "cooldown_until" in result
        assert result["active_live_sessions"] == 0
        assert result["active_paper_sessions"] == 0

    async def test_get_status_inactive(self, client):
        """Test get status when circuit breaker is inactive."""
        mock_status = {
            "is_active": False,
            "triggered_at": None,
            "trigger_type": None,
            "trigger_reason": None,
            "cooldown_until": None,
            "active_live_sessions": 2,
            "active_paper_sessions": 1,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get("/api/v1/circuit-breaker/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["is_active"] is False
        assert result["triggered_at"] is None
        assert result["trigger_type"] is None
        assert result["trigger_reason"] is None
        assert result["cooldown_until"] is None
        assert result["active_live_sessions"] == 2
        assert result["active_paper_sessions"] == 1

    async def test_get_status_auto_trigger(self, client):
        """Test get status when circuit breaker was auto-triggered."""
        mock_status = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "auto",
            "trigger_reason": "Daily loss limit exceeded",
            "cooldown_until": datetime.now(UTC).isoformat(),
            "active_live_sessions": 0,
            "active_paper_sessions": 3,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = await client.get("/api/v1/circuit-breaker/status")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["is_active"] is True
        assert result["trigger_type"] == "auto"
        assert "loss limit" in result["trigger_reason"].lower()


@pytest.mark.asyncio
class TestResetCircuitBreaker:
    """Test circuit breaker reset functionality."""

    async def test_reset_circuit_breaker_success(self, client):
        """Test reset circuit breaker after cooldown."""
        mock_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post("/api/v1/circuit-breaker/reset")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "reset"
        assert result["cooldown_remaining_minutes"] is None

    async def test_reset_circuit_breaker_with_force(self, client):
        """Test reset circuit breaker with force bypass cooldown."""
        mock_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_reset:
            response = await client.post("/api/v1/circuit-breaker/reset?force=true")

            # Verify force parameter was passed
            mock_reset.assert_called_once()
            call_kwargs = mock_reset.call_args.kwargs
            assert call_kwargs["force"] is True

        assert response.status_code == 200

    async def test_reset_circuit_breaker_in_cooldown(self, client):
        """Test reset fails when in cooldown without force."""
        from squant.services.circuit_breaker import CircuitBreakerCooldownError

        # Create error with remaining_minutes as float parameter
        error = CircuitBreakerCooldownError(remaining_minutes=15.5)

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = await client.post("/api/v1/circuit-breaker/reset")

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "code" in detail
        assert detail["code"] == 409
        assert "message" in detail
        assert "cooldown" in detail["message"].lower()
        assert detail["data"]["cooldown_remaining_minutes"] == 15.5

    async def test_reset_not_active(self, client):
        """Test reset when circuit breaker is not active."""
        mock_result = {
            "status": "not_active",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post("/api/v1/circuit-breaker/reset")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["status"] == "not_active"

    async def test_reset_force_bypass_cooldown(self, client):
        """Test force reset bypasses cooldown validation."""
        mock_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_reset:
            # Force reset should succeed even if in cooldown
            response = await client.post("/api/v1/circuit-breaker/reset?force=true")

            mock_reset.assert_called_once_with(force=True)

        assert response.status_code == 200


@pytest.mark.asyncio
class TestCircuitBreakerIntegration:
    """Test integrated circuit breaker workflows."""

    async def test_full_trigger_and_reset_workflow(self, client):
        """Test complete workflow: trigger -> status -> reset."""
        # Step 1: Trigger circuit breaker
        trigger_result = {
            "status": "triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
            "live_sessions_stopped": 1,
            "paper_sessions_stopped": 1,
            "errors": [],
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.trigger",
            new_callable=AsyncMock,
            return_value=trigger_result,
        ):
            response = await client.post(
                "/api/v1/circuit-breaker/trigger",
                json={"reason": "Test workflow"},
            )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "triggered"

        # Step 2: Check status (active)
        status_active = {
            "is_active": True,
            "triggered_at": datetime.now(UTC).isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test workflow",
            "cooldown_until": datetime.now(UTC).isoformat(),
            "active_live_sessions": 0,
            "active_paper_sessions": 0,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=status_active,
        ):
            response = await client.get("/api/v1/circuit-breaker/status")

        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is True

        # Step 3: Reset circuit breaker
        reset_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.services.circuit_breaker.CircuitBreakerService.reset",
            new_callable=AsyncMock,
            return_value=reset_result,
        ):
            response = await client.post("/api/v1/circuit-breaker/reset?force=true")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "reset"

        # Step 4: Check status (inactive)
        status_inactive = {
            "is_active": False,
            "triggered_at": None,
            "trigger_type": None,
            "trigger_reason": None,
            "cooldown_until": None,
            "active_live_sessions": 0,
            "active_paper_sessions": 0,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=status_inactive,
        ):
            response = await client.get("/api/v1/circuit-breaker/status")

        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False
