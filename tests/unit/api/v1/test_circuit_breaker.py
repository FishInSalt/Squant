"""Unit tests for circuit breaker API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from squant.main import app
from squant.services.circuit_breaker import (
    CircuitBreakerAlreadyActiveError,
    CircuitBreakerCooldownError,
)


class TestTriggerCircuitBreaker:
    """Tests for POST /api/v1/circuit-breaker/trigger endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def valid_request(self) -> dict[str, Any]:
        """Create valid trigger request."""
        return {
            "reason": "Emergency test",
            "cooldown_minutes": 30,
        }

    def test_trigger_success(
        self, client: TestClient, valid_request: dict[str, Any]
    ) -> None:
        """Test successful circuit breaker trigger."""
        now = datetime.now(UTC)
        mock_result = {
            "status": "triggered",
            "triggered_at": now.isoformat(),
            "live_sessions_stopped": 2,
            "paper_sessions_stopped": 3,
            "errors": [],
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.trigger = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post(
                "/api/v1/circuit-breaker/trigger", json=valid_request
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["status"] == "triggered"
            assert data["data"]["live_sessions_stopped"] == 2
            assert data["data"]["paper_sessions_stopped"] == 3

    def test_trigger_already_active(
        self, client: TestClient, valid_request: dict[str, Any]
    ) -> None:
        """Test trigger when already active."""
        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.trigger = AsyncMock(
                side_effect=CircuitBreakerAlreadyActiveError()
            )
            mock_service_class.return_value = mock_service

            response = client.post(
                "/api/v1/circuit-breaker/trigger", json=valid_request
            )

            assert response.status_code == 409

    def test_trigger_missing_reason(self, client: TestClient) -> None:
        """Test trigger with missing reason."""
        response = client.post("/api/v1/circuit-breaker/trigger", json={})

        assert response.status_code == 422

    def test_trigger_reason_too_long(self, client: TestClient) -> None:
        """Test trigger with reason exceeding max length."""
        request = {
            "reason": "x" * 257,  # Exceeds 256 char limit
        }
        response = client.post("/api/v1/circuit-breaker/trigger", json=request)

        assert response.status_code == 422

    def test_trigger_invalid_cooldown(self, client: TestClient) -> None:
        """Test trigger with invalid cooldown value."""
        request = {
            "reason": "Test",
            "cooldown_minutes": 2000,  # Exceeds 1440 max
        }
        response = client.post("/api/v1/circuit-breaker/trigger", json=request)

        assert response.status_code == 422


class TestCloseAllPositions:
    """Tests for POST /api/v1/circuit-breaker/close-all-positions endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_close_all_positions_success(self, client: TestClient) -> None:
        """Test successful close all positions."""
        mock_result = {
            "live_positions_closed": 3,
            "paper_positions_reset": 2,
            "orders_cancelled": 5,
            "errors": [],
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.close_all_positions = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/close-all-positions")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["live_positions_closed"] == 3
            assert data["data"]["orders_cancelled"] == 5

    def test_close_all_positions_with_reason(self, client: TestClient) -> None:
        """Test close all positions with custom reason."""
        mock_result = {
            "live_positions_closed": 1,
            "paper_positions_reset": 0,
            "orders_cancelled": 2,
            "errors": [],
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.close_all_positions = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post(
                "/api/v1/circuit-breaker/close-all-positions",
                json={"reason": "Market crash"},
            )

            assert response.status_code == 200

    def test_close_all_positions_with_errors(self, client: TestClient) -> None:
        """Test close all positions when some fail."""
        mock_result = {
            "live_positions_closed": 1,
            "paper_positions_reset": 0,
            "orders_cancelled": 1,
            "errors": [{"run_id": "abc", "error": "Connection lost"}],
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.close_all_positions = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/close-all-positions")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]["errors"]) == 1


class TestGetStatus:
    """Tests for GET /api/v1/circuit-breaker/status endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_get_status_inactive(self, client: TestClient) -> None:
        """Test getting status when inactive."""
        mock_status = {
            "is_active": False,
            "triggered_at": None,
            "trigger_type": None,
            "trigger_reason": None,
            "cooldown_until": None,
            "active_live_sessions": 5,
            "active_paper_sessions": 3,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = client.get("/api/v1/circuit-breaker/status")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["is_active"] is False
            assert data["data"]["active_live_sessions"] == 5

    def test_get_status_active(self, client: TestClient) -> None:
        """Test getting status when active."""
        now = datetime.now(UTC)
        mock_status = {
            "is_active": True,
            "triggered_at": now.isoformat(),
            "trigger_type": "manual",
            "trigger_reason": "Test trigger",
            "cooldown_until": now.isoformat(),
            "active_live_sessions": 0,
            "active_paper_sessions": 0,
        }

        with patch(
            "squant.api.v1.circuit_breaker.get_circuit_breaker_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ):
            response = client.get("/api/v1/circuit-breaker/status")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["is_active"] is True
            assert data["data"]["trigger_type"] == "manual"


class TestResetCircuitBreaker:
    """Tests for POST /api/v1/circuit-breaker/reset endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_reset_success(self, client: TestClient) -> None:
        """Test successful reset."""
        mock_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.reset = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/reset")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "reset"

    def test_reset_not_active(self, client: TestClient) -> None:
        """Test reset when not active."""
        mock_result = {
            "status": "not_active",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.reset = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/reset")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "not_active"

    def test_reset_in_cooldown(self, client: TestClient) -> None:
        """Test reset during cooldown."""
        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.reset = AsyncMock(
                side_effect=CircuitBreakerCooldownError(30.5)
            )
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/reset")

            assert response.status_code == 409

    def test_reset_force(self, client: TestClient) -> None:
        """Test forced reset during cooldown."""
        mock_result = {
            "status": "reset",
            "cooldown_remaining_minutes": None,
        }

        with patch(
            "squant.api.v1.circuit_breaker.CircuitBreakerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.reset = AsyncMock(return_value=mock_result)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/circuit-breaker/reset?force=true")

            assert response.status_code == 200
            mock_service.reset.assert_called_once_with(force=True)
