"""Unit tests for strategy schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from squant.models.enums import StrategyStatus
from squant.schemas.strategy import (
    CreateStrategyRequest,
    StrategyInfo,
    StrategyListItem,
    StrategyResponse,
    UpdateStrategyRequest,
    ValidateCodeRequest,
    ValidationResultResponse,
)


class TestCreateStrategyRequest:
    """Tests for CreateStrategyRequest schema."""

    def test_valid_minimal_request(self):
        """Test creating request with minimal fields."""
        request = CreateStrategyRequest(
            name="My Strategy",
            code="def on_bar(ctx): pass",
        )

        assert request.name == "My Strategy"
        assert request.code == "def on_bar(ctx): pass"
        assert request.description is None
        assert request.params_schema is None
        assert request.default_params is None

    def test_valid_full_request(self):
        """Test creating request with all fields."""
        request = CreateStrategyRequest(
            name="Moving Average Strategy",
            code="def on_bar(ctx): pass",
            description="A simple moving average crossover strategy",
            params_schema={"type": "object", "properties": {"period": {"type": "integer"}}},
            default_params={"period": 20},
        )

        assert request.name == "Moving Average Strategy"
        assert request.description == "A simple moving average crossover strategy"
        assert request.params_schema is not None
        assert request.default_params == {"period": 20}

    def test_name_required(self):
        """Test name is required."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(code="def on_bar(ctx): pass")

        assert "name" in str(exc_info.value)

    def test_code_required(self):
        """Test code is required."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(name="My Strategy")

        assert "code" in str(exc_info.value)

    def test_name_min_length(self):
        """Test name minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(name="", code="def on_bar(ctx): pass")

        assert "name" in str(exc_info.value)

    def test_name_max_length(self):
        """Test name maximum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(name="x" * 129, code="def on_bar(ctx): pass")

        assert "name" in str(exc_info.value)

    def test_code_min_length(self):
        """Test code minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(name="Test", code="")

        assert "code" in str(exc_info.value)

    def test_description_max_length(self):
        """Test description maximum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            CreateStrategyRequest(
                name="Test",
                code="def on_bar(ctx): pass",
                description="x" * 1001,
            )

        assert "description" in str(exc_info.value)


class TestUpdateStrategyRequest:
    """Tests for UpdateStrategyRequest schema."""

    def test_all_fields_optional(self):
        """Test all fields are optional."""
        request = UpdateStrategyRequest()

        assert request.name is None
        assert request.code is None
        assert request.description is None
        assert request.params_schema is None
        assert request.default_params is None
        assert request.status is None

    def test_partial_update(self):
        """Test partial update with some fields."""
        request = UpdateStrategyRequest(name="New Name", status=StrategyStatus.ARCHIVED)

        assert request.name == "New Name"
        assert request.status == StrategyStatus.ARCHIVED
        assert request.code is None

    def test_name_validation(self):
        """Test name validation when provided."""
        with pytest.raises(ValidationError):
            UpdateStrategyRequest(name="")

    def test_code_validation(self):
        """Test code validation when provided."""
        with pytest.raises(ValidationError):
            UpdateStrategyRequest(code="")

    def test_status_enum(self):
        """Test status accepts enum values."""
        request = UpdateStrategyRequest(status=StrategyStatus.ACTIVE)
        assert request.status == StrategyStatus.ACTIVE


class TestValidateCodeRequest:
    """Tests for ValidateCodeRequest schema."""

    def test_valid_request(self):
        """Test creating valid request."""
        request = ValidateCodeRequest(code="def on_bar(ctx): pass")

        assert request.code == "def on_bar(ctx): pass"

    def test_code_required(self):
        """Test code is required."""
        with pytest.raises(ValidationError) as exc_info:
            ValidateCodeRequest()

        assert "code" in str(exc_info.value)

    def test_code_min_length(self):
        """Test code minimum length."""
        with pytest.raises(ValidationError):
            ValidateCodeRequest(code="")


class TestValidationResultResponse:
    """Tests for ValidationResultResponse schema."""

    def test_valid_result(self):
        """Test creating valid result."""
        response = ValidationResultResponse(valid=True)

        assert response.valid is True
        assert response.errors == []
        assert response.warnings == []

    def test_invalid_result_with_errors(self):
        """Test invalid result with errors."""
        response = ValidationResultResponse(
            valid=False,
            errors=["Syntax error on line 5", "Missing on_bar function"],
        )

        assert response.valid is False
        assert len(response.errors) == 2

    def test_valid_result_with_warnings(self):
        """Test valid result with warnings."""
        response = ValidationResultResponse(
            valid=True,
            warnings=["Unused variable 'x'"],
        )

        assert response.valid is True
        assert len(response.warnings) == 1

    def test_strategy_info_default_none(self):
        """Test strategy_info defaults to None (ST-003)."""
        response = ValidationResultResponse(valid=False, errors=["error"])
        assert response.strategy_info is None

    def test_strategy_info_set(self):
        """Test strategy_info can be set (ST-003)."""
        info = StrategyInfo(class_name="MyStrategy", has_on_bar=True, has_init=False)
        response = ValidationResultResponse(valid=True, strategy_info=info)
        assert response.strategy_info is not None
        assert response.strategy_info.class_name == "MyStrategy"
        assert response.strategy_info.has_on_bar is True
        assert response.strategy_info.has_init is False


class TestStrategyInfo:
    """Tests for StrategyInfo schema (ST-003)."""

    def test_defaults(self):
        """Test default values."""
        info = StrategyInfo()
        assert info.class_name is None
        assert info.has_on_bar is False
        assert info.has_init is False

    def test_full_info(self):
        """Test with all fields."""
        info = StrategyInfo(class_name="MACrossover", has_on_bar=True, has_init=True)
        assert info.class_name == "MACrossover"
        assert info.has_on_bar is True
        assert info.has_init is True


class TestStrategyResponse:
    """Tests for StrategyResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(UTC)
        response = StrategyResponse(
            id=uuid4(),
            name="Test Strategy",
            version="1.0.0",
            description="A test strategy",
            code="def on_bar(ctx): pass",
            params_schema={"type": "object"},
            default_params={"period": 20},
            status="active",
            created_at=now,
            updated_at=now,
        )

        assert response.name == "Test Strategy"
        assert response.version == "1.0.0"
        assert response.status == "active"

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert StrategyResponse.model_config.get("from_attributes") is True

    def test_required_fields(self):
        """Test required fields validation."""
        with pytest.raises(ValidationError):
            StrategyResponse(
                id=uuid4(),
                name="Test",
                # Missing required fields
            )


class TestStrategyListItem:
    """Tests for StrategyListItem schema."""

    def test_list_item(self):
        """Test creating list item (without code)."""
        now = datetime.now(UTC)
        item = StrategyListItem(
            id=uuid4(),
            name="Test Strategy",
            version="1.0.0",
            description="A test strategy",
            status="active",
            created_at=now,
            updated_at=now,
        )

        assert item.name == "Test Strategy"
        # StrategyListItem doesn't have code field
        assert not hasattr(item, "code") or "code" not in item.model_fields

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert StrategyListItem.model_config.get("from_attributes") is True

    def test_description_optional(self):
        """Test description is optional."""
        now = datetime.now(UTC)
        item = StrategyListItem(
            id=uuid4(),
            name="Test",
            version="1.0.0",
            description=None,
            status="active",
            created_at=now,
            updated_at=now,
        )

        assert item.description is None
