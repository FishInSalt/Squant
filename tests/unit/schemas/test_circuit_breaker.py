"""Unit tests for circuit breaker schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.schemas.circuit_breaker import (
    CircuitBreakerEventResponse,
    CircuitBreakerStatusResponse,
    CloseAllPositionsRequest,
    CloseAllPositionsResponse,
    ResetCircuitBreakerResponse,
    RiskTriggerListItem,
    RiskTriggerResponse,
    TriggerCircuitBreakerRequest,
    TriggerCircuitBreakerResponse,
)


class TestTriggerCircuitBreakerRequest:
    """Tests for TriggerCircuitBreakerRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        request = TriggerCircuitBreakerRequest(
            reason="Manual safety stop",
        )

        assert request.reason == "Manual safety stop"
        assert request.cooldown_minutes is None

    def test_with_cooldown(self):
        """Test creating request with cooldown."""
        request = TriggerCircuitBreakerRequest(
            reason="Market volatility",
            cooldown_minutes=30,
        )

        assert request.cooldown_minutes == 30

    def test_reason_required(self):
        """Test reason is required."""
        with pytest.raises(ValidationError):
            TriggerCircuitBreakerRequest()

    def test_reason_min_length(self):
        """Test reason minimum length."""
        with pytest.raises(ValidationError):
            TriggerCircuitBreakerRequest(reason="")

    def test_reason_max_length(self):
        """Test reason maximum length."""
        with pytest.raises(ValidationError):
            TriggerCircuitBreakerRequest(reason="x" * 257)

    def test_cooldown_min_value(self):
        """Test cooldown minimum value."""
        with pytest.raises(ValidationError):
            TriggerCircuitBreakerRequest(reason="Test", cooldown_minutes=0)

    def test_cooldown_max_value(self):
        """Test cooldown maximum value (1440 = 24 hours)."""
        with pytest.raises(ValidationError):
            TriggerCircuitBreakerRequest(reason="Test", cooldown_minutes=1441)

    def test_cooldown_at_boundary(self):
        """Test cooldown at boundary values."""
        # Min boundary
        request1 = TriggerCircuitBreakerRequest(reason="Test", cooldown_minutes=1)
        assert request1.cooldown_minutes == 1

        # Max boundary
        request2 = TriggerCircuitBreakerRequest(reason="Test", cooldown_minutes=1440)
        assert request2.cooldown_minutes == 1440


class TestTriggerCircuitBreakerResponse:
    """Tests for TriggerCircuitBreakerResponse schema."""

    def test_triggered_response(self):
        """Test response when circuit breaker was triggered."""
        response = TriggerCircuitBreakerResponse(
            status="triggered",
            triggered_at="2024-01-15T10:30:00Z",
            live_sessions_stopped=3,
            paper_sessions_stopped=5,
        )

        assert response.status == "triggered"
        assert response.live_sessions_stopped == 3
        assert response.errors == []

    def test_already_active_response(self):
        """Test response when already active."""
        response = TriggerCircuitBreakerResponse(
            status="already_active",
            triggered_at="2024-01-15T10:00:00Z",
            live_sessions_stopped=0,
            paper_sessions_stopped=0,
        )

        assert response.status == "already_active"

    def test_with_errors(self):
        """Test response with errors."""
        response = TriggerCircuitBreakerResponse(
            status="triggered",
            triggered_at="2024-01-15T10:30:00Z",
            live_sessions_stopped=2,
            paper_sessions_stopped=3,
            errors=["Failed to stop session abc123", "Connection timeout"],
        )

        assert len(response.errors) == 2


class TestCloseAllPositionsRequest:
    """Tests for CloseAllPositionsRequest schema."""

    def test_default_reason(self):
        """Test default reason value."""
        request = CloseAllPositionsRequest()

        assert request.reason == "Manual close all positions"

    def test_custom_reason(self):
        """Test custom reason."""
        request = CloseAllPositionsRequest(reason="Emergency market conditions")

        assert request.reason == "Emergency market conditions"

    def test_reason_max_length(self):
        """Test reason max length."""
        with pytest.raises(ValidationError):
            CloseAllPositionsRequest(reason="x" * 257)


class TestCloseAllPositionsResponse:
    """Tests for CloseAllPositionsResponse schema."""

    def test_successful_close(self):
        """Test successful close response."""
        response = CloseAllPositionsResponse(
            live_positions_closed=5,
            paper_positions_reset=3,
            orders_cancelled=10,
        )

        assert response.live_positions_closed == 5
        assert response.paper_positions_reset == 3
        assert response.orders_cancelled == 10
        assert response.errors == []

    def test_with_errors(self):
        """Test response with errors."""
        response = CloseAllPositionsResponse(
            live_positions_closed=2,
            paper_positions_reset=1,
            orders_cancelled=5,
            errors=[
                {"session_id": "abc", "error": "Connection failed"},
                {"session_id": "def", "error": "Order not found"},
            ],
        )

        assert len(response.errors) == 2


class TestCircuitBreakerStatusResponse:
    """Tests for CircuitBreakerStatusResponse schema."""

    def test_active_status(self):
        """Test active circuit breaker status."""
        response = CircuitBreakerStatusResponse(
            is_active=True,
            triggered_at="2024-01-15T10:00:00Z",
            trigger_type="manual",
            trigger_reason="Market volatility",
            cooldown_until="2024-01-15T10:30:00Z",
            active_live_sessions=0,
            active_paper_sessions=2,
        )

        assert response.is_active is True
        assert response.trigger_type == "manual"

    def test_inactive_status(self):
        """Test inactive circuit breaker status."""
        response = CircuitBreakerStatusResponse(
            is_active=False,
            triggered_at=None,
            trigger_type=None,
            trigger_reason=None,
            cooldown_until=None,
            active_live_sessions=5,
            active_paper_sessions=10,
        )

        assert response.is_active is False
        assert response.triggered_at is None


class TestResetCircuitBreakerResponse:
    """Tests for ResetCircuitBreakerResponse schema."""

    def test_reset_success(self):
        """Test successful reset."""
        response = ResetCircuitBreakerResponse(
            status="reset",
            cooldown_remaining_minutes=None,
        )

        assert response.status == "reset"

    def test_cooldown_active(self):
        """Test reset during cooldown."""
        response = ResetCircuitBreakerResponse(
            status="cooldown",
            cooldown_remaining_minutes=15.5,
        )

        assert response.status == "cooldown"
        assert response.cooldown_remaining_minutes == 15.5

    def test_not_active(self):
        """Test reset when not active."""
        response = ResetCircuitBreakerResponse(
            status="not_active",
            cooldown_remaining_minutes=None,
        )

        assert response.status == "not_active"


class TestRiskTriggerResponse:
    """Tests for RiskTriggerResponse schema."""

    def test_full_response(self):
        """Test full risk trigger response."""
        now = datetime.now(UTC)
        response = RiskTriggerResponse(
            id=uuid4(),
            time=now,
            rule_id=uuid4(),
            run_id=uuid4(),
            trigger_type="auto",
            details={"rule_name": "daily_loss_limit", "threshold": 0.05, "actual": 0.06},
        )

        assert response.trigger_type == "auto"
        assert "rule_name" in response.details

    def test_minimal_response(self):
        """Test minimal response without optional fields."""
        now = datetime.now(UTC)
        response = RiskTriggerResponse(
            id=uuid4(),
            time=now,
            rule_id=None,
            run_id=None,
            trigger_type="manual",
            details={},
        )

        assert response.rule_id is None
        assert response.run_id is None

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert RiskTriggerResponse.model_config.get("from_attributes") is True


class TestRiskTriggerListItem:
    """Tests for RiskTriggerListItem schema."""

    def test_list_item(self):
        """Test risk trigger list item."""
        now = datetime.now(UTC)
        item = RiskTriggerListItem(
            id=uuid4(),
            time=now,
            rule_id=uuid4(),
            run_id=uuid4(),
            trigger_type="auto",
        )

        assert item.trigger_type == "auto"

    def test_no_details_in_list(self):
        """Test list item doesn't include details."""
        fields = RiskTriggerListItem.model_fields
        assert "details" not in fields


class TestCircuitBreakerEventResponse:
    """Tests for CircuitBreakerEventResponse schema."""

    def test_event_response(self):
        """Test circuit breaker event response."""
        now = datetime.now(UTC)
        response = CircuitBreakerEventResponse(
            id=uuid4(),
            time=now,
            trigger_type="auto",
            trigger_source="risk_rule",
            reason="Daily loss limit exceeded",
            details={"loss_pct": 0.06, "limit": 0.05},
            sessions_stopped=5,
            positions_closed=3,
        )

        assert response.trigger_type == "auto"
        assert response.trigger_source == "risk_rule"
        assert response.sessions_stopped == 5

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert CircuitBreakerEventResponse.model_config.get("from_attributes") is True
