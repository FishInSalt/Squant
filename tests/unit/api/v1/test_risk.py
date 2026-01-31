"""Unit tests for risk rule API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from squant.main import app
from squant.models.enums import RiskRuleType
from squant.services.risk import RiskRuleNotFoundError


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_risk_rule():
    """Create a mock risk rule."""
    rule = MagicMock()
    rule.id = uuid4()
    rule.name = "Max Position Size"
    rule.type = RiskRuleType.POSITION_LIMIT.value
    rule.params = {"max_position": 1.0, "symbol": "BTC/USDT"}
    rule.enabled = True
    rule.created_at = datetime.now(UTC)
    rule.updated_at = datetime.now(UTC)
    return rule


@pytest.fixture
def valid_create_request() -> dict:
    """Create a valid risk rule creation request."""
    return {
        "name": "Max Position Size",
        "type": "position_limit",
        "params": {"max_position": 1.0, "symbol": "BTC/USDT"},
        "enabled": True,
    }


class TestCreateRiskRule:
    """Tests for POST /api/v1/risk-rules endpoint."""

    def test_create_risk_rule_success(
        self, client: TestClient, valid_create_request: dict, mock_risk_rule
    ) -> None:
        """Test successful risk rule creation."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.post("/api/v1/risk-rules", json=valid_create_request)

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["name"] == "Max Position Size"

    def test_create_risk_rule_missing_name(self, client: TestClient) -> None:
        """Test creating risk rule without name."""
        response = client.post(
            "/api/v1/risk-rules",
            json={
                "type": "position_limit",
                "params": {"max_position": 1.0},
            },
        )

        assert response.status_code == 422

    def test_create_risk_rule_missing_type(self, client: TestClient) -> None:
        """Test creating risk rule without type."""
        response = client.post(
            "/api/v1/risk-rules",
            json={
                "name": "Test Rule",
                "params": {"max_position": 1.0},
            },
        )

        assert response.status_code == 422

    def test_create_risk_rule_invalid_type(self, client: TestClient) -> None:
        """Test creating risk rule with invalid type."""
        response = client.post(
            "/api/v1/risk-rules",
            json={
                "name": "Test Rule",
                "type": "invalid_type",
                "params": {"max_position": 1.0},
            },
        )

        assert response.status_code == 422


class TestListRiskRules:
    """Tests for GET /api/v1/risk-rules endpoint."""

    def test_list_risk_rules_success(self, client: TestClient, mock_risk_rule) -> None:
        """Test listing risk rules."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_risk_rule], 1))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-rules")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["total"] == 1
            assert len(data["data"]["items"]) == 1

    def test_list_risk_rules_with_pagination(self, client: TestClient, mock_risk_rule) -> None:
        """Test listing risk rules with pagination."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_risk_rule], 50))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-rules?page=2&page_size=10")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["page"] == 2
            assert data["data"]["page_size"] == 10

    def test_list_risk_rules_with_enabled_filter(self, client: TestClient, mock_risk_rule) -> None:
        """Test listing risk rules with enabled filter."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([mock_risk_rule], 1))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-rules?enabled=true")

            assert response.status_code == 200
            mock_service.list.assert_called_once_with(page=1, page_size=20, enabled=True)

    def test_list_risk_rules_empty(self, client: TestClient) -> None:
        """Test listing risk rules when none exist."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/risk-rules")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["total"] == 0
            assert data["data"]["items"] == []


class TestGetRiskRule:
    """Tests for GET /api/v1/risk-rules/{rule_id} endpoint."""

    def test_get_risk_rule_success(self, client: TestClient, mock_risk_rule) -> None:
        """Test getting a risk rule by ID."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/risk-rules/{mock_risk_rule.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["name"] == "Max Position Size"

    def test_get_risk_rule_not_found(self, client: TestClient) -> None:
        """Test getting a non-existent risk rule."""
        rule_id = uuid4()

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get = AsyncMock(side_effect=RiskRuleNotFoundError(str(rule_id)))
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/v1/risk-rules/{rule_id}")

            assert response.status_code == 404

    def test_get_risk_rule_invalid_id(self, client: TestClient) -> None:
        """Test getting risk rule with invalid ID format."""
        response = client.get("/api/v1/risk-rules/invalid-uuid")

        assert response.status_code == 422


class TestUpdateRiskRule:
    """Tests for PUT /api/v1/risk-rules/{rule_id} endpoint."""

    def test_update_risk_rule_success(self, client: TestClient, mock_risk_rule) -> None:
        """Test updating a risk rule."""
        mock_risk_rule.name = "Updated Rule"

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.put(
                f"/api/v1/risk-rules/{mock_risk_rule.id}",
                json={"name": "Updated Rule"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["name"] == "Updated Rule"

    def test_update_risk_rule_not_found(self, client: TestClient) -> None:
        """Test updating a non-existent risk rule."""
        rule_id = uuid4()

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(side_effect=RiskRuleNotFoundError(str(rule_id)))
            mock_service_class.return_value = mock_service

            response = client.put(
                f"/api/v1/risk-rules/{rule_id}",
                json={"name": "New Name"},
            )

            assert response.status_code == 404

    def test_update_risk_rule_params(self, client: TestClient, mock_risk_rule) -> None:
        """Test updating risk rule parameters."""
        mock_risk_rule.params = {"max_position": 2.0}

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.put(
                f"/api/v1/risk-rules/{mock_risk_rule.id}",
                json={"params": {"max_position": 2.0}},
            )

            assert response.status_code == 200


class TestDeleteRiskRule:
    """Tests for DELETE /api/v1/risk-rules/{rule_id} endpoint."""

    def test_delete_risk_rule_success(self, client: TestClient, mock_risk_rule) -> None:
        """Test deleting a risk rule."""
        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            response = client.delete(f"/api/v1/risk-rules/{mock_risk_rule.id}")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Risk rule deleted"

    def test_delete_risk_rule_not_found(self, client: TestClient) -> None:
        """Test deleting a non-existent risk rule."""
        rule_id = uuid4()

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.delete = AsyncMock(side_effect=RiskRuleNotFoundError(str(rule_id)))
            mock_service_class.return_value = mock_service

            response = client.delete(f"/api/v1/risk-rules/{rule_id}")

            assert response.status_code == 404


class TestToggleRiskRule:
    """Tests for POST /api/v1/risk-rules/{rule_id}/toggle endpoint."""

    def test_toggle_risk_rule_enable(self, client: TestClient, mock_risk_rule) -> None:
        """Test enabling a risk rule."""
        mock_risk_rule.enabled = True

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.toggle = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/risk-rules/{mock_risk_rule.id}/toggle",
                json={"enabled": True},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["enabled"] is True

    def test_toggle_risk_rule_disable(self, client: TestClient, mock_risk_rule) -> None:
        """Test disabling a risk rule."""
        mock_risk_rule.enabled = False

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.toggle = AsyncMock(return_value=mock_risk_rule)
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/risk-rules/{mock_risk_rule.id}/toggle",
                json={"enabled": False},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["enabled"] is False

    def test_toggle_risk_rule_not_found(self, client: TestClient) -> None:
        """Test toggling a non-existent risk rule."""
        rule_id = uuid4()

        with patch("squant.api.v1.risk.RiskRuleService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.toggle = AsyncMock(side_effect=RiskRuleNotFoundError(str(rule_id)))
            mock_service_class.return_value = mock_service

            response = client.post(
                f"/api/v1/risk-rules/{rule_id}/toggle",
                json={"enabled": True},
            )

            assert response.status_code == 404

    def test_toggle_risk_rule_missing_enabled(self, client: TestClient) -> None:
        """Test toggle without enabled field."""
        rule_id = uuid4()

        response = client.post(
            f"/api/v1/risk-rules/{rule_id}/toggle",
            json={},
        )

        assert response.status_code == 422
