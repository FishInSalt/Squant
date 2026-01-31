"""Unit tests for risk schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.models.enums import RiskRuleType
from squant.schemas.risk import (
    CreateRiskRuleRequest,
    RiskRuleListItem,
    RiskRuleResponse,
    ToggleRiskRuleRequest,
    UpdateRiskRuleRequest,
)


class TestCreateRiskRuleRequest:
    """Tests for CreateRiskRuleRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        request = CreateRiskRuleRequest(
            name="Max Order Size",
            type=RiskRuleType.ORDER_LIMIT,
            params={"max_amount": 1.0, "max_value": 10000},
        )

        assert request.name == "Max Order Size"
        assert request.type == RiskRuleType.ORDER_LIMIT
        assert request.params == {"max_amount": 1.0, "max_value": 10000}
        assert request.enabled is True

    def test_disabled_rule(self):
        """Test creating disabled rule."""
        request = CreateRiskRuleRequest(
            name="Daily Loss Limit",
            type=RiskRuleType.DAILY_LOSS_LIMIT,
            params={"max_loss_pct": 5.0},
            enabled=False,
        )

        assert request.enabled is False

    def test_all_rule_types(self):
        """Test all rule types are accepted."""
        rule_types = [
            RiskRuleType.ORDER_LIMIT,
            RiskRuleType.POSITION_LIMIT,
            RiskRuleType.DAILY_LOSS_LIMIT,
            RiskRuleType.TOTAL_LOSS_LIMIT,
            RiskRuleType.FREQUENCY_LIMIT,
            RiskRuleType.VOLATILITY_BREAK,
        ]

        for rule_type in rule_types:
            request = CreateRiskRuleRequest(
                name=f"Rule {rule_type.value}",
                type=rule_type,
                params={},
            )
            assert request.type == rule_type

    def test_name_required(self):
        """Test name is required."""
        with pytest.raises(ValidationError):
            CreateRiskRuleRequest(
                type=RiskRuleType.ORDER_LIMIT,
                params={},
            )

    def test_name_min_length(self):
        """Test name minimum length."""
        with pytest.raises(ValidationError):
            CreateRiskRuleRequest(
                name="",
                type=RiskRuleType.ORDER_LIMIT,
                params={},
            )

    def test_name_max_length(self):
        """Test name maximum length."""
        with pytest.raises(ValidationError):
            CreateRiskRuleRequest(
                name="x" * 65,
                type=RiskRuleType.ORDER_LIMIT,
                params={},
            )

    def test_type_required(self):
        """Test type is required."""
        with pytest.raises(ValidationError):
            CreateRiskRuleRequest(
                name="Test Rule",
                params={},
            )

    def test_params_required(self):
        """Test params is required."""
        with pytest.raises(ValidationError):
            CreateRiskRuleRequest(
                name="Test Rule",
                type=RiskRuleType.ORDER_LIMIT,
            )

    def test_params_can_be_complex(self):
        """Test params can contain complex nested structures."""
        request = CreateRiskRuleRequest(
            name="Complex Rule",
            type=RiskRuleType.FREQUENCY_LIMIT,
            params={
                "max_orders_per_minute": 10,
                "max_orders_per_hour": 100,
                "exceptions": ["BTC/USDT", "ETH/USDT"],
                "config": {"strict_mode": True, "cooldown": 60},
            },
        )

        assert request.params["max_orders_per_minute"] == 10
        assert "exceptions" in request.params


class TestUpdateRiskRuleRequest:
    """Tests for UpdateRiskRuleRequest schema."""

    def test_all_fields_optional(self):
        """Test all fields are optional."""
        request = UpdateRiskRuleRequest()

        assert request.name is None
        assert request.type is None
        assert request.params is None
        assert request.enabled is None

    def test_partial_update(self):
        """Test partial update."""
        request = UpdateRiskRuleRequest(
            name="Updated Name",
            enabled=False,
        )

        assert request.name == "Updated Name"
        assert request.enabled is False
        assert request.type is None

    def test_update_type(self):
        """Test updating rule type."""
        request = UpdateRiskRuleRequest(
            type=RiskRuleType.POSITION_LIMIT,
        )

        assert request.type == RiskRuleType.POSITION_LIMIT

    def test_update_params(self):
        """Test updating params."""
        request = UpdateRiskRuleRequest(
            params={"new_param": "value"},
        )

        assert request.params == {"new_param": "value"}

    def test_name_validation(self):
        """Test name validation when provided."""
        with pytest.raises(ValidationError):
            UpdateRiskRuleRequest(name="")


class TestToggleRiskRuleRequest:
    """Tests for ToggleRiskRuleRequest schema."""

    def test_enable_rule(self):
        """Test enabling a rule."""
        request = ToggleRiskRuleRequest(enabled=True)

        assert request.enabled is True

    def test_disable_rule(self):
        """Test disabling a rule."""
        request = ToggleRiskRuleRequest(enabled=False)

        assert request.enabled is False

    def test_enabled_required(self):
        """Test enabled field is required."""
        with pytest.raises(ValidationError):
            ToggleRiskRuleRequest()


class TestRiskRuleResponse:
    """Tests for RiskRuleResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(UTC)
        response = RiskRuleResponse(
            id=uuid4(),
            name="Max Position",
            type="position_limit",
            params={"max_position": 10.0},
            enabled=True,
            created_at=now,
            updated_at=now,
        )

        assert response.name == "Max Position"
        assert response.type == "position_limit"
        assert response.enabled is True

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert RiskRuleResponse.model_config.get("from_attributes") is True

    def test_type_as_string(self):
        """Test type is stored as string in response."""
        now = datetime.now(UTC)
        response = RiskRuleResponse(
            id=uuid4(),
            name="Test",
            type="daily_loss_limit",
            params={},
            enabled=True,
            created_at=now,
            updated_at=now,
        )

        assert isinstance(response.type, str)


class TestRiskRuleListItem:
    """Tests for RiskRuleListItem schema."""

    def test_list_item(self):
        """Test creating list item."""
        now = datetime.now(UTC)
        item = RiskRuleListItem(
            id=uuid4(),
            name="Order Limit",
            type="order_limit",
            enabled=True,
            created_at=now,
        )

        assert item.name == "Order Limit"
        assert item.enabled is True

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert RiskRuleListItem.model_config.get("from_attributes") is True

    def test_no_params_in_list_item(self):
        """Test list item doesn't include params (for lighter payload)."""
        fields = RiskRuleListItem.model_fields
        assert "params" not in fields

    def test_no_updated_at_in_list_item(self):
        """Test list item doesn't include updated_at."""
        fields = RiskRuleListItem.model_fields
        assert "updated_at" not in fields
