"""Unit tests for risk triggers API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from squant.main import app


class TestListRiskTriggers:
    """Tests for GET /api/v1/risk-triggers endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_list_triggers_empty(self, client: TestClient) -> None:
        """Test listing triggers when none exist."""
        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-triggers")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["items"] == []
            assert data["data"]["total"] == 0

    def test_list_triggers_with_data(self, client: TestClient) -> None:
        """Test listing triggers with data."""
        trigger_id = uuid4()
        rule_id = uuid4()
        run_id = uuid4()
        now = datetime.now(timezone.utc)

        mock_trigger = MagicMock()
        mock_trigger.id = str(trigger_id)
        mock_trigger.time = now
        mock_trigger.rule_id = str(rule_id)
        mock_trigger.run_id = str(run_id)
        mock_trigger.trigger_type = "daily_loss_limit"

        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([mock_trigger], 1))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-triggers")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 1
            assert len(data["data"]["items"]) == 1
            assert data["data"]["items"][0]["trigger_type"] == "daily_loss_limit"

    def test_list_triggers_with_pagination(self, client: TestClient) -> None:
        """Test listing triggers with pagination."""
        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([], 50))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-triggers?page=2&page_size=10")

            assert response.status_code == 200
            mock_service.list_triggers.assert_called_once()
            call_kwargs = mock_service.list_triggers.call_args[1]
            assert call_kwargs["page"] == 2
            assert call_kwargs["page_size"] == 10

    def test_list_triggers_with_time_filter(self, client: TestClient) -> None:
        """Test listing triggers with time filter."""
        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            start_time = "2024-01-01T00:00:00Z"
            end_time = "2024-01-31T23:59:59Z"
            response = client.get(
                f"/api/v1/risk-triggers?start_time={start_time}&end_time={end_time}"
            )

            assert response.status_code == 200
            mock_service.list_triggers.assert_called_once()
            call_kwargs = mock_service.list_triggers.call_args[1]
            assert call_kwargs["start_time"] is not None
            assert call_kwargs["end_time"] is not None

    def test_list_triggers_with_rule_id_filter(self, client: TestClient) -> None:
        """Test listing triggers filtered by rule_id."""
        rule_id = uuid4()

        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/risk-triggers?rule_id={rule_id}")

            assert response.status_code == 200
            call_kwargs = mock_service.list_triggers.call_args[1]
            assert call_kwargs["rule_id"] == rule_id

    def test_list_triggers_with_run_id_filter(self, client: TestClient) -> None:
        """Test listing triggers filtered by run_id."""
        run_id = uuid4()

        with patch(
            "squant.api.v1.risk_triggers.RiskTriggerService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_triggers = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/risk-triggers?run_id={run_id}")

            assert response.status_code == 200
            call_kwargs = mock_service.list_triggers.call_args[1]
            assert call_kwargs["run_id"] == run_id

    def test_list_triggers_invalid_page(self, client: TestClient) -> None:
        """Test listing triggers with invalid page number."""
        response = client.get("/api/v1/risk-triggers?page=0")

        assert response.status_code == 422

    def test_list_triggers_invalid_page_size(self, client: TestClient) -> None:
        """Test listing triggers with invalid page size."""
        response = client.get("/api/v1/risk-triggers?page_size=101")

        assert response.status_code == 422
