"""Unit tests for account schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from squant.schemas.account import (
    ConnectionTestResponse,
    CreateExchangeAccountRequest,
    ExchangeAccountListItem,
    ExchangeAccountResponse,
    UpdateExchangeAccountRequest,
)


class TestCreateExchangeAccountRequest:
    """Tests for CreateExchangeAccountRequest schema."""

    def test_valid_okx_account(self):
        """Test creating valid OKX account request."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="My OKX Account",
            api_key=SecretStr("test-api-key"),
            api_secret=SecretStr("test-api-secret"),
            passphrase=SecretStr("test-passphrase"),
        )

        assert request.exchange == "okx"
        assert request.name == "My OKX Account"
        assert request.api_key.get_secret_value() == "test-api-key"
        assert request.passphrase is not None

    def test_valid_binance_account(self):
        """Test creating valid Binance account request."""
        request = CreateExchangeAccountRequest(
            exchange="binance",
            name="My Binance Account",
            api_key=SecretStr("test-api-key"),
            api_secret=SecretStr("test-api-secret"),
        )

        assert request.exchange == "binance"
        assert request.passphrase is None

    def test_testnet_flag(self):
        """Test testnet flag."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Testnet Account",
            api_key=SecretStr("test-key"),
            api_secret=SecretStr("test-secret"),
            testnet=True,
        )

        assert request.testnet is True

    def test_testnet_default_false(self):
        """Test testnet defaults to False."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Account",
            api_key=SecretStr("key"),
            api_secret=SecretStr("secret"),
        )

        assert request.testnet is False

    def test_exchange_literal_validation(self):
        """Test exchange must be okx or binance."""
        with pytest.raises(ValidationError):
            CreateExchangeAccountRequest(
                exchange="invalid_exchange",
                name="Account",
                api_key=SecretStr("key"),
                api_secret=SecretStr("secret"),
            )

    def test_name_min_length(self):
        """Test name minimum length."""
        with pytest.raises(ValidationError):
            CreateExchangeAccountRequest(
                exchange="okx",
                name="",
                api_key=SecretStr("key"),
                api_secret=SecretStr("secret"),
            )

    def test_name_max_length(self):
        """Test name maximum length."""
        with pytest.raises(ValidationError):
            CreateExchangeAccountRequest(
                exchange="okx",
                name="x" * 65,
                api_key=SecretStr("key"),
                api_secret=SecretStr("secret"),
            )

    def test_api_key_required(self):
        """Test api_key is required."""
        with pytest.raises(ValidationError):
            CreateExchangeAccountRequest(
                exchange="okx",
                name="Account",
                api_secret=SecretStr("secret"),
            )

    def test_api_secret_required(self):
        """Test api_secret is required."""
        with pytest.raises(ValidationError):
            CreateExchangeAccountRequest(
                exchange="okx",
                name="Account",
                api_key=SecretStr("key"),
            )

    def test_secrets_are_protected(self):
        """Test secrets don't expose values in string representation."""
        request = CreateExchangeAccountRequest(
            exchange="okx",
            name="Account",
            api_key=SecretStr("my-secret-key"),
            api_secret=SecretStr("my-secret-secret"),
        )

        # SecretStr should not expose value in repr
        assert "my-secret-key" not in str(request.api_key)
        assert "my-secret-secret" not in str(request.api_secret)


class TestUpdateExchangeAccountRequest:
    """Tests for UpdateExchangeAccountRequest schema."""

    def test_all_fields_optional(self):
        """Test all fields are optional."""
        request = UpdateExchangeAccountRequest()

        assert request.name is None
        assert request.api_key is None
        assert request.api_secret is None
        assert request.passphrase is None
        assert request.testnet is None
        assert request.is_active is None

    def test_partial_update(self):
        """Test partial update with some fields."""
        request = UpdateExchangeAccountRequest(
            name="New Name",
            is_active=False,
        )

        assert request.name == "New Name"
        assert request.is_active is False
        assert request.api_key is None

    def test_update_credentials(self):
        """Test updating credentials."""
        request = UpdateExchangeAccountRequest(
            api_key=SecretStr("new-key"),
            api_secret=SecretStr("new-secret"),
        )

        assert request.api_key.get_secret_value() == "new-key"
        assert request.api_secret.get_secret_value() == "new-secret"

    def test_name_validation(self):
        """Test name validation when provided."""
        with pytest.raises(ValidationError):
            UpdateExchangeAccountRequest(name="")


class TestExchangeAccountResponse:
    """Tests for ExchangeAccountResponse schema."""

    def test_full_response(self):
        """Test creating full response."""
        now = datetime.now(UTC)
        response = ExchangeAccountResponse(
            id=uuid4(),
            exchange="okx",
            name="My Account",
            testnet=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        assert response.exchange == "okx"
        assert response.name == "My Account"
        assert response.is_active is True

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert ExchangeAccountResponse.model_config.get("from_attributes") is True

    def test_no_credentials_in_response(self):
        """Test response doesn't have credential fields."""
        fields = ExchangeAccountResponse.model_fields
        assert "api_key" not in fields
        assert "api_secret" not in fields
        assert "passphrase" not in fields


class TestExchangeAccountListItem:
    """Tests for ExchangeAccountListItem schema."""

    def test_list_item(self):
        """Test creating list item."""
        now = datetime.now(UTC)
        item = ExchangeAccountListItem(
            id=uuid4(),
            exchange="binance",
            name="Trading Account",
            testnet=True,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        assert item.exchange == "binance"
        assert item.testnet is True

    def test_from_attributes_config(self):
        """Test model has from_attributes config."""
        assert ExchangeAccountListItem.model_config.get("from_attributes") is True


class TestConnectionTestResponse:
    """Tests for ConnectionTestResponse schema."""

    def test_successful_connection(self):
        """Test successful connection response."""
        response = ConnectionTestResponse(
            success=True,
            message=None,
            balance_count=5,
        )

        assert response.success is True
        assert response.message is None
        assert response.balance_count == 5

    def test_failed_connection(self):
        """Test failed connection response."""
        response = ConnectionTestResponse(
            success=False,
            message="Invalid API key",
            balance_count=None,
        )

        assert response.success is False
        assert response.message == "Invalid API key"
        assert response.balance_count is None

    def test_success_required(self):
        """Test success field is required."""
        with pytest.raises(ValidationError):
            ConnectionTestResponse()
